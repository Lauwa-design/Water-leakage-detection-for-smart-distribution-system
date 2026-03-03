"""
Advanced Leak Scenario Dataset Generator
Realistic leak types: Continuous, Pressure-Dependent, Demand-Driven, Intermittent
"""

import json
import random
import copy
from pathlib import Path
from datetime import datetime
from concurrent.futures import ProcessPoolExecutor, TimeoutError
from typing import Dict, List, Tuple, Optional

import numpy as np
import pandas as pd
from tqdm import tqdm
import wntr


# ===================== CONFIG =====================
TIMEOUT_SECONDS = 120      # ⏱ per scenario
MAX_WORKERS = 1            # ⚠ MUST stay 1 for WNTR on Windows
# Leak type distribution (matches real-world statistics)
LEAK_TYPE_DISTRIBUTION = {
    "continuous": 0.60,      # 60% - Pipe breaks (constant 24/7)
    "pressure": 0.25,        # 25% - Pressure-dependent (night-only)
    "demand": 0.10,          # 10% - Demand-driven (follows usage)
    "intermittent": 0.05     # 5%  - Random bursts
}
# ==================================================


class LeakScenarioGenerator:
    def __init__(
        self,
        network_file: str,
        output_dir: str,
        sim_duration_hours: int = 24,
        timestep_minutes: int = 30,
        mode: str = "PDD",
    ):
        self.network_file = network_file
        self.output_dir = Path(output_dir)
        self.sim_duration_hours = sim_duration_hours
        self.timestep_minutes = timestep_minutes
        self.mode = mode

        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Load base network
        self.base_wn = wntr.network.WaterNetworkModel(network_file)
        
        # Configure simulation options
        self.base_wn.options.hydraulic.demand_model = "PDD" if mode == "PDD" else "DD"
        self.base_wn.options.time.duration = sim_duration_hours * 3600
        self.base_wn.options.time.hydraulic_timestep = timestep_minutes * 60
        self.base_wn.options.time.report_timestep = timestep_minutes * 60
        
        # Pre-calculate common patterns for efficiency
        self._initialize_patterns()
        
        print("✓ Network loaded")
        print(f"  Junctions: {len(self.base_wn.junction_name_list)}")
        print(f"  Pipes: {len(self.base_wn.pipe_name_list)}")
        print(f"  Simulation: {sim_duration_hours}h, Timestep: {timestep_minutes}min")

    # ------------------------------------------------

    def _initialize_patterns(self):
        """Initialize all leak pattern templates"""
        # Base residential pattern for demand-driven leaks
        self.residential_pattern = [
            0.1, 0.1, 0.1, 0.1, 0.1, 0.2,  # 12AM-5AM: Very low
            1.5, 1.2, 0.8, 0.6, 0.5, 0.5,  # 6AM-11AM: Morning peak
            0.5, 0.5, 0.5, 0.6, 0.8, 1.2,  # 12PM-5PM: Afternoon
            1.5, 1.2, 0.8, 0.6, 0.4, 0.2   # 6PM-11PM: Evening peak
        ]
        
        # Pressure pattern (higher at night)
        self.pressure_pattern = [
            1.3, 1.4, 1.4, 1.3, 1.2, 1.1,  # 12AM-5AM: Highest pressure
            0.9, 0.7, 0.6, 0.5, 0.5, 0.5,  # 6AM-11AM: Pressure drops
            0.5, 0.5, 0.5, 0.6, 0.7, 0.8,  # 12PM-5PM: Steady
            0.9, 1.0, 1.1, 1.2, 1.3, 1.3   # 6PM-11PM: Pressure rises
        ]

    # ------------------------------------------------

    def _create_leak_pattern(self, leak_type: str, start_hour: int, 
                           duration_hours: int) -> List[float]:
        """Create pattern based on leak type and timing"""
        pattern = [0.0] * 24
        
        for hour_offset in range(duration_hours):
            hour = (start_hour + hour_offset) % 24
            
            if leak_type == "continuous":
                # Continuous leak: full intensity during leak period
                pattern[hour] = 1.0
                
            elif leak_type == "pressure":
                # Pressure-dependent: scaled by pressure pattern
                pattern[hour] = self.pressure_pattern[hour]
                
            elif leak_type == "demand":
                # Demand-driven: follows residential usage pattern
                pattern[hour] = self.residential_pattern[hour]
                
            elif leak_type == "intermittent":
                # Intermittent: random on/off during leak period
                if random.random() < 0.7:  # 70% chance of being "on"
                    # Varying intensity when on
                    pattern[hour] = random.uniform(0.3, 1.0)
                else:
                    pattern[hour] = 0.0
                    
            else:
                # Default to continuous
                pattern[hour] = 1.0
        
        return pattern

    # ------------------------------------------------

    def generate_scenario(self, scenario_id: int, leak_probability: float) -> bool:
        """Generate a single leak scenario with realistic leak behavior"""
        scenario_dir = self.output_dir / f"scenario_{scenario_id:04d}"
        scenario_dir.mkdir(parents=True, exist_ok=True)

        # Create fresh network copy
        wn = copy.deepcopy(self.base_wn)
        
        # Decide if this scenario has a leak
        has_leak = random.random() < leak_probability
        leak_details = None
        leak_type = None
        start_time = end_time = None

        if has_leak:
            # ===== LEAK CONFIGURATION =====
            # Select random junction for leak
            junction_name = random.choice(wn.junction_name_list)
            junction = wn.get_node(junction_name)
            
            # Leak characteristics
            leak_demand = random.uniform(0.001, 0.01)  # 1-10 L/s
            
            # Select leak type based on distribution
            leak_type = random.choices(
                list(LEAK_TYPE_DISTRIBUTION.keys()),
                weights=list(LEAK_TYPE_DISTRIBUTION.values())
            )[0]
            
            # Determine timing based on leak type
            if leak_type == "continuous":
                # Once starts, continues until simulation end (most realistic)
                start_hour = random.randint(1, 12)
                duration_hours = self.sim_duration_hours - start_hour
                
            elif leak_type == "pressure":
                # Pressure-dependent: usually starts at night
                start_hour = random.choice([20, 21, 22, 23, 0, 1, 2])
                duration_hours = random.randint(6, 10)  # Typical night duration
                
            elif leak_type == "demand":
                # Demand-driven: follows usage patterns
                start_hour = random.randint(6, 20)  # During active hours
                duration_hours = random.randint(3, 8)
                
            else:  # intermittent
                # Random bursts
                start_hour = random.randint(1, 18)
                duration_hours = random.randint(2, 6)
            
            # Ensure duration doesn't exceed simulation
            if start_hour + duration_hours > self.sim_duration_hours:
                duration_hours = self.sim_duration_hours - start_hour
            
            start_time = start_hour * 3600
            end_time = (start_hour + duration_hours) * 3600
            
            # ===== CREATE AND APPLY LEAK PATTERN =====
            leak_pattern = self._create_leak_pattern(leak_type, start_hour, duration_hours)
            
            # Add pattern to network
            pattern_name = f"LeakPattern_{scenario_id:04d}"
            wn.add_pattern(pattern_name, leak_pattern)
            
            # Apply leak to junction
            junction.add_demand(leak_demand, pattern_name=pattern_name, category="leak")
            
            # Store leak details
            leak_details = {
                "junction": junction_name,
                "leak_type": leak_type,
                "leak_demand_m3s": leak_demand,
                "start_hour": start_hour,
                "duration_hours": duration_hours,
                "pattern_used": pattern_name,
                "pattern_values": leak_pattern
            }
        
        # ===== RUN SIMULATION =====
        try:
            sim = wntr.sim.EpanetSimulator(wn)
            results = sim.run_sim()
            
            # Extract results
            pressures = results.node["pressure"]
            demands = results.node["demand"]
            flows = results.link["flowrate"]
            
            # Create labels (0=no leak, 1=leak)
            labels = pd.Series(0, index=pressures.index, name="leak")
            if has_leak:
                # For intermittent leaks, create more complex labels
                if leak_type == "intermittent":
                    # Label only hours where pattern > 0.5 as "leak"
                    for i, timestamp in enumerate(labels.index):
                        hour = timestamp / 3600  # Convert seconds to hours
                        hour_index = int(hour) % 24
                        if (start_hour <= hour < start_hour + duration_hours and 
                            leak_pattern[hour_index] > 0.5):
                            labels.loc[timestamp] = 1
                else:
                    # Simple binary labeling for other leak types
                    labels.loc[
                        (labels.index >= start_time) & (labels.index <= end_time)
                    ] = 1
            
            # ===== SAVE RESULTS =====
            pressures.to_csv(scenario_dir / "pressures.csv")
            demands.to_csv(scenario_dir / "demands.csv")
            flows.to_csv(scenario_dir / "flows.csv")
            labels.to_csv(scenario_dir / "labels.csv")
            
            # Save leak info with type classification
            leak_info = {
                "has_leak": has_leak,
                "leak_details": leak_details,
                "scenario_id": scenario_id,
                "leak_probability": leak_probability,
                "simulation_duration_hours": self.sim_duration_hours,
                "timestep_minutes": self.timestep_minutes
            }
            
            with open(scenario_dir / "leak_info.json", "w") as f:
                json.dump(leak_info, f, indent=4)
            
            # Save leak type as separate classification label
            if has_leak:
                type_label = {"leak_type": leak_type}
                with open(scenario_dir / "leak_type.json", "w") as f:
                    json.dump(type_label, f, indent=4)
            else:
                type_label = {"leak_type": "no_leak"}
                with open(scenario_dir / "leak_type.json", "w") as f:
                    json.dump(type_label, f, indent=4)
            
            return True
            
        except Exception as e:
            print(f"  ✗ Scenario {scenario_id} simulation failed: {e}")
            # Clean up failed scenario directory
            import shutil
            if scenario_dir.exists():
                shutil.rmtree(scenario_dir)
            return False


