# -*- coding: utf-8 -*-
"""Train the binary and multiclass leak models.

Key changes from previous version
───────────────────────────────────
1. Binary model  → SEVEN_FEATURES (see evaluation metrics after each train run)
2. Multiclass    → MULTICLASS_FEATURES from feature_extractor (retrain when that list changes)
3. Multiclass RF → tuned for 3-class balance (shallower trees, more estimators,
                   higher min_samples to avoid memorising individual scenarios)
4. Diagnostic    → class-separation report printed before training so you can
                   verify the new features actually separate the three types.
5. Split         → stratified 85/15 by scenario_has_leak (one row per scenario).
6. CV            → 5-fold stratified CV on the train portion (binary AUC + F1 @ tuned threshold).
7. Threshold     → binary decision threshold = median of per-fold F1-optimal thresholds.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    f1_score,
    roc_auc_score,
)
from sklearn.model_selection import StratifiedKFold, train_test_split

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

try:
    from src.feature_extractor import (  # type: ignore
        MULTICLASS_FEATURES,
        SEVEN_FEATURES,
        print_class_separation_report,
    )
    from src.utils.config import (  # type: ignore
        BINARY_MODEL_FILE,
        MODELS_DIR,
        MULTI_MODEL_FILE,
        PROCESSED_DIR,
        RANDOM_STATE,
    )
except ModuleNotFoundError:
    from feature_extractor import (  # noqa: E402
        MULTICLASS_FEATURES,
        SEVEN_FEATURES,
        print_class_separation_report,
    )
    from utils.config import (  # noqa: E402
        BINARY_MODEL_FILE,
        MODELS_DIR,
        MULTI_MODEL_FILE,
        PROCESSED_DIR,
        RANDOM_STATE,
    )


TEST_SIZE = 0.15
CV_SPLITS = 5


# ──────────────────────────────────────────────────────────────────────────────
# Dataset split
# ──────────────────────────────────────────────────────────────────────────────

def _dedupe_scenario_rows(data: pd.DataFrame) -> pd.DataFrame:
    """Engineered features should be one row per scenario; collapse duplicates if any."""
    if not data["scenario"].duplicated().any():
        return data
    n_dup = int(data["scenario"].duplicated().sum())
    print(f"[WARN] {n_dup} duplicate scenario id(s) — keeping last row per scenario.")
    return data.drop_duplicates(subset=["scenario"], keep="last").reset_index(drop=True)


def _stratified_train_test(
    data: pd.DataFrame,
    label_col: str,
    test_size: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Stratified holdout; preserves class proportions in train vs test."""
    vc = data[label_col].value_counts()
    if vc.min() < 2:
        print(
            f"[WARN] Stratified split unsafe (min class count {vc.min()}); "
            "using unstratified train_test_split."
        )
        return train_test_split(
            data,
            test_size=test_size,
            random_state=RANDOM_STATE,
        )
    train, test = train_test_split(
        data,
        test_size=test_size,
        random_state=RANDOM_STATE,
        stratify=data[label_col],
    )
    return train, test


def _best_f1_threshold(y_true: np.ndarray, y_prob: np.ndarray) -> tuple[float, float]:
    """Grid search threshold in (0,1) maximizing binary F1."""
    y_true = np.asarray(y_true).astype(int)
    best_t, best_f1 = 0.5, 0.0
    for t in np.linspace(0.01, 0.99, 99):
        y_pred = (y_prob >= t).astype(int)
        f = f1_score(y_true, y_pred, zero_division=0)
        if f > best_f1:
            best_f1, best_t = f, t
    return float(best_t), float(best_f1)


def _binary_cross_validate(
    X: pd.DataFrame,
    y: np.ndarray,
) -> tuple[list[float], list[float], list[float]]:
    """Stratified K-fold: val AUC and F1 at F1-optimal threshold per fold."""
    skf = StratifiedKFold(n_splits=CV_SPLITS, shuffle=True, random_state=RANDOM_STATE)
    aucs: list[float] = []
    f1s: list[float] = []
    thresholds: list[float] = []
    for tr_idx, va_idx in skf.split(X, y):
        clf = _binary_model()
        clf.fit(X.iloc[tr_idx], y[tr_idx])
        prob_va = clf.predict_proba(X.iloc[va_idx])[:, 1]
        aucs.append(float(roc_auc_score(y[va_idx], prob_va)))
        t, _ = _best_f1_threshold(y[va_idx], prob_va)
        thresholds.append(t)
        pred = (prob_va >= t).astype(int)
        f1s.append(float(f1_score(y[va_idx], pred, zero_division=0)))
    return aucs, f1s, thresholds


