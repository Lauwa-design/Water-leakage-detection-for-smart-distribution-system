"""
Scenario Generator with Variability
Generates water network scenarios with realistic variability in no-leak conditions
"""

import numpy as np
import pandas as pd
import wntr
from pathlib import Path
import json
import argparse
from tqdm import tqdm
import warnings
warnings.filterwarnings('ignore')


class LeakScenarioGenerator:
    def __init__(self, network_file, output_dir, leak_probability=0.3):
        self.network_file = network_file          # keep path for fresh loads
        self.output_dir = Path(output_dir)
        self.leak_probability = leak_probability
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Load base network once to read junction names and demands
        self.wn = wntr.network.WaterNetworkModel(network_file)

        # Leak types and their distributions
        self.leak_types = {
            'continuous':  0.60,
            'pressure':    0.25,
            'demand':      0.10,
            'intermittent':0.05
        }

        # Store original base demands (junctions only)
        self.original_demands = {}
        for node_name in self.wn.node_name_list:
            node = self.wn.get_node(node_name)
            if node.node_type == 'Junction':
                self.original_demands[node_name] = node.base_demand

        # Demand patterns for time-of-day variability
        self.demand_patterns = self._create_demand_patterns()

        print(f"Network loaded: {len(self.wn.node_name_list)} total nodes")
        print(f"Junctions with demand: {sum(1 for d in self.original_demands.values() if d > 0)}")

    # ------------------------------------------------------------------ #

    def _create_demand_patterns(self):
        return {
            'residential': [
                0.3, 0.25, 0.2, 0.2, 0.2, 0.3, 0.5, 0.8, 1.0, 0.9, 0.8, 0.7,
                0.7, 0.6, 0.6, 0.7, 0.9, 1.0, 1.1, 1.0, 0.8, 0.6, 0.4, 0.3
            ],
            'commercial': [
                0.2, 0.1, 0.1, 0.1, 0.1, 0.2, 0.4, 0.8, 1.0, 0.9, 0.8, 0.7,
                0.6, 0.6, 0.7, 0.8, 0.9, 0.8, 0.7, 0.6, 0.5, 0.4, 0.3, 0.2
            ],
            'industrial': [
                0.5, 0.4, 0.3, 0.3, 0.3, 0.4, 0.6, 0.9, 1.0, 0.9, 0.8, 0.7,
                0.7, 0.7, 0.7, 0.8, 0.9, 0.9, 0.8, 0.7, 0.6, 0.5, 0.5, 0.5
            ],
        }

    # ------------------------------------------------------------------ #

    def _fresh_network(self):
        """
        Return a brand-new WaterNetworkModel loaded from file.

        wntr.network.WaterNetworkModel has no .copy() method, so we reload
        from the original .inp file each time. This is the correct WNTR
        pattern for generating independent scenario copies.
        """
        return wntr.network.WaterNetworkModel(self.network_file)

    # ------------------------------------------------------------------ #

    def _add_demand_variability(self, wn_copy, scenario_id):
        """Add realistic daily demand patterns and variability to junctions."""
        for node_name in wn_copy.node_name_list:
            node = wn_copy.get_node(node_name)
            if node.node_type != 'Junction' or node.base_demand <= 0:
                continue

            pattern_type   = np.random.choice(list(self.demand_patterns.keys()))
            pattern_values = self.demand_patterns[pattern_type].copy()

            # Daily variability
            daily_factor   = np.random.uniform(0.85, 1.15)
            pattern_values = [v * daily_factor for v in pattern_values]

            # Random noise (±5%)
            noise          = np.random.normal(0, 0.05, len(pattern_values))
            pattern_values = [max(0.1, v + n) for v, n in zip(pattern_values, noise)]

            pattern_name = f'DemandPattern_{scenario_id:04d}_{node_name}'
            wn_copy.add_pattern(pattern_name, pattern_values)

            node.base_demand = self.original_demands[node_name]
            node.add_pattern(pattern_name)

    # ------------------------------------------------------------------ #

    def _add_leak(self, wn_copy, scenario_id):
        """Add a leak to the network with a realistic pattern."""
        leak_type = np.random.choice(
            list(self.leak_types.keys()),
            p=list(self.leak_types.values())
        )

        junctions_with_demand = [
            name for name, demand in self.original_demands.items() if demand > 0
        ]
        if not junctions_with_demand:
            return None, None

        junction_name  = np.random.choice(junctions_with_demand)
        leak_magnitude = np.random.uniform(0.005, 0.02)   # m³/s
        start_hour     = np.random.randint(0, 24)
        duration       = np.random.randint(2, 12)

        if leak_type == 'continuous':
            pattern_values = [1.0] * 24

        elif leak_type == 'pressure':
            pattern_values = [0.5 + 0.5 * np.sin(2 * np.pi * (h - 3) / 24)
                              for h in range(24)]

        elif leak_type == 'demand':
            pattern_values = [0.3 + 0.7 * np.sin(2 * np.pi * (h - 6) / 24)
                              for h in range(24)]

        else:  # intermittent
            pattern_values = [
                1.0 if start_hour <= h < start_hour + duration else 0.0
                for h in range(24)
            ]

        noise          = np.random.normal(0, 0.05, len(pattern_values))
        pattern_values = [max(0.0, p + n) for p, n in zip(pattern_values, noise)]

        pattern_name = f'LeakPattern_{scenario_id:04d}'
        wn_copy.add_pattern(pattern_name, pattern_values)

        try:
            wn_copy.add_leak(junction_name, leak_magnitude, pattern_name=pattern_name)
        except Exception as e:
            print(f"  Could not add leak to {junction_name}: {e}")
            return None, None

        return leak_type, {
            'junction':         junction_name,
            'leak_type':        leak_type,
            'leak_demand_m3s':  leak_magnitude,
            'start_hour':       start_hour,
            'duration_hours':   duration,
            'pattern_used':     pattern_name,
            'pattern_values':   pattern_values,
        }

    # ------------------------------------------------------------------ #

    def generate_scenario(self, scenario_id):
        """Generate a single scenario with or without a leak."""

        # ── FIX: reload from file instead of calling .copy() ─────────────
        wn_copy = self._fresh_network()
        # ─────────────────────────────────────────────────────────────────

        self._add_demand_variability(wn_copy, scenario_id)

        has_leak     = np.random.random() < self.leak_probability
        leak_type    = None
        leak_details = None

        if has_leak:
            leak_type, leak_details = self._add_leak(wn_copy, scenario_id)
            if leak_type is None:
                has_leak = False

        duration  = 24      # hours
        timestep  = 3600    # seconds (1 hour)

        try:
            sim     = wntr.sim.EpanetSimulator(wn_copy)
            results = sim.run_sim()

            scenario_dir = self.output_dir / f'scenario_{scenario_id:04d}'
            scenario_dir.mkdir(exist_ok=True)

            nodes = wn_copy.node_name_list
            links = wn_copy.link_name_list

            # ── Demands ──────────────────────────────────────────────────
            demands = results.node['demand']
            demands_df = pd.DataFrame(demands.values[:duration], columns=nodes)
            demands_df.to_csv(scenario_dir / 'demands.csv', index=False)

            # ── Pressures ────────────────────────────────────────────────
            pressures = results.node['pressure']
            pressures_df = pd.DataFrame(pressures.values[:duration], columns=nodes)
            pressures_df.to_csv(scenario_dir / 'pressures.csv', index=False)

            # ── Flows ────────────────────────────────────────────────────
            flows = results.link['flowrate']
            flows_df = pd.DataFrame(flows.values[:duration], columns=links)
            flows_df.to_csv(scenario_dir / 'flows.csv', index=False)

            # ── Labels ───────────────────────────────────────────────────
            if has_leak and leak_details:
                start  = leak_details['start_hour']
                end    = start + leak_details['duration_hours']
                labels = [1 if start <= t < end else 0 for t in range(duration)]
            else:
                labels = [0] * duration

            pd.DataFrame({'leak': labels}).to_csv(
                scenario_dir / 'labels.csv', index=False
            )

            # ── Metadata ─────────────────────────────────────────────────
            leak_info = {
                'has_leak':                   has_leak,
                'leak_details':               leak_details,
                'scenario_id':                scenario_id,
                'leak_probability':           self.leak_probability,
                'simulation_duration_hours':  duration,
                'timestep_minutes':           timestep // 60,
            }
            with open(scenario_dir / 'leak_info.json', 'w') as f:
                json.dump(leak_info, f, indent=2)

            with open(scenario_dir / 'leak_type.json', 'w') as f:
                json.dump({'leak_type': leak_type if has_leak else 'no_leak'}, f)

            return has_leak, leak_type

        except Exception as e:
            print(f"  Error in scenario {scenario_id}: {e}")
            return None, None


