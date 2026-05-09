# -*- coding: utf-8 -*-
"""Extract the 7 documented hydraulic indicators for model training."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

try:
    from src.utils.config import PROCESSED_DIR  # type: ignore
except ModuleNotFoundError:
    from utils.config import PROCESSED_DIR  # noqa: E402


SEVEN_FEATURES = [
    "mnf",
    "night_flow_ratio",
    "flow_variance",
    "daily_variance",
    "pressure_flow_correlation",
    "pressure_drop_pattern",
    "flow_trend",
]

# Enhanced feature set with better discriminative power
ENHANCED_FEATURES = [
    # Original features
    "mnf",
    "night_flow_ratio",
    "flow_variance",
    "daily_variance",
    "pressure_flow_correlation",
    "pressure_drop_pattern",
    "flow_trend",
    # New time-based features
    "peak_hour_flow",
    "off_peak_flow",
    "flow_consistency_score",
    # New pressure features
    "pressure_variance",
    "pressure_trend",
    "pressure_stability",
    # New combined features
    "flow_pressure_ratio",
    "anomaly_score",
    "leak_signature_strength",
]

# Sliding window features for temporal leak detection
WINDOW_FEATURES = [
    "mean_flow",
    "max_flow",
    "min_flow",
    "flow_variance",
    "flow_spike",
    "flow_trend",
    "mean_pressure",
    "min_pressure",
    "pressure_drop",
    "pressure_variance",
    "flow_pressure_corr",
    "flow_acceleration",
    "pressure_stability_score",
]


def _derive_hour(df: pd.DataFrame) -> pd.Series:
    if "timestamp" in df.columns:
        timestamps = pd.to_datetime(df["timestamp"], errors="coerce")
        if timestamps.notna().any():
            return timestamps.dt.hour.fillna(0).astype(int)

    if "time_index" in df.columns:
        # Generator uses 5-minute intervals, so 12 samples == 1 hour.
        return ((pd.to_numeric(df["time_index"], errors="coerce").fillna(0) // 12) % 24).astype(int)

    return pd.Series(np.zeros(len(df), dtype=int), index=df.index)


def _safe_corr(a: pd.Series, b: pd.Series) -> float:
    if len(a) < 3 or len(b) < 3:
        return 0.0
    value = float(a.corr(b))
    return 0.0 if np.isnan(value) else value


def _safe_flow_trend(flow: pd.Series) -> float:
    if len(flow) < 5:
        return 0.0
    x = np.arange(len(flow), dtype=float)
    return float(np.polyfit(x, flow.to_numpy(dtype=float), 1)[0])


def _safe_pressure_drop(pressure: pd.Series) -> float:
    if len(pressure) < 3:
        return 0.0
    window = min(10, max(len(pressure) // 3, 1))
    early_pressure = float(pressure.iloc[:window].mean())
    recent_pressure = float(pressure.iloc[-window:].mean())
    if early_pressure <= 0:
        return 0.0
    return (early_pressure - recent_pressure) / early_pressure


def _scenario_features(group: pd.DataFrame) -> dict[str, float | int | str]:
    group = group.sort_values("time_index").copy() if "time_index" in group.columns else group.copy()
    group["hour"] = _derive_hour(group)

    flow = pd.to_numeric(group["mean_flow"], errors="coerce").fillna(0.0)
    pressure = pd.to_numeric(group["mean_pressure"], errors="coerce").fillna(0.0)
    night_mask = group["hour"].between(0, 6)
    day_mask = ~night_mask
    peak_mask = group["hour"].between(6, 9) | group["hour"].between(17, 20)
    off_peak_mask = group["hour"].between(22, 23) | group["hour"].between(0, 5)

    mnf = float(flow[night_mask].min()) if night_mask.any() else float(flow.min())
    if night_mask.any() and day_mask.any():
        night_avg = float(flow[night_mask].mean())
        day_avg = float(flow[day_mask].mean())
        night_flow_ratio = night_avg / day_avg if day_avg > 0 else 0.0
    else:
        night_flow_ratio = 0.0

    # Enhanced features
    peak_hour_flow = float(flow[peak_mask].mean()) if peak_mask.any() else float(flow.mean())
    off_peak_flow = float(flow[off_peak_mask].mean()) if off_peak_mask.any() else float(flow.mean())
    
    # Flow consistency: lower values indicate more consistent flow (potential leak)
    flow_std = float(flow.std()) if len(flow) > 1 else 0.0
    flow_mean = float(flow.mean())
    flow_consistency_score = flow_std / flow_mean if flow_mean > 0 else 0.0
    
    # Pressure features
    pressure_variance = float(pressure.var()) if len(pressure) > 1 else 0.0
    pressure_trend = _safe_flow_trend(pressure)
    pressure_std = float(pressure.std()) if len(pressure) > 1 else 0.0
    pressure_mean = float(pressure.mean())
    pressure_stability = pressure_std / pressure_mean if pressure_mean > 0 else 0.0
    
    # Combined features
    flow_pressure_ratio = flow_mean / pressure_mean if pressure_mean > 0 else 0.0
    
    # Anomaly score: combination of unusual patterns
    baseline_flow = float(flow[off_peak_mask].median()) if off_peak_mask.any() else float(flow.median())
    flow_deviation = abs(flow_mean - baseline_flow) / baseline_flow if baseline_flow > 0 else 0.0
    
    # Leak signature strength: combines multiple indicators
    pressure_drop_val = _safe_pressure_drop(pressure)
    leak_signature_strength = (
        flow_deviation * 0.4 +
        abs(pressure_drop_val) * 0.3 +
        (1.0 - flow_consistency_score) * 0.3
    )

    result: dict[str, float | int | str] = {
        "scenario": int(group["scenario"].iloc[0]),
        # Original features
        "mnf": mnf,
        "night_flow_ratio": night_flow_ratio,
        "flow_variance": float(flow.var()) if len(flow) > 1 else 0.0,
        "daily_variance": float(flow.max() - flow.min()) if len(flow) > 1 else 0.0,
        "pressure_flow_correlation": _safe_corr(flow, pressure),
        "pressure_drop_pattern": pressure_drop_val,
        "flow_trend": _safe_flow_trend(flow),
        # Enhanced features
        "peak_hour_flow": peak_hour_flow,
        "off_peak_flow": off_peak_flow,
        "flow_consistency_score": flow_consistency_score,
        "pressure_variance": pressure_variance,
        "pressure_trend": pressure_trend,
        "pressure_stability": pressure_stability,
        "flow_pressure_ratio": flow_pressure_ratio,
        "anomaly_score": flow_deviation,
        "leak_signature_strength": leak_signature_strength,
        # Labels
        "scenario_has_leak": int(group["scenario_has_leak"].iloc[0]),
        "leak_type": str(group["leak_type"].iloc[0]),
    }

    # Keep useful metadata for analysis without feeding it into the model.
    for optional in [
        "meter_model",
        "meter_size_mm",
        "leak_magnitude_l_min",
        "leak_start_idx",
        "leak_end_idx",
        "simulation_source",
    ]:
        if optional in group.columns:
            result[optional] = group[optional].iloc[0]

    return result


def extract_features(df: pd.DataFrame) -> pd.DataFrame:
    required = {"scenario", "mean_flow", "mean_pressure", "scenario_has_leak", "leak_type"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Missing required columns for feature extraction: {missing}")

    df = df.sort_values(["scenario", "time_index"] if "time_index" in df.columns else ["scenario"]).copy()
    features_df = pd.DataFrame([_scenario_features(group) for _, group in df.groupby("scenario", sort=True)])
    
    # Replace infinities and NaNs in all feature columns
    all_feature_cols = SEVEN_FEATURES + [
        "peak_hour_flow", "off_peak_flow", "flow_consistency_score",
        "pressure_variance", "pressure_trend", "pressure_stability",
        "flow_pressure_ratio", "anomaly_score", "leak_signature_strength"
    ]
    features_df[all_feature_cols] = features_df[all_feature_cols].replace([np.inf, -np.inf], 0.0).fillna(0.0)

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    output_path = PROCESSED_DIR / "engineered_features.csv"
    features_df.to_csv(output_path, index=False)
    print(f"[OK] Saved enhanced feature dataset to {output_path}")
    return features_df


def extract_window_features(df: pd.DataFrame, window_size: int = 24, overlap: float = 0.5) -> pd.DataFrame:
    """
    Extract features from sliding windows for temporal leak detection.
    
    Args:
        df: Raw time-series data with columns: scenario, time_index, mean_flow, mean_pressure, etc.
        window_size: Number of timesteps per window (default: 24 = 2 hours at 5-min intervals)
        overlap: Fraction of overlap between windows (default: 0.5 = 50% overlap)
    
    Returns:
        DataFrame with window-level features and labels
    """
    required = {"scenario", "time_index", "mean_flow", "mean_pressure", "scenario_has_leak", "leak_type"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Missing required columns for window feature extraction: {missing}")
    
    all_windows = []
    step_size = max(1, int(window_size * (1 - overlap)))
    
    for scenario_id, group in df.groupby("scenario", sort=True):
        group = group.sort_values("time_index").reset_index(drop=True)
        scenario_has_leak = int(group["scenario_has_leak"].iloc[0])
        leak_start = int(group["leak_start_idx"].iloc[0]) if "leak_start_idx" in group.columns else -1
        leak_end = int(group["leak_end_idx"].iloc[0]) if "leak_end_idx" in group.columns else -1
        leak_type = str(group["leak_type"].iloc[0])
        leak_magnitude = float(group["leak_magnitude_l_min"].iloc[0]) if "leak_magnitude_l_min" in group.columns else 0.0
        
        # Slide window across the scenario
        for start_idx in range(0, len(group) - window_size + 1, step_size):
            end_idx = start_idx + window_size
            window = group.iloc[start_idx:end_idx]
            
            # Determine if this window contains a leak
            window_has_leak = 0
            window_leak_type = "none"
            if scenario_has_leak and leak_start >= 0 and leak_end >= 0:
                # Check if leak period overlaps with window
                if not (leak_end < start_idx or leak_start >= end_idx):
                    window_has_leak = 1
                    window_leak_type = leak_type
            
            # Extract time-series data
            flow = pd.to_numeric(window["mean_flow"], errors="coerce").fillna(0.0)
            pressure = pd.to_numeric(window["mean_pressure"], errors="coerce").fillna(0.0)
            
            # Calculate window features
            flow_mean = float(flow.mean())
            flow_max = float(flow.max())
            flow_min = float(flow.min())
            flow_std = float(flow.std()) if len(flow) > 1 else 0.0
            
            pressure_mean = float(pressure.mean())
            pressure_min = float(pressure.min())
            pressure_std = float(pressure.std()) if len(pressure) > 1 else 0.0
            
            # Flow spike: how much max exceeds median
            flow_spike = float(flow_max - flow.median())
            
            # Flow trend: linear regression slope
            if len(flow) >= 3:
                x = np.arange(len(flow), dtype=float)
                flow_trend = float(np.polyfit(x, flow.to_numpy(dtype=float), 1)[0])
            else:
                flow_trend = 0.0
            
            # Pressure drop: first - last
            pressure_drop = float(pressure.iloc[0] - pressure.iloc[-1])
            
            # Flow-pressure correlation
            flow_pressure_corr = _safe_corr(flow, pressure)
            
            # Flow acceleration: change in trend (second derivative)
            if len(flow) >= 5:
                mid_point = len(flow) // 2
                x1 = np.arange(mid_point, dtype=float)
                x2 = np.arange(len(flow) - mid_point, dtype=float)
                trend1 = float(np.polyfit(x1, flow.iloc[:mid_point].to_numpy(dtype=float), 1)[0])
                trend2 = float(np.polyfit(x2, flow.iloc[mid_point:].to_numpy(dtype=float), 1)[0])
                flow_acceleration = trend2 - trend1
            else:
                flow_acceleration = 0.0
            
            # Pressure stability score: coefficient of variation
            pressure_stability_score = pressure_std / pressure_mean if pressure_mean > 0 else 0.0
            
            features = {
                "scenario": scenario_id,
                "window_start": start_idx,
                "window_end": end_idx,
                "window_center_time": (start_idx + end_idx) // 2,
                # Flow features
                "mean_flow": flow_mean,
                "max_flow": flow_max,
                "min_flow": flow_min,
                "flow_variance": float(flow.var()) if len(flow) > 1 else 0.0,
                "flow_spike": flow_spike,
                "flow_trend": flow_trend,
                "flow_acceleration": flow_acceleration,
                # Pressure features
                "mean_pressure": pressure_mean,
                "min_pressure": pressure_min,
                "pressure_drop": pressure_drop,
                "pressure_variance": float(pressure.var()) if len(pressure) > 1 else 0.0,
                "pressure_stability_score": pressure_stability_score,
                # Combined features
                "flow_pressure_corr": flow_pressure_corr,
                # Labels
                "window_has_leak": window_has_leak,
                "leak_type": window_leak_type,
                "leak_magnitude_l_min": leak_magnitude if window_has_leak else 0.0,
                # Metadata
                "scenario_has_leak": scenario_has_leak,
            }
            all_windows.append(features)
    
    windows_df = pd.DataFrame(all_windows)
    
    # Replace infinities and NaNs
    windows_df[WINDOW_FEATURES] = windows_df[WINDOW_FEATURES].replace([np.inf, -np.inf], 0.0).fillna(0.0)
    
    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    output_path = PROCESSED_DIR / "window_features.csv"
    windows_df.to_csv(output_path, index=False)
    print(f"[OK] Saved {len(windows_df)} windows from {windows_df['scenario'].nunique()} scenarios to {output_path}")
    print(f"    Window size: {window_size} timesteps ({window_size * 5} minutes)")
    print(f"    Overlap: {overlap * 100:.0f}%")
    print(f"    Windows with leaks: {windows_df['window_has_leak'].sum()} ({windows_df['window_has_leak'].mean() * 100:.1f}%)")
    
    return windows_df


if __name__ == "__main__":
    source = PROCESSED_DIR / "merged_dataset.csv"
    
    # Extract both scenario-level and window-level features
    print("=" * 60)
    print("Extracting scenario-level features...")
    print("=" * 60)
    extract_features(pd.read_csv(source))
    
    print("\n" + "=" * 60)
    print("Extracting sliding window features...")
    print("=" * 60)
    extract_window_features(pd.read_csv(source), window_size=24, overlap=0.5)
