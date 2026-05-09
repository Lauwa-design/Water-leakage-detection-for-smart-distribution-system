"""Real-time feature extractor for hydraulic leak detection."""
from typing import Dict
import pandas as pd
import numpy as np


class RealtimeFeatureExtractor:
    """Extract 7 hydraulic features matching the documented design."""

    def extract_features(self, meter_id: str) -> Dict[str, float]:
        """Extract 7 hydraulic features for leak prediction."""
        from backend.mysql_database_manager import db_manager

        readings = db_manager.get_sensor_readings(meter_id=meter_id, hours=24)
        if readings.empty or len(readings) < 3:
            return self._get_default_features()

        readings = readings.sort_values("timestamp").copy()
        readings["hour"] = pd.to_datetime(readings["timestamp"]).dt.hour
        flow = readings["flow_rate"].astype(float)
        pressure = readings["pressure"].astype(float)

        # Feature 1: Minimum Night Flow (MNF) - lowest flow during 0-6h
        night_mask = readings["hour"].between(0, 6)
        if night_mask.any():
            mnf = float(flow[night_mask].min())
        else:
            mnf = float(flow.min())

        # Feature 2: Night-Flow Ratio - night flow / day flow
        day_mask = ~night_mask
        if night_mask.any() and day_mask.any():
            night_avg = float(flow[night_mask].mean())
            day_avg = float(flow[day_mask].mean())
            night_flow_ratio = night_avg / day_avg if day_avg > 0 else 0.0
        else:
            night_flow_ratio = 0.0

        # Feature 3: Flow Variance - statistical variability
        flow_var = float(flow.var()) if len(flow) > 1 else 0.0

        # Feature 4: Daily Variance - 24h fluctuation measure
        daily_var = float(flow.max() - flow.min()) if len(flow) > 1 else 0.0

        # Feature 5: Pressure-Flow Relationship - correlation coefficient
        if len(flow) > 2 and len(pressure) > 2:
            pressure_flow_corr = float(flow.corr(pressure))
            if np.isnan(pressure_flow_corr):
                pressure_flow_corr = 0.0
        else:
            pressure_flow_corr = 0.0

        # Feature 6: Pressure-Drop Pattern - sustained pressure loss
        pressure_drop = float(pressure.max() - pressure.min())
        # Detect if pressure drop is sustained (not just transient)
        pressure_sustained_drop = 0.0
        if len(pressure) > 10:
            recent_pressure = float(pressure.iloc[-10:].mean())
            early_pressure = float(pressure.iloc[:10].mean())
            if early_pressure > 0:
                pressure_sustained_drop = (early_pressure - recent_pressure) / early_pressure

        # Feature 7: Flow Trend - directional indicator
        if len(flow) >= 5:
            # Linear regression slope
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
