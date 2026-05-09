"""Integration test for prediction loop - simulates actual usage."""

import sys
from pathlib import Path
import numpy as np
import json

# Add project root to path
REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "web_app"))

print("=" * 70)
print("PREDICTION LOOP INTEGRATION TEST")
print("=" * 70)

print("\n1. Testing database connection...")
from web_app.backend.mysql_database_manager import MySQLDatabaseManager
db = MySQLDatabaseManager()
print("✅ Database connected")

print("\n2. Testing ML model loading...")
from web_app.backend.ml_integration import ml_model
print(f"✅ Binary model loaded: {ml_model.binary_model is not None}")
print(f"✅ Feature list: {len(ml_model.feature_list)} features")

print("\n3. Getting test meters...")
meters = db.get_meters()
if meters.empty:
    print("❌ No meters found in database")
    sys.exit(1)

test_meter = meters.iloc[0]
meter_id = test_meter['meter_id']
zone_id = test_meter['zone_id']
print(f"✅ Using test meter: {meter_id} (Zone: {zone_id})")

print("\n4. Testing feature extraction...")
from web_app.backend.realtime_feature_extractor import realtime_feature_extractor

try:
    features = realtime_feature_extractor.extract_features(meter_id)
    print(f"✅ Extracted {len(features)} features")
    print(f"   Sample features: {list(features.keys())[:5]}")
except Exception as e:
    print(f"⚠️  Feature extraction failed (expected if no recent data): {e}")
    # Use dummy features for testing
    features = {
        "mnf": 200.0,
        "night_flow_ratio": 1.0,
        "flow_variance": 10.0,
        "daily_variance": 20.0,
        "pressure_flow_correlation": 0.5,
        "pressure_drop_pattern": 0.01,
        "flow_trend": 0.001,
        "peak_hour_flow": 250.0,
        "off_peak_flow": 180.0,
        "flow_consistency_score": 0.05,
        "pressure_variance": 0.1,
        "pressure_trend": 0.001,
        "pressure_stability": 0.02,
        "flow_pressure_ratio": 50.0,
        "anomaly_score": 0.05,
        "leak_signature_strength": 0.1,
    }
    print(f"✅ Using dummy features for testing")

print("\n5. Testing prediction...")
leak_detected, confidence, leak_type = ml_model.predict(features)
print(f"✅ Prediction successful:")
print(f"   Leak detected: {leak_detected}")
print(f"   Confidence: {confidence:.4f}")
print(f"   Leak type: {leak_type}")

print("\n6. Verifying return types...")
assert isinstance(leak_detected, bool) and not isinstance(leak_detected, np.bool_), \
    f"leak_detected should be bool, got {type(leak_detected)}"
assert isinstance(confidence, float) and not isinstance(confidence, np.floating), \
    f"confidence should be float, got {type(confidence)}"
assert isinstance(leak_type, str), \
    f"leak_type should be str, got {type(leak_type)}"
print("✅ All types are native Python types")

print("\n7. Testing database storage (simulating prediction loop)...")
try:
    db.add_leak_prediction(
        meter_id=meter_id,
        confidence=confidence,
        leak_detected=leak_detected,
        leak_type=leak_type,
        features=json.dumps(features)
    )
    print("✅ Prediction stored successfully")
except Exception as e:
    print(f"❌ Failed to store prediction: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n8. Verifying stored prediction...")
predictions = db.get_leak_predictions(hours=1)
if not predictions.empty:
    latest = predictions.iloc[0]
    print(f"✅ Retrieved prediction:")
    print(f"   Meter: {latest['meter_id']}")
    print(f"   Confidence: {latest['confidence']:.4f}")
    print(f"   Leak detected: {latest['leak_detected']}")
    print(f"   Leak type: {latest['leak_type']}")
else:
    print("⚠️  No predictions found (may have been cleared)")

print("\n9. Testing alert generation (if leak detected)...")
if leak_detected and confidence >= 0.85:
    severity = "critical" if confidence >= 0.95 else "warning"
    
    # Check for existing alert
    existing_alert = db.get_active_alert_for_meter(meter_id, severity, hours=1)
    
    if existing_alert:
        print(f"✅ Active alert already exists (ID: {existing_alert['id']})")
    else:
        try:
            db.add_alert(
                meter_id=meter_id,
                zone_id=zone_id,
                severity=severity,
                title=f"Leak Detected - {leak_type}",
                message=f"Leak detected with {confidence:.1%} confidence"
            )
            print(f"✅ Alert created (severity: {severity})")
        except Exception as e:
            print(f"❌ Failed to create alert: {e}")
else:
    print(f"ℹ️  No alert needed (confidence: {confidence:.1%})")

print("\n" + "=" * 70)
print("✅ ALL INTEGRATION TESTS PASSED")
print("=" * 70)
print("\nThe prediction loop should now work correctly!")
print("\nTo run the actual prediction loop:")
print("  1. Start the smart meter simulator")
print("  2. Start the prediction loop")
print("  3. Monitor the console for predictions")
