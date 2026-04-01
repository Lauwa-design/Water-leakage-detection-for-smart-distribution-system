"""
feature_extractor.py — THIWASCO Leak Detection
===============================================
Engineers features from the merged dataset for ML training.

Pipeline position:  data_builder.py  →  [THIS FILE]  →  train_model.py

Feature groups (Option B — instant + slow leak detection):

    1. BASELINE DEVIATION FEATURES
       Deviations from no-leak baseline statistics.
       Baseline calculated from NO-LEAK scenarios ONLY (no data leakage).

    2. INSTANT LEAK FEATURES (1-2h window)
       Capture sudden changes — pipe bursts, pressure-driven failures.
       Maps to: continuous, pressure leak types → CRITICAL alert.
       Features: pressure/flow/demand diff from previous hour,
                 pressure drop rate, flow spike score.

    3. SLOW LEAK FEATURES (6h + 12h windows)
       Capture gradual drift — seepage, joint failures, demand leaks.
       Maps to: demand, intermittent leak types → WARNING alert.
       Features: rolling means, trend slopes, sustained excess flow,
                 night sustained excess, combined slow leak score.

    4. HYDRAULIC FEATURES
       Flow-demand imbalance — water going somewhere unexpected.

Key design principles:
    - Baseline from NO-LEAK scenarios ONLY → no data leakage
    - Windows computed PER SCENARIO → no cross-scenario leakage
    - All NaNs filled explicitly → no silent failures
    - Output validated against ENGINEERED_FEATURE_COLUMNS from config
    - Baseline saved to disk → app uses same baseline for real-time

Input:
    data/processed/merged_dataset.csv

Output:
    data/processed/engineered_features.csv
    outputs/models/baseline_stats.json  ← loaded by app for real-time

Usage:
    python src/feature_extractor.py
    python src/feature_extractor.py --input data/processed/merged_dataset.csv
"""

import json
import argparse
from pathlib import Path

import numpy as np
import pandas as pd
import warnings
warnings.filterwarnings('ignore')

import sys
sys.path.append(str(Path(__file__).resolve().parent))
from utils.config import (
    MERGED_DATASET, ENGINEERED_DATASET, BASELINE_FILE,
    ID_COLUMNS, TARGET_COLUMNS,
    RAW_FEATURE_COLUMNS, ENGINEERED_FEATURE_COLUMNS,
    WINDOW_SHORT, WINDOW_MEDIUM, WINDOW_LONG,
    INSTANT_LEAK_TYPES, SLOW_LEAK_TYPES,
    create_directories,
)


# STEP 1 — BASELINE FROM NO-LEAK SCENARIOS ONLY

def calculate_baseline(df: pd.DataFrame) -> dict:
    """
    Calculate baseline statistics from NO-LEAK scenarios only.

    CRITICAL: Using all scenarios to calculate baseline would
    contaminate features with leak signal → data leakage.
    Only no-leak scenarios represent normal network behaviour.

    Returns:
        dict of baseline stats used for deviation features
    """
    no_leak = df[df['scenario_has_leak'] == 0].copy()

    n_scenarios = no_leak['scenario'].nunique()
    print(f"  Baseline from {n_scenarios} no-leak scenarios "
          f"({len(no_leak):,} rows)")

    baseline = {
        'flow_mean':          float(no_leak['mean_flow'].mean()),
        'flow_std':           float(no_leak['mean_flow'].std()),
        'pressure_mean':      float(no_leak['mean_pressure'].mean()),
        'pressure_std':       float(no_leak['mean_pressure'].std()),
        'demand_mean':        float(no_leak['mean_demand'].mean()),
        'demand_std':         float(no_leak['mean_demand'].std()),
        'night_flow_mean':    float(no_leak['night_flow_mean'].mean()),
        'night_flow_std':     float(no_leak['night_flow_mean'].std()),
        'pressure_drop_mean': float(no_leak['pressure_range'].mean()),
        'pressure_drop_std':  float(no_leak['pressure_range'].std()),
    }

    print("\n  Baseline statistics (no-leak normal behaviour):")
    for key, val in baseline.items():
        print(f"    {key:25s}: {val:.6f}")

    return baseline


# STEP 2 — BASELINE DEVIATION FEATURES

