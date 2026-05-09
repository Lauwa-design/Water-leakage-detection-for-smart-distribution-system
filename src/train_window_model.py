# -*- coding: utf-8 -*-
"""Train leak detection models using sliding window features for better temporal resolution."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, roc_auc_score, confusion_matrix, precision_recall_fscore_support

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

try:
    from src.feature_extractor import WINDOW_FEATURES  # type: ignore
    from src.utils.config import MODELS_DIR, PROCESSED_DIR, RANDOM_STATE  # type: ignore
except ModuleNotFoundError:
    from feature_extractor import WINDOW_FEATURES  # noqa: E402
    from utils.config import MODELS_DIR, PROCESSED_DIR, RANDOM_STATE  # noqa: E402


def _split_by_scenario(data: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Split windows by scenario to prevent data leakage."""
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
    """Binary classifier: leak vs no-leak."""
    return RandomForestClassifier(
        n_estimators=500,
        class_weight="balanced",
        random_state=RANDOM_STATE,
        max_depth=15,
        min_samples_split=4,
        min_samples_leaf=2,
        max_features="sqrt",
        n_jobs=-1,
    )


def _multiclass_model(class_weights: dict[str, float] | None) -> RandomForestClassifier:
    """Multiclass classifier: leak type classification."""
    return RandomForestClassifier(
        n_estimators=500,
        random_state=RANDOM_STATE,
        max_depth=15,
        min_samples_split=4,
        min_samples_leaf=2,
        max_features="sqrt",
        class_weight=class_weights,
        n_jobs=-1,
    )


