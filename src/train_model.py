"""
Leak Detection Model Training - Random Forest
As specified in the project proposal
"""

import pandas as pd
import numpy as np
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (classification_report, confusion_matrix, 
                             roc_auc_score, roc_curve, accuracy_score,
                             precision_score, recall_score, f1_score)
import matplotlib.pyplot as plt
import seaborn as sns
import warnings
import os
import joblib

warnings.filterwarnings('ignore')

# Create output directories
os.makedirs('outputs/models', exist_ok=True)
os.makedirs('outputs/figures', exist_ok=True)

print("="*70)
print("LEAK DETECTION MODEL TRAINING")
print("Random Forest Classifier (as per proposal)")
print("="*70)

# ============================================================
# 1. LOAD DATA
# ============================================================
print("\n1. Loading engineered features...")

df = pd.read_csv('data/processed/engineered_features.csv')
print(f"   Dataset shape: {df.shape}")

# ============================================================
# 2. PREPARE FEATURES AND TARGETS
# ============================================================
print("\n2. Preparing features and targets...")

exclude_cols = ['scenario', 'leak_type', 'scenario_has_leak', 'leak_score', 'leak_active']
feature_cols = [col for col in df.columns if col not in exclude_cols]

X = df[feature_cols].values
y_binary = df['scenario_has_leak'].values
y_multiclass = df['leak_type'].values

print(f"   Features: {len(feature_cols)}")
print(f"   Leak samples: {sum(y_binary)} ({sum(y_binary)/len(y_binary)*100:.1f}%)")
print(f"   No-leak samples: {len(y_binary)-sum(y_binary)}")

# Encode multi-class labels
le = LabelEncoder()
y_multiclass_encoded = le.fit_transform(y_multiclass)

# ============================================================
# 3. DATA SPLIT
# ============================================================
print("\n3. Splitting data (70% train, 15% val, 15% test)...")

X_temp, X_test, y_binary_temp, y_binary_test, y_multi_temp, y_multi_test = train_test_split(
    X, y_binary, y_multiclass_encoded, test_size=0.15, random_state=42, stratify=y_binary
)

X_train, X_val, y_binary_train, y_binary_val, y_multi_train, y_multi_val = train_test_split(
    X_temp, y_binary_temp, y_multi_temp, test_size=0.176, random_state=42, stratify=y_binary_temp
)

print(f"   Training:   {len(X_train)} samples")
print(f"   Validation: {len(X_val)} samples")
print(f"   Test:       {len(X_test)} samples")

# ============================================================
# 4. FEATURE SCALING
# ============================================================
print("\n4. Scaling features...")
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_val_scaled = scaler.transform(X_val)
X_test_scaled = scaler.transform(X_test)

# ============================================================
# 5. TRAIN RANDOM FOREST (BINARY CLASSIFICATION)
# ============================================================
print("\n" + "="*70)
print("TRAINING RANDOM FOREST - Binary Classification")
print("="*70)

rf_binary = RandomForestClassifier(
    n_estimators=200,
    max_depth=15,
    min_samples_split=5,
    min_samples_leaf=2,
    class_weight='balanced',
    random_state=42,
    n_jobs=-1
)

print("Training...")
rf_binary.fit(X_train_scaled, y_binary_train)

# ============================================================
# 6. EVALUATE BINARY CLASSIFICATION
# ============================================================
print("\n" + "="*70)
print("BINARY CLASSIFICATION RESULTS")
print("="*70)

# Validation set
y_val_pred = rf_binary.predict(X_val_scaled)
y_val_proba = rf_binary.predict_proba(X_val_scaled)[:, 1]

# Test set
y_test_pred = rf_binary.predict(X_test_scaled)
y_test_proba = rf_binary.predict_proba(X_test_scaled)[:, 1]

# Metrics
accuracy = accuracy_score(y_binary_test, y_test_pred)
precision = precision_score(y_binary_test, y_test_pred)
recall = recall_score(y_binary_test, y_test_pred)
f1 = f1_score(y_binary_test, y_test_pred)
roc_auc = roc_auc_score(y_binary_test, y_test_proba)

print(f"\nTest Set Performance:")
print(f"   Accuracy:  {accuracy:.4f}")
print(f"   Precision: {precision:.4f}")
print(f"   Recall:    {recall:.4f}")
print(f"   F1-Score:  {f1:.4f}")
print(f"   ROC-AUC:   {roc_auc:.4f}")

print(f"\nClassification Report:")
print(classification_report(y_binary_test, y_test_pred, target_names=['No Leak', 'Leak']))

# ============================================================
# 7. FEATURE IMPORTANCE (Key for your report)
# ============================================================
print("\n" + "="*70)
print("FEATURE IMPORTANCE ANALYSIS")
print("="*70)

feature_importance = pd.DataFrame({
    'feature': feature_cols,
    'importance': rf_binary.feature_importances_
}).sort_values('importance', ascending=False)

print("\nTop 15 Most Important Features:")
print(feature_importance.head(15).to_string(index=False))

# Save feature importance
feature_importance.to_csv('outputs/feature_importance.csv', index=False)
print("\n✓ Feature importance saved")

