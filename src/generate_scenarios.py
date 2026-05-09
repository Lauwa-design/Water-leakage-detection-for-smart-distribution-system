# -*- coding: utf-8 -*-
"""Generate hydraulic leak scenarios for model training."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import wntr

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

try:  # Support execution both as a script and as an imported module.
    from src.utils.config  import (  # type: ignore
        DAILY_READINGS,
        EXTREME_LEAK_THRESHOLD,
        FLOW_NOISE_STD,
        FLOW_RANGE,
        LEAK_MAG_MAX,
        METER_BATTERY_LIFE_YEARS,
        METER_INGRESS_RATING,
        METER_INTERNAL_SAMPLE_SECONDS,
        METER_MODEL,
        METER_SIZE_OPTIONS_MM,
        METER_VELOCITY_RANGE_MS,
        METER_MAX_FLOW_M3H,
        METER_MIN_FLOW_M3H,
        METER_READING_INTERVAL,
        MODERATE_LEAK_THRESHOLD,
        NUM_SCENARIOS,
        PRESSURE_NOISE_STD,
        PRESSURE_RANGE,
        RANDOM_STATE,
        RAW_DIR,
        SLOW_LEAK_THRESHOLD,
    )
except ModuleNotFoundError:
    from utils.config import (  # noqa: E402
        DAILY_READINGS,
        EXTREME_LEAK_THRESHOLD,
        FLOW_NOISE_STD,
        FLOW_RANGE,
        LEAK_MAG_MAX,
        METER_BATTERY_LIFE_YEARS,
        METER_INGRESS_RATING,
        METER_INTERNAL_SAMPLE_SECONDS,
        METER_MODEL,
        METER_SIZE_OPTIONS_MM,
        METER_VELOCITY_RANGE_MS,
        METER_MAX_FLOW_M3H,
        METER_MIN_FLOW_M3H,
        METER_READING_INTERVAL,
        MODERATE_LEAK_THRESHOLD,
        NUM_SCENARIOS,
        PRESSURE_NOISE_STD,
        PRESSURE_RANGE,
        RANDOM_STATE,
        RAW_DIR,
        SLOW_LEAK_THRESHOLD,
    )


GRAVITY = 9.81
DEFAULT_DISCHARGE_COEFF = 0.75
NOMINAL_PRESSURE_HEAD_M = 35.0


def get_num_scenarios() -> int:
    """Allow small smoke tests without editing config."""
    override = os.getenv("NUM_SCENARIOS_OVERRIDE")
    if override:
        return max(1, int(override))
    return NUM_SCENARIOS


def pipe_area_m2(meter_size_mm: int) -> float:
    diameter_m = meter_size_mm / 1000.0
    return np.pi * (diameter_m ** 2) / 4.0


def flow_lpm_to_m3h(flow_lpm: np.ndarray | float) -> np.ndarray | float:
    return np.asarray(flow_lpm) * 0.06 if isinstance(flow_lpm, np.ndarray) else flow_lpm * 0.06


def flow_lpm_to_velocity_ms(flow_lpm: np.ndarray,
                            meter_size_mm: int) -> np.ndarray:
    flow_m3s = flow_lpm / 60000.0
    velocity = flow_m3s / max(pipe_area_m2(meter_size_mm), 1e-6)
    return np.clip(velocity, METER_VELOCITY_RANGE_MS[0], METER_VELOCITY_RANGE_MS[1])


def cumulative_totalizer_m3(flow_lpm: np.ndarray) -> np.ndarray:
    interval_minutes = METER_READING_INTERVAL / 60.0
    volume_per_interval_m3 = (flow_lpm * interval_minutes) / 1000.0
    return np.cumsum(volume_per_interval_m3)


def build_meter_status(leak_type: str,
                       reverse_flow_m3h: np.ndarray,
                       leak_start_idx: int = -1,
                       leak_end_idx: int = -1) -> np.ndarray:
    status = np.full(DAILY_READINGS, "OK", dtype=object)
    status[reverse_flow_m3h > 0.01] = "REVERSE_FLOW_ALERT"
    if 0 <= leak_start_idx <= leak_end_idx < DAILY_READINGS:
        leak_window = slice(leak_start_idx, leak_end_idx + 1)
        if leak_type == "slow_leak":
            status[leak_window] = np.where(status[leak_window] == "OK", "LEAK_MONITOR", status[leak_window])
        elif leak_type == "moderate_leak":
            status[leak_window] = np.where(status[leak_window] == "OK", "LEAK_SUSPECT", status[leak_window])
        elif leak_type == "extreme_leak":
            status[leak_window] = np.where(status[leak_window] == "OK", "LEAK_ALERT", status[leak_window])
    return status


def flow_lpm_to_leak_area(flow_lpm: float,
                          pressure_head_m: float = NOMINAL_PRESSURE_HEAD_M,
                          discharge_coeff: float = DEFAULT_DISCHARGE_COEFF) -> float:
    """Approximate leak area from target flow using the orifice equation."""
    flow_m3_per_s = max(flow_lpm, 0.0) / 60000.0
    denominator = discharge_coeff * np.sqrt(2 * GRAVITY * max(pressure_head_m, 1.0))
    return flow_m3_per_s / denominator


def sample_leak_signature(rng: np.random.Generator) -> dict[str, float | int | str]:
    """Sample a leak type with a time-localized hydraulic signature."""
    magnitude_lpm = float(rng.uniform(SLOW_LEAK_THRESHOLD, LEAK_MAG_MAX))

    if magnitude_lpm >= EXTREME_LEAK_THRESHOLD:
        leak_type = "extreme_leak"
        start_idx = int(rng.integers(72, 240))  # 6 AM to 8 PM
        duration_steps = int(rng.integers(6, 25))  # 30 min to 2 hours
    elif magnitude_lpm >= MODERATE_LEAK_THRESHOLD:
        leak_type = "moderate_leak"
        start_idx = int(rng.integers(48, 228))  # 4 AM to 7 PM
        duration_steps = int(rng.integers(24, 73))  # 2 to 6 hours
    elif magnitude_lpm >= SLOW_LEAK_THRESHOLD:
        leak_type = "slow_leak"
        start_idx = int(rng.integers(0, 216))  # midnight to 6 PM
        duration_steps = int(rng.integers(48, 169))  # 4 to 14 hours (slow leaks persist longer)
    else:
        leak_type = "slow_leak"
        start_idx = int(rng.integers(0, 144))  # midnight to noon
        duration_steps = int(rng.integers(72, 193))  # 6 to 16 hours

    end_idx = min(start_idx + duration_steps, DAILY_READINGS - 1)
    start_time = start_idx * METER_READING_INTERVAL
    # Keep the end time inside the 24h simulation horizon.
    end_time = min((end_idx + 1) * METER_READING_INTERVAL, DAILY_READINGS * METER_READING_INTERVAL - METER_READING_INTERVAL)
    leak_area = flow_lpm_to_leak_area(magnitude_lpm)

    return {
        "leak_type": leak_type,
        "magnitude_lpm": magnitude_lpm,
        "start_idx": start_idx,
        "end_idx": end_idx,
        "start_time": start_time,
        "end_time": end_time,
        "leak_area_m2": leak_area,
    }


def choose_observation_nodes(wn: wntr.network.WaterNetworkModel,
                             rng: np.random.Generator,
                             leak_node: str | None) -> list[str]:
    """Pick representative meter observation nodes, always including the leak node when present."""
    junctions = list(wn.junction_name_list)
    if not junctions:
        return []

    if leak_node and leak_node in junctions:
        other_nodes = [name for name in junctions if name != leak_node]
        sample_size = min(4, len(other_nodes))
        sampled = rng.choice(other_nodes, size=sample_size, replace=False).tolist() if sample_size else []
        return [leak_node] + sampled

    sample_size = min(5, len(junctions))
    return rng.choice(junctions, size=sample_size, replace=False).tolist()


def simulate_hydraulic_scenario(inp_file: Path,
                                scenario_id: int,
                                rng: np.random.Generator) -> pd.DataFrame:
    """Run one WNTR/EPANET scenario and return a meter-style time series."""
    wn = wntr.network.WaterNetworkModel(inp_file)
    wn.options.time.duration = 24 * 3600
    wn.options.time.hydraulic_timestep = METER_READING_INTERVAL
    wn.options.time.report_timestep = METER_READING_INTERVAL

    has_leak = bool(rng.choice([0, 1], p=[0.5, 0.5]))
    leak_signature = None
    leak_node = None

    if has_leak:
        junctions = list(wn.junction_name_list)
        leak_node = str(rng.choice(junctions))
        leak_signature = sample_leak_signature(rng)
        wn.get_node(leak_node).add_leak(
            wn,
            area=float(leak_signature["leak_area_m2"]),
            discharge_coeff=DEFAULT_DISCHARGE_COEFF,
            start_time=int(leak_signature["start_time"]),
            end_time=int(leak_signature["end_time"]),
        )

    observed_nodes = choose_observation_nodes(wn, rng, leak_node)
    if not observed_nodes:
        raise RuntimeError("No junctions available for observation in the hydraulic model.")

    meter_size_mm = int(rng.choice(METER_SIZE_OPTIONS_MM))

    sim = wntr.sim.EpanetSimulator(wn)
    results = sim.run_sim()
    time_points = np.arange(DAILY_READINGS) * METER_READING_INTERVAL

    demand_m3_per_s = results.node["demand"].loc[time_points, observed_nodes].sum(axis=1).to_numpy()
    pressure_m = results.node["pressure"].loc[time_points, observed_nodes].mean(axis=1).to_numpy()

    raw_flow_lpm = demand_m3_per_s * 60000.0
    target_dma_baseline_lpm = float(rng.uniform(180.0, 420.0))
    scale_factor = target_dma_baseline_lpm / max(float(np.median(raw_flow_lpm)), 1.0)
    mean_flow = raw_flow_lpm * scale_factor
    mean_pressure = pressure_m / 10.197

    flow_noise = rng.normal(0, np.maximum(mean_flow * FLOW_NOISE_STD, 0.5), DAILY_READINGS)
    pressure_noise = rng.normal(0, np.maximum(mean_pressure * PRESSURE_NOISE_STD, 0.05), DAILY_READINGS)
    mean_flow = np.clip(mean_flow + flow_noise, FLOW_RANGE[0], FLOW_RANGE[1])
    mean_pressure = np.clip(mean_pressure + pressure_noise, PRESSURE_RANGE[0], PRESSURE_RANGE[1])

    temperature_c = np.clip(
        rng.uniform(15, 25, DAILY_READINGS) + rng.normal(0, 0.5, DAILY_READINGS),
        10,
        30,
    )

    if leak_signature is None:
        leak_type = "none"
        leak_magnitude_l_min = 0.0
        leak_start_idx = -1
        leak_end_idx = -1
        leak_area_m2 = 0.0
    else:
        leak_type = str(leak_signature["leak_type"])
        leak_magnitude_l_min = float(leak_signature["magnitude_lpm"])
        leak_start_idx = int(leak_signature["start_idx"])
        leak_end_idx = int(leak_signature["end_idx"])
        leak_area_m2 = float(leak_signature["leak_area_m2"])

    flow_rate_m3_h = np.clip(flow_lpm_to_m3h(mean_flow), METER_MIN_FLOW_M3H, METER_MAX_FLOW_M3H)
    reverse_flow_m3_h = np.where(rng.random(DAILY_READINGS) < 0.01, rng.uniform(0.0, 0.02, DAILY_READINGS), 0.0)
    forward_flow_m3_h = np.clip(flow_rate_m3_h - reverse_flow_m3_h, 0.0, None)
    totalized_volume_m3 = cumulative_totalizer_m3(mean_flow)
    velocity_ms = flow_lpm_to_velocity_ms(mean_flow, meter_size_mm)
    meter_status = build_meter_status(
        leak_type,
        reverse_flow_m3_h,
        leak_start_idx=leak_start_idx,
        leak_end_idx=leak_end_idx,
    )

    return pd.DataFrame(
        {
            "scenario": scenario_id,
            "time_index": np.arange(DAILY_READINGS),
            "timestamp": pd.date_range("2024-01-01", periods=DAILY_READINGS, freq="5min"),
            "meter_model": METER_MODEL,
            "meter_size_mm": meter_size_mm,
            "meter_internal_sample_seconds": METER_INTERNAL_SAMPLE_SECONDS,
            "meter_output_interval_seconds": METER_READING_INTERVAL,
            "meter_battery_design_years": METER_BATTERY_LIFE_YEARS,
            "meter_ingress_rating": METER_INGRESS_RATING,
            "flow_rate_m3_h": flow_rate_m3_h,
            "forward_flow_m3_h": forward_flow_m3_h,
            "reverse_flow_m3_h": reverse_flow_m3_h,
            "totalized_volume_m3": totalized_volume_m3,
            "flow_velocity_m_s": velocity_ms,
            "meter_status": meter_status,
            # Keep legacy names so the rest of the pipeline still works.
            "mean_flow": mean_flow,
            "mean_pressure": mean_pressure,
            # Keep explicit unit-labelled aliases for dashboard or later use.
            "flow_rate_l_min": mean_flow,
            "pressure_bar": mean_pressure,
            "temperature_c": temperature_c,
            "scenario_has_leak": int(has_leak),
            "leak_type": leak_type,
            "leak_magnitude_l_min": leak_magnitude_l_min,
            "leak_start_idx": leak_start_idx,
            "leak_end_idx": leak_end_idx,
            "leak_area_m2": leak_area_m2,
            "leak_node": leak_node if leak_node else "none",
            "simulation_source": "wntr_hydraulic",
        }
    )


def generate_synthetic_fallback() -> None:
    """
    Fallback generation with hydraulic-style signatures when WNTR is unavailable.
    The fallback still emits the legacy columns the feature extractor expects.
    """
    rng = np.random.default_rng(RANDOM_STATE)
    all_data = []
    num_scenarios = get_num_scenarios()

    for i in range(num_scenarios):
        has_leak = bool(rng.choice([0, 1], p=[0.5, 0.5]))
        leak_signature = sample_leak_signature(rng) if has_leak else None
        time_index = np.arange(DAILY_READINGS)
        meter_size_mm = int(rng.choice(METER_SIZE_OPTIONS_MM))

        daily_variation = rng.uniform(0.9, 1.1)
        base_flow = 250 * daily_variation + 100 * np.sin(2 * np.pi * (time_index / DAILY_READINGS - 0.25))
        base_pressure = 4.0 * daily_variation + rng.normal(0, 0.2, DAILY_READINGS)

        demand_pattern = np.zeros(DAILY_READINGS)
        demand_pattern[72:108] = 50.0
        demand_pattern[204:240] = 40.0
        mean_flow = base_flow + demand_pattern
        mean_pressure = base_pressure.copy()

        if leak_signature is not None:
            start_idx = int(leak_signature["start_idx"])
            end_idx = int(leak_signature["end_idx"])
            magnitude = float(leak_signature["magnitude_lpm"])

            # ENHANCED: Make leak signatures more pronounced and realistic
            if leak_signature["leak_type"] == "slow_leak":
                # Slow leaks: gradual flow increase, subtle pressure drop
                ramp_up = np.linspace(0.3, 1.0, min(12, end_idx - start_idx + 1))
                leak_window = slice(start_idx, min(start_idx + len(ramp_up), end_idx + 1))
                mean_flow[leak_window] += magnitude * 0.7 * ramp_up[:len(mean_flow[leak_window])]
                mean_pressure[leak_window] -= magnitude * 0.012 * ramp_up[:len(mean_pressure[leak_window])]
            elif leak_signature["leak_type"] == "moderate_leak":
                # Moderate leaks: noticeable flow increase, clear pressure drop
                ramp_up = np.linspace(0.5, 1.0, min(6, end_idx - start_idx + 1))
                leak_window = slice(start_idx, min(start_idx + len(ramp_up), end_idx + 1))
                mean_flow[leak_window] += magnitude * 1.2 * ramp_up[:len(mean_flow[leak_window])]
                mean_pressure[leak_window] -= magnitude * 0.025 * ramp_up[:len(mean_pressure[leak_window])]
                # Add sustained effect
                sustained_window = slice(min(start_idx + len(ramp_up), end_idx + 1), end_idx + 1)
                mean_flow[sustained_window] += magnitude * 1.2
                mean_pressure[sustained_window] -= magnitude * 0.025
            else:  # extreme_leak
                # Extreme leaks: sharp flow spike, significant pressure drop
                mean_flow[start_idx:end_idx + 1] += magnitude * 1.5
                mean_pressure[start_idx:end_idx + 1] -= magnitude * 0.035
                # Add pressure recovery lag
                recovery_window = slice(end_idx + 1, min(end_idx + 13, DAILY_READINGS))
                recovery_factor = np.linspace(0.5, 0.0, len(mean_pressure[recovery_window]))
                mean_pressure[recovery_window] -= magnitude * 0.015 * recovery_factor

        mean_flow += rng.normal(0, np.maximum(mean_flow * FLOW_NOISE_STD, 0.5), DAILY_READINGS)
        mean_pressure += rng.normal(0, np.maximum(mean_pressure * PRESSURE_NOISE_STD, 0.05), DAILY_READINGS)
        mean_flow = np.clip(mean_flow, FLOW_RANGE[0], FLOW_RANGE[1])
        mean_pressure = np.clip(mean_pressure, PRESSURE_RANGE[0], PRESSURE_RANGE[1])
        temperature = np.clip(
            rng.uniform(15, 25, DAILY_READINGS) + rng.normal(0, 0.5, DAILY_READINGS),
            10,
            30,
        )
        flow_rate_m3_h = np.clip(flow_lpm_to_m3h(mean_flow), METER_MIN_FLOW_M3H, METER_MAX_FLOW_M3H)
        reverse_flow_m3_h = np.where(rng.random(DAILY_READINGS) < 0.01, rng.uniform(0.0, 0.02, DAILY_READINGS), 0.0)
        forward_flow_m3_h = np.clip(flow_rate_m3_h - reverse_flow_m3_h, 0.0, None)
        totalized_volume_m3 = cumulative_totalizer_m3(mean_flow)
        velocity_ms = flow_lpm_to_velocity_ms(mean_flow, meter_size_mm)
        leak_type_for_status = str(leak_signature["leak_type"]) if leak_signature else "none"
        meter_status = build_meter_status(
            leak_type_for_status,
            reverse_flow_m3_h,
            leak_start_idx=int(leak_signature["start_idx"]) if leak_signature else -1,
            leak_end_idx=int(leak_signature["end_idx"]) if leak_signature else -1,
        )

        all_data.append(
            pd.DataFrame(
                {
                    "scenario": i,
                    "time_index": time_index,
                    "timestamp": pd.date_range("2024-01-01", periods=DAILY_READINGS, freq="5min"),
                    "meter_model": METER_MODEL,
                    "meter_size_mm": meter_size_mm,
                    "meter_internal_sample_seconds": METER_INTERNAL_SAMPLE_SECONDS,
                    "meter_output_interval_seconds": METER_READING_INTERVAL,
                    "meter_battery_design_years": METER_BATTERY_LIFE_YEARS,
                    "meter_ingress_rating": METER_INGRESS_RATING,
                    "flow_rate_m3_h": flow_rate_m3_h,
                    "forward_flow_m3_h": forward_flow_m3_h,
                    "reverse_flow_m3_h": reverse_flow_m3_h,
                    "totalized_volume_m3": totalized_volume_m3,
                    "flow_velocity_m_s": velocity_ms,
                    "meter_status": meter_status,
                    "mean_flow": mean_flow,
                    "mean_pressure": mean_pressure,
                    "flow_rate_l_min": mean_flow,
                    "pressure_bar": mean_pressure,
                    "temperature_c": temperature,
                    "scenario_has_leak": int(has_leak),
                    "leak_type": leak_signature["leak_type"] if leak_signature else "none",
                    "leak_magnitude_l_min": float(leak_signature["magnitude_lpm"]) if leak_signature else 0.0,
                    "leak_start_idx": int(leak_signature["start_idx"]) if leak_signature else -1,
                    "leak_end_idx": int(leak_signature["end_idx"]) if leak_signature else -1,
                    "leak_area_m2": float(leak_signature["leak_area_m2"]) if leak_signature else 0.0,
                    "leak_node": "synthetic",
                    "simulation_source": "synthetic_fallback",
                }
            )
        )

        if (i + 1) % 100 == 0:
            print(f"Generated {i + 1}/{NUM_SCENARIOS} scenarios (fallback)")

    pd.concat(all_data, ignore_index=True).to_csv(RAW_DIR / "simulated_leaks.csv", index=False)
    print(f"[OK] Generated {num_scenarios} fallback scenarios with hydraulic-style signatures.")


def generate_scenarios() -> None:
    """Generate scenarios using hydraulic simulation where possible."""
    rng = np.random.default_rng(RANDOM_STATE)
    inp_file = Path(__file__).resolve().parent.parent / "data" / "external" / "hanoi_network.inp"
    num_scenarios = get_num_scenarios()
    output_file = RAW_DIR / "simulated_leaks.csv"

    if not inp_file.exists():
        print(f"ERROR: Network model not found at {inp_file}")
        print("Using fallback synthetic generation")
        generate_synthetic_fallback()
        return

    # Ensure output directory exists and handle file overwrite
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    
    # Check if file exists and warn about overwrite
    if output_file.exists():
        print(f"WARNING: Overwriting existing file: {output_file}")

    all_data = []
    batch_size = 50  # Process in batches to optimize memory usage
    batch_data = []
    
    try:
        for scenario_id in range(num_scenarios):
            try:
                scenario_data = simulate_hydraulic_scenario(inp_file, scenario_id, rng)
                batch_data.append(scenario_data)
                
                # Process batch when it reaches batch_size or at the end
                if len(batch_data) >= batch_size or scenario_id == num_scenarios - 1:
                    if batch_data:
                        batch_df = pd.concat(batch_data, ignore_index=True)
                        all_data.append(batch_df)
                        batch_data = []
                
                # Progress reporting
                if (scenario_id + 1) % 25 == 0:
                    print(f"Generated {scenario_id + 1}/{num_scenarios} hydraulic scenarios")
                    
            except Exception as scenario_exc:
                print(f"WARNING: Failed to generate scenario {scenario_id}: {scenario_exc}")
                continue

        # Concatenate all batches and save with overwrite protection
        if all_data:
            final_df = pd.concat(all_data, ignore_index=True)
            
            # Save with overwrite handling
            try:
                final_df.to_csv(output_file, index=False, mode='w')
                print(f"[OK] Generated {len(final_df)} records from {num_scenarios} hydraulic scenarios using WNTR/EPANET.")
                print(f"Output saved to: {output_file}")
            except PermissionError:
                print(f"ERROR: Permission denied writing to {output_file}")
                print("Please close the file if it's open in another program")
                # Try alternative filename
                alt_file = output_file.with_name(f"simulated_leaks_{int(time.time())}.csv")
                final_df.to_csv(alt_file, index=False)
                print(f"Saved to alternative file: {alt_file}")
        else:
            print("WARNING: No scenarios were successfully generated")
            
    except Exception as exc:
        print(f"ERROR in hydraulic simulation: {exc}")
        print("Falling back to synthetic generation")
        generate_synthetic_fallback()


if __name__ == "__main__":
    generate_scenarios()