# ==================================================

def run_with_timeout(args):
    """Wrapper for timeout handling"""
    generator, scenario_id, leak_probability = args
    return generator.generate_scenario(scenario_id, leak_probability)


# ==================================================

def generate_dataset(
    generator: LeakScenarioGenerator,
    num_scenarios: int,
    leak_probability: float,
    resume: bool = True
):
    """Generate dataset with progress tracking and detailed logging"""
    
    # Check for existing scenarios
    existing = {
        int(p.name.split("_")[1])
        for p in generator.output_dir.glob("scenario_*")
        if p.is_dir()
    }
    
    successful = len(existing)
    failed = 0
    
    print(f"\n{'='*60}")
    print(f"DATASET GENERATION WITH {len(LEAK_TYPE_DISTRIBUTION)} LEAK TYPES")
    print(f"{'='*60}")
    print(f"Resume mode: {'ON' if resume else 'OFF'}")
    print(f"Existing scenarios found: {successful}")
    print(f"Leak probability: {leak_probability*100:.0f}%")
    print(f"Leak type distribution: {LEAK_TYPE_DISTRIBUTION}")
    print(f"{'='*60}\n")
    
    # Color codes for output
    class Colors:
        GREEN = '\033[92m'
        RED = '\033[91m'
        YELLOW = '\033[93m'
        BLUE = '\033[94m'
        CYAN = '\033[96m'
        BOLD = '\033[1m'
        RESET = '\033[0m'
    
    start_time = datetime.now()
    leak_type_counts = {lt: 0 for lt in LEAK_TYPE_DISTRIBUTION.keys()}
    leak_type_counts["no_leak"] = 0
    
    with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = []
        
        for i in tqdm(range(1, num_scenarios + 1), desc="Generating scenarios"):
            if resume and i in existing:
                # Try to read leak type from existing scenario
                try:
                    type_file = generator.output_dir / f"scenario_{i:04d}" / "leak_type.json"
                    if type_file.exists():
                        with open(type_file) as f:
                            data = json.load(f)
                            leak_type = data.get("leak_type", "unknown")
                            if leak_type in leak_type_counts:
                                leak_type_counts[leak_type] += 1
                except:
                    pass
                continue
            
            # Submit scenario for generation
            future = executor.submit(
                run_with_timeout,
                (generator, i, leak_probability)
            )
            futures.append((i, future))
        
        # Process results as they complete
        for i, future in tqdm(futures, desc="Processing", leave=False):
            try:
                success = future.result(timeout=TIMEOUT_SECONDS)
                
                if success:
                    successful += 1
                    # Read leak type from generated file
                    try:
                        type_file = generator.output_dir / f"scenario_{i:04d}" / "leak_type.json"
                        if type_file.exists():
                            with open(type_file) as f:
                                data = json.load(f)
                                leak_type = data.get("leak_type", "unknown")
                                if leak_type in leak_type_counts:
                                    leak_type_counts[leak_type] += 1
                                    color = Colors.GREEN if leak_type != "no_leak" else Colors.BLUE
                                    tqdm.write(f"{color}✓ Scenario {i:04d}: {leak_type}{Colors.RESET}")
                    except:
                        tqdm.write(f"{Colors.GREEN}✓ Scenario {i:04d}: Success{Colors.RESET}")
                else:
                    failed += 1
                    tqdm.write(f"{Colors.RED}✗ Scenario {i:04d}: Failed{Colors.RESET}")
                    
            except TimeoutError:
                failed += 1
                tqdm.write(f"{Colors.RED}⏱ Scenario {i:04d}: Timeout{Colors.RESET}")
            except Exception as e:
                failed += 1
                tqdm.write(f"{Colors.RED}✗ Scenario {i:04d}: {str(e)[:50]}...{Colors.RESET}")
    
    # Calculate statistics
    total_time = (datetime.now() - start_time).total_seconds()
    
    # Save dataset metadata
    metadata = {
        "num_scenarios_requested": num_scenarios,
        "num_scenarios_generated": successful,
        "num_scenarios_failed": failed,
        "leak_probability": leak_probability,
        "leak_type_distribution": LEAK_TYPE_DISTRIBUTION,
        "leak_type_counts": leak_type_counts,
        "simulation_duration_hours": generator.sim_duration_hours,
        "timestep_minutes": generator.timestep_minutes,
        "timeout_seconds": TIMEOUT_SECONDS,
        "generation_time_seconds": total_time,
        "success_rate_percent": (successful/(successful+failed))*100 if (successful+failed) > 0 else 0,
        "timestamp": datetime.now().isoformat()
    }
    
    with open(generator.output_dir / "dataset_metadata.json", "w") as f:
        json.dump(metadata, f, indent=4)
    
    # Print comprehensive summary
    print(f"\n{Colors.BOLD}{'='*70}{Colors.RESET}")
    print(f"{Colors.BOLD}DATASET GENERATION COMPLETE{Colors.RESET}")
    print(f"{Colors.BOLD}{'='*70}{Colors.RESET}")
    
    print(f"\n{Colors.CYAN}{'SCENARIO STATISTICS':^70}{Colors.RESET}")
    print(f"{Colors.BLUE}{'-'*70}{Colors.RESET}")
    print(f"{Colors.GREEN}Successful scenarios:{Colors.RESET} {successful:>8}")
    print(f"{Colors.RED}Failed scenarios:{Colors.RESET}     {failed:>8}")
    print(f"{Colors.BLUE}Total requested:{Colors.RESET}      {num_scenarios:>8}")
    print(f"{Colors.BLUE}{'-'*70}{Colors.RESET}")
    
    print(f"\n{Colors.CYAN}{'LEAK TYPE DISTRIBUTION':^70}{Colors.RESET}")
    print(f"{Colors.BLUE}{'-'*70}{Colors.RESET}")
    total_leaks = sum(leak_type_counts[lt] for lt in LEAK_TYPE_DISTRIBUTION.keys())
    for leak_type, count in leak_type_counts.items():
        if leak_type == "no_leak":
            percentage = (count/successful)*100 if successful > 0 else 0
            print(f"{Colors.BLUE}{leak_type:20}{Colors.RESET} {count:>8} ({percentage:.1f}%)")
        else:
            percentage = (count/total_leaks)*100 if total_leaks > 0 else 0
            color = Colors.GREEN if leak_type == "continuous" else Colors.YELLOW
            print(f"{color}{leak_type:20}{Colors.RESET} {count:>8} ({percentage:.1f}%)")
    print(f"{Colors.BLUE}{'-'*70}{Colors.RESET}")
    
    print(f"\n{Colors.CYAN}{'PERFORMANCE':^70}{Colors.RESET}")
    print(f"{Colors.BLUE}{'-'*70}{Colors.RESET}")
    print(f"{Colors.BLUE}Total generation time:{Colors.RESET} {total_time:.1f} seconds")
    if successful > 0:
        print(f"{Colors.BLUE}Average time/scenario:{Colors.RESET} {total_time/successful:.2f} seconds")
    print(f"{Colors.BLUE}{'-'*70}{Colors.RESET}")
    
    print(f"\n{Colors.CYAN}Output directory:{Colors.RESET} {generator.output_dir}")
    print(f"{Colors.CYAN}Metadata saved to:{Colors.RESET} {generator.output_dir / 'dataset_metadata.json'}")
    
    # ML readiness check
    print(f"\n{Colors.BOLD}{Colors.CYAN}ML READINESS CHECK:{Colors.RESET}")
    if total_leaks > 50 and all(count > 5 for lt, count in leak_type_counts.items() if lt != "no_leak"):
        print(f"{Colors.GREEN}✅ Dataset is ready for multi-class leak classification!{Colors.RESET}")
        print(f"   You can train models for: Binary detection AND Leak type classification")
    elif total_leaks > 20:
        print(f"{Colors.YELLOW}⚠️  Dataset can be used for binary leak detection{Colors.RESET}")
        print(f"   Consider generating more scenarios for reliable multi-class training")
    else:
        print(f"{Colors.RED}❌ Generate more scenarios for meaningful ML training{Colors.RESET}")


