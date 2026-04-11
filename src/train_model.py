import pandas as pd
import numpy as np
import joblib
import sys
from pathlib import Path
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import roc_auc_score, classification_report

sys.path.append(str(Path(__file__).resolve().parent.parent))
from utils.config import (
    PROCESSED_DIR, BINARY_MODEL_FILE, 
    MULTI_MODEL_FILE, RANDOM_STATE
)

def to_scenario_signature(df):
    """
    Collapses hourly data into one row per scenario.
    This is where we pull in the 'Delta' features to hit 90%+.
    """
    agg = df.groupby('scenario').agg({
        'z_f': ['max', 'mean', 'std'],
        'z_p': ['min', 'mean'],
        'mean_flow_delta': ['last'],      # Key for 'Instant' leaks
        'mean_pressure_delta': ['last'],   # Key for 'Extreme' bursts
        'flow_slope': ['max'],
        'scenario_has_leak': 'first',
        'leak_type': 'first'
    })
    
    # MNF (Minimum Night Flow) Ratio
    # Uses the smoothed 'roll' column for stability in the UI
    night = df[df['is_night']==1].groupby('scenario')['mean_flow_roll'].mean()
    day = df.groupby('scenario')['mean_flow_roll'].mean()
    agg['mnf_ratio'] = night / (day + 1e-6)
    
    # Flatten multi-index columns (e.g., z_f_max)
    agg.columns = ['_'.join(c).strip() if isinstance(c, tuple) else c for c in agg.columns]
    return agg.reset_index().fillna(0)

def run():
    # 1. Load the features you just extracted
    df = pd.read_csv(PROCESSED_DIR / "engineered_features.csv")
    data = to_scenario_signature(df)
    
    # 2. Train/Test Split (80/20)
    scenarios = data['scenario'].unique()
    np.random.seed(RANDOM_STATE)
    np.random.shuffle(scenarios)
    split = int(0.8 * len(scenarios))
    
    train = data[data['scenario'].isin(scenarios[:split])]
    test = data[data['scenario'].isin(scenarios[split:])]
    
    # Define features (exclude labels and IDs)
    features = [c for c in train.columns if c not in ['scenario', 'scenario_has_leak_first', 'leak_type_first']]
    
    # 3. Binary Model (Is there a leak?)
    clf_b = RandomForestClassifier(
        n_estimators=300, 
        class_weight='balanced', 
        random_state=RANDOM_STATE,
        max_depth=15 # Prevents extreme overfitting
    )
    clf_b.fit(train[features], train['scenario_has_leak_first'])
    
    # 4. Multiclass Model (What kind of leak?)
    # Only train on scenarios that actually HAVE leaks
    train_m = train[train['scenario_has_leak_first'] == 1]
    clf_m = RandomForestClassifier(
        n_estimators=300, 
        random_state=RANDOM_STATE,
        max_depth=15
    )
    clf_m.fit(train_m[features], train_m['leak_type_first'])

    # --- RESULTS REPORTING ---
    print("\n" + "="*45)
    print("TOP HYDRAULIC INDICATORS (EXTREMES)")
    print("="*45)
    importances = pd.Series(clf_m.feature_importances_, index=features).sort_values(ascending=False)
    print(importances.head(5))

    # Binary Performance
    prob_b = clf_b.predict_proba(test[features])[:, 1]
    print(f"\nBINARY AUC: {roc_auc_score(test['scenario_has_leak_first'], prob_b):.4f}")
    
    # Multiclass Performance
    print("\nEXTREMES REPORT (Slow, Instant, Extreme):")
    test_m = test[test['scenario_has_leak_first'] == 1]
    y_pred_m = clf_m.predict(test_m[features])
    print(classification_report(test_m['leak_type_first'], y_pred_m))
    
    # 5. Save Models for the Real-time UI
    joblib.dump(clf_b, BINARY_MODEL_FILE)
    joblib.dump(clf_m, MULTI_MODEL_FILE)
    print(f"\n✓ Models successfully optimized and saved to {BINARY_MODEL_FILE}")

if __name__ == "__main__":
    run()