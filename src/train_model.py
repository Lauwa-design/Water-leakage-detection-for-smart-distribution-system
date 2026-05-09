# -*- coding: utf-8 -*-
"""Train the binary and multiclass leak models on the 7 hydraulic indicators."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, roc_auc_score

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

try:
    from src.feature_extractor import SEVEN_FEATURES, ENHANCED_FEATURES  # type: ignore
    from src.utils.config import BINARY_MODEL_FILE, MODELS_DIR, MULTI_MODEL_FILE, PROCESSED_DIR, RANDOM_STATE  # type: ignore
except ModuleNotFoundError:
    from feature_extractor import SEVEN_FEATURES, ENHANCED_FEATURES  # noqa: E402
    from utils.config import BINARY_MODEL_FILE, MODELS_DIR, MULTI_MODEL_FILE, PROCESSED_DIR, RANDOM_STATE  # noqa: E402

# Use enhanced features by default, fall back to original 7 if not available
USE_ENHANCED = True


def _split_scenarios(data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    scenarios = data["scenario"].unique().copy()
    np.random.seed(RANDOM_STATE)
    np.random.shuffle(scenarios)

    train_end = int(0.7 * len(scenarios))
    val_end = int(0.85 * len(scenarios))

    train = data[data["scenario"].isin(scenarios[:train_end])].copy()
    val = data[data["scenario"].isin(scenarios[train_end:val_end])].copy()
    test = data[data["scenario"].isin(scenarios[val_end:])].copy()
    return train, val, test


def _binary_model() -> RandomForestClassifier:
    return RandomForestClassifier(
        n_estimators=300,
        class_weight="balanced",
        random_state=RANDOM_STATE,
        max_depth=12,
        min_samples_split=4,
        min_samples_leaf=2,
        max_features="sqrt",
    )


def _multiclass_model(class_weights: dict[str, float] | None) -> RandomForestClassifier:
    return RandomForestClassifier(
        n_estimators=300,
        random_state=RANDOM_STATE,
        max_depth=12,
        min_samples_split=4,
        min_samples_leaf=2,
        max_features="sqrt",
        class_weight=class_weights,
    )


def run() -> None:
    data_path = PROCESSED_DIR / "engineered_features.csv"
    data = pd.read_csv(data_path)
    
    # Determine which feature set to use
    if USE_ENHANCED and all(f in data.columns for f in ENHANCED_FEATURES):
        FEATURES = ENHANCED_FEATURES
        print(f"Using ENHANCED feature set ({len(FEATURES)} features)")
    else:
        FEATURES = SEVEN_FEATURES
        print(f"Using ORIGINAL feature set ({len(FEATURES)} features)")
    
    missing = [feature for feature in FEATURES if feature not in data.columns]
    if missing:
        raise ValueError(f"Training dataset is missing documented features: {missing}")

    train, val, test = _split_scenarios(data)
    print("Dataset split:")
    print(f"  Train: {train['scenario'].nunique()} scenarios")
    print(f"  Val:   {val['scenario'].nunique()} scenarios")
    print(f"  Test:  {test['scenario'].nunique()} scenarios")

    X_train = train[FEATURES]
    X_val = val[FEATURES]
    X_test = test[FEATURES]

    y_train_binary = train["scenario_has_leak"]
    y_val_binary = val["scenario_has_leak"]
    y_test_binary = test["scenario_has_leak"]

    clf_b = _binary_model()
    clf_b.fit(X_train, y_train_binary)

    val_prob_b = clf_b.predict_proba(X_val)[:, 1]
    test_prob_b = clf_b.predict_proba(X_test)[:, 1]
    print(f"Validation Binary AUC: {roc_auc_score(y_val_binary, val_prob_b):.4f}")
    print(f"Test Binary AUC: {roc_auc_score(y_test_binary, test_prob_b):.4f}")
    print(f"Test Binary Accuracy: {accuracy_score(y_test_binary, clf_b.predict(X_test)):.4f}")

    leak_train = train[train["scenario_has_leak"] == 1].copy()
    leak_val = val[val["scenario_has_leak"] == 1].copy()
    leak_test = test[test["scenario_has_leak"] == 1].copy()

    clf_m = None
    multiclass_report = None
    if not leak_train.empty and leak_train["leak_type"].nunique() > 1:
        type_counts = leak_train["leak_type"].value_counts()
        total = len(leak_train)
        class_weights = {label: total / (len(type_counts) * count) for label, count in type_counts.items()}

        clf_m = _multiclass_model(class_weights)
        clf_m.fit(leak_train[FEATURES], leak_train["leak_type"])

        if not leak_val.empty:
            print("\nValidation Multiclass Report:")
            print(classification_report(leak_val["leak_type"], clf_m.predict(leak_val[FEATURES]), zero_division=0))

        if not leak_test.empty:
            print("\nTest Multiclass Report:")
            multiclass_report = classification_report(
                leak_test["leak_type"],
                clf_m.predict(leak_test[FEATURES]),
                output_dict=True,
                zero_division=0,
            )
            print(classification_report(leak_test["leak_type"], clf_m.predict(leak_test[FEATURES]), zero_division=0))

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump(clf_b, BINARY_MODEL_FILE)
    if clf_m is not None:
        joblib.dump(clf_m, MULTI_MODEL_FILE)

    with open(MODELS_DIR / "feature_list.json", "w", encoding="utf-8") as handle:
        json.dump({"features": FEATURES}, handle, indent=2)

    metrics = {
        "binary_validation_auc": float(roc_auc_score(y_val_binary, val_prob_b)),
        "binary_test_auc": float(roc_auc_score(y_test_binary, test_prob_b)),
        "binary_test_accuracy": float(accuracy_score(y_test_binary, clf_b.predict(X_test))),
        "features": FEATURES,
        "multiclass_classes": sorted(leak_train["leak_type"].unique().tolist()) if not leak_train.empty else [],
        "multiclass_test_report": multiclass_report,
    }
    metrics_dir = REPO_ROOT / "outputs" / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    with open(metrics_dir / "evaluation_metrics.json", "w", encoding="utf-8") as handle:
        json.dump(metrics, handle, indent=2)

    print(f"\n[OK] Saved binary model to {BINARY_MODEL_FILE}")
    if clf_m is not None:
        print(f"[OK] Saved multiclass model to {MULTI_MODEL_FILE}")
    print(f"[OK] Saved feature list to {MODELS_DIR / 'feature_list.json'}")


if __name__ == "__main__":
    run()
