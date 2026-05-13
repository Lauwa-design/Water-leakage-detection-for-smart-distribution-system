"""Prediction Loop - Continuously runs ML predictions on incoming sensor data"""
import signal
import time
import threading
import json
from datetime import datetime
import sys
import os
import warnings

# Suppress numpy correlation warnings for cleaner output
warnings.filterwarnings('ignore', message='invalid value encountered in divide')
warnings.filterwarnings('ignore', category=RuntimeWarning, module='numpy')

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.mysql_database_manager import db_manager
from backend.smart_meter_simulator import smart_meter_simulator
from backend.realtime_feature_extractor import realtime_feature_extractor
from backend.ml_integration import ml_model

class PredictionLoop:
    """Continuously checks meters for leaks and generates alerts"""

    def __init__(self, check_interval: int = 30, demo_mode: bool = True):
        self.check_interval = check_interval
        self.is_running = False
        self.thread = None
        self._stop_event = threading.Event()
        self._checked_meters = set()
        self.demo_mode = demo_mode

    def start(self):
        """Start the prediction loop"""
        if not self.is_running:
            self._stop_event.clear()
            self.is_running = True
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()
            print("[Prediction Loop] Started successfully")
        else:
            print("[Prediction Loop] Already running, skipping start")

    def stop(self):
        """Stop the prediction loop — returns immediately; thread exits within seconds."""
        self.is_running = False
        self._stop_event.set()      # wake the sleeping thread instantly
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=5)
        print("[Prediction Loop] Stopped")

    def _loop(self):
        """Main prediction loop"""
        print("[Prediction Loop] Thread started")
        while self.is_running and not self._stop_event.is_set():
            try:
                self._check_all_meters()
            except Exception as e:
                print(f"[Prediction Loop] Error in loop: {e}")
            # Interruptible sleep: wakes immediately when stop() is called
            self._stop_event.wait(timeout=self.check_interval)
        print("[Prediction Loop] Thread stopped")
    
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
                    # Extract features — returns None when readings are too sparse
                    features = realtime_feature_extractor.extract_features(meter_id)
                    if features is None:
                        # Not enough sensor data for this meter; skip
                        continue

                    # Degeneracy guard: if ALL variance/trend features are zero the
                    # readings are constant (simulator cold-start or DB replays with
                    # no noise).  The model returns a spurious 0.61 for such inputs —
                    # skip rather than flood the DB with false positives.
                    _var_total = (
                        abs(features.get("flow_variance", 0.0))
                        + abs(features.get("daily_variance", 0.0))
                        + abs(features.get("flow_trend", 0.0))
                    )
                    if _var_total < 1e-6:
                        continue

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
                        severity = "critical" if confidence >= 0.95 else "warning"

                        # Guard 1: one active alert per meter
                        existing_meter = db_manager.get_active_alert_for_meter(meter_id)
                        if existing_meter:
                            continue

                        # Guard 2: zone correlation — if another meter in the same zone
                        # was flagged within the last 15 minutes, treat it as the same
                        # hydraulic source and suppress the duplicate alert.
                        recent_zone = db_manager.get_recent_zone_alert(zone_id, within_minutes=15)
                        if recent_zone:
                            print(
                                f"[Prediction Loop] Suppressed duplicate: {meter_id} in zone {zone_id} "
                                f"— same source as alert {recent_zone['id']} on meter {recent_zone['meter_id']}"
                            )
                            continue

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

# Always use real ML predictions — demo mode is permanently disabled
prediction_loop = PredictionLoop(check_interval=30, demo_mode=False)

def start_prediction_loop():
    """Start the prediction loop"""
    prediction_loop.start()

def stop_prediction_loop():
    """Stop the prediction loop"""
    prediction_loop.stop()

if __name__ == "__main__":
    print("Starting prediction loop in standalone mode...")
    print("Press Ctrl+C to stop.\n")

    # Explicit SIGINT handler — required for reliable Ctrl+C on Windows when
    # the main thread is sleeping inside a multi-threaded process.
    _shutdown = threading.Event()

    def _handle_sigint(sig, frame):
        print("\n[Prediction Loop] Ctrl+C received — shutting down...")
        _shutdown.set()

    signal.signal(signal.SIGINT, _handle_sigint)

    start_prediction_loop()

    # Wait until Ctrl+C or the loop stops on its own
    while not _shutdown.is_set() and prediction_loop.is_running:
        time.sleep(0.2)

    print("\nStopping prediction loop...")
    stop_prediction_loop()