# ============================================================
# 8. MULTI-CLASS CLASSIFICATION (Leak Types)
# ============================================================
print("\n" + "="*70)
print("TRAINING RANDOM FOREST - Multi-class Classification")
print("="*70)

# Filter only leak scenarios
leak_indices_train = y_binary_train == 1
leak_indices_test = y_binary_test == 1

X_multi_train = X_train_scaled[leak_indices_train]
y_multi_train_filtered = y_multi_train[leak_indices_train]

X_multi_test = X_test_scaled[leak_indices_test]
y_multi_test_filtered = y_multi_test[leak_indices_test]

print(f"\nMulti-class training samples: {len(X_multi_train)}")
print(f"Multi-class test samples: {len(X_multi_test)}")

# Train multi-class Random Forest
rf_multi = RandomForestClassifier(
    n_estimators=200,
    max_depth=10,
    min_samples_split=5,
    class_weight='balanced',
    random_state=42,
    n_jobs=-1
)

rf_multi.fit(X_multi_train, y_multi_train_filtered)

# Evaluate
y_multi_pred = rf_multi.predict(X_multi_test)
multi_accuracy = accuracy_score(y_multi_test_filtered, y_multi_pred)

print(f"\nTest Set Performance:")
print(f"   Accuracy: {multi_accuracy:.4f}")
print(f"\nClassification Report:")
print(classification_report(y_multi_test_filtered, y_multi_pred, 
                            target_names=le.classes_[le.classes_ != 'no_leak']))

# ============================================================
# 9. VISUALIZATIONS
# ============================================================
print("\n" + "="*70)
print("GENERATING VISUALIZATIONS")
print("="*70)

# Feature Importance Plot
plt.figure(figsize=(12, 10))
top_features = feature_importance.head(15)
plt.barh(range(len(top_features)), top_features['importance'][::-1])
plt.yticks(range(len(top_features)), top_features['feature'][::-1])
plt.xlabel('Importance')
plt.title('Top 15 Features for Leak Detection (Random Forest)', fontweight='bold')
plt.tight_layout()
plt.savefig('outputs/figures/feature_importance.png', dpi=150)
plt.close()
print("✓ Feature importance plot saved")

# Confusion Matrix
fig, axes = plt.subplots(1, 2, figsize=(12, 5))

from sklearn.metrics import ConfusionMatrixDisplay
ConfusionMatrixDisplay.from_estimator(rf_binary, X_val_scaled, y_binary_val,
                                       display_labels=['No Leak', 'Leak'],
                                       ax=axes[0], cmap='Blues')
axes[0].set_title('Validation Set')

ConfusionMatrixDisplay.from_estimator(rf_binary, X_test_scaled, y_binary_test,
                                       display_labels=['No Leak', 'Leak'],
                                       ax=axes[1], cmap='Greens')
axes[1].set_title('Test Set')

plt.tight_layout()
plt.savefig('outputs/figures/confusion_matrices.png', dpi=150)
plt.close()
print("✓ Confusion matrices saved")

# ROC Curve
plt.figure(figsize=(8, 6))
fpr, tpr, _ = roc_curve(y_binary_test, y_test_proba)
plt.plot(fpr, tpr, 'b-', linewidth=2, label=f'Random Forest (AUC = {roc_auc:.3f})')
plt.plot([0, 1], [0, 1], 'k--', alpha=0.5)
plt.xlabel('False Positive Rate')
plt.ylabel('True Positive Rate')
plt.title('ROC Curve - Leak Detection', fontweight='bold')
plt.legend()
plt.grid(True, alpha=0.3)
plt.tight_layout()
plt.savefig('outputs/figures/roc_curve.png', dpi=150)
plt.close()
print("✓ ROC curve saved")

# ============================================================
# 10. SAVE MODELS
# ============================================================
print("\n" + "="*70)
print("SAVING MODELS")
print("="*70)

joblib.dump(rf_binary, 'outputs/models/random_forest_binary.pkl')
joblib.dump(rf_multi, 'outputs/models/random_forest_multi.pkl')
joblib.dump(scaler, 'outputs/models/scaler.pkl')
joblib.dump(le, 'outputs/models/label_encoder.pkl')

print("✓ Models saved to 'outputs/models/'")

# ============================================================
# 11. FINAL SUMMARY
# ============================================================
print("\n" + "="*70)
print("FINAL SUMMARY")
print("="*70)

print(f"""
Random Forest Leak Detection Model - Results

DATASET:
- Total scenarios: {len(df)}
- Features: {len(feature_cols)}
- Leak scenarios: {sum(y_binary)} ({sum(y_binary)/len(y_binary)*100:.1f}%)
- No-leak scenarios: {len(y_binary)-sum(y_binary)}

PERFORMANCE (Test Set):
- Accuracy:  {accuracy:.4f}
- Precision: {precision:.4f}
- Recall:    {recall:.4f}
- F1-Score:  {f1:.4f}
- ROC-AUC:   {roc_auc:.4f}

TOP 5 LEAK INDICATORS:
{feature_importance.head(5).to_string(index=False)}

OUTPUTS:
- Models: outputs/models/
- Figures: outputs/figures/
- Feature Importance: outputs/feature_importance.csv

Random Forest model successfully trained!
""")

print("="*70)