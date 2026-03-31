"""
data_builder.py — THIWASCO Leak Detection
==========================================
Merges raw per-scenario CSV files into a single flat ML-ready dataset.

Pipeline position:  generate_scenarios.py  →  [THIS FILE]  →  feature_extractor.py

Input:
    data/raw/scenarios/scenario_XXXX/
        demands.csv     shape (24, n_nodes)
        pressures.csv   shape (24, n_nodes)
        flows.csv       shape (24, n_links)
        labels.csv      shape (24, 1)  — column: 'leak'
        leak_info.json
        leak_type.json

Output:
    data/processed/merged_dataset.csv

    Guaranteed schema (defined in config.py):
        ID_COLUMNS     : scenario, time_index
        TARGET_COLUMNS : scenario_has_leak, leak_type, leak_score,
                         leak_active_at_timestep
        RAW_FEATURE_COLUMNS : demand/pressure/flow stats,
                              night flow metrics, temporal features

    Total rows = 24 × number_of_valid_scenarios

Usage:
    python src/data_builder.py
    python src/data_builder.py --input data/raw/scenarios --output data/processed/merged_dataset.csv
"""

import json
import argparse
from pathlib import Path

import numpy as np
import pandas as pd

import sys
sys.path.append(str(Path(__file__).resolve().parent))
from utils.config import (
    RAW_SCENARIOS_DIR, MERGED_DATASET,
    TIMESTEPS_PER_DAY, NIGHT_HOURS, DAY_HOURS,
    ID_COLUMNS, TARGET_COLUMNS, RAW_FEATURE_COLUMNS,
    LEAK_MAG_MAX, create_directories,
)

MAX_POSSIBLE_LEAK = LEAK_MAG_MAX  # m³/s — for normalising leak_score


# ================================================================
# STEP 1 — VALIDATE SCENARIO FILES
# ================================================================

def validate_scenario_files(scenario_dir: Path) -> bool:
    """
    Check all required files exist and row counts match TIMESTEPS_PER_DAY.
    Returns True if usable, False if scenario should be skipped.
    """
    required = [
        'demands.csv', 'pressures.csv', 'flows.csv',
        'labels.csv', 'leak_info.json', 'leak_type.json'
    ]
    for fname in required:
        if not (scenario_dir / fname).exists():
            print(f"  ⚠ {scenario_dir.name}: missing {fname} — skipping")
            return False

    try:
        counts = {
            'demands':   len(pd.read_csv(scenario_dir / 'demands.csv')),
            'pressures': len(pd.read_csv(scenario_dir / 'pressures.csv')),
            'flows':     len(pd.read_csv(scenario_dir / 'flows.csv')),
            'labels':    len(pd.read_csv(scenario_dir / 'labels.csv')),
        }
    except Exception as e:
        print(f"  ⚠ {scenario_dir.name}: read error ({e}) — skipping")
        return False

    if not all(v == TIMESTEPS_PER_DAY for v in counts.values()):
        print(f"  ⚠ {scenario_dir.name}: inconsistent row counts "
              f"{counts} (expected {TIMESTEPS_PER_DAY}) — skipping")
        return False

    return True


# ================================================================
# STEP 2 — READ LEAK METADATA
# ================================================================

def read_leak_metadata(scenario_dir: Path):
    """
    Read leak_type.json and leak_info.json.

    Returns:
        leak_type  (str)   — e.g. 'continuous' or 'no_leak'
        has_leak   (bool)
        leak_score (float) — normalised severity 0–1
    """
    with open(scenario_dir / 'leak_type.json') as f:
        leak_type = json.load(f).get('leak_type', 'no_leak')

    leak_score = 0.0
    with open(scenario_dir / 'leak_info.json') as f:
        info = json.load(f)

    if info.get('has_leak') and info.get('leak_details'):
        magnitude  = info['leak_details'].get('leak_demand_m3s', 0.0)
        leak_score = float(np.clip(magnitude / MAX_POSSIBLE_LEAK, 0.0, 1.0))

    has_leak = (leak_type != 'no_leak')
    return leak_type, has_leak, leak_score


# ================================================================
# STEP 3 — SCENARIO-LEVEL AGGREGATES
# ================================================================

