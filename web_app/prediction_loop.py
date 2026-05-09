"""Prediction Loop - Continuously runs ML predictions on incoming sensor data"""
import time
import threading
import json
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.database_manager import db_manager
from backend.smart_meter_simulator import smart_meter_simulator
from backend.realtime_feature_extractor import realtime_feature_extractor
from backend.ml_integration import ml_model

class PredictionLoop:
    """Continuously checks meters for leaks and generates alerts"""
    
    def __init__(self, check_interval: int = 30, demo_mode: bool = True):
        self.check_interval = check_interval
        self.is_running = False
        self.thread = None
        self._checked_meters = set()
        self.demo_mode = demo_mode  # Artificially create leaks for demo
    
    def start(self):
        """Start the prediction loop"""
        if not self.is_running:
            self.is_running = True
            self.thread = threading.Thread(target=self._loop)
            self.thread.daemon = True
            self.thread.start()
            print("[Prediction Loop] Started successfully")
        else:
            print("[Prediction Loop] Already running, skipping start")
    
    def stop(self):
        """Stop the prediction loop"""
        self.is_running = False
        if self.thread:
            self.thread.join(timeout=1)
        print("Prediction loop stopped")
    
    def _loop(self):
        """Main prediction loop"""
        print("[Prediction Loop] _loop thread started")
        while self.is_running:
            try:
                print(f"[Prediction Loop] Running check cycle (is_running={self.is_running})")
                self._check_all_meters()
                print(f"[Prediction Loop] Sleeping for {self.check_interval} seconds...")
                time.sleep(self.check_interval)
            except Exception as e:
                print(f"[Prediction Loop] Error in loop: {e}")
                time.sleep(self.check_interval)
        print("[Prediction Loop] _loop thread stopped")
    
    def _check_all_meters(self):
        """Check all meters for leaks"""
        try:
            # Get all meters
            meters = db_manager.get_meters()
            print(f"[Prediction Loop] Checking {len(meters)} meters for leaks...")
            
            for _, meter in meters.iterrows():
                meter_id = meter['meter_id']
                zone_id = meter['zone_id']
                
                try:
                    # Extract features
                    features = realtime_feature_extractor.extract_features(meter_id)
                    
                    # Make prediction
                    leak_detected, confidence, leak_type = ml_model.predict(features)
                    
                    # Demo mode: artificially create some leaks for demonstration
                    if self.demo_mode and not leak_detected:
                        import random
                        # 2% chance of simulated leak in demo mode (reduced from 10%)
                        if random.random() < 0.02:
                            leak_detected = True
                            confidence = random.uniform(0.75, 0.95)
                            leak_type = random.choice(['slow_creep', 'moderate_burst'])
                            print(f"[Prediction Loop] Demo mode: Simulated leak for {meter_id}")
                    
                    # Store prediction
                    db_manager.add_leak_prediction(
                        meter_id=meter_id,
                        confidence=confidence,
                        leak_detected=leak_detected,
                        leak_type=leak_type,
                        features=json.dumps(features)
                    )
                    print(f"[Prediction Loop] Saved prediction for {meter_id}: leak={leak_detected}, conf={confidence:.2f}")
                    
                    # Create alert if leak detected with high confidence (≥85% for warning, ≥95% for critical)
                    if leak_detected and confidence >= 0.85:
                        # Check if we already have an active alert for this meter
                        recent_alerts = db_manager.get_alerts(
                            status='new', hours=1
                        )
                        existing = recent_alerts[
                            recent_alerts['meter_id'] == meter_id
                        ] if len(recent_alerts) > 0 else None
                        
                        if existing is None or len(existing) == 0:
                            # Create new alert
                            severity = "critical" if confidence >= 0.95 else "warning"
                            title = f"Leak Detected - {leak_type}"
                            message = f"Confidence: {confidence:.1%}. Potential leak detected on meter {meter_id}."
                            
                            db_manager.add_alert(
                                meter_id=meter_id,
                                zone_id=zone_id,
                                severity=severity,
                                title=title,
                                message=message
                            )
                            print(f"[Prediction Loop] Alert created: {meter_id} - {leak_type} ({confidence:.1%})")
                    
                except Exception as e:
                    print(f"[Prediction Loop] Error processing meter {meter_id}: {e}")
        except Exception as e:
            print(f"[Prediction Loop] Error in _check_all_meters: {e}")

# Global instance
prediction_loop = PredictionLoop(check_interval=30)

def start_prediction_loop():
    """Start the prediction loop"""
    prediction_loop.start()

def stop_prediction_loop():
    """Stop the prediction loop"""
    prediction_loop.stop()

if __name__ == "__main__":
    # Standalone mode
    print("Starting prediction loop...")
    start_prediction_loop()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\nStopping prediction loop...")
        stop_prediction_loop()