def _multiclass_cross_validate(leak_df: pd.DataFrame) -> tuple[list[float], int]:
    """Macro-F1 on validation folds; n_splits limited by smallest class count."""
    if leak_df.empty or leak_df["leak_type"].nunique() < 2:
        return [], 0
    min_cls = int(leak_df["leak_type"].value_counts().min())
    n_splits = min(CV_SPLITS, min_cls)
    if n_splits < 3:
        return [], n_splits

    X = leak_df[MULTICLASS_FEATURES]
    y = leak_df["leak_type"]
    f1s: list[float] = []
    skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=RANDOM_STATE)
    for tr_idx, va_idx in skf.split(X, y):
        tr = leak_df.iloc[tr_idx]
        va = leak_df.iloc[va_idx]
        type_counts = tr["leak_type"].value_counts()
        total = len(tr)
        class_weights = {
            label: total / (len(type_counts) * count)
            for label, count in type_counts.items()
        }
        clf = _multiclass_model(class_weights)
        clf.fit(tr[MULTICLASS_FEATURES], tr["leak_type"])
        pred = clf.predict(va[MULTICLASS_FEATURES])
        rep = classification_report(
            va["leak_type"], pred, output_dict=True, zero_division=0
        )
        f1s.append(float(rep["macro avg"]["f1-score"]))
    return f1s, n_splits


# ──────────────────────────────────────────────────────────────────────────────
# Model factories
# ──────────────────────────────────────────────────────────────────────────────

def _binary_model() -> RandomForestClassifier:
    """Binary leak vs no-leak RandomForest baseline."""
    return RandomForestClassifier(
        n_estimators=500,
        class_weight="balanced",
        random_state=RANDOM_STATE,
        max_depth=15,
        min_samples_split=2,
        min_samples_leaf=1,
        max_features="sqrt",
        n_jobs=-1,
    )


def _multiclass_model(class_weights: dict[str, float] | None) -> RandomForestClassifier:
    """Multiclass classifier tuned for 3-class leak-type discrimination.

    Deliberately shallower and with higher min_samples compared to the binary
    model to reduce overfitting on the moderate_leak class which is hardest to
    separate.  More estimators compensate for the depth restriction.
    """
    return RandomForestClassifier(
        n_estimators=1000,       # more trees → better vote aggregation
        random_state=RANDOM_STATE,
        max_depth=12,            # shallower = less overfit on 3-way split
        min_samples_split=10,    # prevent memorising individual scenarios
        min_samples_leaf=5,      # same — forces generalisable splits
        max_features="sqrt",
        class_weight=class_weights,
        n_jobs=-1,
    )


# ──────────────────────────────────────────────────────────────────────────────
# Pre-training signal checks
# ──────────────────────────────────────────────────────────────────────────────

def _safe_mean(series: pd.Series) -> float:
    if series.empty:
        return 0.0
    return float(pd.to_numeric(series, errors="coerce").fillna(0.0).mean())