# ====================================================================== #

def main():
    parser = argparse.ArgumentParser(
        description='Generate leak detection scenarios with variability'
    )
    parser.add_argument('--network',          required=True,        help='EPANET .inp file')
    parser.add_argument('--output',           required=True,        help='Output directory')
    parser.add_argument('--num-scenarios',    type=int,   default=1000, help='Number of scenarios')
    parser.add_argument('--leak-probability', type=float, default=0.3,  help='Probability of leak (0–1)')
    args = parser.parse_args()

    generator = LeakScenarioGenerator(args.network, args.output, args.leak_probability)

    print(f"\n{'='*60}")
    print(f"Generating {args.num_scenarios} scenarios with variability")
    print(f"Leak probability: {args.leak_probability}")
    print(f"{'='*60}\n")

    successful   = 0
    leak_counts  = {k: 0 for k in ['continuous', 'pressure', 'demand', 'intermittent', 'no_leak']}

    for i in tqdm(range(1, args.num_scenarios + 1)):
        has_leak, leak_type = generator.generate_scenario(i)
        if has_leak is not None:
            successful += 1
            leak_counts[leak_type if has_leak else 'no_leak'] += 1

        if i % 100 == 0:
            print(f"  Progress: {i}/{args.num_scenarios} scenarios generated")

    # Save dataset-level metadata
    metadata = {
        'total_scenarios':       args.num_scenarios,
        'successful_scenarios':  successful,
        'leak_probability':      args.leak_probability,
        'leak_type_distribution':leak_counts,
    }
    with open(Path(args.output) / 'dataset_metadata.json', 'w') as f:
        json.dump(metadata, f, indent=2)

    print(f"\n{'='*60}")
    print(f"✓ Generation complete!")
    print(f"  Successful: {successful}/{args.num_scenarios}")
    print(f"  Leak distribution:")
    for t, count in leak_counts.items():
        print(f"    {t}: {count}")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