def compute_night_flow_metrics(flows_df: pd.DataFrame) -> dict:
    """
    Night vs day flow statistics across all pipe links.
    These are scenario-level — same value repeated for all 24 rows.

    Parameters:
        flows_df — shape (24, n_links)
    """
    night_vals = np.abs(flows_df.iloc[NIGHT_HOURS].values.flatten())
    day_vals   = np.abs(flows_df.iloc[DAY_HOURS].values.flatten())
    day_mean   = float(np.mean(day_vals))

    return {
        'night_flow_min':     float(np.min(night_vals)),
        'night_flow_mean':    float(np.mean(night_vals)),
        'night_flow_std':     float(np.std(night_vals)),
        'day_flow_mean':      day_mean,
        'night_to_day_ratio': float(np.mean(night_vals)) / (day_mean + 1e-6),
    }


def compute_temporal_features(mean_flow_series: np.ndarray) -> dict:
    """
    Trend and variability over the scenario's mean-flow time series.
    These are scenario-level — same value repeated for all 24 rows.

    Parameters:
        mean_flow_series — 1-D array of length TIMESTEPS_PER_DAY
    """
    x     = np.arange(len(mean_flow_series))
    slope = float(np.polyfit(x, mean_flow_series, 1)[0])

    s         = pd.Series(mean_flow_series)
    roll_mean = s.rolling(window=6, min_periods=1).mean()
    roll_std  = s.rolling(window=6, min_periods=1).std().fillna(0.0)
    mean_val  = float(s.mean())

    return {
        'flow_trend_slope':      slope,
        'flow_rolling_mean_avg': float(roll_mean.mean()),
        'flow_rolling_std_avg':  float(roll_std.mean()),
        'flow_cv':               float(s.std() / (mean_val + 1e-6)),
    }


# ================================================================
# STEP 4 — VALIDATE OUTPUT SCHEMA
# ================================================================

def validate_output_schema(df: pd.DataFrame) -> None:
    """
    Confirm the assembled dataset has every column defined in config.
    Raises ValueError if any column is missing or contains NaNs.
    """
    expected = ID_COLUMNS + TARGET_COLUMNS + RAW_FEATURE_COLUMNS
    missing  = [c for c in expected if c not in df.columns]
    if missing:
        raise ValueError(f"Output dataset missing columns: {missing}")

    nan_cols = {
        col: int(df[col].isnull().sum())
        for col in RAW_FEATURE_COLUMNS
        if df[col].isnull().sum() > 0
    }
    if nan_cols:
        raise ValueError(f"NaN values in feature columns: {nan_cols}")

    print("✓ Schema validation passed")


# ================================================================
# CORE — BUILD DATASET
# ================================================================

