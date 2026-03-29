"""
Dataset Builder
Merges raw per-scenario CSV files into a single flat dataset.

Pipeline position:  generate_scenarios.py  →  [THIS FILE]  →  feature_extractor.py

Input:  data/raw/scenarios/scenario_XXXX/
          demands.csv, pressures.csv, flows.csv, labels.csv,
          leak_info.json, leak_type.json
Output: data/processed/merged_dataset.csv
          One row per scenario × timestep (48 rows per 24-hour scenario)
          Columns: scenario, time_index, scenario_has_leak, leak_type, leak_score,
                   leak_active_at_timestep, mean/max/min/std/range for demand, 
                   pressure, flow, flow_demand_ratio
"""

import json
import argparse
from pathlib import Path

import pandas as pd
import numpy as np


# Normalize leak severity against this maximum (m³/s)
MAX_POSSIBLE_LEAK = 0.01


def get_leak_info(scenario_dir: Path):
    """
    Extract leak information from scenario folder.
    
    Returns:
        tuple: (leak_type, has_leak, leak_score)
    """
    # Get leak type
    leak_type_file = scenario_dir / "leak_type.json"
    if leak_type_file.exists():
        with open(leak_type_file) as f:
            leak_type = json.load(f).get("leak_type", "no_leak")
    else:
        leak_type = "no_leak"
    
    # Get leak severity score
    leak_score = 0.0
    leak_info_file = scenario_dir / "leak_info.json"
    if leak_info_file.exists():
        with open(leak_info_file) as f:
            leak_info = json.load(f)
        if leak_info.get("has_leak"):
            leak_severity = leak_info.get("leak_details", {}).get(
                "leak_demand_m3s", 0.0
            )
            leak_score = min(leak_severity / MAX_POSSIBLE_LEAK, 1.0)
    
    has_leak = leak_type != "no_leak"
    
    return leak_type, has_leak, leak_score


def calculate_night_flow_metrics(flows_df: pd.DataFrame, night_hours: list = [0, 1, 2, 3, 4, 5]):
    """
    Calculate night flow metrics for the entire scenario.
    
    Parameters:
    -----------
    flows_df : DataFrame with shape (timesteps, nodes)
    night_hours : list of hour indices considered as night time
    
    Returns:
    --------
    dict: Night flow statistics
    """
    night_flows = flows_df.iloc[night_hours].values.flatten()
    day_flows = flows_df.drop(index=night_hours).values.flatten()
    
    return {
        "night_flow_min": night_flows.min(),
        "night_flow_mean": night_flows.mean(),
        "night_flow_std": night_flows.std(),
        "day_flow_mean": day_flows.mean(),
        "night_to_day_ratio": night_flows.mean() / (day_flows.mean() + 1e-6)
    }


def calculate_temporal_features(series: pd.Series):
    """
    Calculate temporal trend features for a time series.
    
    Parameters:
    -----------
    series : pandas Series of values over time
    
    Returns:
    --------
    dict: Temporal features
    """
    # Linear trend (slope)
    x = np.arange(len(series))
    slope = np.polyfit(x, series.values, 1)[0]
    
    # Rolling statistics
    rolling_mean = series.rolling(window=6, min_periods=1).mean()
    rolling_std = series.rolling(window=6, min_periods=1).std()
    
    return {
        "trend_slope": slope,
        "rolling_mean_avg": rolling_mean.mean(),
        "rolling_std_avg": rolling_std.mean(),
        "coefficient_variation": series.std() / (series.mean() + 1e-6)
    }


