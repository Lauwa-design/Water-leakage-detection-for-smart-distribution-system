"""Generate improved synthetic leak data with enhanced signatures - bypasses WNTR dependency."""

import sys
from pathlib import Path
import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parent
sys.path.append(str(REPO_ROOT))

from src.utils.config import (
    DAILY_READINGS,
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
    EXTREME_LEAK_THRESHOLD,
)


def pipe_area_m2(meter_size_mm: int) -> float:
    diameter_m = meter_size_mm / 1000.0
    return np.pi * (diameter_m ** 2) / 4.0


def flow_lpm_to_m3h(flow_lpm):
    return np.asarray(flow_lpm) * 0.06 if isinstance(flow_lpm, np.ndarray) else flow_lpm * 0.06


def flow_lpm_to_velocity_ms(flow_lpm, meter_size_mm):
    flow_m3s = flow_lpm / 60000.0
    velocity = flow_m3s / max(pipe_area_m2(meter_size_mm), 1e-6)
    return np.clip(velocity, METER_VELOCITY_RANGE_MS[0], METER_VELOCITY_RANGE_MS[1])


def cumulative_totalizer_m3(flow_lpm):
    interval_minutes = METER_READING_INTERVAL / 60.0
    volume_per_interval_m3 = (flow_lpm * interval_minutes) / 1000.0
    return np.cumsum(volume_per_interval_m3)


def build_meter_status(leak_type, reverse_flow_m3h, leak_start_idx=-1, leak_end_idx=-1):
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


def sample_leak_signature(rng):
    """Sample a leak type with enhanced hydraulic signature."""
    magnitude_lpm = float(rng.uniform(SLOW_LEAK_THRESHOLD, LEAK_MAG_MAX))

    if magnitude_lpm >= EXTREME_LEAK_THRESHOLD:
        leak_type = "extreme_leak"
        start_idx = int(rng.integers(72, 240))
        duration_steps = int(rng.integers(6, 25))
    elif magnitude_lpm >= MODERATE_LEAK_THRESHOLD:
        leak_type = "moderate_leak"
        start_idx = int(rng.integers(48, 228))
        duration_steps = int(rng.integers(24, 73))
    elif magnitude_lpm >= SLOW_LEAK_THRESHOLD:
        leak_type = "slow_leak"
        start_idx = int(rng.integers(0, 216))
        duration_steps = int(rng.integers(48, 169))
    else:
        leak_type = "slow_leak"
        start_idx = int(rng.integers(0, 144))
        duration_steps = int(rng.integers(72, 193))

    end_idx = min(start_idx + duration_steps, DAILY_READINGS - 1)
    
    return {
        "leak_type": leak_type,
        "magnitude_lpm": magnitude_lpm,
        "start_idx": start_idx,
        "end_idx": end_idx,
        "leak_area_m2": magnitude_lpm * 0.0001,  # Simplified
    }


def generate_improved_scenarios():
    """Generate scenarios with ENHANCED leak signatures."""
    rng = np.random.default_rng(RANDOM_STATE)
    all_data = []

    print(f"Generating {NUM_SCENARIOS} scenarios with ENHANCED leak signatures...")

    for i in range(NUM_SCENARIOS):
        has_leak = bool(rng.choice([0, 1], p=[0.5, 0.5]))
        leak_signature = sample_leak_signature(rng) if has_leak else None
        time_index = np.arange(DAILY_READINGS)
        meter_size_mm = int(rng.choice(METER_SIZE_OPTIONS_MM))

        # Base patterns
        daily_variation = rng.uniform(0.9, 1.1)
        base_flow = 250 * daily_variation + 100 * np.sin(2 * np.pi * (time_index / DAILY_READINGS - 0.25))
        base_pressure = 4.0 * daily_variation + rng.normal(0, 0.2, DAILY_READINGS)

        # Demand patterns
        demand_pattern = np.zeros(DAILY_READINGS)
        demand_pattern[72:108] = 50.0  # Morning peak
        demand_pattern[204:240] = 40.0  # Evening peak
        mean_flow = base_flow + demand_pattern
        mean_pressure = base_pressure.copy()

        # ENHANCED LEAK SIGNATURES
        if leak_signature is not None:
            start_idx = int(leak_signature["start_idx"])
            end_idx = int(leak_signature["end_idx"])
            magnitude = float(leak_signature["magnitude_lpm"])

            if leak_signature["leak_type"] == "slow_leak":
                # Gradual ramp-up
                ramp_up = np.linspace(0.3, 1.0, min(12, end_idx - start_idx + 1))
                leak_window = slice(start_idx, min(start_idx + len(ramp_up), end_idx + 1))
                mean_flow[leak_window] += magnitude * 0.7 * ramp_up[:len(mean_flow[leak_window])]
                mean_pressure[leak_window] -= magnitude * 0.012 * ramp_up[:len(mean_pressure[leak_window])]
            elif leak_signature["leak_type"] == "moderate_leak":
                # Faster ramp-up with sustained effect
                ramp_up = np.linspace(0.5, 1.0, min(6, end_idx - start_idx + 1))
                leak_window = slice(start_idx, min(start_idx + len(ramp_up), end_idx + 1))
                mean_flow[leak_window] += magnitude * 1.2 * ramp_up[:len(mean_flow[leak_window])]
                mean_pressure[leak_window] -= magnitude * 0.025 * ramp_up[:len(mean_pressure[leak_window])]
                # Sustained effect
                sustained_window = slice(min(start_idx + len(ramp_up), end_idx + 1), end_idx + 1)
                mean_flow[sustained_window] += magnitude * 1.2
                mean_pressure[sustained_window] -= magnitude * 0.025
            else:  # extreme_leak
                # Sharp spike with pressure recovery lag
                mean_flow[start_idx:end_idx + 1] += magnitude * 1.5
                mean_pressure[start_idx:end_idx + 1] -= magnitude * 0.035
                # Pressure recovery lag
                recovery_window = slice(end_idx + 1, min(end_idx + 13, DAILY_READINGS))
                recovery_factor = np.linspace(0.5, 0.0, len(mean_pressure[recovery_window]))
                mean_pressure[recovery_window] -= magnitude * 0.015 * recovery_factor

        # Add noise
        mean_flow += rng.normal(0, np.maximum(mean_flow * FLOW_NOISE_STD, 0.5), DAILY_READINGS)
        mean_pressure += rng.normal(0, np.maximum(mean_pressure * PRESSURE_NOISE_STD, 0.05), DAILY_READINGS)
        mean_flow = np.clip(mean_flow, FLOW_RANGE[0], FLOW_RANGE[1])
        mean_pressure = np.clip(mean_pressure, PRESSURE_RANGE[0], PRESSURE_RANGE[1])
        
        temperature = np.clip(
            rng.uniform(15, 25, DAILY_READINGS) + rng.normal(0, 0.5, DAILY_READINGS),
            10, 30
        )
        
        # Meter readings
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
            pd.DataFrame({
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
                "simulation_source": "synthetic_enhanced",
            })
        )

        if (i + 1) % 100 == 0:
            print(f"  Generated {i + 1}/{NUM_SCENARIOS} scenarios")

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    output_file = RAW_DIR / "simulated_leaks.csv"
    pd.concat(all_data, ignore_index=True).to_csv(output_file, index=False)
    print(f"\n[OK] Generated {NUM_SCENARIOS} scenarios with ENHANCED leak signatures")
    print(f"[OK] Saved to {output_file}")


if __name__ == "__main__":
    generate_improved_scenarios()