def build_dataset(scenarios_dir: Path, output_csv: Path) -> pd.DataFrame:
    """
    Iterate all scenario_XXXX folders and assemble one flat dataset.

    Row structure:
        One row per timestep per scenario.
        Total rows = TIMESTEPS_PER_DAY × valid_scenario_count.

    Column order (enforced by config):
        ID_COLUMNS → TARGET_COLUMNS → RAW_FEATURE_COLUMNS
    """
    scenario_dirs = sorted(scenarios_dir.glob('scenario_*'))

    if not scenario_dirs:
        raise FileNotFoundError(
            f"No scenario_* folders found in:\n  {scenarios_dir}\n"
            "Run generate_scenarios.py first."
        )

    n_total = len(scenario_dirs)
    print(f"Found {n_total} scenario folders")
    print("Building dataset...\n")

    rows    = []
    skipped = []

    for idx, scenario_dir in enumerate(scenario_dirs, 1):

        if idx % 100 == 0 or idx == n_total:
            print(f"  Processing {idx}/{n_total} ...")

        # ── Validate ───────────────────────────────────────────────
        if not validate_scenario_files(scenario_dir):
            skipped.append(scenario_dir.name)
            continue

        # ── Load CSVs ──────────────────────────────────────────────
        try:
            demands   = pd.read_csv(scenario_dir / 'demands.csv')
            pressures = pd.read_csv(scenario_dir / 'pressures.csv')
            flows     = pd.read_csv(scenario_dir / 'flows.csv')
            labels    = pd.read_csv(scenario_dir / 'labels.csv')
        except Exception as e:
            print(f"  ⚠ {scenario_dir.name}: read error ({e}) — skipping")
            skipped.append(scenario_dir.name)
            continue

        # ── Leak metadata ──────────────────────────────────────────
        try:
            leak_type, has_leak, leak_score = read_leak_metadata(scenario_dir)
        except Exception as e:
            print(f"  ⚠ {scenario_dir.name}: metadata error ({e}) — skipping")
            skipped.append(scenario_dir.name)
            continue

        # ── Scenario-level aggregates ──────────────────────────────
        night_metrics = compute_night_flow_metrics(flows)
        temporal      = compute_temporal_features(
            flows.mean(axis=1).values
        )

        # ── One row per timestep ───────────────────────────────────
        label_col = 'leak' if 'leak' in labels.columns else labels.columns[0]

        for t in range(TIMESTEPS_PER_DAY):
            leak_active = int(labels.iloc[t][label_col])

            row = {
                # Identifiers
                'scenario':   scenario_dir.name,
                'time_index': t,

                # Targets
                'scenario_has_leak':       int(has_leak),
                'leak_type':               leak_type,
                'leak_score':              leak_score,
                'leak_active_at_timestep': leak_active,

                # Demand statistics at timestep t
                'mean_demand':  float(demands.iloc[t].mean()),
                'max_demand':   float(demands.iloc[t].max()),
                'min_demand':   float(demands.iloc[t].min()),
                'std_demand':   float(demands.iloc[t].std()),
                'demand_range': float(
                    demands.iloc[t].max() - demands.iloc[t].min()
                ),
                'total_demand': float(demands.iloc[t].sum()),

                # Pressure statistics at timestep t
                'mean_pressure':  float(pressures.iloc[t].mean()),
                'max_pressure':   float(pressures.iloc[t].max()),
                'min_pressure':   float(pressures.iloc[t].min()),
                'std_pressure':   float(pressures.iloc[t].std()),
                'pressure_range': float(
                    pressures.iloc[t].max() - pressures.iloc[t].min()
                ),

                # Flow statistics at timestep t
                'mean_flow':  float(flows.iloc[t].mean()),
                'max_flow':   float(flows.iloc[t].max()),
                'min_flow':   float(flows.iloc[t].min()),
                'std_flow':   float(flows.iloc[t].std()),
                'flow_range': float(
                    flows.iloc[t].max() - flows.iloc[t].min()
                ),
                'total_flow': float(flows.iloc[t].sum()),

                # Hydraulic balance
                'flow_demand_ratio': float(
                    flows.iloc[t].mean() /
                    (demands.iloc[t].mean() + 1e-6)
                ),

                # Scenario-level night/day metrics
                **night_metrics,

                # Scenario-level temporal features
                **temporal,
            }

            rows.append(row)

    # ── Assemble DataFrame ─────────────────────────────────────────
    if not rows:
        raise ValueError(
            "No rows were generated. "
            "Ensure scenario folders contain valid CSV files."
        )

    df = pd.DataFrame(rows)

    # Enforce exact column order from config
    ordered_cols = ID_COLUMNS + TARGET_COLUMNS + RAW_FEATURE_COLUMNS
    df = df[ordered_cols]

    # Sort by scenario then time
    df = df.sort_values(
        ['scenario', 'time_index']
    ).reset_index(drop=True)

    # ── Validate schema ────────────────────────────────────────────
    validate_output_schema(df)

    # ── Save ───────────────────────────────────────────────────────
    output_csv.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_csv, index=False)

    # ── Summary ────────────────────────────────────────────────────
    n_scenarios = df['scenario'].nunique()
    n_leak      = int(
        df.groupby('scenario')['scenario_has_leak'].first().sum()
    )
    n_no_leak   = n_scenarios - n_leak
    t_active    = int((df['leak_active_at_timestep'] == 1).sum())

    print(f"\n{'='*60}")
    print(f"✓ DATASET BUILD COMPLETE")
    print(f"{'='*60}")
    print(f"  Output               : {output_csv}")
    print(f"  Total rows           : {len(df):,}")
    print(f"  Total columns        : {len(df.columns)}")
    print(f"  Scenarios processed  : {n_scenarios:,}")
    print(f"  Scenarios skipped    : {len(skipped)}")
    print(f"  Leak scenarios       : {n_leak:,}")
    print(f"  No-leak scenarios    : {n_no_leak:,}")
    print(f"  Leak-active timesteps: {t_active:,} "
          f"({t_active/len(df)*100:.1f}%)")
    print(f"{'='*60}")

    if skipped:
        shown = ', '.join(skipped[:5])
        extra = f" +{len(skipped)-5} more" if len(skipped) > 5 else ""
        print(f"\n  Skipped: {shown}{extra}")

    return df


# ENTRY POINT

if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Build merged dataset from raw scenario folders'
    )
    parser.add_argument(
        '--input',
        default=str(RAW_SCENARIOS_DIR),
        help='Root directory containing scenario_XXXX folders'
    )
    parser.add_argument(
        '--output',
        default=str(MERGED_DATASET),
        help='Output path for merged_dataset.csv'
    )
    args = parser.parse_args()

    create_directories()
    build_dataset(Path(args.input), Path(args.output))
