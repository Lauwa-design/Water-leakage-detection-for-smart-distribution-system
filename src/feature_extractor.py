# -*- coding: utf-8 -*-
"""Extract hydraulic indicators for model training.

Changes from previous version
──────────────────────────────
1. Removed label leakage: _scenario_features() no longer uses leak_start_idx /
   leak_end_idx to split the time-series into "inside vs outside" windows.
   All features are now computed blind — exactly as they would be at inference time.

2. Added MULTICLASS_FEATURES: baseline-relative and shape features (no leak timing).
     - flow_p95, flow_p99         → peak magnitude (extreme)
     - above_baseline_fraction   → sustained elevation vs early-window reference (~0.25 is not enforced)
     - spike_sharpness            → sharp peaks vs early median
     - night_mnf_ratio            → slow leaks elevate night vs day flow
     - pressure_drop_abs          → extreme leaks cause largest absolute drops
     - flow_cv                    → moderate leaks add extra variance
     - flow_max_step              → extreme onset = single large step change
     - pressure_cv                → pressure variability
     - flow_late_vs_early_rel      → cumulative ramp (slow) vs flat (none)

3. Window-based features (WINDOW_FEATURES / extract_window_features) are
   unchanged — they were not affected by the leakage issue.
"""

from __future__ import annotations

import json
import sys
import warnings
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


# ──────────────────────────────────────────────────────────────────────────────
# Feature-set definitions
# ──────────────────────────────────────────────────────────────────────────────

SEVEN_FEATURES = [
    "mnf",
    "night_flow_ratio",
    "flow_variance",
    "daily_variance",
    "pressure_flow_correlation",
    "pressure_drop_pattern",
    "flow_trend",
]

# Used by the multiclass classifier only (binary still uses SEVEN_FEATURES).
# Seven originals plus 10 leak-shape / baseline-relative features (retrain after changes).
MULTICLASS_FEATURES = [
    # Original 7
    "mnf",
    "night_flow_ratio",
    "flow_variance",
    "daily_variance",
    "pressure_flow_correlation",
    "pressure_drop_pattern",
    "flow_trend",
    # New — peak magnitude (extreme leaks dominate here)
    "flow_p95",
    "flow_p99",
    # New — fraction of timestep above early-window threshold (slow = more coverage)
    "above_baseline_fraction",
    # New — spike sharpness vs early-window scale
    "spike_sharpness",
    # New — night vs day (slow leaks elevate MNF most)
    "night_mnf_ratio",
    # New — absolute pressure drop (extreme leaks cause largest drops)
    "pressure_drop_abs",
    # New — coefficient of variation (moderate leaks add variance)
    "flow_cv",
    # New — single-step change at onset (extreme leaks spike sharply)
    "flow_max_step",
    # New — pressure coefficient of variation
    "pressure_cv",
    # New — late-day vs early-day relative flow ramp (label-free thirds split)
    "flow_late_vs_early_rel",
]

# Kept for backwards compatibility with window-based training scripts
ENHANCED_FEATURES = [
    "mnf",
    "night_flow_ratio",
    "flow_variance",
    "daily_variance",
    "pressure_flow_correlation",
    "pressure_drop_pattern",
    "flow_trend",
    "peak_hour_flow",
    "off_peak_flow",
    "flow_consistency_score",
    "pressure_variance",
    "pressure_trend",
    "pressure_stability",
    "flow_pressure_ratio",
    "anomaly_score",
    "leak_signature_strength",
]

# Sliding-window feature names (unchanged)
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

# All scenario-level feature columns written to engineered_features.csv
_ALL_SCENARIO_FEATURE_COLS = list(
    dict.fromkeys(SEVEN_FEATURES + MULTICLASS_FEATURES + ENHANCED_FEATURES)
)