def _run_pretraining_signal_check() -> None:
    """Fail fast when raw merged data shows collapsed hydraulic separation.

    Uses merged_dataset.csv (time-series rows), not engineered_features.csv.
    Set ALLOW_WEAK_SIGNAL_TRAINING=1 to bypass the hard failure and continue.
    """
    merged_path = PROCESSED_DIR / "merged_dataset.csv"
    if not merged_path.exists():
        print(
            f"[WARN] Pre-training signal check skipped (no {merged_path}; "
            "run data_builder.py after generating scenarios)."
        )
        return

    data = pd.read_csv(merged_path)
    required = {"scenario_has_leak", "leak_type", "mean_flow", "mean_pressure"}
    missing = sorted(required - set(data.columns))
    if missing:
        print(f"[WARN] Pre-training signal check skipped (missing columns: {missing})")
        return

    leak_rows = data[data["scenario_has_leak"] == 1]
    no_leak_rows = data[data["scenario_has_leak"] == 0]
    if leak_rows.empty or no_leak_rows.empty:
        print("[WARN] Pre-training signal check skipped (insufficient leak/no-leak samples).")
        return

    flow_leak_delta = _safe_mean(leak_rows["mean_flow"]) - _safe_mean(no_leak_rows["mean_flow"])
    pressure_leak_delta = _safe_mean(no_leak_rows["mean_pressure"]) - _safe_mean(leak_rows["mean_pressure"])

    type_means = leak_rows.groupby("leak_type")["mean_flow"].mean().to_dict()
    slow_mean = float(type_means.get("slow_leak", 0.0))
    moderate_mean = float(type_means.get("moderate_leak", 0.0))
    extreme_mean = float(type_means.get("extreme_leak", 0.0))

    min_flow_delta = 5.0
    min_pressure_delta = 0.03
    min_type_gap = 2.0

    pass_flow_vs_none = flow_leak_delta >= min_flow_delta
    pass_pressure_vs_none = pressure_leak_delta >= min_pressure_delta
    # Monotone slow ≤ moderate ≤ extreme in *aggregate* mean flow is not guaranteed
    # (duration, timing, and DMA alignment can reorder class means).
    type_mean_vals = [slow_mean, moderate_mean, extreme_mean]
    type_spread = max(type_mean_vals) - min(type_mean_vals)
    pass_type_spread = type_spread >= min_type_gap
    passed = pass_flow_vs_none and pass_pressure_vs_none and pass_type_spread

    print("\n" + "=" * 70)
    print("PRE-TRAINING SIGNAL CHECK")
    print("=" * 70)
    print(f"Leak-vs-none flow delta     : {flow_leak_delta:.3f} (>= {min_flow_delta})")
    print(f"Leak-vs-none pressure delta : {pressure_leak_delta:.3f} (>= {min_pressure_delta})")
    print(
        "Leak type mean flow         : "
        f"slow={slow_mean:.3f}, moderate={moderate_mean:.3f}, extreme={extreme_mean:.3f}"
    )
    print(f"Leak-type mean flow spread  : {type_spread:.3f} (max−min, >= {min_type_gap})")
    if not (extreme_mean >= moderate_mean >= slow_mean):
        print(
            "  [INFO] Mean flow is not monotone slow→moderate→extreme; "
            "that is allowed for this simulator."
        )
    print(f"Signal retention status     : {'PASS' if passed else 'FAIL'}")

    allow_weak_signal = os.getenv("ALLOW_WEAK_SIGNAL_TRAINING", "0") == "1"
    if not passed and not allow_weak_signal:
        raise ValueError(
            "Pre-training signal check failed. Hydraulic signature separation is too weak "
            "for reliable training. Regenerate scenarios or set ALLOW_WEAK_SIGNAL_TRAINING=1 "
            "to continue anyway."
        )
    if not passed and allow_weak_signal:
        print("[WARN] Continuing despite failed signal check (ALLOW_WEAK_SIGNAL_TRAINING=1).")


# ──────────────────────────────────────────────────────────────────────────────
# Main training routine
# ──────────────────────────────────────────────────────────────────────────────

