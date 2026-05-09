"""Simplified real-time feature extractor that matches the 7-feature model."""
import pandas as pd
import numpy as np
from typing import Dict, Optional
from backend.database_manager import db_manager


class RealtimeFeatureExtractor:
    """Extract 7 core features for leak prediction matching the trained model."""

    def __init__(self):
        self.required_features = [
            "flow_rate",
            "pressure",
            "temperature",
            "night_flow",
            "pressure_drop",
            "flow_variance",
            "pressure_variance",
        ]

    def extract_features(self, meter_id: str) -> Optional[Dict[str, float]]:
        """Extract 7 core features for a meter."""
        readings = db_manager.get_recent_readings(meter_id, hours=24)
        if readings.empty or len(readings) < 3:
            return self._get_default_features()

        readings = readings.sort_values("timestamp")
        flow = readings["flow_rate"]
        pressure = readings["pressure"]
        temperature = readings["temperature"]

        # Calculate night flow (average flow during night hours 22:00-06:00)
        readings["hour"] = pd.to_datetime(readings["timestamp"]).dt.hour
        night_mask = (readings["hour"] >= 22) | (readings["hour"] <= 6)
        night_flow = readings.loc[night_mask, "flow_rate"].mean() if night_mask.any() else flow.mean()

        # Pressure drop (max - min over last few readings)
        pressure_drop = pressure.tail(6).max() - pressure.tail(6).min()

        # Calculate variances
        flow_variance = flow.tail(12).var() if len(flow) >= 12 else flow.var()
        pressure_variance = pressure.tail(12).var() if len(pressure) >= 12 else pressure.var()

        return {
            "flow_rate": float(flow.iloc[-1]),
            "pressure": float(pressure.iloc[-1]),
            "temperature": float(temperature.iloc[-1]),
            "night_flow": float(night_flow),
            "pressure_drop": float(pressure_drop),
            "flow_variance": float(flow_variance) if not np.isnan(flow_variance) else 0.0,
            "pressure_variance": float(pressure_variance) if not np.isnan(pressure_variance) else 0.0,
        }

    def _get_default_features(self) -> Dict[str, float]:
        """Return defaults when data is sparse."""
        return {
            "flow_rate": 0.0,
            "pressure": 0.0,
            "temperature": 20.0,
            "night_flow": 0.0,
            "pressure_drop": 0.0,
            "flow_variance": 0.0,
            "pressure_variance": 0.0,
        }


realtime_feature_extractor = RealtimeFeatureExtractor()
