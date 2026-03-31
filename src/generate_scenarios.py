"""
generate_scenarios.py — THIWASCO Leak Detection
=================================================
Generates water network scenarios using EPANET/WNTR simulation.

Pipeline position:  [THIS FILE]  →  data_builder.py

wntr 1.2.0 leak API (IMPORTANT):
    - Leak is added on the JUNCTION object, not the network
    - node.add_leak(wn, area, discharge_coeff, start_time, end_time)
    - area is in m² (converted from leak magnitude)
    - start_time / end_time are in SECONDS
    - Leak type is modelled via start/end timing + area size

Output per scenario (data/raw/scenarios/scenario_XXXX/):
    demands.csv     shape (24, n_nodes)
    pressures.csv   shape (24, n_nodes)
    flows.csv       shape (24, n_links)
    labels.csv      shape (24, 1) — column 'leak': 0 or 1 per hour
    leak_info.json
    leak_type.json

Label rules:
    continuous   → label=1 for ALL 24 hours
    pressure     → label=1 for ALL 24 hours
    demand       → label=1 for ALL 24 hours
    intermittent → label=1 only during [start_hour, start_hour+duration)
    no_leak      → label=0 for ALL 24 hours

Usage:
    python src/generate_scenarios.py
    python src/generate_scenarios.py --num-scenarios 5 --seed 42
"""

import json
import argparse
import warnings
from pathlib import Path

import numpy as np
import pandas as pd
import wntr
from tqdm import tqdm

warnings.filterwarnings('ignore')

import sys
sys.path.append(str(Path(__file__).resolve().parent))
from utils.config import (
    RAW_SCENARIOS_DIR, NETWORK_FILE,
    NUM_SCENARIOS, LEAK_PROBABILITY, LEAK_TYPES,
    LEAK_MAG_MIN, LEAK_MAG_MAX,
    LEAK_START_MIN, LEAK_START_MAX,
    LEAK_DURATION_MIN, LEAK_DURATION_MAX,
    TIMESTEPS_PER_DAY, RANDOM_STATE,
    create_directories, verify_network_file,
)

# ── Leak area conversion ──────────────────────────────────────────────
# wntr 1.2.0 uses leak AREA (m²) not flow magnitude
# We convert our magnitude range to an equivalent orifice area
# Q = Cd * A * sqrt(2*g*h)  →  A = Q / (Cd * sqrt(2*g*h))
# Assuming h=30m (typical network pressure), Cd=0.75, g=9.81
DISCHARGE_COEFF  = 0.75
GRAVITY          = 9.81
TYPICAL_HEAD     = 30.0   # metres
AREA_FACTOR      = DISCHARGE_COEFF * np.sqrt(2 * GRAVITY * TYPICAL_HEAD)

def magnitude_to_area(magnitude_m3s: float) -> float:
    """Convert desired leak flow (m³/s) to orifice area (m²)."""
    return magnitude_m3s / AREA_FACTOR

HOUR_TO_SEC = 3600  # seconds per hour