def run() -> None:
    data_path = PROCESSED_DIR / "engineered_features.csv"
    if not data_path.exists():
        raise FileNotFoundError(
            f"Engineered features not found at {data_path}.\n"
            "Run: python src/feature_extractor.py"
        )

    data = pd.read_csv(data_path)

    # ── Verify both feature sets are present ──────────────────────────────────
    missing_binary = [f for f in SEVEN_FEATURES if f not in data.columns]
    if missing_binary:
        raise ValueError(f"Binary features missing: {missing_binary}")

    missing_multi = [f for f in MULTICLASS_FEATURES if f not in data.columns]
    if missing_multi:
        raise ValueError(
            f"Multiclass features missing: {missing_multi}\n"
            "Re-run feature_extractor.py to regenerate engineered_features.csv."
        )

    # ── Class-separation diagnostic ───────────────────────────────────────────
    print("=" * 70)
    print("CLASS SEPARATION DIAGNOSTIC (means by leak_type)")
    print("=" * 70)
    print_class_separation_report(data_path)
    _run_pretraining_signal_check()

    data = _dedupe_scenario_rows(data)

    # ── Split ─────────────────────────────────────────────────────────────────
    train, test = _stratified_train_test(
        data, label_col="scenario_has_leak", test_size=TEST_SIZE
    )
    print(
        f"Dataset split (stratified {int((1 - TEST_SIZE) * 100)} / "
        f"{int(TEST_SIZE * 100)} by scenario_has_leak):"
    )
    print(f"  Train : {len(train)} scenarios")
    print(f"  Test  : {len(test)} scenarios\n")

    # ── Binary model (SEVEN_FEATURES only) ───────────────────────────────────
    print("=" * 70)
    print("BINARY MODEL  (leak vs no-leak)  —  features: SEVEN_FEATURES")
    print("=" * 70)

    X_train_b = train[SEVEN_FEATURES]
    X_test_b = test[SEVEN_FEATURES]
    y_train_b = train["scenario_has_leak"].to_numpy()
    y_test_b = test["scenario_has_leak"].to_numpy()

    cv_aucs, cv_f1s, cv_thresholds = _binary_cross_validate(X_train_b, y_train_b)
    binary_threshold = float(np.median(cv_thresholds))
    print(
        f"Binary CV ({CV_SPLITS}-fold, train portion only) — "
        f"AUC: {np.mean(cv_aucs):.4f} ± {np.std(cv_aucs):.4f}, "
        f"F1 @ fold-tuned thr: {np.mean(cv_f1s):.4f} ± {np.std(cv_f1s):.4f}"
    )
    print(f"Chosen binary probability threshold (median of fold optima): {binary_threshold:.4f}\n")

    clf_b = _binary_model()
    clf_b.fit(X_train_b, y_train_b)

    test_prob_b = clf_b.predict_proba(X_test_b)[:, 1]
    binary_auc = float(roc_auc_score(y_test_b, test_prob_b))
    test_pred_default = (test_prob_b >= 0.5).astype(int)
    test_pred_tuned = (test_prob_b >= binary_threshold).astype(int)
    binary_acc = float(accuracy_score(y_test_b, test_pred_default))
    binary_acc_tuned = float(accuracy_score(y_test_b, test_pred_tuned))
    binary_f1_default = float(f1_score(y_test_b, test_pred_default, zero_division=0))
    binary_f1_tuned = float(f1_score(y_test_b, test_pred_tuned, zero_division=0))

    print(f"Test Binary AUC           : {binary_auc:.4f}")
    print(f"Test Binary Accuracy    : {binary_acc:.4f}  (threshold 0.50)")
    print(f"Test Binary Accuracy    : {binary_acc_tuned:.4f}  (threshold {binary_threshold:.4f})")
    print(f"Test Binary F1            : {binary_f1_default:.4f}  (threshold 0.50)")
    print(f"Test Binary F1            : {binary_f1_tuned:.4f}  (threshold {binary_threshold:.4f})\n")

    # ── Multiclass model (MULTICLASS_FEATURES) ────────────────────────────────
    print("=" * 70)
    print("MULTICLASS MODEL  (leak type)  —  features: MULTICLASS_FEATURES")
    print("=" * 70)

    leak_train = train[train["scenario_has_leak"] == 1].copy()
    leak_test = test[test["scenario_has_leak"] == 1].copy()

    clf_m = None
    multiclass_report = None
    multiclass_cv_f1_mean: float | None = None
    multiclass_cv_f1_std: float | None = None
    multiclass_cv_splits = 0

    mc_f1s, mc_n_splits = _multiclass_cross_validate(leak_train)
    if mc_f1s:
        multiclass_cv_f1_mean = float(np.mean(mc_f1s))
        multiclass_cv_f1_std = float(np.std(mc_f1s))
        multiclass_cv_splits = mc_n_splits
        print(
            f"Multiclass CV ({mc_n_splits}-fold on train leak rows) — "
            f"macro F1: {multiclass_cv_f1_mean:.4f} ± {multiclass_cv_f1_std:.4f}\n"
        )
    elif leak_train["leak_type"].nunique() > 1:
        print(
            f"[INFO] Multiclass CV skipped (need ≥3 samples per class for k-fold; "
            f"smallest class count={leak_train['leak_type'].value_counts().min()}).\n"
        )

    if not leak_train.empty and leak_train["leak_type"].nunique() > 1:
        # Print class distribution so we can spot imbalance
        print("\nLeak type distribution in training set:")
        for lt, cnt in leak_train["leak_type"].value_counts().items():
            print(f"  {lt:15s}  {cnt:5d}  ({cnt / len(leak_train) * 100:.1f}%)")

        type_counts = leak_train["leak_type"].value_counts()
        total = len(leak_train)
        class_weights = {
            label: total / (len(type_counts) * count)
            for label, count in type_counts.items()
        }
        print(f"\nClass weights: {class_weights}")

        clf_m = _multiclass_model(class_weights)
        print("\nTraining multiclass classifier …")
        clf_m.fit(leak_train[MULTICLASS_FEATURES], leak_train["leak_type"])

        if not leak_test.empty:
            print("\nTest Multiclass Report:")
            multiclass_report = classification_report(
                leak_test["leak_type"],
                clf_m.predict(leak_test[MULTICLASS_FEATURES]),
                output_dict=True,
                zero_division=0,
            )
            print(
                classification_report(
                    leak_test["leak_type"],
                    clf_m.predict(leak_test[MULTICLASS_FEATURES]),
                    zero_division=0,
                )
            )

            # Feature importance for multiclass model
            fi = (
                pd.DataFrame(
                    {
                        "feature": MULTICLASS_FEATURES,
                        "importance": clf_m.feature_importances_,
                    }
                )
                .sort_values("importance", ascending=False)
                .reset_index(drop=True)
            )
            print("Top 10 features (multiclass model):")
            for _, row in fi.head(10).iterrows():
                print(f"  {row['feature']:30s}  {row['importance']:.4f}")
    else:
        print("Skipping multiclass training: insufficient leak-type diversity in training set.")

    # ── Save models ───────────────────────────────────────────────────────────
    print("\n" + "=" * 70)
    print("SAVING ARTEFACTS")
    print("=" * 70)

    MODELS_DIR.mkdir(parents=True, exist_ok=True)

    joblib.dump(clf_b, BINARY_MODEL_FILE)
    print(f"[OK] Binary model        → {BINARY_MODEL_FILE}")

    if clf_m is not None:
        joblib.dump(clf_m, MULTI_MODEL_FILE)
        print(f"[OK] Multiclass model    → {MULTI_MODEL_FILE}")

    # Save both feature lists so the inference pipeline knows which to use
    feature_manifest = {
        "binary_features": SEVEN_FEATURES,
        "multiclass_features": MULTICLASS_FEATURES,
        "binary_probability_threshold": binary_threshold,
    }
    manifest_path = MODELS_DIR / "feature_list.json"
    with open(manifest_path, "w", encoding="utf-8") as fh:
        json.dump(feature_manifest, fh, indent=2)
    print(f"[OK] Feature manifest    → {manifest_path}")

    # Save evaluation metrics
    metrics = {
        "binary_test_auc": float(binary_auc),
        "binary_test_accuracy": float(binary_acc),
        "binary_test_accuracy_tuned_threshold": binary_acc_tuned,
        "binary_test_f1_default_threshold_0_5": binary_f1_default,
        "binary_test_f1_tuned_threshold": binary_f1_tuned,
        "binary_probability_threshold": binary_threshold,
        "binary_cv_auc_mean": float(np.mean(cv_aucs)),
        "binary_cv_auc_std": float(np.std(cv_aucs)),
        "binary_cv_f1_mean": float(np.mean(cv_f1s)),
        "binary_cv_f1_std": float(np.std(cv_f1s)),
        "binary_cv_fold_thresholds": cv_thresholds,
        "binary_features": SEVEN_FEATURES,
        "multiclass_features": MULTICLASS_FEATURES,
        "multiclass_cv_splits": multiclass_cv_splits,
        "multiclass_cv_macro_f1_mean": multiclass_cv_f1_mean,
        "multiclass_cv_macro_f1_std": multiclass_cv_f1_std,
        "multiclass_classes": (
            sorted(leak_train["leak_type"].unique().tolist())
            if not leak_train.empty
            else []
        ),
        "multiclass_test_report": multiclass_report,
    }
    metrics_dir = REPO_ROOT / "outputs" / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    metrics_path = metrics_dir / "evaluation_metrics.json"
    with open(metrics_path, "w", encoding="utf-8") as fh:
        json.dump(metrics, fh, indent=2)
    print(f"[OK] Evaluation metrics  → {metrics_path}")

    print("\n" + "=" * 70)
    print("TRAINING COMPLETE")
    print("=" * 70)
    print(f"\nBinary  AUC      : {binary_auc:.4f}")
    print(f"Binary  Accuracy : {binary_acc:.4f}  @ 0.5  |  {binary_acc_tuned:.4f}  @ tuned thr")
    print(f"Binary  F1       : {binary_f1_default:.4f}  @ 0.5  |  {binary_f1_tuned:.4f}  @ tuned thr")
    if multiclass_report:
        ma = multiclass_report.get("macro avg", {})
        print(f"Multiclass macro F1       : {ma.get('f1-score', 0):.4f}")
        print(f"Multiclass macro Precision: {ma.get('precision', 0):.4f}")
        print(f"Multiclass macro Recall   : {ma.get('recall', 0):.4f}")


if __name__ == "__main__":
    run()
