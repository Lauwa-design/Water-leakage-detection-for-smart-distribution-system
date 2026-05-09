"""Test script to verify prediction loop fixes."""

import sys
from pathlib import Path
import numpy as np

# Add project root to path
REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "web_app"))

print("Testing MySQL database manager...")
from web_app.backend.mysql_database_manager import MySQLDatabaseManager

# Test database connection and add_leak_prediction method
db = MySQLDatabaseManager()

# Check if method exists
if hasattr(db, 'add_leak_prediction'):
    print("✅ add_leak_prediction method exists")
else:
    print("❌ add_leak_prediction method NOT found")
    sys.exit(1)

# Test the method
try:
    # Get a valid meter_id from the database
    meters = db.get_meters()
    if not meters.empty:
        test_meter_id = meters.iloc[0]['meter_id']
        print(f"Using test meter: {test_meter_id}")
        
        db.add_leak_prediction(
            meter_id=test_meter_id,
            confidence=0.75,
            leak_detected=True,
            leak_type="moderate_leak",
            features='{"test": "data"}'
        )
        print("✅ add_leak_prediction method works")
    else:
        print("⚠️  No meters in database, skipping add_leak_prediction test")
        print("✅ add_leak_prediction method exists (not tested due to no meters)")
except Exception as e:
    print(f"❌ add_leak_prediction failed: {e}")
    sys.exit(1)

print("\nTesting ML integration...")
from web_app.backend.ml_integration import ml_model

# Test prediction with proper feature names
test_features = {
    "mnf": 200.0,
    "night_flow_ratio": 1.0,
    "flow_variance": 10.0,
    "daily_variance": 20.0,
    "pressure_flow_correlation": 0.5,
    "pressure_drop_pattern": 0.01,
    "flow_trend": 0.001,
}

try:
    leak_detected, confidence, leak_type = ml_model.predict(test_features)
    print(f"✅ Prediction successful:")
    print(f"   Leak detected: {leak_detected} (type: {type(leak_detected).__name__})")
    print(f"   Confidence: {confidence:.4f} (type: {type(confidence).__name__})")
    print(f"   Leak type: {leak_type} (type: {type(leak_type).__name__})")
    
    # Verify types are native Python types
    assert isinstance(leak_detected, bool) and not isinstance(leak_detected, np.bool_), "leak_detected should be native Python bool"
    assert isinstance(confidence, float) and not isinstance(confidence, np.floating), "confidence should be native Python float"
    assert isinstance(leak_type, str), "leak_type should be native Python str"
    print("✅ All return types are native Python types (not numpy)")
    
except Exception as e:
    print(f"❌ Prediction failed: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n✅ All tests passed!")
print("\nYou can now run the prediction loop without errors.")
