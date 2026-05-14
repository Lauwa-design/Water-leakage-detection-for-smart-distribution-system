"""Real-time feature extractor for hydraulic leak detection."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict, Optional

import numpy as np
import pandas as pd
import warnings

_REPO_ROOT = Path(__file__).resolve().parents[2]


class RealtimeFeatureExtractor:
    """Extract hydraulic features aligned with ``src.feature_extractor`` training."""

    def _extract_live_features(self, frame: pd.DataFrame) -> Dict[str, float]:
        """Full binary + multiclass feature dict from a time-ordered readings frame."""
        if frame.empty:
            return {}
        if str(_REPO_ROOT) not in sys.path:
            sys.path.insert(0, str(_REPO_ROOT))
        try:
            from src.feature_extractor import live_features_from_readings_frame  # type: ignore

            return live_features_from_readings_frame(frame)
        except Exception as exc:
            print(f"Warning: live_features_from_readings_frame failed ({exc}); 7-feature fallback.")
            return self._legacy_seven_features_from_frame(frame)

    def _legacy_seven_features_from_frame(self, readings: pd.DataFrame) -> Dict[str, float]:
        """Original 7-feature path (only ``flow_rate`` / ``pressure``)."""
        if readings.empty or len(readings) < 3:
            return self._get_default_features()

        readings = readings.sort_values("timestamp").copy()
        readings["hour"] = pd.to_datetime(readings["timestamp"]).dt.hour

        # Scale flow from m³/h (DB) to the training distribution (L/min, ~300 L/min
        # midpoint).  Training data used DMA bulk flow in L/min (180–420 L/min);
        # live readings are individual-meter m³/h (50–70× smaller).  Without this
        # rescaling, absolute features (mnf, daily_variance, flow_variance) are far
        # outside the model's training range, producing a uniform ~0.92 probability.
        _M3H_TO_LMIN = 1000.0 / 60.0
        _TRAINING_BASELINE_LMIN = 300.0
        raw_flow = readings["flow_rate"].astype(float)
        _meter_mean_lmin = float(raw_flow.mean()) * _M3H_TO_LMIN
        if _meter_mean_lmin > 0.1:
            _scale = _TRAINING_BASELINE_LMIN / _meter_mean_lmin
        else:
            _scale = _M3H_TO_LMIN
        flow = raw_flow * (_M3H_TO_LMIN * _scale)
        pressure = readings["pressure"].astype(float)

        # ── Night-window features (full 24h) ─────────────────────────────────
        # These are the primary leak indicators and need the full diurnal cycle.
        night_mask = readings["hour"].between(0, 6)
        day_mask = ~night_mask
        if night_mask.any():
            mnf = float(flow[night_mask].min())
            night_mean = float(flow[night_mask].mean())
        else:
            mnf = float(flow.min())
            night_mean = float(flow.mean())

        if night_mask.any() and day_mask.any():
            day_avg = float(flow[day_mask].mean())
            night_flow_ratio = night_mean / day_avg if day_avg > 0 else 0.0
        else:
            night_flow_ratio = 0.0

        # ── Recent-window features (last 2h) ──────────────────────────────────
        # Computing trend, variance, pressure drop, and pressure-flow correlation
        # over the full 24h window conflates normal diurnal swings (night 0.3× →
        # peak 1.5×) with actual leak anomalies.  The diurnal anti-correlation
        # (morning: flow ↑, pressure ↓) also makes every meter look suspicious
        # when correlation is computed over the full day.  Restricting to the last
        # 2 hours removes both confounders while still capturing sudden anomalies.
        cutoff = pd.to_datetime(readings["timestamp"]).max() - pd.Timedelta(hours=2)
        recent_mask_2h = pd.to_datetime(readings["timestamp"]) >= cutoff
        recent = readings[recent_mask_2h]
        if len(recent) < 5:
            recent = readings.tail(20)

        flow_r = recent["flow_rate"].astype(float) * (_M3H_TO_LMIN * _scale)
        pres_r = recent["pressure"].astype(float)

        flow_var = float(flow_r.var()) if len(flow_r) > 1 else 0.0
        daily_var = float(flow_r.max() - flow_r.min()) if len(flow_r) > 1 else 0.0
        pressure_flow_corr = self._safe_correlation(flow_r, pres_r)

        pressure_sustained_drop = 0.0
        if len(pres_r) > 10:
            recent_pressure = float(pres_r.iloc[-10:].mean())
            early_pressure = float(pres_r.iloc[:10].mean())
            if early_pressure > 0:
                pressure_sustained_drop = (early_pressure - recent_pressure) / early_pressure

        if len(flow_r) >= 5:
            x = np.arange(len(flow_r))
            flow_trend = float(np.polyfit(x, flow_r, 1)[0])
        else:
            flow_trend = 0.0

        # ── Diurnal correction for night-based features ───────────────────────
        # The simulator uses a 0.3× night multiplier (night = 30% of day demand).
        # Training data (WNTR/EPANET Hanoi) has FLAT demand — no diurnal — so
        # training non-leaks have night_flow_ratio ≈ 1.0 and mnf ≈ mean_flow.
        # Dividing by the known night multiplier removes the diurnal component and
        # maps normal diurnal meters back to the training non-leak distribution:
        #   night_flow_ratio  0.30 → 1.0  (training non-leak ≈ 1.0)
        #   mnf               90  → 300 L/min  (training non-leak ≈ 300)
        # A meter with an actual night leak will have night_flow_ratio > 0.30
        # (e.g. 0.40 → corrected 1.33) which correctly signals elevation above
        # normal, matching the training leak distribution (ratio > 1.0).
        _NIGHT_MULT = 0.3
        mnf              = mnf              / _NIGHT_MULT if _NIGHT_MULT > 0 else mnf
        night_flow_ratio = night_flow_ratio / _NIGHT_MULT if _NIGHT_MULT > 0 else night_flow_ratio

        return {
            "mnf": mnf,
            "night_flow_ratio": night_flow_ratio,
            "flow_variance": flow_var if not np.isnan(flow_var) else 0.0,
            "daily_variance": daily_var,
            "pressure_flow_correlation": pressure_flow_corr,
            "pressure_drop_pattern": pressure_sustained_drop,
            "flow_trend": flow_trend,
        }

    # Minimum number of readings required before we'll trust a prediction.
    # Below this threshold, features are too sparse and the model returns a
    # spurious constant output (observed: 0.61 for all-zero feature vectors).
    MIN_READINGS = 10

    def extract_features(self, meter_id: str) -> Optional[Dict[str, float]]:
        """Extract features from a short recent window to avoid historical leak contamination.

        Uses 2 hours so that completed simulator leak scenarios (typically 30–120 min)
        fall outside the window and no longer inflate every meter's features.
        Falls back to 1 h if 2 h returns too few readings.
        """
        from backend.mysql_database_manager import db_manager

        readings = db_manager.get_sensor_readings(meter_id=meter_id, hours=2)
        if readings.empty or len(readings) < self.MIN_READINGS:
            readings = db_manager.get_sensor_readings(meter_id=meter_id, hours=1)
        if readings.empty or len(readings) < self.MIN_READINGS:
            return None

        readings = readings.sort_values("timestamp").copy()
        return self._extract_live_features(readings)

    def _safe_correlation(self, series1: pd.Series, series2: pd.Series) -> float:
        """Calculate correlation safely, handling zero-variance cases."""
        if len(series1) < 3 or len(series2) < 3:
            return 0.0
        
        # Check for zero variance (constant values)
        if series1.std() == 0 or series2.std() == 0:
            return 0.0
        
        # Suppress numpy warnings for correlation calculation
        with warnings.catch_warnings():
            warnings.filterwarnings('ignore', category=RuntimeWarning)
            corr = float(series1.corr(series2))
            return 0.0 if np.isnan(corr) else corr

    def _get_default_features(self) -> Dict[str, float]:
        """Return defaults when data is sparse."""
        return {
            "mnf": 0.0,
            "night_flow_ratio": 0.0,
            "flow_variance": 0.0,
            "daily_variance": 0.0,
            "pressure_flow_correlation": 0.0,
            "pressure_drop_pattern": 0.0,
            "flow_trend": 0.0,
        }


realtime_feature_extractor = RealtimeFeatureExtractor()