def write_feature_extraction_quality_report(features_df: pd.DataFrame) -> Path:
    """Persist lightweight separation stats for MULTICLASS + binary feature sets."""
    report: dict = {
        "multiclass_leak_type_separation": {},
        "binary_leak_vs_none_separation": {},
        "notes": {},
    }

    leak_df = features_df[features_df["scenario_has_leak"] == 1]
    for feat in MULTICLASS_FEATURES:
        if feat not in features_df.columns:
            continue
        groups = [
            g[feat].to_numpy(dtype=float)
            for _, g in leak_df.groupby("leak_type")
            if len(g) > 0
        ]
        if len(groups) < 2:
            report["multiclass_leak_type_separation"][feat] = {"f_ratio": 0.0}
            continue
        means = [float(np.mean(g)) for g in groups]
        between = float(np.var(means))
        within = float(
            np.mean([float(np.var(g)) if len(g) > 1 else 0.0 for g in groups])
        )
        f_ratio = between / within if within > 1e-12 else 0.0
        report["multiclass_leak_type_separation"][feat] = {"f_ratio": round(f_ratio, 6)}

    no_leak = features_df[features_df["scenario_has_leak"] == 0]
    has_leak = features_df[features_df["scenario_has_leak"] == 1]
    for feat in SEVEN_FEATURES:
        if feat not in features_df.columns or no_leak.empty or has_leak.empty:
            continue
        m0 = float(pd.to_numeric(no_leak[feat], errors="coerce").mean())
        m1 = float(pd.to_numeric(has_leak[feat], errors="coerce").mean())
        mean_diff = abs(m1 - m0)
        s0 = float(pd.to_numeric(no_leak[feat], errors="coerce").std())
        s1 = float(pd.to_numeric(has_leak[feat], errors="coerce").std())
        pooled = (s0 + s1) / 2.0 if (s0 + s1) > 0 else 1e-12
        cohen_proxy = mean_diff / max(pooled, 1e-12)
        report["binary_leak_vs_none_separation"][feat] = {
            "mean_diff": round(mean_diff, 6),
            "cohen_d_proxy": round(float(cohen_proxy), 6),
        }

    low_multi = [
        f
        for f, v in report["multiclass_leak_type_separation"].items()
        if isinstance(v, dict) and v.get("f_ratio", 0.0) < 1e-6
    ]
    report["notes"] = {
        "multiclass_low_separation_features": low_multi,
        "f_ratio_explainer": (
            "variance of class-wise means divided by mean within-class variance; "
            "larger implies more multiclass discrimination."
        ),
    }

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    path = PROCESSED_DIR / "feature_extraction_quality.json"
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2)
    print(f"[OK] Feature quality report → {path}")
    return path


# ──────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ──────────────────────────────────────────────────────────────────────────────

