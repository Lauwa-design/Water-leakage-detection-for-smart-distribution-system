# Quick data verification script (WNTR dataset compatible)

import json
import pandas as pd
from pathlib import Path


def check_dataset(dataset_path):
    """Verify dataset integrity"""

    dataset_path = Path(dataset_path)

    print("\n" + "=" * 60)
    print(f"CHECKING DATASET: {dataset_path.name}")
    print("=" * 60 + "\n")

    # ----------------------------
    # Check metadata
    # ----------------------------
    metadata_file = dataset_path / "metadata.json"
    if metadata_file.exists():
        with open(metadata_file) as f:
            metadata = json.load(f)

        print("Dataset Metadata:")
        print(f"  Total scenarios: {metadata.get('num_scenarios', 'N/A')}")
        print(f"  Leak probability: {metadata.get('leak_probability', 0) * 100:.0f}%")
        print(f"  Duration: {metadata.get('duration_hours', 'N/A')} hours")
        print(f"  Timestep: {metadata.get('timestep_minutes', 'N/A')} minutes")
        print(f"  Demand model: {metadata.get('demand_model', 'N/A')}")
    else:
        print("⚠ metadata.json not found")

    # ----------------------------
    # Check scenarios
    # ----------------------------
    scenario_dirs = sorted(dataset_path.glob("scenario_*"))
    print(f"\nFound {len(scenario_dirs)} scenario folders")

    if not scenario_dirs:
        print("⚠ No scenario folders found!")
        print("\n" + "=" * 60 + "\n")
        return

    # ----------------------------
    # Inspect first scenario
    # ----------------------------
    first_scenario = scenario_dirs[0]
    print(f"\nChecking {first_scenario.name}:")

    files = [
        "pressures.csv",
        "flows.csv",
        "demands.csv",
        "labels.csv",
        "leak_info.json",
    ]

    for file in files:
        file_path = first_scenario / file
        if file_path.exists():
            print(f"  ✓ {file}")
            if file.endswith(".csv"):
                df = pd.read_csv(file_path, index_col=0)
                print(f"    Shape: {df.shape}")
        else:
            print(f"  ✗ {file} MISSING!")

    # ----------------------------
    # Check leak info format
    # ----------------------------
    leak_info_path = first_scenario / "leak_info.json"
    if leak_info_path.exists():
        with open(leak_info_path) as f:
            leak_info = json.load(f)

        print("\n  Leak Info:")
        print(f"    Has leak: {leak_info.get('has_leak')}")

        if leak_info.get("has_leak"):
            leak = leak_info.get("leak_details", {})
            print(f"    Junction: {leak.get('junction', 'N/A')}")
            print(f"    Model: {leak.get('model', 'N/A')}")
            print(f"    Leak demand: {leak.get('leak_demand_m3s', 0):.5f} m³/s")
            print(f"    Duration: {leak.get('duration_hours', 0)} hours")

    # ----------------------------
    # Count scenarios with leaks
    # ----------------------------
    leak_count = 0
    for scenario_dir in scenario_dirs:
        leak_file = scenario_dir / "leak_info.json"
        if leak_file.exists():
            with open(leak_file) as f:
                info = json.load(f)
                if info.get("has_leak"):
                    leak_count += 1

    print(
        f"\nScenarios with leaks: {leak_count}/{len(scenario_dirs)} "
        f"({leak_count / len(scenario_dirs) * 100:.1f}%)"
    )

    print("\n" + "=" * 60 + "\n")


if __name__ == "__main__":
    import os

    test_dirs = [
        "data/raw/test_10scenarios",
        "data/raw/scenarios",
    ]

    for test_dir in test_dirs:
        if os.path.exists(test_dir):
            check_dataset(test_dir)
        else:
            print(f"\n⚠ Directory not found: {test_dir}")
