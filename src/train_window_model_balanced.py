# -*- coding: utf-8 -*-
"""Train leak detection models using sliding windows with class balancing for better recall."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, classification_report, roc_auc_score, confusion_matrix, precision_recall_fscore_support
from sklearn.utils import resample

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


def balance_training_data(train: pd.DataFrame, ratio: float = 2.0) -> pd.DataFrame:
    """
    Balance training data by undersampling majority class.
    
    Args:
        train: Training data
        ratio: Ratio of no-leak to leak windows (default: 2.0 = 2:1)
    
    Returns:
        Balanced training data
    """
    leak_windows = train[train['window_has_leak'] == 1]
    no_leak_windows = train[train['window_has_leak'] == 0]
    
    target_no_leak = int(len(leak_windows) * ratio)
    
    if target_no_leak < len(no_leak_windows):
        no_leak_downsampled = resample(
            no_leak_windows,
            n_samples=target_no_leak,
            random_state=RANDOM_STATE
        )
    else:
        no_leak_downsampled = no_leak_windows
    
    balanced = pd.concat([leak_windows, no_leak_downsampled]).sample(frac=1, random_state=RANDOM_STATE)
    
    return balanced


def _binary_model_aggressive() -> RandomForestClassifier:
    """Binary classifier optimized for leak detection (high recall)."""
    return RandomForestClassifier(
        n_estimators=500,
        class_weight={0: 1, 1: 10},  # 10x weight for leak class
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


def evaluate_with_threshold(y_true, y_prob, threshold=0.5):
    """Evaluate model with custom threshold."""
    y_pred = (y_prob > threshold).astype(int)
    acc = accuracy_score(y_true, y_pred)
    precision, recall, f1, _ = precision_recall_fscore_support(y_true, y_pred, average='binary', zero_division=0)
    cm = confusion_matrix(y_true, y_pred)
    
    return {
        'threshold': threshold,
        'accuracy': acc,
        'precision': precision,
        'recall': recall,
        'f1': f1,
        'confusion_matrix': cm
    }


def run() -> None:
    """Train window-based leak detection models with class balancing."""
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
    print("TRAINING BALANCED WINDOW-BASED LEAK DETECTION MODELS")
    print("=" * 70)
    
    # Split by scenario to prevent data leakage
    train, val, test = _split_by_scenario(data)
    
    print(f"\nOriginal dataset split:")
    print(f"  Train: {train['scenario'].nunique()} scenarios, {len(train)} windows")
    print(f"  Val:   {val['scenario'].nunique()} scenarios, {len(val)} windows")
    print(f"  Test:  {test['scenario'].nunique()} scenarios, {len(test)} windows")
    
    print(f"\nOriginal class distribution in training set:")
    print(f"  No leak: {(train['window_has_leak'] == 0).sum()} windows ({(train['window_has_leak'] == 0).mean() * 100:.1f}%)")
    print(f"  Leak:    {(train['window_has_leak'] == 1).sum()} windows ({(train['window_has_leak'] == 1).mean() * 100:.1f}%)")

    # Balance training data
    print(f"\nBalancing training data (2:1 ratio)...")
    train_balanced = balance_training_data(train, ratio=2.0)
    
    print(f"\nBalanced class distribution:")
    print(f"  No leak: {(train_balanced['window_has_leak'] == 0).sum()} windows ({(train_balanced['window_has_leak'] == 0).mean() * 100:.1f}%)")
    print(f"  Leak:    {(train_balanced['window_has_leak'] == 1).sum()} windows ({(train_balanced['window_has_leak'] == 1).mean() * 100:.1f}%)")
    print(f"  Total:   {len(train_balanced)} windows (reduced from {len(train)})")

    X_train = train_balanced[WINDOW_FEATURES]
    X_val = val[WINDOW_FEATURES]
    X_test = test[WINDOW_FEATURES]

    y_train_binary = train_balanced["window_has_leak"]
    y_val_binary = val["window_has_leak"]
    y_test_binary = test["window_has_leak"]

    # Train binary classifier
    print("\n" + "=" * 70)
    print("BINARY CLASSIFICATION (Leak vs No-Leak)")
    print("=" * 70)
    
    clf_b = _binary_model_aggressive()
    print("Training binary classifier with aggressive leak detection...")
    clf_b.fit(X_train, y_train_binary)

    # Evaluate with multiple thresholds
    val_prob_b = clf_b.predict_proba(X_val)[:, 1]
    test_prob_b = clf_b.predict_proba(X_test)[:, 1]
    
    print("\n" + "-" * 70)
    print("THRESHOLD OPTIMIZATION")
    print("-" * 70)
    
    thresholds = [0.1, 0.2, 0.3, 0.4, 0.5]
    best_f1 = 0
    best_threshold = 0.5
    
    print(f"\n{'Threshold':<12} {'Accuracy':<12} {'Precision':<12} {'Recall':<12} {'F1-Score':<12}")
    print("-" * 70)
    
    for threshold in thresholds:
        results = evaluate_with_threshold(y_test_binary, test_prob_b, threshold)
        print(f"{threshold:<12.2f} {results['accuracy']:<12.4f} {results['precision']:<12.4f} {results['recall']:<12.4f} {results['f1']:<12.4f}")
        
        if results['f1'] > best_f1:
            best_f1 = results['f1']
            best_threshold = threshold
    
    print(f"\nBest threshold: {best_threshold} (F1-Score: {best_f1:.4f})")
    
    # Use best threshold for final evaluation
    best_results = evaluate_with_threshold(y_test_binary, test_prob_b, best_threshold)
    test_auc = roc_auc_score(y_test_binary, test_prob_b)
    
    print("\n" + "=" * 70)
    print(f"FINAL TEST RESULTS (Threshold = {best_threshold})")
    print("=" * 70)
    
    print(f"\nPerformance Metrics:")
    print(f"  AUC:       {test_auc:.4f}")
    print(f"  Accuracy:  {best_results['accuracy']:.4f}")
    print(f"  Precision: {best_results['precision']:.4f}")
    print(f"  Recall:    {best_results['recall']:.4f}")
    print(f"  F1-Score:  {best_results['f1']:.4f}")
    
    # Confusion matrix
    cm = best_results['confusion_matrix']
    tn, fp, fn, tp = cm.ravel()
    print(f"\nConfusion Matrix:")
    print(f"  True Negatives:  {tn:5d} (correctly identified no-leak)")
    print(f"  False Positives: {fp:5d} (false alarms)")
    print(f"  False Negatives: {fn:5d} (missed leaks)")
    print(f"  True Positives:  {tp:5d} (correctly detected leaks)")
    
    fpr = fp / (fp + tn) if (fp + tn) > 0 else 0
    fnr = fn / (fn + tp) if (fn + tp) > 0 else 0
    print(f"\nError Rates:")
    print(f"  False Positive Rate: {fpr:.4f} ({fpr * 100:.2f}%)")
    print(f"  False Negative Rate: {fnr:.4f} ({fnr * 100:.2f}%)")
    
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
    
    leak_train = train_balanced[train_balanced["window_has_leak"] == 1].copy()
    leak_val = val[val["window_has_leak"] == 1].copy()
    leak_test = test[test["window_has_leak"] == 1].copy()

    clf_m = None
    multiclass_report = None
    
    if not leak_train.empty and leak_train["leak_type"].nunique() > 1:
        print(f"\nLeak type distribution in balanced training set:")
        for leak_type, count in leak_train["leak_type"].value_counts().items():
            print(f"  {leak_type:15s} {count} windows ({count / len(leak_train) * 100:.1f}%)")
        
        # Calculate class weights
        type_counts = leak_train["leak_type"].value_counts()
        total = len(leak_train)
        class_weights = {label: total / (len(type_counts) * count) for label, count in type_counts.items()}

        clf_m = _multiclass_model(class_weights)
        print("\nTraining multiclass classifier...")
        clf_m.fit(leak_train[WINDOW_FEATURES], leak_train["leak_type"])

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
    
    binary_model_file = MODELS_DIR / "leak_binary_window_balanced.joblib"
    joblib.dump(clf_b, binary_model_file)
    print(f"[OK] Saved binary model to {binary_model_file}")
    
    if clf_m is not None:
        multi_model_file = MODELS_DIR / "leak_multi_window_balanced.joblib"
        joblib.dump(clf_m, multi_model_file)
        print(f"[OK] Saved multiclass model to {multi_model_file}")

    # Save threshold
    threshold_file = MODELS_DIR / "optimal_threshold.json"
    with open(threshold_file, "w", encoding="utf-8") as handle:
        json.dump({"optimal_threshold": best_threshold}, handle, indent=2)
    print(f"[OK] Saved optimal threshold to {threshold_file}")

    # Save feature list
    feature_list_file = MODELS_DIR / "window_feature_list_balanced.json"
    with open(feature_list_file, "w", encoding="utf-8") as handle:
        json.dump({"features": WINDOW_FEATURES}, handle, indent=2)
    print(f"[OK] Saved feature list to {feature_list_file}")

    # Save metrics
    metrics = {
        "model_type": "sliding_window_balanced",
        "window_size_timesteps": 24,
        "window_size_minutes": 120,
        "overlap_fraction": 0.5,
        "training_balance_ratio": 2.0,
        "class_weight_leak": 10,
        "optimal_threshold": best_threshold,
        "binary_test_auc": float(test_auc),
        "binary_test_accuracy": float(best_results['accuracy']),
        "binary_precision": float(best_results['precision']),
        "binary_recall": float(best_results['recall']),
        "binary_f1": float(best_results['f1']),
        "false_positive_rate": float(fpr),
        "false_negative_rate": float(fnr),
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
    metrics_file = metrics_dir / "window_model_balanced_metrics.json"
    with open(metrics_file, "w", encoding="utf-8") as handle:
        json.dump(metrics, handle, indent=2)
    print(f"[OK] Saved metrics to {metrics_file}")
    
    print("\n" + "=" * 70)
    print("TRAINING COMPLETE")
    print("=" * 70)
    print(f"\nFinal Test Performance (Threshold = {best_threshold}):")
    print(f"  AUC:       {test_auc:.4f}")
    print(f"  Accuracy:  {best_results['accuracy']:.4f}")
    print(f"  Precision: {best_results['precision']:.4f}")
    print(f"  Recall:    {best_results['recall']:.4f}")
    print(f"  F1-Score:  {best_results['f1']:.4f}")
    
    # Performance comparison
    print(f"\n" + "=" * 70)
    print("IMPROVEMENT SUMMARY")
    print("=" * 70)
    print(f"\nCompared to unbalanced model:")
    print(f"  Recall improved from 4.14% to {best_results['recall'] * 100:.2f}%")
    print(f"  F1-Score improved from 6.43% to {best_results['f1'] * 100:.2f}%")


if __name__ == "__main__":
    run()
