"""
THIWASCO Leak Detection Backend
Single source of truth for leak detection logic
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import joblib
import os
from dataclasses import dataclass
from enum import Enum

class LeakSeverity(Enum):
    NONE = "none"
    SLOW = "slow"
    MODERATE = "moderate"
    INSTANT = "instant"

@dataclass
class LeakPrediction:
    """Standard data contract for leak predictions"""
    meter_id: str
    timestamp: datetime
    leak_detected: bool
    severity: LeakSeverity
    confidence: float
    pressure: float
    flow_rate: float
    pressure_delta: float
    flow_delta: float
    features_used: Dict[str, float]
    recommendation: str
    model_version: str = "1.0"

class LeakDetector:
    """Centralized leak detection system - single source of truth"""
    
    def __init__(self):
        self.model = None
        self.model_path = None
        self.load_model()
    
    def load_model(self):
        """Load trained ML model"""
        try:
            # Try to find the trained model - check actual model locations
            model_paths = [
                "../../outputs/models/random_forest_binary.pkl",
                "../outputs/models/random_forest_binary.pkl", 
                "outputs/models/random_forest_binary.pkl",
                "models/leak_detection_model.pkl",
                "../models/leak_detection_model.pkl",
                "../../models/leak_detection_model.pkl"
            ]
            
            for path in model_paths:
                if os.path.exists(path):
                    self.model = joblib.load(path)
                    self.model_path = path
                    print(f"Model loaded from: {path}")
                    break
            
            if self.model is None:
                print("Warning: No trained model found. Using fallback logic.")
                
        except Exception as e:
            print(f"Error loading model: {e}")
            self.model = None
    
    def extract_features(self, meter_data: pd.DataFrame) -> Dict[str, float]:
        """Extract features from meter data for ML prediction"""
        if len(meter_data) < 2:
            return {}
        
        # Calculate temporal features
        recent = meter_data.tail(10)  # Last 10 readings
        older = meter_data.tail(20).head(10)  # Previous 10 readings
        
        features = {}
        
        # Current values
        features['pressure_current'] = meter_data['pressure'].iloc[-1]
        features['flow_current'] = meter_data['flow_rate'].iloc[-1]
        
        # Delta features
        if len(recent) >= 2 and len(older) >= 2:
            features['pressure_delta'] = recent['pressure'].mean() - older['pressure'].mean()
            features['flow_delta'] = recent['flow_rate'].mean() - older['flow_rate'].mean()
        else:
            features['pressure_delta'] = 0
            features['flow_delta'] = 0
        
        # Statistical features
        features['pressure_std'] = recent['pressure'].std()
        features['flow_std'] = recent['flow_rate'].std()
        features['pressure_trend'] = self._calculate_trend(recent['pressure'])
        features['flow_trend'] = self._calculate_trend(recent['flow_rate'])
        
        # Ratio features
        if features['flow_current'] > 0:
            features['pressure_flow_ratio'] = features['pressure_current'] / features['flow_current']
        else:
            features['pressure_flow_ratio'] = 0
        
        # Anomaly features
        features['pressure_anomaly'] = self._detect_anomaly(recent['pressure'])
        features['flow_anomaly'] = self._detect_anomaly(recent['flow_rate'])
        
        return features
    
    def _calculate_trend(self, series: pd.Series) -> float:
        """Calculate linear trend coefficient"""
        if len(series) < 2:
            return 0.0
        
        x = np.arange(len(series))
        y = series.values
        
        # Simple linear regression slope
        n = len(x)
        if n == 0:
            return 0.0
            
        slope = (n * np.sum(x * y) - np.sum(x) * np.sum(y)) / (n * np.sum(x**2) - (np.sum(x))**2)
        return slope
    
    def _detect_anomaly(self, series: pd.Series) -> float:
        """Detect anomaly score based on deviation from mean"""
        if len(series) < 3:
            return 0.0
        
        mean_val = series.mean()
        std_val = series.std()
        
        if std_val == 0:
            return 0.0
        
        # Z-score of last value
        last_val = series.iloc[-1]
        z_score = abs(last_val - mean_val) / std_val
        
        return min(z_score, 5.0)  # Cap at 5 to avoid extreme values
    
    def predict_leak(self, features: Dict[str, float]) -> LeakPrediction:
        """
        Core prediction interface - single source of truth
        This is the ONLY place leak detection logic should exist
        """
        # Default values
        meter_id = features.get('meter_id', 'UNKNOWN')
        timestamp = datetime.now()
        pressure = features.get('pressure_current', 0)
        flow_rate = features.get('flow_current', 0)
        pressure_delta = features.get('pressure_delta', 0)
        flow_delta = features.get('flow_delta', 0)
        
        # Use ML model if available
        if self.model is not None:
            return self._predict_with_model(features, meter_id, timestamp, pressure, flow_rate, pressure_delta, flow_delta)
        else:
            return self._predict_with_rules(features, meter_id, timestamp, pressure, flow_rate, pressure_delta, flow_delta)
    
    def _predict_with_model(self, features: Dict[str, float], meter_id: str, timestamp: datetime, 
                          pressure: float, flow_rate: float, pressure_delta: float, flow_delta: float) -> LeakPrediction:
        """Use trained ML model for prediction"""
        try:
            # Prepare features for model (ensure all required features exist)
            feature_names = ['pressure_current', 'flow_current', 'pressure_delta', 'flow_delta', 
                            'pressure_std', 'flow_std', 'pressure_trend', 'flow_trend',
                            'pressure_flow_ratio', 'pressure_anomaly', 'flow_anomaly']
            
            model_features = []
            for name in feature_names:
                model_features.append(features.get(name, 0))
            
            # Make prediction
            prediction_proba = self.model.predict_proba([model_features])[0]
            prediction = self.model.predict([model_features])[0]
            
            leak_detected = bool(prediction)
            confidence = float(prediction_proba[1]) if leak_detected else float(prediction_proba[0])
            
            # Determine severity based on probability and features
            severity = self._determine_severity(leak_detected, confidence, pressure_delta, flow_delta)
            
            # Generate recommendation
            recommendation = self._generate_recommendation(severity, confidence, pressure, flow_rate)
            
            return LeakPrediction(
                meter_id=meter_id,
                timestamp=timestamp,
                leak_detected=leak_detected,
                severity=severity,
                confidence=confidence,
                pressure=pressure,
                flow_rate=flow_rate,
                pressure_delta=pressure_delta,
                flow_delta=flow_delta,
                features_used=features,
                recommendation=recommendation,
                model_version="ML_v1.0"
            )
            
        except Exception as e:
            print(f"Model prediction failed: {e}")
            # Fallback to rules
            return self._predict_with_rules(features, meter_id, timestamp, pressure, flow_rate, pressure_delta, flow_delta)
    
    def _predict_with_rules(self, features: Dict[str, float], meter_id: str, timestamp: datetime,
                          pressure: float, flow_rate: float, pressure_delta: float, flow_delta: float) -> LeakPrediction:
        """Fallback rule-based prediction when model is not available"""
        
        # Rule-based leak detection (only used when ML model fails)
        leak_detected = False
        severity = LeakSeverity.NONE
        confidence = 0.5
        
        # Pressure drop rules
        if pressure_delta < -1.5:
            leak_detected = True
            confidence = 0.8
            severity = LeakSeverity.INSTANT if pressure_delta < -3.0 else LeakSeverity.MODERATE
        elif pressure_delta < -0.8:
            leak_detected = True
            confidence = 0.6
            severity = LeakSeverity.SLOW
        
        # Flow rate increase rules (leak causes flow increase)
        if flow_delta > 15:
            leak_detected = True
            confidence = max(confidence, 0.7)
            severity = LeakSeverity.MODERATE if flow_delta > 25 else LeakSeverity.SLOW
        elif flow_delta > 8:
            leak_detected = True
            confidence = max(confidence, 0.5)
            severity = LeakSeverity.SLOW
        
        # Anomaly rules
        pressure_anomaly = features.get('pressure_anomaly', 0)
        flow_anomaly = features.get('flow_anomaly', 0)
        
        if pressure_anomaly > 3.0 or flow_anomaly > 3.0:
            leak_detected = True
            confidence = max(confidence, 0.6)
            if severity == LeakSeverity.NONE:
                severity = LeakSeverity.SLOW
        
        # Generate recommendation
        recommendation = self._generate_recommendation(severity, confidence, pressure, flow_rate)
        
        return LeakPrediction(
            meter_id=meter_id,
            timestamp=timestamp,
            leak_detected=leak_detected,
            severity=severity,
            confidence=confidence,
            pressure=pressure,
            flow_rate=flow_rate,
            pressure_delta=pressure_delta,
            flow_delta=flow_delta,
            features_used=features,
            recommendation=recommendation,
            model_version="RULES_v1.0"
        )
    
    def _determine_severity(self, leak_detected: bool, confidence: float, pressure_delta: float, flow_delta: float) -> LeakSeverity:
        """Determine leak severity based on prediction and features"""
        if not leak_detected:
            return LeakSeverity.NONE
        
        # High confidence + large deltas = instant
        if confidence > 0.8 and (pressure_delta < -2.5 or flow_delta > 20):
            return LeakSeverity.INSTANT
        
        # Medium confidence or moderate deltas = moderate
        if confidence > 0.6 or (pressure_delta < -1.0 or flow_delta > 10):
            return LeakSeverity.MODERATE
        
        # Low confidence or small deltas = slow
        return LeakSeverity.SLOW
    
    def _generate_recommendation(self, severity: LeakSeverity, confidence: float, pressure: float, flow_rate: float) -> str:
        """Generate actionable recommendations based on prediction"""
        if severity == LeakSeverity.NONE:
            return "No action needed - System operating normally"
        
        if severity == LeakSeverity.INSTANT:
            return "IMMEDIATE ACTION REQUIRED: Critical leak detected - Dispatch emergency repair team immediately"
        
        if severity == LeakSeverity.MODERATE:
            if confidence > 0.8:
                return "Schedule urgent inspection within 24 hours - Moderate leak confirmed"
            else:
                return "Schedule inspection within 48 hours - Possible moderate leak"
        
        if severity == LeakSeverity.SLOW:
            if confidence > 0.7:
                return "Monitor closely and schedule routine inspection - Minor leak detected"
            else:
                return "Continue monitoring - Anomaly detected but not confirmed"
        
        return "Further investigation required"

# Global instance - single source of truth
leak_detector = LeakDetector()

# Public API - this is the ONLY interface for leak detection
def predict_leak(meter_data: pd.DataFrame, meter_id: str = "UNKNOWN") -> LeakPrediction:
    """
    Public API for leak prediction
    
    Args:
        meter_data: DataFrame with columns ['timestamp', 'pressure', 'flow_rate']
        meter_id: Unique identifier for the meter
    
    Returns:
        LeakPrediction: Standardized prediction result
    """
    features = leak_detector.extract_features(meter_data)
    features['meter_id'] = meter_id
    
    return leak_detector.predict_leak(features)

def batch_predict(meter_data_dict: Dict[str, pd.DataFrame]) -> List[LeakPrediction]:
    """
    Batch prediction for multiple meters
    
    Args:
        meter_data_dict: Dictionary of meter_id -> DataFrame
    
    Returns:
        List[LeakPrediction]: Predictions for all meters
    """
    predictions = []
    
    for meter_id, data in meter_data_dict.items():
        if len(data) > 0:
            prediction = predict_leak(data, meter_id)
            predictions.append(prediction)
    
    return predictions