def extract_baseline_features(df: pd.DataFrame,
                               baseline: dict) -> pd.DataFrame:
    """
    Deviations from no-leak baseline.
    These capture how far current readings are from normal behaviour.
    """
    features = {}

    # Night flow deviation
    night_dev = (
        df['night_flow_mean'] - baseline['night_flow_mean']
    ) / (baseline['night_flow_std'] + 1e-6)
    features['night_flow_deviation'] = night_dev
    features['night_flow_anomaly']   = np.maximum(0, night_dev)
    features['night_to_day_ratio']   = df['night_to_day_ratio']

    # Pressure deviation
    press_dev = (
        df['mean_pressure'] - baseline['pressure_mean']
    ) / (baseline['pressure_std'] + 1e-6)
    features['pressure_deviation']      = press_dev
    features['pressure_drop_alert']     = np.maximum(0, -press_dev)
    features['pressure_drop_deviation'] = (
        df['pressure_range'] - baseline['pressure_drop_mean']
    ) / (baseline['pressure_drop_std'] + 1e-6)
    features['pressure_cv'] = (
        df['std_pressure'] / (df['mean_pressure'] + 1e-6)
    )

    # Flow deviation
    flow_dev = (
        df['mean_flow'] - baseline['flow_mean']
    ) / (baseline['flow_std'] + 1e-6)
    features['flow_deviation']  = flow_dev
    features['high_flow_alert'] = np.maximum(0, flow_dev)
    features['flow_cv']         = df['flow_cv']
    features['flow_stability']  = (
        df['mean_flow'] / (df['std_flow'] + 1e-6)
    )

    # Demand deviation
    demand_dev = (
        df['mean_demand'] - baseline['demand_mean']
    ) / (baseline['demand_std'] + 1e-6)
    features['demand_deviation']  = demand_dev
    features['peak_demand_ratio'] = (
        df['max_demand'] / (df['mean_demand'] + 1e-6)
    )

    # Hydraulic imbalance
    features['flow_demand_ratio']  = df['flow_demand_ratio']
    features['hydraulic_imbalance'] = np.maximum(
        0, df['flow_demand_ratio'] - 1
    )
    features['mass_balance_error'] = (
        (df['mean_flow'] - df['mean_demand']) /
        (df['mean_demand'] + 1e-6)
    )

    # Cross-signal ratios
    features['flow_pressure_ratio'] = (
        df['mean_flow'] / (df['mean_pressure'] + 1e-6)
    )
    features['demand_pressure_ratio'] = (
        df['mean_demand'] / (df['mean_pressure'] + 1e-6)
    )

    # Derived
    features['pressure_drop'] = df['pressure_range']
    features['flow_anomaly_score'] = (
        (df['mean_flow'] - df['night_flow_mean']) /
        (df['std_flow'] + 1e-6)
    )

    return pd.DataFrame(features, index=df.index)



# STEP 3 — INSTANT LEAK FEATURES (1-2h window)

def extract_instant_features(df: pd.DataFrame,
                              baseline: dict) -> pd.DataFrame:
    """
    Features for detecting INSTANT leaks (continuous, pressure types).

    Instant leaks produce:
        - Sharp pressure drop within 1-2 hours
        - Sudden flow spike
        - Abrupt demand change

    Computed PER SCENARIO using groupby to prevent cross-scenario leakage.
    First timestep in each scenario gets 0 (no previous hour to diff).
    """
    features = pd.DataFrame(index=df.index)

    # Per-scenario diff — prevents leakage between scenarios
    grp = df.groupby('scenario')

    # 1h differences (change from previous timestep)
    features['pressure_diff_1h'] = (
        grp['mean_pressure'].diff().fillna(0)
    )
    features['flow_diff_1h'] = (
        grp['mean_flow'].diff().fillna(0)
    )
    features['demand_diff_1h'] = (
        grp['mean_demand'].diff().fillna(0)
    )

    # Pressure drop rate — slope over last 2 timesteps
    # Negative slope = pressure falling (leak indicator)
    press_diff = grp['mean_pressure'].diff().fillna(0)
    features['pressure_drop_rate'] = np.minimum(0, press_diff)

    # Flow spike score — how much current flow exceeds
    # the short-window (3h) rolling mean within scenario
    rolling_short = (
        grp['mean_flow']
        .transform(lambda x: x.rolling(
            window=WINDOW_SHORT, min_periods=1
        ).mean())
    )
    features['flow_spike_score'] = np.maximum(
        0, df['mean_flow'] - rolling_short
    )

    return features


