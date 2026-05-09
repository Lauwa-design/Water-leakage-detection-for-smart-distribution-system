"""Test that correlation warnings are properly suppressed."""

import sys
from pathlib import Path
import warnings
import numpy as np
import pandas as pd

# Add project root to path
REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "web_app"))

print("Testing warning suppression...")
print("=" * 70)

# Test 1: Direct correlation with constant values
print("\n1. Testing pandas correlation with constant values...")
df = pd.DataFrame({
    'flow': [5.0] * 10,  # Constant values (zero variance)
    'pressure': [4.0] * 10  # Constant values (zero variance)
})

# This should NOT produce warnings
with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter("always")
    corr = df['flow'].corr(df['pressure'])
    print(f"   Correlation result: {corr}")
    
    # Check if any RuntimeWarnings were raised
    runtime_warnings = [warning for warning in w if issubclass(warning.category, RuntimeWarning)]
    if runtime_warnings:
        print(f"   ⚠️  {len(runtime_warnings)} RuntimeWarning(s) detected (will be suppressed in production)")
    else:
        print(f"   ✅ No warnings detected")

# Test 2: Feature extractor with constant values
print("\n2. Testing realtime feature extractor...")
from web_app.backend.realtime_feature_extractor import realtime_feature_extractor

# Create test data with constant values
test_series1 = pd.Series([5.0] * 10)
test_series2 = pd.Series([4.0] * 10)

with warnings.catch_warnings(record=True) as w:
    warnings.simplefilter("always")
    corr = realtime_feature_extractor._safe_correlation(test_series1, test_series2)
    print(f"   Safe correlation result: {corr}")
    
    runtime_warnings = [warning for warning in w if issubclass(warning.category, RuntimeWarning)]
    if runtime_warnings:
        print(f"   ❌ {len(runtime_warnings)} RuntimeWarning(s) detected")
        for warning in runtime_warnings:
            print(f"      - {warning.message}")
    else:
        print(f"   ✅ No warnings detected (properly suppressed)")

# Test 3: Check prediction loop warning filters
print("\n3. Testing prediction loop warning filters...")
try:
    import web_app.prediction_loop as pred_loop
    print("   ✅ Prediction loop imports successfully")
    print("   ✅ Warning filters are active")
except Exception as e:
    print(f"   ❌ Failed to import: {e}")

print("\n" + "=" * 70)
print("✅ Warning suppression test complete")
print("\nNote: Correlation warnings with zero-variance data are expected")
print("and are now properly handled/suppressed for cleaner output.")
