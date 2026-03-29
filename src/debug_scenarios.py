"""
debug_scenarios.py - Diagnose scenario folder structure
"""

import json
import pandas as pd
from pathlib import Path

def debug_scenario(scenario_dir):
    """Check a single scenario folder and report its structure"""
    print(f"\n{'='*60}")
    print(f"Checking: {scenario_dir.name}")
    print(f"{'='*60}")
    
    # List all files
    files = list(scenario_dir.glob("*"))
    print(f"Files found: {[f.name for f in files]}")
    
    # Check demands.csv
    demands_file = scenario_dir / "demands.csv"
    if demands_file.exists():
        df = pd.read_csv(demands_file)
        print(f"\ndemands.csv shape: {df.shape}")
        print(f"demands.csv columns: {df.columns.tolist()}")
        print(f"First 2 rows:\n{df.head(2)}")
    else:
        print("❌ demands.csv NOT FOUND")
    
    # Check pressures.csv
    pressures_file = scenario_dir / "pressures.csv"
    if pressures_file.exists():
        df = pd.read_csv(pressures_file)
        print(f"\npressures.csv shape: {df.shape}")
        print(f"pressures.csv columns: {df.columns.tolist()}")
    else:
        print("❌ pressures.csv NOT FOUND")
    
    # Check flows.csv
    flows_file = scenario_dir / "flows.csv"
    if flows_file.exists():
        df = pd.read_csv(flows_file)
        print(f"\nflows.csv shape: {df.shape}")
        print(f"flows.csv columns: {df.columns.tolist()}")
    else:
        print("❌ flows.csv NOT FOUND")
    
    # Check labels.csv
    labels_file = scenario_dir / "labels.csv"
    if labels_file.exists():
        df = pd.read_csv(labels_file)
        print(f"\nlabels.csv shape: {df.shape}")
        print(f"labels.csv columns: {df.columns.tolist()}")
        print(f"labels values: {df.values.flatten()}")
    else:
        print("❌ labels.csv NOT FOUND")
    
    # Check JSON files
    for json_file in scenario_dir.glob("*.json"):
        with open(json_file) as f:
            data = json.load(f)
            print(f"\n{json_file.name}: {data}")

def main():
    scenarios_dir = Path("data/raw/scenarios")
    
    # Get all scenario folders
    scenario_dirs = sorted(scenarios_dir.glob("scenario_*"))
    print(f"Found {len(scenario_dirs)} scenario folders")
    
    # Check first few and last few scenarios
    print("\n" + "="*60)
    print("CHECKING FIRST 3 SCENARIOS")
    print("="*60)
    for scenario_dir in scenario_dirs[:3]:
        debug_scenario(scenario_dir)
    
    print("\n" + "="*60)
    print("CHECKING LAST 3 SCENARIOS")
    print("="*60)
    for scenario_dir in scenario_dirs[-3:]:
        debug_scenario(scenario_dir)
    
    # Check one of the problematic scenarios
    print("\n" + "="*60)
    print("CHECKING A PROBLEMATIC SCENARIO (scenario_1727)")
    print("="*60)
    problematic = scenarios_dir / "scenario_1727"
    if problematic.exists():
        debug_scenario(problematic)
    else:
        print("scenario_1727 not found")

if __name__ == "__main__":
    main()