# STEP 4 — SLOW LEAK FEATURES (6h + 12h windows)

def extract_slow_features(df: pd.DataFrame,
                           baseline: dict) -> pd.DataFrame:
    """
    Features for detecting SLOW leaks (demand, intermittent types).

    Slow leaks produce:
        - Gradual pressure drift over 6-12 hours
        - Sustained excess flow above baseline
        - Night flow consistently above normal

    Computed PER SCENARIO to prevent cross-scenario leakage.
    Early timesteps use min_periods=1 to avoid NaNs.
    """
    features = pd.DataFrame(index=df.index)
    grp      = df.groupby('scenario')

    # ── 6-hour window features ─────────────────────────────────────
    roll6_press = grp['mean_pressure'].transform(
        lambda x: x.rolling(window=WINDOW_MEDIUM, min_periods=1).mean()
    )
    roll6_flow = grp['mean_flow'].transform(
        lambda x: x.rolling(window=WINDOW_MEDIUM, min_periods=1).mean()
    )
    roll6_press_std = grp['mean_pressure'].transform(
        lambda x: x.rolling(
            window=WINDOW_MEDIUM, min_periods=1
        ).std().fillna(0)
    )

    features['rolling_6h_pressure_mean'] = roll6_press
    features['rolling_6h_flow_mean']     = roll6_flow
    features['rolling_6h_pressure_std']  = roll6_press_std

    # Pressure trend over 6h — negative = gradual drop (slow leak)
    def trend_slope(x, window):
        """Rolling linear trend slope."""
        result = pd.Series(index=x.index, dtype=float)
        for i in range(len(x)):
            start = max(0, i - window + 1)
            chunk = x.iloc[start:i+1].values
            if len(chunk) < 2:
                result.iloc[i] = 0.0
            else:
                t     = np.arange(len(chunk))
                result.iloc[i] = float(np.polyfit(t, chunk, 1)[0])
        return result

    features['pressure_trend_6h'] = grp['mean_pressure'].transform(
        lambda x: trend_slope(x, WINDOW_MEDIUM)
    )

    # Cumulative excess flow over 6h above baseline
    flow_excess = np.maximum(
        0, df['mean_flow'] - baseline['flow_mean']
    )
    features['flow_excess_6h'] = (
        pd.Series(flow_excess, index=df.index)
        .groupby(df['scenario'])
        .transform(lambda x: x.rolling(
            window=WINDOW_MEDIUM, min_periods=1
        ).sum())
    )

    # ── 12-hour window features ────────────────────────────────────
    roll12_press = grp['mean_pressure'].transform(
        lambda x: x.rolling(window=WINDOW_LONG, min_periods=1).mean()
    )
    roll12_flow = grp['mean_flow'].transform(
        lambda x: x.rolling(window=WINDOW_LONG, min_periods=1).mean()
    )

    features['rolling_12h_pressure_mean'] = roll12_press
    features['rolling_12h_flow_mean']     = roll12_flow

    features['pressure_trend_12h'] = grp['mean_pressure'].transform(
        lambda x: trend_slope(x, WINDOW_LONG)
    )

    # Night sustained excess — how many night hours have flow
    # above baseline within this scenario (same for all 24 rows)
    night_excess_count = df.groupby('scenario').apply(
        lambda g: (
            g[g['time_index'].isin(range(0, 6))]['mean_flow']
            > baseline['flow_mean']
        ).sum()
    )
    features['night_sustained_excess'] = (
        df['scenario'].map(night_excess_count)
    )

    # Combined slow leak score — weighted combination of slow indicators
    # Normalised to 0-1 range
    slow_score = (
        np.abs(features['pressure_trend_12h']) * 0.4 +
        (features['rolling_12h_flow_mean'] - baseline['flow_mean']) /
        (baseline['flow_std'] + 1e-6) * 0.4 +
        features['night_sustained_excess'] / 6.0 * 0.2
    )
    features['slow_leak_score'] = np.clip(slow_score, 0, None)

    return features


