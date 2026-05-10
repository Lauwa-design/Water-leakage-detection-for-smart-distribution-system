"""Real-time feature extractor for hydraulic leak detection."""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Dict

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
        flow = readings["flow_rate"].astype(float)
        pressure = readings["pressure"].astype(float)

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

        flow_var = float(flow.var()) if len(flow) > 1 else 0.0
        daily_var = float(flow.max() - flow.min()) if len(flow) > 1 else 0.0
        pressure_flow_corr = self._safe_correlation(flow, pressure)

        pressure_sustained_drop = 0.0
        if len(pressure) > 10:
            recent_pressure = float(pressure.iloc[-10:].mean())
            early_pressure = float(pressure.iloc[:10].mean())
            if early_pressure > 0:
                pressure_sustained_drop = (early_pressure - recent_pressure) / early_pressure

        if len(flow) >= 5:
            x = np.arange(len(flow))
            flow_trend = float(np.polyfit(x, flow, 1)[0])
        else:
            flow_trend = 0.0

        return {
            "mnf": mnf,
            "night_flow_ratio": night_flow_ratio,
            "flow_variance": flow_var if not np.isnan(flow_var) else 0.0,
            "daily_variance": daily_var,
            "pressure_flow_correlation": pressure_flow_corr,
            "pressure_drop_pattern": pressure_sustained_drop,
            "flow_trend": flow_trend,
        }

    def extract_features(self, meter_id: str) -> Dict[str, float]:
        """Extract scenario-level features (binary + multiclass columns when possible)."""
        from backend.mysql_database_manager import db_manager

        readings = db_manager.get_sensor_readings(meter_id=meter_id, hours=24)
        if readings.empty or len(readings) < 3:
            return self._get_default_features()

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
