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

    DAILY_LEAK_CAP = 20  # max leak=True predictions saved per calendar day

    def __init__(self, check_interval: int = 30, demo_mode: bool = True):
        self.check_interval = check_interval
        self.is_running = False
        self.thread = None
        self._stop_event = threading.Event()
        self._checked_meters = set()
        self.demo_mode = demo_mode
        # last saved prediction per meter: {meter_id: (leak_detected, confidence, saved_at)}
        self._last_saved: dict[str, tuple[bool, float, float]] = {}
        # consecutive positive-prediction count per meter; resets to 0 on False
        self._positive_streak: dict[str, int] = {}
        # daily leak counter — resets when the calendar date changes
        self._daily_leak_date: str = ""
        self._daily_leak_count: int = 0

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
            meters = db_manager.get_meters()
            print(f"[Prediction Loop] Checking {len(meters)} meters for leaks...")

            # ── Daily cap — reset counter on new calendar day ─────────────────
            _today = datetime.now().strftime("%Y-%m-%d")
            if self._daily_leak_date != _today:
                self._daily_leak_date = _today
                self._daily_leak_count = 0

            # ── Pass 1: collect raw predictions ───────────────────────────────
            raw_predictions = []  # (meter_id, zone_id, confidence, leak_type, features)
            _now = time.time()

            for _, meter in meters.iterrows():
                meter_id = meter['meter_id']
                zone_id  = meter['zone_id']
                try:
                    features = realtime_feature_extractor.extract_features(meter_id)
                    if features is None:
                        continue

                    _var_total = (
                        abs(features.get("flow_variance", 0.0))
                        + abs(features.get("daily_variance", 0.0))
                        + abs(features.get("flow_trend", 0.0))
                    )
                    if _var_total < 1e-6:
                        continue

                    leak_detected, confidence, leak_type = ml_model.predict(features)
                    raw_predictions.append((meter_id, zone_id, confidence, leak_type, features, leak_detected))

                except Exception as e:
                    print(f"[Prediction Loop] Error processing meter {meter_id}: {e}")

            if not raw_predictions:
                return

            # ── Absolute threshold — fixed confidence floor for a true-leak save ──
            # The previous relative threshold (mean + std across the batch) caused
            # rapid True→False→True oscillation: a single positive meter always
            # fell just below its own mean+margin, so it was demoted to False every
            # other batch.  An absolute floor is predictable and batch-independent.
            SAVE_THRESHOLD = 0.92   # minimum confidence to save as leak=True
            # A meter must produce CONFIRM_COUNT consecutive positive predictions
            # (each ≥ SAVE_THRESHOLD) before its state is promoted to True.  This
            # prevents a single-batch spike from permanently flipping the status.
            CONFIRM_COUNT = 2

            # ── Pass 2: save predictions + create alerts ──────────────────────
            candidates = []
            for meter_id, zone_id, confidence, leak_type, features, leak_detected in raw_predictions:
                # Apply absolute threshold
                if leak_detected and confidence < SAVE_THRESHOLD:
                    leak_detected = False
                    leak_type     = "none"

                # Update consecutive-positive streak
                if leak_detected:
                    self._positive_streak[meter_id] = self._positive_streak.get(meter_id, 0) + 1
                else:
                    self._positive_streak[meter_id] = 0

                # Require confirmation: must be positive for CONFIRM_COUNT batches in a row
                confirmed_leak = leak_detected and self._positive_streak.get(meter_id, 0) >= CONFIRM_COUNT

                # Daily cap — after 20 true leaks today, save remainder as False
                if confirmed_leak and self._daily_leak_count >= self.DAILY_LEAK_CAP:
                    confirmed_leak = False
                    confidence     = 0.0
                    leak_type      = "none"

                # State-change guard — skip DB write if status unchanged
                _prev = self._last_saved.get(meter_id)
                if _prev is not None and _prev[0] == confirmed_leak:
                    if confirmed_leak:
                        candidates.append((meter_id, zone_id, confidence, leak_type))
                    continue

                db_manager.add_leak_prediction(
                    meter_id=meter_id,
                    confidence=confidence,
                    leak_detected=confirmed_leak,
                    leak_type=leak_type,
                    features=json.dumps(features)
                )
                self._last_saved[meter_id] = (confirmed_leak, confidence, _now)
                if confirmed_leak:
                    self._daily_leak_count += 1
                    candidates.append((meter_id, zone_id, confidence, leak_type))
                print(f"[Prediction Loop] Saved prediction for {meter_id}: leak={confirmed_leak}, conf={confidence:.2f}")

            if not candidates:
                return

            for meter_id, zone_id, confidence, leak_type in sorted(candidates, key=lambda x: -x[2]):
                if confidence < SAVE_THRESHOLD:
                    break  # sorted descending — nothing below this will qualify

                existing_meter = db_manager.get_active_alert_for_meter(meter_id)
                if existing_meter:
                    continue

                recent_zone = db_manager.get_recent_zone_alert(zone_id, within_minutes=15)
                if recent_zone:
                    print(
                        f"[Prediction Loop] Suppressed duplicate: {meter_id} in zone {zone_id} "
                        f"— same source as alert {recent_zone['id']} on meter {recent_zone['meter_id']}"
                    )
                    continue

                severity = "critical" if confidence >= 0.95 else "warning"
                title   = f"Leak Detected - {leak_type}"
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