class LeakScenarioGenerator:

    def __init__(self, network_file: str, output_dir: Path,
                 leak_probability: float = LEAK_PROBABILITY):

        self.network_file     = str(network_file)
        self.output_dir       = Path(output_dir)
        self.leak_probability = leak_probability
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Load network once to read topology
        self.wn = wntr.network.WaterNetworkModel(self.network_file)

        # wntr 1.2.0 API: read base demand from demand_timeseries_list
        self.original_demands = {}
        for name in self.wn.junction_name_list:
            node = self.wn.get_node(name)
            dts  = node.demand_timeseries_list
            if len(dts) > 0 and dts[0].base_value > 0:
                self.original_demands[name] = dts[0].base_value

        self.valid_junctions  = list(self.original_demands.keys())
        self.demand_patterns  = self._create_demand_patterns()

        print(f"  Network file     : {self.network_file}")
        print(f"  Total nodes      : {len(self.wn.node_name_list)}")
        print(f"  Valid junctions  : {len(self.valid_junctions)}")
        print(f"  Links            : {len(self.wn.link_name_list)}")

    # ------------------------------------------------------------------ #
    # DEMAND PATTERNS
    # ------------------------------------------------------------------ #

    def _create_demand_patterns(self) -> dict:
        """24-hour multiplier patterns for realistic demand variability."""
        return {
            'residential': [
                0.30, 0.25, 0.20, 0.20, 0.20, 0.30,
                0.50, 0.80, 1.00, 0.90, 0.80, 0.70,
                0.70, 0.60, 0.60, 0.70, 0.90, 1.00,
                1.10, 1.00, 0.80, 0.60, 0.40, 0.30,
            ],
            'commercial': [
                0.20, 0.10, 0.10, 0.10, 0.10, 0.20,
                0.40, 0.80, 1.00, 0.90, 0.80, 0.70,
                0.60, 0.60, 0.70, 0.80, 0.90, 0.80,
                0.70, 0.60, 0.50, 0.40, 0.30, 0.20,
            ],
            'industrial': [
                0.50, 0.40, 0.30, 0.30, 0.30, 0.40,
                0.60, 0.90, 1.00, 0.90, 0.80, 0.70,
                0.70, 0.70, 0.70, 0.80, 0.90, 0.90,
                0.80, 0.70, 0.60, 0.50, 0.50, 0.50,
            ],
        }

    # ------------------------------------------------------------------ #
    # FRESH NETWORK — wntr has no .copy(), must reload from file
    # ------------------------------------------------------------------ #

    def _fresh_network(self) -> wntr.network.WaterNetworkModel:
        return wntr.network.WaterNetworkModel(self.network_file)

    # ------------------------------------------------------------------ #
    # DEMAND VARIABILITY
    # ------------------------------------------------------------------ #

    def _add_demand_variability(self, wn: wntr.network.WaterNetworkModel,
                                scenario_id: int) -> None:
        """
        Assign realistic daily demand patterns to every active junction.
        wntr 1.2.0 API:
            demand_timeseries_list[0].base_value   — sets base demand
            demand_timeseries_list[0].pattern_name — sets pattern
        """
        for node_name in self.valid_junctions:
            node = wn.get_node(node_name)
            dts  = node.demand_timeseries_list
            if len(dts) == 0:
                continue

            pattern_type   = np.random.choice(list(self.demand_patterns.keys()))
            pattern_values = self.demand_patterns[pattern_type].copy()

            # Daily scaling ±15%
            daily_factor   = np.random.uniform(0.85, 1.15)
            pattern_values = [v * daily_factor for v in pattern_values]

            # Random noise ±5%
            noise          = np.random.normal(0, 0.05, len(pattern_values))
            pattern_values = [max(0.05, v + n)
                              for v, n in zip(pattern_values, noise)]

            pattern_name = f'DP_{scenario_id:04d}_{node_name}'
            wn.add_pattern(pattern_name, pattern_values)

            # wntr 1.2.0: set via demand_timeseries_list
            dts[0].base_value   = self.original_demands[node_name]
            dts[0].pattern_name = pattern_name

    # ------------------------------------------------------------------ #
    # LEAK INJECTION — wntr 1.2.0 API
    # ------------------------------------------------------------------ #

    def _add_leak(self, wn: wntr.network.WaterNetworkModel,
                  scenario_id: int):
        """
        Inject a leak using wntr 1.2.0 Junction.add_leak() API:
            node.add_leak(wn, area, discharge_coeff, start_time, end_time)

        Leak types are modelled via start/end timing:
            continuous   → start=0s,         end=None (runs to end)
            pressure     → start=0s,         end=None (runs to end)
            demand       → start=0s,         end=None (runs to end)
            intermittent → start=start_hour, end=start_hour+duration

        Returns:
            (leak_type, leak_details, active_hours) on success
            (None, None, None) on failure
        """
        if not self.valid_junctions:
            return None, None, None

        leak_type      = np.random.choice(
            list(LEAK_TYPES.keys()), p=list(LEAK_TYPES.values())
        )
        junction_name  = np.random.choice(self.valid_junctions)
        leak_magnitude = float(np.random.uniform(LEAK_MAG_MIN, LEAK_MAG_MAX))
        leak_area      = magnitude_to_area(leak_magnitude)

        start_hour = int(np.random.randint(LEAK_START_MIN, LEAK_START_MAX + 1))
        duration   = int(np.random.randint(LEAK_DURATION_MIN, LEAK_DURATION_MAX + 1))

        # ── Determine timing and active hours per leak type ────────────
        if leak_type in ('continuous', 'pressure', 'demand'):
            # Active for the entire simulation
            start_time_sec = 0
            end_time_sec   = None   # runs until end of simulation
            active_hours   = list(range(TIMESTEPS_PER_DAY))

        else:
            # Intermittent — active only during [start_hour, start_hour+duration)
            end_hour       = min(start_hour + duration, TIMESTEPS_PER_DAY)
            start_time_sec = start_hour * HOUR_TO_SEC
            end_time_sec   = end_hour   * HOUR_TO_SEC
            active_hours   = list(range(start_hour, end_hour))

        # ── Add leak to junction using wntr 1.2.0 API ─────────────────
        try:
            node = wn.get_node(junction_name)
            node.add_leak(
                wn,
                area            = leak_area,
                discharge_coeff = DISCHARGE_COEFF,
                start_time      = start_time_sec,
                end_time        = end_time_sec,
            )
        except Exception as e:
            print(f"  ⚠ Could not add leak to {junction_name}: {e}")
            return None, None, None

        leak_details = {
            'junction':        junction_name,
            'leak_type':       leak_type,
            'leak_demand_m3s': leak_magnitude,
            'leak_area_m2':    leak_area,
            'discharge_coeff': DISCHARGE_COEFF,
            'start_hour':      start_hour,
            'duration_hours':  duration,
            'start_time_sec':  start_time_sec,
            'end_time_sec':    end_time_sec,
            'active_hours':    active_hours,
        }

        return leak_type, leak_details, active_hours

    # ------------------------------------------------------------------ #
    # SINGLE SCENARIO
    # ------------------------------------------------------------------ #

    def generate_scenario(self, scenario_id: int):
        """
        Generate, simulate and save one scenario.

        Returns:
            (has_leak, leak_type) on success
            (None, None) on failure
        """
        wn = self._fresh_network()
        self._add_demand_variability(wn, scenario_id)

        has_leak     = np.random.random() < self.leak_probability
        leak_type    = None
        leak_details = None
        active_hours = []

        if has_leak:
            leak_type, leak_details, active_hours = self._add_leak(wn, scenario_id)
            if leak_type is None:
                # Leak injection failed — treat as no-leak
                has_leak     = False
                active_hours = []

        # ── Run EPANET simulation ──────────────────────────────────────
        try:
            sim     = wntr.sim.EpanetSimulator(wn)
            results = sim.run_sim()
        except Exception as e:
            print(f"  ⚠ Simulation failed for scenario {scenario_id}: {e}")
            return None, None

        # ── Save outputs ───────────────────────────────────────────────
        scenario_dir = self.output_dir / f'scenario_{scenario_id:04d}'
        scenario_dir.mkdir(exist_ok=True)

        nodes = wn.node_name_list
        links = wn.link_name_list
        T     = TIMESTEPS_PER_DAY

        try:
            # demands.csv
            pd.DataFrame(
                results.node['demand'].values[:T], columns=nodes
            ).to_csv(scenario_dir / 'demands.csv', index=False)

            # pressures.csv
            pd.DataFrame(
                results.node['pressure'].values[:T], columns=nodes
            ).to_csv(scenario_dir / 'pressures.csv', index=False)

            # flows.csv
            pd.DataFrame(
                results.link['flowrate'].values[:T], columns=links
            ).to_csv(scenario_dir / 'flows.csv', index=False)

            # labels.csv — built from active_hours (correct for ALL leak types)
            labels = [1 if t in active_hours else 0 for t in range(T)]
            pd.DataFrame({'leak': labels}).to_csv(
                scenario_dir / 'labels.csv', index=False
            )

            # leak_info.json
            leak_info = {
                'has_leak':                  has_leak,
                'leak_details':              leak_details,
                'scenario_id':               scenario_id,
                'leak_probability_used':     self.leak_probability,
                'simulation_duration_hours': T,
                'timestep_hours':            1,
            }
            with open(scenario_dir / 'leak_info.json', 'w') as f:
                json.dump(leak_info, f, indent=2)

            # leak_type.json
            with open(scenario_dir / 'leak_type.json', 'w') as f:
                json.dump(
                    {'leak_type': leak_type if has_leak else 'no_leak'}, f
                )

        except Exception as e:
            print(f"  ⚠ Failed to save scenario {scenario_id}: {e}")
            return None, None

        return has_leak, (leak_type if has_leak else 'no_leak')