# STEP 5 — VALIDATE OUTPUT

def validate_output(df: pd.DataFrame) -> None:
    """
    Confirm all ENGINEERED_FEATURE_COLUMNS present and NaN-free.
    Raises ValueError on any issue.
    """
    missing = [c for c in ENGINEERED_FEATURE_COLUMNS
               if c not in df.columns]
    if missing:
        raise ValueError(
            f"Missing engineered feature columns: {missing}"
        )

    nan_cols = {
        col: int(df[col].isnull().sum())
        for col in ENGINEERED_FEATURE_COLUMNS
        if df[col].isnull().sum() > 0
    }
    if nan_cols:
        raise ValueError(
            f"NaN values found in engineered features: {nan_cols}"
        )

    inf_cols = {
        col: int(np.isinf(df[col]).sum())
        for col in ENGINEERED_FEATURE_COLUMNS
        if np.isinf(df[col]).sum() > 0
    }
    if inf_cols:
        raise ValueError(
            f"Infinite values found in engineered features: {inf_cols}"
        )

    print("✓ Feature validation passed — no missing, NaN or inf values")


# CORE — ENGINEER FEATURES

def engineer_features(input_file: Path,
                       output_file: Path) -> pd.DataFrame:
    """
    Full feature engineering pipeline.

    Steps:
        1. Load merged dataset
        2. Calculate baseline from no-leak scenarios only
        3. Extract baseline deviation features
        4. Extract instant leak features (1-2h window)
        5. Extract slow leak features (6h + 12h windows)
        6. Fill NaNs and infinities
        7. Validate output schema
        8. Save engineered features + baseline stats
    """
    print(f"\n{'='*60}")
    print(f"FEATURE ENGINEERING — THIWASCO Leak Detection")
    print(f"{'='*60}")
    print(f"Option B: Baseline + Instant (1-2h) + Slow (6h/12h) features")

    # ── Load ───────────────────────────────────────────────────────
    print(f"\n[1] Loading: {input_file}")
    df = pd.read_csv(input_file)
    print(f"    Shape            : {df.shape}")
    print(f"    Scenarios        : {df['scenario'].nunique():,}")

    leak_scenarios = df.groupby('scenario')['scenario_has_leak'].first()
    print(f"    Leak scenarios   : {leak_scenarios.sum():,}")
    print(f"    No-leak scenarios: {(leak_scenarios == 0).sum():,}")

    leak_type_dist = df.groupby('scenario')['leak_type'].first().value_counts()
    print(f"\n    Leak type distribution:")
    for lt, count in leak_type_dist.items():
        speed = ('INSTANT' if lt in INSTANT_LEAK_TYPES
                 else 'SLOW' if lt in SLOW_LEAK_TYPES
                 else 'NONE')
        print(f"      {lt:15s}: {count:4d}  [{speed}]")

    # ── Baseline ───────────────────────────────────────────────────
    print(f"\n[2] Calculating baseline from no-leak scenarios...")
    baseline = calculate_baseline(df)

    # ── Extract features ───────────────────────────────────────────
    print(f"\n[3] Extracting baseline deviation features...")
    baseline_feats = extract_baseline_features(df, baseline)

    print(f"[4] Extracting instant leak features (1-2h window)...")
    instant_feats  = extract_instant_features(df, baseline)

    print(f"[5] Extracting slow leak features (6h + 12h windows)...")
    slow_feats     = extract_slow_features(df, baseline)

    # ── Combine ────────────────────────────────────────────────────
    features_df = pd.concat(
        [baseline_feats, instant_feats, slow_feats], axis=1
    )
    features_df = features_df.loc[:, ~features_df.columns.duplicated()]

    # ── Clean NaNs and infinities ──────────────────────────────────
    print(f"\n[6] Cleaning NaNs and infinities...")
    nan_count = features_df.isnull().sum().sum()
    inf_count = np.isinf(features_df.select_dtypes(
        include=[np.number]
    ).values).sum()

    if nan_count > 0:
        print(f"    Filling {nan_count} NaN values with 0")
        features_df = features_df.fillna(0.0)
    if inf_count > 0:
        print(f"    Replacing {inf_count} infinite values with 0")
        features_df = features_df.replace([np.inf, -np.inf], 0.0)
    if nan_count == 0 and inf_count == 0:
        print(f"    No NaNs or infinities found ✓")

    # ── Assemble final dataset ─────────────────────────────────────
    targets_df = df[ID_COLUMNS + TARGET_COLUMNS].copy()
    result_df  = pd.concat(
        [targets_df.reset_index(drop=True),
         features_df.reset_index(drop=True)],
        axis=1
    )

    # Enforce exact column order from config
    final_cols = ID_COLUMNS + TARGET_COLUMNS + ENGINEERED_FEATURE_COLUMNS
    result_df  = result_df[final_cols]

    # ── Validate ───────────────────────────────────────────────────
    print(f"\n[7] Validating output schema...")
    validate_output(result_df)

    # ── Save engineered features ───────────────────────────────────
    output_file.parent.mkdir(parents=True, exist_ok=True)
    result_df.to_csv(output_file, index=False)
    print(f"\n[8] Saved engineered features → {output_file}")

    # ── Save baseline for app real-time use ────────────────────────
    BASELINE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(BASELINE_FILE, 'w') as f:
        json.dump(baseline, f, indent=2)
    print(f"    Saved baseline stats     → {BASELINE_FILE}")

    # ── Summary ────────────────────────────────────────────────────
    print(f"\n{'='*60}")
    print(f"✓ FEATURE ENGINEERING COMPLETE")
    print(f"{'='*60}")
    print(f"  Output rows      : {len(result_df):,}")
    print(f"  Output columns   : {len(result_df.columns)}")
    print(f"  Feature columns  : {len(ENGINEERED_FEATURE_COLUMNS)}")
    print(f"\n  Feature groups:")
    print(f"    Baseline deviation : 20 features")
    print(f"    Instant leak (1-2h):  5 features")
    print(f"    Slow leak (6h)     :  5 features")
    print(f"    Slow leak (12h)    :  5 features")
    print(f"    Total              : {len(ENGINEERED_FEATURE_COLUMNS)} features")

    # Top correlations with primary label
    print(f"\n  Top 10 features correlated with leak_active_at_timestep:")
    numeric_feats = result_df[ENGINEERED_FEATURE_COLUMNS]
    correlations  = (
        numeric_feats
        .corrwith(result_df['leak_active_at_timestep'])
        .abs()
        .sort_values(ascending=False)
    )
    for feat, corr in correlations.head(10).items():
        print(f"    {feat:35s}: {corr:.4f}")

    # Correlation split by instant vs slow
    print(f"\n  Instant leak feature correlations (top 3):")
    instant_cols = [
        'pressure_diff_1h', 'flow_diff_1h', 'demand_diff_1h',
        'pressure_drop_rate', 'flow_spike_score'
    ]
    inst_corr = (
        result_df[instant_cols]
        .corrwith(result_df['leak_active_at_timestep'])
        .abs()
        .sort_values(ascending=False)
    )
    for feat, corr in inst_corr.head(3).items():
        print(f"    {feat:35s}: {corr:.4f}")

    print(f"\n  Slow leak feature correlations (top 3):")
    slow_cols = [
        'rolling_6h_pressure_mean', 'rolling_12h_pressure_mean',
        'pressure_trend_6h', 'pressure_trend_12h',
        'flow_excess_6h', 'night_sustained_excess', 'slow_leak_score'
    ]
    slow_corr = (
        result_df[slow_cols]
        .corrwith(result_df['leak_active_at_timestep'])
        .abs()
        .sort_values(ascending=False)
    )
    for feat, corr in slow_corr.head(3).items():
        print(f"    {feat:35s}: {corr:.4f}")

    print(f"{'='*60}\n")

    return result_df



# ENTRY POINT

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Engineer features for instant and slow leak detection'
    )
    parser.add_argument(
        '--input',
        default=str(MERGED_DATASET),
        help='Input merged_dataset.csv'
    )
    parser.add_argument(
        '--output',
        default=str(ENGINEERED_DATASET),
        help='Output engineered_features.csv'
    )
    args = parser.parse_args()

    create_directories()
    engineer_features(Path(args.input), Path(args.output))
