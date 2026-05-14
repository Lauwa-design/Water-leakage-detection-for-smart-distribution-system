"""ML Integration - load the existing trained artifacts and score live features."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, Optional, Tuple

import joblib
import numpy as np
import pandas as pd


MODEL_DIR = Path(__file__).resolve().parents[2] / "outputs" / "models"
DEFAULT_FEATURES = [
    "mnf",
    "night_flow_ratio",
    "flow_variance",
    "daily_variance",
    "pressure_flow_correlation",
    "pressure_drop_pattern",
    "flow_trend",
]


class LeakDetectionModel:
    """ML model wrapper for leak detection."""

    def __init__(self) -> None:
        self.binary_model = None
        self.multi_model = None
        # Binary / multiclass column order must match training ``feature_list.json``.
        self.binary_features: list[str] = DEFAULT_FEATURES.copy()
        self.multiclass_features: list[str] = DEFAULT_FEATURES.copy()
        self.feature_list: list[str] | None = None  # mirrors binary_features after load
        self.scaler = None
        self.leak_detection_threshold = 0.5
        self.binary_model_path = self._find_first_existing(
            "leak_binary.joblib",
            "leak_binary_model.joblib",
            "random_forest_binary.pkl",
        )
        self.multi_model_path = self._find_first_existing(
            "leak_multi.joblib",
            "leak_type_model.joblib",
            "random_forest_multi.pkl",
        )
        self.scaler_path = None
        self.features_path = self._find_first_existing("feature_list.json")
        self._load_models()

    def _find_first_existing(self, *names: str) -> Optional[Path]:
        for name in names:
            candidate = MODEL_DIR / name
            if candidate.exists():
                return candidate
        return None

    def _load_models(self) -> None:
        """Load the trained models and feature list from the existing artifacts."""
        try:
            if self.binary_model_path is not None:
                self.binary_model = joblib.load(self.binary_model_path)
                if hasattr(self.binary_model, "monotonic_cst"):
                    delattr(self.binary_model, "monotonic_cst")
                print(f"Binary model loaded from {self.binary_model_path}")

            if self.multi_model_path is not None:
                try:
                    self.multi_model = joblib.load(self.multi_model_path)
                    print(f"Multi-class model loaded from {self.multi_model_path}")
                except Exception as exc:
                    print(f"Warning: Could not load multi-class model: {exc}")

            if self.scaler_path is not None:
                try:
                    self.scaler = joblib.load(self.scaler_path)
                    print(f"Scaler loaded from {self.scaler_path}")
                except Exception as exc:
                    print(f"Warning: Could not load scaler: {exc}")

            if self.features_path is not None:
                try:
                    with open(self.features_path, "r", encoding="utf-8") as handle:
                        feature_data = json.load(handle)
                    legacy = feature_data.get("features")
                    bf = feature_data.get("binary_features")
                    mf = feature_data.get("multiclass_features")
                    if bf:
                        self.binary_features = list(bf)
                    if mf:
                        self.multiclass_features = list(mf)
                    elif legacy:
                        self.binary_features = list(legacy)
                        self.multiclass_features = list(legacy)
                    thr = feature_data.get("binary_probability_threshold")
                    if thr is not None:
                        self.leak_detection_threshold = float(thr)
                    self.feature_list = self.binary_features
                    print(
                        f"Feature manifest: binary n={len(self.binary_features)}, "
                        f"multiclass n={len(self.multiclass_features)}, "
                        f"threshold={self.leak_detection_threshold:.4f}"
                    )
                except Exception as exc:
                    print(f"Warning: Could not load feature list: {exc}")

            if not self.feature_list:
                self.feature_list = self.binary_features.copy()
        except Exception as exc:
            print(f"Error loading models: {exc}")
            self.binary_model = None
            self.multi_model = None
            self.binary_features = DEFAULT_FEATURES.copy()
            self.multiclass_features = DEFAULT_FEATURES.copy()
            self.feature_list = DEFAULT_FEATURES.copy()

    def predict(self, features: Dict[str, float]) -> Tuple[bool, float, str]:
        """
        Make leak prediction.
        Returns: (leak_detected, snce, leak_type)
        """
        if self.binary_model is None or self.feature_list is None:
            return False, 0.0, "None"

        try:
            bin_vals = [float(features.get(name, 0.0)) for name in self.binary_features]
            df_bin = pd.DataFrame([bin_vals], columns=self.binary_features)

            if self.scaler is not None:
                try:
                    arr = self.scaler.transform(df_bin)
                    df_bin = pd.DataFrame(arr, columns=self.binary_features)
                except Exception as exc:
                    print(f"Warning: could not scale features: {exc}")

            try:
                if hasattr(self.binary_model, "predict_proba"):
                    probabilities = self.binary_model.predict_proba(df_bin)[0]
                    leak_prob = probabilities[1] if len(probabilities) > 1 else probabilities[0]
                else:
                    leak_prob = float(self.binary_model.predict(df_bin)[0])
            except AttributeError as exc:
                if "monotonic_cst" in str(exc):
                    leak_prob = self._fallback_prediction(features)
                else:
                    raise

            leak_detected = leak_prob > self.leak_detection_threshold

            if leak_detected:
                # The multi-class model expects all 17 MULTICLASS_FEATURES. If
                # the feature dict only has the 7 legacy keys, the remaining 10
                # default to 0.0, which pushes every prediction into the same RF
                # leaves as "no data" — producing wrong classifications.  Guard:
                # only use the multi-class model when all required features are
                # present (i.e. the primary live_features path succeeded).
                _has_all_multi = all(name in features for name in self.multiclass_features)
                if self.multi_model is not None and hasattr(self.multi_model, "predict") and _has_all_multi:
                    try:
                        multi_vals = [
                            float(features.get(name, 0.0)) for name in self.multiclass_features
                        ]
                        df_multi = pd.DataFrame([multi_vals], columns=self.multiclass_features)
                        leak_type = str(self.multi_model.predict(df_multi)[0])
                    except Exception as exc:
                        print(f"Warning: multiclass predict failed ({exc}); using rule fallback.")
                        leak_type = self._classify_leak_type(leak_prob, features)
                else:
                    leak_type = self._classify_leak_type(leak_prob, features)
            else:
                leak_type = "None"

            # Convert to native Python types to avoid numpy type issues
            return bool(leak_detected), float(leak_prob), str(leak_type)
        except Exception as exc:
            print(f"Prediction error: {exc}")
            return False, 0.0, "None"

    def _classify_leak_type(self, leak_prob: float, features: Dict[str, float]) -> str:
        """Classify leak type based on probability and feature patterns."""
        pressure_drop = max(features.get("pressure_drop_pattern", 0.0), 0.0)
        daily_variance = features.get("daily_variance", 0.0)
        flow_variance = features.get("flow_variance", 0.0)
        flow_trend = features.get("flow_trend", 0.0)

        if leak_prob > 0.85 and (pressure_drop > 0.015 or daily_variance > 35):
            return "extreme_leak"
        if leak_prob > 0.72 and (flow_variance > 5 or abs(flow_trend) > 0.005):
            return "moderate_leak"
        return "slow_leak"

    def _fallback_prediction(self, features: Dict[str, float]) -> float:
        """Fallback leak score when model compatibility issues occur."""
        leak_score = 0.0

        night_ratio = features.get("night_flow_ratio", 0.5)
        if night_ratio > 1.05:
            leak_score += 0.2
        elif night_ratio > 0.98:
            leak_score += 0.08

        flow_variance = features.get("flow_variance", 0.0)
        if flow_variance > 30:
            leak_score += 0.2
        elif flow_variance > 15:
            leak_score += 0.1

        daily_variance = features.get("daily_variance", 0.0)
        if daily_variance > 35:
            leak_score += 0.18
        elif daily_variance > 20:
            leak_score += 0.08

        pressure_drop = max(features.get("pressure_drop_pattern", 0.0), 0.0)
        if pressure_drop > 0.015:
            leak_score += 0.2
        elif pressure_drop > 0.008:
            leak_score += 0.1

        leak_score += min(abs(features.get("flow_trend", 0.0)) * 10.0, 0.17)

        return min(leak_score, 0.95)

    def get_feature_importance(self) -> Optional[pd.DataFrame]:
        """Get feature importance from the binary model."""
        if self.binary_model is None:
            return None

        try:
            if hasattr(self.binary_model, "feature_importances_"):
                importance = self.binary_model.feature_importances_
            elif hasattr(self.binary_model, "coef_"):
                importance = np.abs(self.binary_model.coef_[0])
            else:
                return None

            names = self.binary_features
            if len(importance) != len(names):
                names = self.feature_list or names
            return pd.DataFrame(
                {"feature": names, "importance": importance}
            ).sort_values("importance", ascending=False)
        except Exception as exc:
            print(f"Error getting feature importance: {exc}")
            return None

    def predict_for_readings(self, readings_df) -> Dict:
        """Get prediction for a readings dataframe."""
        try:
            if readings_df.empty:
                return {
                    "leak_detected": False,
                    "leak_probability": 0.0,
                    "leak_type": "None",
                    "risk_factors": ["No recent data"],
                    "features_used": [],
                }

            features = self._extract_features(readings_df)
            leak_detected, confidence, leak_type = self.predict(features)

            risk_factors = []
            if features.get("night_flow_ratio", 0.0) > 1.0:
                risk_factors.append("High night flow")
            if features.get("pressure_drop_pattern", 0.0) > 0.01:
                risk_factors.append("Sustained pressure drop")
            if features.get("flow_variance", 0.0) > 20:
                risk_factors.append("High flow variability")
            if abs(features.get("flow_trend", 0.0)) > 0.02:
                risk_factors.append("Flow trend shift")
            if not risk_factors:
                risk_factors.append("Normal operation")

            return {
                "leak_detected": leak_detected,
                "leak_probability": confidence,
                "leak_type": leak_type,
                "risk_factors": risk_factors,
                "features_used": list(features.keys())[:6],
            }
        except Exception as exc:
            print(f"Error predicting from readings: {exc}")
            return {
                "leak_detected": False,
                "leak_probability": 0.0,
                "leak_type": "None",
                "risk_factors": [f"Error: {str(exc)[:50]}"],
                "features_used": [],
            }

    def predict_for_meter(self, meter_id: str) -> Dict:
        """Get prediction for a specific meter using recent readings."""
        from backend.mysql_database_manager import db_manager
        from backend.smart_meter_simulator import smart_meter_simulator

        try:
            readings = db_manager.get_sensor_readings(meter_id, hours=24)
            if readings.empty and smart_meter_simulator.is_running:
                readings = smart_meter_simulator.get_recent_readings(meter_id, n=120)
            return self.predict_for_readings(readings)
        except Exception as exc:
            print(f"Error predicting for meter {meter_id}: {exc}")
            return {
                "leak_detected": False,
                "leak_probability": 0.0,
                "leak_type": "None",
                "risk_factors": [f"Error: {str(exc)[:50]}"],
                "features_used": [],
            }

    def _extract_features(self, readings_df) -> Dict[str, float]:
        """Extract features using the live feature extractor."""
        from backend.realtime_feature_extractor import realtime_feature_extractor

        if readings_df.empty:
            return {}

        frame = readings_df.copy()
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
        frame = frame.dropna(subset=["timestamp"]).sort_values("timestamp").reset_index(drop=True)

        if frame.empty:
            return {}

        return realtime_feature_extractor._extract_live_features(frame)


ml_model = LeakDetectionModel()