# ====================================================================== #
# ENTRY POINT
# ====================================================================== #

def main():
    parser = argparse.ArgumentParser(
        description='Generate THIWASCO leak detection scenarios'
    )
    parser.add_argument('--network',
        default=str(NETWORK_FILE),
        help='Path to EPANET .inp file')
    parser.add_argument('--output',
        default=str(RAW_SCENARIOS_DIR),
        help='Output directory for scenario_XXXX folders')
    parser.add_argument('--num-scenarios',
        type=int, default=NUM_SCENARIOS,
        help=f'Number of scenarios (default: {NUM_SCENARIOS})')
    parser.add_argument('--leak-probability',
        type=float, default=LEAK_PROBABILITY,
        help=f'Leak probability (default: {LEAK_PROBABILITY})')
    parser.add_argument('--seed',
        type=int, default=RANDOM_STATE,
        help=f'Random seed (default: {RANDOM_STATE})')
    args = parser.parse_args()

    np.random.seed(args.seed)

    create_directories()
    if not verify_network_file():
        raise FileNotFoundError(
            f"Network file not found: {args.network}\n"
            "Place hanoi_network.inp in data/external/ before running."
        )

    print(f"\n{'='*60}")
    print(f"THIWASCO — SCENARIO GENERATION")
    print(f"{'='*60}")
    print(f"  Scenarios       : {args.num_scenarios}")
    print(f"  Leak probability: {args.leak_probability}")
    print(f"  Output dir      : {args.output}")
    print(f"  Random seed     : {args.seed}")
    print(f"{'='*60}\n")

    generator = LeakScenarioGenerator(
        network_file     = args.network,
        output_dir       = Path(args.output),
        leak_probability = args.leak_probability,
    )

    successful  = 0
    failed      = 0
    leak_counts = {k: 0 for k in list(LEAK_TYPES.keys()) + ['no_leak']}

    for i in tqdm(range(1, args.num_scenarios + 1),
                  desc="Generating scenarios"):
        has_leak, leak_type = generator.generate_scenario(i)

        if has_leak is None:
            failed += 1
            continue

        successful += 1
        leak_counts[leak_type] += 1

    # Save dataset-level metadata
    metadata = {
        'total_requested':        args.num_scenarios,
        'successful':             successful,
        'failed':                 failed,
        'leak_probability':       args.leak_probability,
        'random_seed':            args.seed,
        'timestep_hours':         1,
        'timesteps_per_scenario': TIMESTEPS_PER_DAY,
        'leak_type_distribution': leak_counts,
    }
    metadata_path = Path(args.output) / 'dataset_metadata.json'
    with open(metadata_path, 'w') as f:
        json.dump(metadata, f, indent=2)

    print(f"\n{'='*60}")
    print(f"✓ GENERATION COMPLETE")
    print(f"{'='*60}")
    print(f"  Successful : {successful}/{args.num_scenarios}")
    print(f"  Failed     : {failed}")
    print(f"\n  Leak type distribution:")
    for t, count in leak_counts.items():
        pct = (count / successful * 100) if successful > 0 else 0
        print(f"    {t:15s}: {count:5d}  ({pct:.1f}%)")
    print(f"\n  Metadata   : {metadata_path}")
    print(f"{'='*60}")


if __name__ == '__main__':
    main()