def run() -> None:
    """Train window-based leak detection models."""
    data_path = PROCESSED_DIR / "window_features.csv"
    
    if not data_path.exists():
        print(f"ERROR: Window features not found at {data_path}")
        print("Please run: python src/feature_extractor.py")
        return
    
    data = pd.read_csv(data_path)
    
    # Verify features exist
    missing = [feature for feature in WINDOW_FEATURES if feature not in data.columns]
    if missing:
        raise ValueError(f"Window dataset is missing features: {missing}")

    print("=" * 70)
    print("TRAINING WINDOW-BASED LEAK DETECTION MODELS")
    print("=" * 70)
    
    # Split by scenario to prevent data leakage
    train, val, test = _split_by_scenario(data)
    
    print(f"\nDataset split (by scenario):")
    print(f"  Train: {train['scenario'].nunique()} scenarios, {len(train)} windows")
    print(f"  Val:   {val['scenario'].nunique()} scenarios, {len(val)} windows")
    print(f"  Test:  {test['scenario'].nunique()} scenarios, {len(test)} windows")
    
    print(f"\nClass distribution in training set:")
    print(f"  No leak: {(train['window_has_leak'] == 0).sum()} windows ({(train['window_has_leak'] == 0).mean() * 100:.1f}%)")
    print(f"  Leak:    {(train['window_has_leak'] == 1).sum()} windows ({(train['window_has_leak'] == 1).mean() * 100:.1f}%)")

    X_train = train[WINDOW_FEATURES]
    X_val = val[WINDOW_FEATURES]
    X_test = test[WINDOW_FEATURES]

    y_train_binary = train["window_has_leak"]
    y_val_binary = val["window_has_leak"]
    y_test_binary = test["window_has_leak"]

    # Train binary classifier
    print("\n" + "=" * 70)
    print("BINARY CLASSIFICATION (Leak vs No-Leak)")
    print("=" * 70)
    
    clf_b = _binary_model()
    print("Training binary classifier...")
    clf_b.fit(X_train, y_train_binary)

    # Evaluate binary model
    val_prob_b = clf_b.predict_proba(X_val)[:, 1]
    test_prob_b = clf_b.predict_proba(X_test)[:, 1]
    val_pred_b = clf_b.predict(X_val)
    test_pred_b = clf_b.predict(X_test)
    
    val_auc = roc_auc_score(y_val_binary, val_prob_b)
    test_auc = roc_auc_score(y_test_binary, test_prob_b)
    val_acc = accuracy_score(y_val_binary, val_pred_b)
    test_acc = accuracy_score(y_test_binary, test_pred_b)
    
    print(f"\nValidation Results:")
    print(f"  AUC:      {val_auc:.4f}")
    print(f"  Accuracy: {val_acc:.4f}")
    
    print(f"\nTest Results:")
    print(f"  AUC:      {test_auc:.4f}")
    print(f"  Accuracy: {test_acc:.4f}")
    
    # Confusion matrix
    cm = confusion_matrix(y_test_binary, test_pred_b)
    tn, fp, fn, tp = cm.ravel()
    print(f"\nConfusion Matrix:")
    print(f"  True Negatives:  {tn}")
    print(f"  False Positives: {fp}")
    print(f"  False Negatives: {fn}")
    print(f"  True Positives:  {tp}")
    
    precision, recall, f1, _ = precision_recall_fscore_support(y_test_binary, test_pred_b, average='binary')
    print(f"\nDetailed Metrics:")
    print(f"  Precision: {precision:.4f}")
    print(f"  Recall:    {recall:.4f}")
    print(f"  F1-Score:  {f1:.4f}")
    
    # Feature importance
    feature_importance = pd.DataFrame({
        'feature': WINDOW_FEATURES,
        'importance': clf_b.feature_importances_
    }).sort_values('importance', ascending=False)
    
    print(f"\nTop 10 Most Important Features:")
    for idx, row in feature_importance.head(10).iterrows():
        print(f"  {row['feature']:30s} {row['importance']:.4f}")

    # Train multiclass classifier on leak windows only
    print("\n" + "=" * 70)
    print("MULTICLASS CLASSIFICATION (Leak Type)")
    print("=" * 70)
    
    leak_train = train[train["window_has_leak"] == 1].copy()
    leak_val = val[val["window_has_leak"] == 1].copy()
    leak_test = test[test["window_has_leak"] == 1].copy()

    clf_m = None
    multiclass_report = None
    
    if not leak_train.empty and leak_train["leak_type"].nunique() > 1:
        print(f"\nLeak type distribution in training set:")
        for leak_type, count in leak_train["leak_type"].value_counts().items():
            print(f"  {leak_type:15s} {count} windows ({count / len(leak_train) * 100:.1f}%)")
        
        # Calculate class weights
        type_counts = leak_train["leak_type"].value_counts()
        total = len(leak_train)
        class_weights = {label: total / (len(type_counts) * count) for label, count in type_counts.items()}

        clf_m = _multiclass_model(class_weights)
        print("\nTraining multiclass classifier...")
        clf_m.fit(leak_train[WINDOW_FEATURES], leak_train["leak_type"])

        if not leak_val.empty:
            print("\nValidation Multiclass Report:")
            print(classification_report(leak_val["leak_type"], clf_m.predict(leak_val[WINDOW_FEATURES]), zero_division=0))

        if not leak_test.empty:
            print("\nTest Multiclass Report:")
            multiclass_report = classification_report(
                leak_test["leak_type"],
                clf_m.predict(leak_test[WINDOW_FEATURES]),
                output_dict=True,
                zero_division=0,
            )
            print(classification_report(leak_test["leak_type"], clf_m.predict(leak_test[WINDOW_FEATURES]), zero_division=0))
    else:
        print("\nSkipping multiclass training: insufficient leak type diversity")

    # Save models
    print("\n" + "=" * 70)
    print("SAVING MODELS")
    print("=" * 70)
    
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    
    binary_model_file = MODELS_DIR / "leak_binary_window.joblib"
    joblib.dump(clf_b, binary_model_file)
    print(f"[OK] Saved binary model to {binary_model_file}")
    
    if clf_m is not None:
        multi_model_file = MODELS_DIR / "leak_multi_window.joblib"
        joblib.dump(clf_m, multi_model_file)
        print(f"[OK] Saved multiclass model to {multi_model_file}")

    # Save feature list
    feature_list_file = MODELS_DIR / "window_feature_list.json"
    with open(feature_list_file, "w", encoding="utf-8") as handle:
        json.dump({"features": WINDOW_FEATURES}, handle, indent=2)
    print(f"[OK] Saved feature list to {feature_list_file}")

    # Save metrics
    metrics = {
        "model_type": "sliding_window",
        "window_size_timesteps": 24,
        "window_size_minutes": 120,
        "overlap_fraction": 0.5,
        "binary_validation_auc": float(val_auc),
        "binary_test_auc": float(test_auc),
        "binary_validation_accuracy": float(val_acc),
        "binary_test_accuracy": float(test_acc),
        "binary_precision": float(precision),
        "binary_recall": float(recall),
        "binary_f1": float(f1),
        "confusion_matrix": {
            "true_negatives": int(tn),
            "false_positives": int(fp),
            "false_negatives": int(fn),
            "true_positives": int(tp),
        },
        "features": WINDOW_FEATURES,
        "feature_importance": feature_importance.to_dict('records'),
        "multiclass_classes": sorted(leak_train["leak_type"].unique().tolist()) if not leak_train.empty else [],
        "multiclass_test_report": multiclass_report,
    }
    
    metrics_dir = REPO_ROOT / "outputs" / "metrics"
    metrics_dir.mkdir(parents=True, exist_ok=True)
    metrics_file = metrics_dir / "window_model_metrics.json"
    with open(metrics_file, "w", encoding="utf-8") as handle:
        json.dump(metrics, handle, indent=2)
    print(f"[OK] Saved metrics to {metrics_file}")
    
    print("\n" + "=" * 70)
    print("TRAINING COMPLETE")
    print("=" * 70)
    print(f"\nFinal Test Performance:")
    print(f"  Binary AUC:      {test_auc:.4f}")
    print(f"  Binary Accuracy: {test_acc:.4f}")
    print(f"  Precision:       {precision:.4f}")
    print(f"  Recall:          {recall:.4f}")
    print(f"  F1-Score:        {f1:.4f}")


if __name__ == "__main__":
    run()