# ==================================================

if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(
        description="Generate realistic leak scenarios for water networks with multiple leak types",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Generate 500 scenarios with default settings
  python generate_scenarios.py --network hanoi.inp --output data/scenarios --num-scenarios 500
  
  # Generate 1000 scenarios with 50% leak probability
  python generate_scenarios.py --network network.inp --output data/train --num-scenarios 1000 --leak-probability 0.5
  
  # Generate with custom duration and timestep
  python generate_scenarios.py --network hanoi.inp --output data/test --num-scenarios 200 --duration 48 --timestep 15
        """
    )
    
    parser.add_argument("--network", required=True,
                       help="EPANET .inp file for the water network")
    parser.add_argument("--output", required=True,
                       help="Output directory for generated scenarios")
    parser.add_argument("--num-scenarios", type=int, default=100,
                       help="Number of scenarios to generate (default: 100)")
    parser.add_argument("--leak-probability", type=float, default=0.7,
                       help="Probability of a leak in each scenario (default: 0.7)")
    parser.add_argument("--duration", type=int, default=24,
                       help="Simulation duration in hours (default: 24)")
    parser.add_argument("--timestep", type=int, default=30,
                       help="Simulation timestep in minutes (default: 30)")
    parser.add_argument("--no-resume", action="store_true",
                       help="Disable resume mode (overwrite existing scenarios)")
    
    args = parser.parse_args()
    
    # Create generator with enhanced capabilities
    generator = LeakScenarioGenerator(
        network_file=args.network,
        output_dir=args.output,
        sim_duration_hours=args.duration,
        timestep_minutes=args.timestep,
    )
    
    # Generate dataset
    generate_dataset(
        generator,
        num_scenarios=args.num_scenarios,
        leak_probability=args.leak_probability,
        resume=not args.no_resume
    )