def _derive_hour(df: pd.DataFrame) -> pd.Series:
    if "timestamp" in df.columns:
        timestamps = pd.to_datetime(df["timestamp"], errors="coerce")
        if timestamps.notna().any():
            return timestamps.dt.hour.fillna(0).astype(int)

    if "time_index" in df.columns:
        # 5-minute intervals → 12 samples per hour
        return ((pd.to_numeric(df["time_index"], errors="coerce").fillna(0) // 12) % 24).astype(int)

    return pd.Series(np.zeros(len(df), dtype=int), index=df.index)


def _safe_corr(a: pd.Series, b: pd.Series) -> float:
    """Pearson r; 0.0 if undefined (too short or zero-variance series)."""
    if len(a) < 3 or len(b) < 3:
        return 0.0
    ax = pd.to_numeric(a, errors="coerce")
    bx = pd.to_numeric(b, errors="coerce")
    if ax.notna().sum() < 3 or bx.notna().sum() < 3:
        return 0.0
    sa = float(ax.std(skipna=True))
    sb = float(bx.std(skipna=True))
    if sa < 1e-12 or sb < 1e-12 or not np.isfinite(sa) or not np.isfinite(sb):
        return 0.0
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", RuntimeWarning)
        value = float(ax.corr(bx))
    return 0.0 if not np.isfinite(value) else value


def _safe_flow_trend(flow: pd.Series) -> float:
    if len(flow) < 5:
        return 0.0
    x = np.arange(len(flow), dtype=float)
    return float(np.polyfit(x, flow.to_numpy(dtype=float), 1)[0])


def _early_reference_window_len(series_len: int) -> int:
    """Fraction of horizon used as causal reference (~2–6 h at 5-min steps)."""
    return max(24, min(72, max(1, series_len // 4)))


def _safe_pressure_drop(pressure: pd.Series) -> float:
    """Fractional pressure drop: (early_mean - recent_mean) / early_mean."""
    if len(pressure) < 3:
        return 0.0
    window = min(10, max(len(pressure) // 3, 1))
    early = float(pressure.iloc[:window].mean())
    recent = float(pressure.iloc[-window:].mean())
    if early <= 0:
        return 0.0
    return (early - recent) / early


# ──────────────────────────────────────────────────────────────────────────────
# Scenario-level feature extraction  (label-leakage free)
# ──────────────────────────────────────────────────────────────────────────────

def _scenario_features(group: pd.DataFrame) -> dict[str, float | int | str]:
    """Compute all scenario-level features from raw time-series.

    IMPORTANT: This function deliberately does NOT use leak_start_idx,
    leak_end_idx, or leak_magnitude_l_min when computing features.  Those
    columns are only carried through as metadata.  Using them to split the
    series into "inside/outside leak window" constitutes label leakage and
    causes the model to fail at inference time.
    """
    group = (
        group.sort_values("time_index").copy()
        if "time_index" in group.columns
        else group.copy()
    )
    group["hour"] = _derive_hour(group)

    flow = pd.to_numeric(group["mean_flow"], errors="coerce").fillna(0.0)
    pressure = pd.to_numeric(group["mean_pressure"], errors="coerce").fillna(0.0)

    night_mask = group["hour"].between(0, 6)   # 00:00–06:59
    day_mask = ~night_mask

    # ── FEATURE 1: MNF (Minimum Night Flow) ──────────────────────────────────
    # Leaks elevate night flow because the leak runs 24/7.
    if night_mask.any():
        mnf = float(flow[night_mask].min())
        night_mean = float(flow[night_mask].mean())
    else:
        mnf = float(flow.min())
        night_mean = float(flow.mean())

    # ── FEATURE 2: Night Flow Ratio ───────────────────────────────────────────
    # Leaks push night flow closer to (or above) day flow.
    if night_mask.any() and day_mask.any():
        day_mean = float(flow[day_mask].mean())
        night_flow_ratio = night_mean / day_mean if day_mean > 0 else 0.0
    else:
        night_flow_ratio = 0.0

    # ── FEATURE 3: Flow Variance (global, blind) ──────────────────────────────
    flow_variance = float(flow.var()) if len(flow) > 1 else 0.0

    # ── FEATURE 4: Daily Range ────────────────────────────────────────────────
    daily_variance = float(flow.max() - flow.min())

    # ── FEATURE 5: Pressure-Flow Correlation ──────────────────────────────────
    # During leaks flow ↑ while pressure ↓ → negative correlation.
    pressure_flow_correlation = _safe_corr(flow, pressure)

    # ── FEATURE 6: Pressure Drop Pattern (global, blind) ─────────────────────
    pressure_drop_pattern = _safe_pressure_drop(pressure)

    # ── FEATURE 7: Flow Trend ─────────────────────────────────────────────────
    flow_trend = _safe_flow_trend(flow)

    # Causal early window — first segment only (no leak_start_idx).
    ew = _early_reference_window_len(len(flow))
    early_flow = flow.iloc[:ew]
    baseline_mean = float(early_flow.mean())
    baseline_std = float(early_flow.std()) if len(early_flow) > 1 else 0.0
    baseline_median = float(early_flow.median())

    # ── NEW: Peak flow magnitude ───────────────────────────────────────────────
    # Extreme leaks drive very high short-duration spikes.
    flow_p95 = float(flow.quantile(0.95))
    flow_p99 = float(flow.quantile(0.99))

    # ── NEW: Sustained elevation vs early baseline (slow leaks stay high longer)
    threshold = baseline_mean + 0.5 * max(baseline_std, baseline_mean * 0.02 + 1e-6)
    above_baseline_fraction = float((flow > threshold).mean())

    # ── NEW: Spike sharpness (extreme spikes vs typical early flow scale)
    spike_sharpness = flow_p99 / max(abs(baseline_median), 1e-6)

    # ── NEW: Late vs early thirds — ramp/leak persistence without timing labels
    seg = max(1, len(flow) // 3)
    early_seg_mean = float(flow.iloc[:seg].mean())
    late_seg_mean = float(flow.iloc[-seg:].mean())
    denom = max(abs(early_seg_mean), 1e-6)
    flow_late_vs_early_rel = (late_seg_mean - early_seg_mean) / denom

    # ── NEW: Night MNF ratio ───────────────────────────────────────────────────
    # Slow leaks lift the night minimum closest to the daytime average.
    day_mean_val = float(flow[day_mask].mean()) if day_mask.any() else float(flow.mean())
    night_mnf_ratio = mnf / day_mean_val if day_mean_val > 0 else 0.0

    # ── NEW: Absolute pressure drop ───────────────────────────────────────────
    # P95 − P05 captures total swing; extreme leaks cause the largest drops.
    pressure_drop_abs = float(pressure.quantile(0.95) - pressure.quantile(0.05))

    # ── NEW: Flow coefficient of variation ────────────────────────────────────
    # Moderate leaks add extra stochastic variance.
    flow_mean_val = float(flow.mean())
    flow_cv = float(flow.std() / flow_mean_val) if flow_mean_val > 0 else 0.0

    # ── NEW: Max single-step flow change ──────────────────────────────────────
    # Extreme leak onset = one large step; slow leaks ramp gradually.
    flow_max_step = float(flow.diff().abs().max()) if len(flow) > 1 else 0.0

    # ── NEW: Pressure coefficient of variation ────────────────────────────────
    pressure_mean_val = float(pressure.mean())
    pressure_cv = (
        float(pressure.std() / pressure_mean_val) if pressure_mean_val > 0 else 0.0
    )

    # ── ENHANCED / legacy features (kept for backward compatibility) ──────────
    peak_hour_mask = group["hour"].between(6, 9) | group["hour"].between(17, 20)
    off_peak_mask = group["hour"].between(22, 23) | group["hour"].between(0, 5)
    peak_hour_flow = float(flow[peak_hour_mask].mean()) if peak_hour_mask.any() else flow_mean_val
    off_peak_flow = float(flow[off_peak_mask].mean()) if off_peak_mask.any() else flow_mean_val
    flow_consistency_score = float(flow.std() / flow_mean_val) if flow_mean_val > 0 else 0.0
    pressure_variance = float(pressure.var()) if len(pressure) > 1 else 0.0
    pressure_trend = _safe_flow_trend(pressure)
    pressure_stability = (
        float(pressure.std() / pressure_mean_val) if pressure_mean_val > 0 else 0.0
    )
    flow_pressure_ratio = float(flow_mean_val / pressure_mean_val) if pressure_mean_val > 0 else 0.0
    flow_median = float(flow.median())
    anomaly_score = (
        abs(flow_mean_val - flow_median) / flow_median if flow_median > 0 else 0.0
    )
    leak_signature_strength = (
        abs(pressure_drop_pattern) * 0.4
        + abs(pressure_flow_correlation) * 0.3
        + (night_flow_ratio - 0.5) * 0.3
        if night_flow_ratio > 0.5
        else abs(pressure_drop_pattern) * 0.5 + abs(pressure_flow_correlation) * 0.5
    )

    result: dict[str, float | int | str] = {
        "scenario": int(group["scenario"].iloc[0]),
        # ── Original 7 features ──
        "mnf": mnf,
        "night_flow_ratio": night_flow_ratio,
        "flow_variance": flow_variance,
        "daily_variance": daily_variance,
        "pressure_flow_correlation": pressure_flow_correlation,
        "pressure_drop_pattern": pressure_drop_pattern,
        "flow_trend": flow_trend,
        # ── New multiclass-discriminative features ──
        "flow_p95": flow_p95,
        "flow_p99": flow_p99,
        "above_baseline_fraction": above_baseline_fraction,
        "spike_sharpness": spike_sharpness,
        "night_mnf_ratio": night_mnf_ratio,
        "pressure_drop_abs": pressure_drop_abs,
        "flow_cv": flow_cv,
        "flow_max_step": flow_max_step,
        "pressure_cv": pressure_cv,
        "flow_late_vs_early_rel": flow_late_vs_early_rel,
        # ── Legacy enhanced features ──
        "peak_hour_flow": peak_hour_flow,
        "off_peak_flow": off_peak_flow,
        "flow_consistency_score": flow_consistency_score,
        "pressure_variance": pressure_variance,
        "pressure_trend": pressure_trend,
        "pressure_stability": pressure_stability,
        "flow_pressure_ratio": flow_pressure_ratio,
        "anomaly_score": anomaly_score,
        "leak_signature_strength": leak_signature_strength,
        # ── Labels ──
        "scenario_has_leak": int(group["scenario_has_leak"].iloc[0]),
        "leak_type": str(group["leak_type"].iloc[0]),
    }

    # Pass-through metadata columns (never fed into any model).
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


def live_features_from_readings_frame(frame: pd.DataFrame) -> dict[str, float]:
    """Scenario-level features from live meter readings (binary + multiclass columns).

    Expected columns: ``timestamp`` (optional), and either ``mean_flow`` or
    ``flow_rate``, and either ``mean_pressure`` or ``pressure``. Rows must be
    time-ordered readings for a single meter; semantics match training slices
    of ``merged_dataset`` (no leak-index leakage — labels are ignored).

    Returns a flat dict with keys from ``SEVEN_FEATURES`` ∪ ``MULTICLASS_FEATURES``.
    """
    if frame.empty:
        return {}

    df = frame.copy()
    if "mean_flow" not in df.columns:
        if "flow_rate" not in df.columns:
            raise ValueError("readings must include mean_flow or flow_rate")
        df["mean_flow"] = pd.to_numeric(df["flow_rate"], errors="coerce").fillna(0.0)
    else:
        df["mean_flow"] = pd.to_numeric(df["mean_flow"], errors="coerce").fillna(0.0)

    if "mean_pressure" not in df.columns:
        if "pressure" not in df.columns:
            raise ValueError("readings must include mean_pressure or pressure")
        df["mean_pressure"] = pd.to_numeric(df["pressure"], errors="coerce").fillna(0.0)
    else:
        df["mean_pressure"] = pd.to_numeric(df["mean_pressure"], errors="coerce").fillna(0.0)

    df["scenario"] = 0
    df["scenario_has_leak"] = 0
    df["leak_type"] = "none"
    if "time_index" not in df.columns:
        df["time_index"] = np.arange(len(df), dtype=int)

    df = df.sort_values("time_index", kind="mergesort").reset_index(drop=True)
    raw = _scenario_features(df)

    out: dict[str, float] = {}
    for k in dict.fromkeys(SEVEN_FEATURES + MULTICLASS_FEATURES):
        if k not in raw:
            continue
        v = raw[k]
        if isinstance(v, (int, float, np.floating)):
            fv = float(v)
            out[k] = fv if np.isfinite(fv) else 0.0
    return out


# ──────────────────────────────────────────────────────────────────────────────
# Public API — scenario-level
# ──────────────────────────────────────────────────────────────────────────────

def extract_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute scenario-level features and write engineered_features.csv."""
    required = {"scenario", "mean_flow", "mean_pressure", "scenario_has_leak", "leak_type"}
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Missing required columns for feature extraction: {missing}")

    df = df.sort_values(
        ["scenario", "time_index"] if "time_index" in df.columns else ["scenario"]
    ).copy()

    features_df = pd.DataFrame(
        [_scenario_features(g) for _, g in df.groupby("scenario", sort=True)]
    )

    # Sanitise all numeric feature columns
    features_df[_ALL_SCENARIO_FEATURE_COLS] = (
        features_df[_ALL_SCENARIO_FEATURE_COLS]
        .replace([np.inf, -np.inf], 0.0)
        .fillna(0.0)
    )

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    output_path = PROCESSED_DIR / "engineered_features.csv"
    features_df.to_csv(output_path, index=False)
    print(f"[OK] Saved enhanced feature dataset ({len(features_df)} scenarios) to {output_path}")
    write_feature_extraction_quality_report(features_df)
    return features_df


# ──────────────────────────────────────────────────────────────────────────────
# Public API — window-level  (unchanged from previous version)
# ──────────────────────────────────────────────────────────────────────────────

def extract_window_features(
    df: pd.DataFrame,
    window_size: int = 24,
    overlap: float = 0.5,
) -> pd.DataFrame:
    """Extract features from sliding windows for temporal leak detection.

    Args:
        df: Raw time-series data.
        window_size: Timesteps per window (default 24 = 2 h at 5-min intervals).
        overlap: Fraction of overlap between consecutive windows (default 0.5).

    Returns:
        DataFrame with one row per window.
    """
    required = {
        "scenario", "time_index", "mean_flow", "mean_pressure",
        "scenario_has_leak", "leak_type",
    }
    missing = sorted(required - set(df.columns))
    if missing:
        raise ValueError(f"Missing required columns for window feature extraction: {missing}")

    all_windows: list[dict] = []
    step_size = max(1, int(window_size * (1 - overlap)))

    for scenario_id, group in df.groupby("scenario", sort=True):
        group = group.sort_values("time_index").reset_index(drop=True)
        scenario_has_leak = int(group["scenario_has_leak"].iloc[0])
        leak_start = int(group["leak_start_idx"].iloc[0]) if "leak_start_idx" in group.columns else -1
        leak_end = int(group["leak_end_idx"].iloc[0]) if "leak_end_idx" in group.columns else -1
        leak_type = str(group["leak_type"].iloc[0])
        leak_magnitude = (
            float(group["leak_magnitude_l_min"].iloc[0])
            if "leak_magnitude_l_min" in group.columns
            else 0.0
        )

        for start_idx in range(0, len(group) - window_size + 1, step_size):
            end_idx = start_idx + window_size
            window = group.iloc[start_idx:end_idx]

            # Label this window
            window_has_leak = 0
            window_leak_type = "none"
            if scenario_has_leak and leak_start >= 0 and leak_end >= 0:
                if not (leak_end < start_idx or leak_start >= end_idx):
                    window_has_leak = 1
                    window_leak_type = leak_type

            flow = pd.to_numeric(window["mean_flow"], errors="coerce").fillna(0.0)
            pressure = pd.to_numeric(window["mean_pressure"], errors="coerce").fillna(0.0)

            flow_mean = float(flow.mean())
            flow_max = float(flow.max())
            flow_min = float(flow.min())
            pressure_mean = float(pressure.mean())
            pressure_min = float(pressure.min())
            pressure_std = float(pressure.std()) if len(pressure) > 1 else 0.0

            flow_spike = float(flow_max - flow.median())
            pressure_drop = float(pressure.iloc[0] - pressure.iloc[-1])
            flow_pressure_corr = _safe_corr(flow, pressure)
            pressure_stability_score = (
                pressure_std / pressure_mean if pressure_mean > 0 else 0.0
            )

            if len(flow) >= 3:
                x = np.arange(len(flow), dtype=float)
                flow_trend = float(np.polyfit(x, flow.to_numpy(dtype=float), 1)[0])
            else:
                flow_trend = 0.0

            if len(flow) >= 5:
                mid = len(flow) // 2
                t1 = float(np.polyfit(np.arange(mid, dtype=float), flow.iloc[:mid].to_numpy(dtype=float), 1)[0])
                t2 = float(np.polyfit(np.arange(len(flow) - mid, dtype=float), flow.iloc[mid:].to_numpy(dtype=float), 1)[0])
                flow_acceleration = t2 - t1
            else:
                flow_acceleration = 0.0

            all_windows.append(
                {
                    "scenario": scenario_id,
                    "window_start": start_idx,
                    "window_end": end_idx,
                    "window_center_time": (start_idx + end_idx) // 2,
                    "mean_flow": flow_mean,
                    "max_flow": flow_max,
                    "min_flow": flow_min,
                    "flow_variance": float(flow.var()) if len(flow) > 1 else 0.0,
                    "flow_spike": flow_spike,
                    "flow_trend": flow_trend,
                    "flow_acceleration": flow_acceleration,
                    "mean_pressure": pressure_mean,
                    "min_pressure": pressure_min,
                    "pressure_drop": pressure_drop,
                    "pressure_variance": float(pressure.var()) if len(pressure) > 1 else 0.0,
                    "pressure_stability_score": pressure_stability_score,
                    "flow_pressure_corr": flow_pressure_corr,
                    "window_has_leak": window_has_leak,
                    "leak_type": window_leak_type,
                    "leak_magnitude_l_min": leak_magnitude if window_has_leak else 0.0,
                    "scenario_has_leak": scenario_has_leak,
                }
            )

    windows_df = pd.DataFrame(all_windows)
    windows_df[WINDOW_FEATURES] = (
        windows_df[WINDOW_FEATURES].replace([np.inf, -np.inf], 0.0).fillna(0.0)
    )

    PROCESSED_DIR.mkdir(parents=True, exist_ok=True)
    output_path = PROCESSED_DIR / "window_features.csv"
    windows_df.to_csv(output_path, index=False)

    print(f"[OK] Saved {len(windows_df)} windows from {windows_df['scenario'].nunique()} scenarios → {output_path}")
    print(f"     Window size : {window_size} timesteps  ({window_size * 5} min)")
    print(f"     Overlap     : {overlap * 100:.0f}%")
    print(f"     Leak windows: {windows_df['window_has_leak'].sum()} ({windows_df['window_has_leak'].mean() * 100:.1f}%)")
    return windows_df


# ──────────────────────────────────────────────────────────────────────────────
# Quick diagnostic helper
# ──────────────────────────────────────────────────────────────────────────────

def print_class_separation_report(features_csv: str | Path | None = None) -> None:
    """Print mean values of MULTICLASS_FEATURES grouped by leak_type.

    Run this after extract_features() to verify that the new features
    actually separate the three leak classes before you spend time training.
    """
    path = Path(features_csv) if features_csv else PROCESSED_DIR / "engineered_features.csv"
    if not path.exists():
        print(f"[WARN] {path} not found — run extract_features() first.")
        return

    df = pd.read_csv(path)
    leak_df = df[df["scenario_has_leak"] == 1]

    check_cols = [
        "flow_p99",
        "above_baseline_fraction",
        "flow_late_vs_early_rel",
        "spike_sharpness",
        "night_mnf_ratio",
        "pressure_drop_abs",
        "flow_cv",
        "flow_max_step",
        "pressure_cv",
    ]
    available = [c for c in check_cols if c in leak_df.columns]
    if not available:
        print("[WARN] New feature columns not found — re-run extract_features().")
        return

    print("\n── Class separation report (means by leak_type) ──")
    print(leak_df.groupby("leak_type")[available].mean().round(4).to_string())
    print()


# ──────────────────────────────────────────────────────────────────────────────
# Entry point
# ──────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    source = PROCESSED_DIR / "merged_dataset.csv"

    print("=" * 60)
    print("Extracting scenario-level features …")
    print("=" * 60)
    extract_features(pd.read_csv(source))
    print_class_separation_report()

    print("\n" + "=" * 60)
    print("Extracting sliding-window features …")
    print("=" * 60)
    extract_window_features(pd.read_csv(source), window_size=24, overlap=0.5)