def build_dataset(scenarios_dir: str, output_csv: str) -> pd.DataFrame:
    """
    Merge all scenario folders into one flat CSV with timestep-level rows.
    Each row represents one timestep in one scenario.

    Parameters
    ----------
    scenarios_dir : path to raw scenarios root (contains scenario_XXXX folders)
    output_csv    : destination path for merged_dataset.csv
    """
    scenarios_dir = Path(scenarios_dir)
    output_csv = Path(output_csv)

    scenario_dirs = sorted(scenarios_dir.glob("scenario_*"))

    if not scenario_dirs:
        raise FileNotFoundError(f"No scenario folders found in {scenarios_dir}")

    print(f"Found {len(scenario_dirs)} scenarios")
    print("Building dataset...")

    rows = []
    skipped_scenarios = []

    for idx, scenario_dir in enumerate(scenario_dirs, 1):
        try:
            scenario_id = scenario_dir.name
            
            # Progress indicator
            if idx % 100 == 0:
                print(f"  Processing scenario {idx}/{len(scenario_dirs)}")
            
            # ── Load per-timestep CSVs ──────────────────────────────────────
            demands = pd.read_csv(scenario_dir / "demands.csv")
            pressures = pd.read_csv(scenario_dir / "pressures.csv")
            flows = pd.read_csv(scenario_dir / "flows.csv")
            labels = pd.read_csv(scenario_dir / "labels.csv")
            
            # Verify data consistency
            n_timesteps = len(demands)
            if not (len(pressures) == len(flows) == len(labels) == n_timesteps):
                print(f"  ⚠ Warning: Inconsistent timesteps in {scenario_id}")
                continue
            
            # ── Get scenario-level leak information ─────────────────────────
            leak_type, has_leak, leak_score = get_leak_info(scenario_dir)
            
            # ── Calculate scenario-level features ───────────────────────────
            # Night flow metrics (assuming 24 timesteps per day)
            night_metrics = calculate_night_flow_metrics(flows)
            
            # Temporal features for mean flow across nodes
            mean_flow_over_time = flows.mean(axis=1)
            temporal_features = calculate_temporal_features(mean_flow_over_time)
            
            # ── One row per timestep ───────────────────────────────────────
            for timestep in range(n_timesteps):
                # Check if leak is active at this timestep
                leak_active = int(labels.iloc[timestep].max()) if len(labels.columns) > 0 else 0
                
                row = {
                    # Identifiers
                    "scenario": scenario_id,
                    "time_index": timestep,
                    
                    # Targets (for classification and analysis)
                    "scenario_has_leak": int(has_leak),
                    "leak_type": leak_type,
                    "leak_score": leak_score,
                    "leak_active_at_timestep": leak_active,
                    
                    # Demand statistics across all nodes at this timestep
                    "mean_demand": demands.iloc[timestep].mean(),
                    "max_demand": demands.iloc[timestep].max(),
                    "min_demand": demands.iloc[timestep].min(),
                    "std_demand": demands.iloc[timestep].std(),
                    "demand_range": demands.iloc[timestep].max() - demands.iloc[timestep].min(),
                    "total_demand": demands.iloc[timestep].sum(),
                    
                    # Pressure statistics
                    "mean_pressure": pressures.iloc[timestep].mean(),
                    "max_pressure": pressures.iloc[timestep].max(),
                    "min_pressure": pressures.iloc[timestep].min(),
                    "std_pressure": pressures.iloc[timestep].std(),
                    "pressure_range": pressures.iloc[timestep].max() - pressures.iloc[timestep].min(),
                    
                    # Flow statistics
                    "mean_flow": flows.iloc[timestep].mean(),
                    "max_flow": flows.iloc[timestep].max(),
                    "min_flow": flows.iloc[timestep].min(),
                    "std_flow": flows.iloc[timestep].std(),
                    "flow_range": flows.iloc[timestep].max() - flows.iloc[timestep].min(),
                    "total_flow": flows.iloc[timestep].sum(),
                    
                    # Hydraulic imbalance indicators
                    "flow_demand_ratio": (
                        flows.iloc[timestep].mean() / (demands.iloc[timestep].mean() + 1e-6)
                    ),
                    
                    # Scenario-level features (same for all timesteps in this scenario)
                    "night_flow_min": night_metrics["night_flow_min"],
                    "night_flow_mean": night_metrics["night_flow_mean"],
                    "night_flow_std": night_metrics["night_flow_std"],
                    "day_flow_mean": night_metrics["day_flow_mean"],
                    "night_to_day_ratio": night_metrics["night_to_day_ratio"],
                    
                    # Temporal trend features
                    "flow_trend_slope": temporal_features["trend_slope"],
                    "flow_rolling_mean_avg": temporal_features["rolling_mean_avg"],
                    "flow_rolling_std_avg": temporal_features["rolling_std_avg"],
                    "flow_cv": temporal_features["coefficient_variation"],
                }
                
                rows.append(row)
                
        except Exception as e:
            print(f"  ⚠ Skipping {scenario_dir.name}: {e}")
            skipped_scenarios.append(scenario_dir.name)
            continue
    
    if not rows:
        raise ValueError("No data rows were generated. Check your scenario folders.")
    
    # Create DataFrame
    df = pd.DataFrame(rows)
    
    # Convert leak_type to categorical for better memory usage
    df['leak_type'] = df['leak_type'].astype('category')
    
    # Add some derived features
    df['pressure_drop'] = df['max_pressure'] - df['min_pressure']
    df['flow_anomaly_score'] = (df['mean_flow'] - df['night_flow_mean']) / (df['std_flow'] + 1e-6)
    
    # Sort for consistency
    df = df.sort_values(['scenario', 'time_index']).reset_index(drop=True)
    
    # Save to CSV
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False)
    
    # Print statistics
    print(f"\n{'='*70}")
    print(f"✓ DATASET BUILD COMPLETE!")
    print(f"{'='*70}")
    print(f"\nOutput file: {output_csv}")
    print(f"Total rows: {len(df):,}")
    print(f"Total columns: {len(df.columns)}")
    print(f"\n{'='*70}")
    print(f"SCENARIO STATISTICS")
    print(f"{'='*70}")
    print(f"Total scenarios: {len(scenario_dirs)}")
    print(f"Successful: {len(scenario_dirs) - len(skipped_scenarios)}")
    print(f"Skipped: {len(skipped_scenarios)}")
    
    if skipped_scenarios:
        print(f"\nSkipped scenarios: {', '.join(skipped_scenarios[:5])}")
        if len(skipped_scenarios) > 5:
            print(f"  ... and {len(skipped_scenarios)-5} more")
    
    print(f"\n{'='*70}")
    print(f"LABEL DISTRIBUTION")
    print(f"{'='*70}")
    print(f"\nScenario-level leak presence:")
    scenario_stats = df.groupby('scenario')['scenario_has_leak'].first().value_counts()
    print(f"  No leak:  {scenario_stats.get(0, 0):,} scenarios")
    print(f"  Leak:     {scenario_stats.get(1, 0):,} scenarios")
    
    print(f"\nLeak type distribution (scenario-level):")
    leak_type_stats = df.groupby('scenario')['leak_type'].first().value_counts()
    for leak_type, count in leak_type_stats.items():
        print(f"  {leak_type}: {count:,} scenarios")
    
    print(f"\nTimestep-level leak activity:")
    timestep_active = df[df['leak_active_at_timestep'] == 1].shape[0]
    timestep_inactive = df[df['leak_active_at_timestep'] == 0].shape[0]
    print(f"  Leak active:  {timestep_active:,} timesteps ({timestep_active/len(df)*100:.1f}%)")
    print(f"  No leak:      {timestep_inactive:,} timesteps ({timestep_inactive/len(df)*100:.1f}%)")
    
    print(f"\n{'='*70}")
    print(f"FEATURE SUMMARY")
    print(f"{'='*70}")
    print(f"Feature columns: {', '.join(df.select_dtypes(include=[np.number]).columns.tolist()[:10])}...")
    print(f"Categorical columns: {', '.join(df.select_dtypes(include=['category', 'object']).columns.tolist())}")
    
    print(f"\n{'='*70}")
    print(f"ML READINESS CHECK")
    print(f"{'='*70}")
    
    # Check if dataset is suitable for ML
    n_leak_scenarios = scenario_stats.get(1, 0)
    n_no_leak_scenarios = scenario_stats.get(0, 0)
    
    if n_leak_scenarios >= 100 and n_no_leak_scenarios >= 100:
        print("✅ Dataset is ready for ML training!")
        print(f"   - {n_leak_scenarios} leak scenarios for training")
        print(f"   - {n_no_leak_scenarios} no-leak scenarios for training")
        print(f"   - {len(df):,} timestep-level records for time-series analysis")
    else:
        print("⚠️ Dataset needs more scenarios for robust ML training")
        print(f"   - Leak scenarios: {n_leak_scenarios} (recommend at least 100)")
        print(f"   - No-leak scenarios: {n_no_leak_scenarios} (recommend at least 100)")
    
    return df


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Build merged dataset from raw scenarios",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python data_builder.py
  python data_builder.py --input data/raw/scenarios --output data/processed/merged_dataset.csv
        """
    )
    parser.add_argument(
        "--input", 
        default="data/raw/scenarios",
        help="Root directory containing scenario_XXXX folders (default: data/raw/scenarios)"
    )
    parser.add_argument(
        "--output", 
        default="data/processed/merged_dataset.csv",
        help="Output path for merged CSV (default: data/processed/merged_dataset.csv)"
    )
    args = parser.parse_args()
    
    # Run the builder
    df = build_dataset(args.input, args.output)
    
    print(f"\n{'='*70}")
    print(f"✓ Dataset successfully saved to: {args.output}")
    print(f"{'='*70}")