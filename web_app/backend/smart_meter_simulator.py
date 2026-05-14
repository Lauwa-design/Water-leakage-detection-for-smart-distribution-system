"""Smart Meter Simulator - Simulates sensor readings and leak scenarios"""
import threading
import time
import random
import numpy as np
from datetime import datetime, timedelta
from enum import Enum
from typing import Dict, List, Optional
import pandas as pd

class LeakType(Enum):
    NONE = "none"
    SLOW = "slow"
    MODERATE = "moderate"
    INSTANT = "instant"

class SmartMeterSimulator:
    def __init__(self):
        self.meters: Dict[str, Dict] = {}
        self.is_running = False
        self.simulation_thread = None
        self.leak_scenarios: Dict[str, Dict] = {}
        self.data_buffer: Dict[str, List[Dict]] = {}
        self._lock = threading.Lock()
    
    def add_meter(self, meter_id: str, zone_id: str, location: str,
                  base_pressure: float = 65.0, base_flow: float = 0.25):
        """Add a meter to simulate"""
        self.meters[meter_id] = {
            'meter_id': meter_id,
            'zone_id': zone_id,
            'location': location,
            'base_pressure': base_pressure,
            'base_flow': base_flow,
            'status': 'active'
        }
        self.data_buffer[meter_id] = []
    
    def _generate_reading(self, meter_id: str) -> Dict:
        """Generate a sensor reading with hydraulic-based leak simulation"""
        meter = self.meters[meter_id]
        base_pressure = meter['base_pressure']
        base_flow = meter['base_flow']
        
        # Check if there's an active leak scenario
        leak_scenario = self.leak_scenarios.get(meter_id)
        leak_type = LeakType.NONE
        leak_magnitude = 0.0
        
        if leak_scenario:
            end_time = leak_scenario['start_time'] + timedelta(minutes=leak_scenario['duration_minutes'])
            if datetime.now() < end_time:
                leak_type = leak_scenario['leak_type']
                leak_magnitude = leak_scenario['magnitude']
            else:
                # Leak scenario expired
                del self.leak_scenarios[meter_id]
        
        # Base patterns (time-of-day demand)
        hour = datetime.now().hour
        is_night = 0 <= hour < 6
        is_peak = 6 <= hour < 9 or 17 <= hour < 21

        if is_night:
            expected_flow = base_flow * 0.3
            expected_pressure = base_pressure * 0.95
        elif is_peak:
            expected_flow = base_flow * 1.5
            expected_pressure = base_pressure * 0.85
        else:
            expected_flow = base_flow
            expected_pressure = base_pressure

        # Realistic measurement noise — matches training data spread (std_f ≈ 5%,
        # std_p ≈ 0.75%).  Without this every reading in a period is identical,
        # producing all-zero variance features that confuse the classifier.
        expected_flow     = max(0.0, expected_flow     + np.random.normal(0, expected_flow     * 0.05))
        expected_pressure = max(0.0, expected_pressure + np.random.normal(0, expected_pressure * 0.0075))

        # Hydraulic orifice-based leak simulation
        # Flow through orifice: Q = C * A * sqrt(2 * g * h) ~ sqrt(pressure)
        if leak_type == LeakType.INSTANT:
            # Sudden pipe burst - major orifice opening
            orifice_flow = leak_magnitude * np.sqrt(max(0, expected_pressure))
            pressure_loss = leak_magnitude * 80  # Significant hydraulic head loss
            flow_increase = orifice_flow
        elif leak_type == LeakType.MODERATE:
            # Moderate leak - smaller orifice
            orifice_flow = leak_magnitude * 0.5 * np.sqrt(max(0, expected_pressure))
            pressure_loss = leak_magnitude * 40
            flow_increase = orifice_flow
        elif leak_type == LeakType.SLOW:
            # Slow background leak - very small orifice
            orifice_flow = leak_magnitude * 0.2 * np.sqrt(max(0, expected_pressure))
            pressure_loss = leak_magnitude * 15
            flow_increase = orifice_flow
        else:
            pressure_loss = 0
            flow_increase = 0

        # Apply hydraulic principles
        pressure  = max(30, expected_pressure - pressure_loss)
        flow_rate = max(0,  expected_flow     + flow_increase)

        # Temperature varies slightly
        temperature = 20 + np.random.normal(0, 0.5)
        
        reading = {
            'meter_id': meter_id,
            'timestamp': datetime.now(),
            'pressure': pressure,
            'flow_rate': flow_rate,
            'temperature': temperature,
            'is_night': is_night,
            'is_peak': is_peak,
            'leak_type': leak_type.value
        }
        
        return reading
    
    def _simulation_loop(self):
        """Main simulation loop"""
        leak_check_counter = 0
        while self.is_running:
            try:
                for meter_id in self.meters:
                    reading = self._generate_reading(meter_id)
                    
                    # Store in buffer
                    with self._lock:
                        self.data_buffer[meter_id].append(reading)
                        # Keep only last 100 readings
                        if len(self.data_buffer[meter_id]) > 100:
                            self.data_buffer[meter_id] = self.data_buffer[meter_id][-100:]
                    
                    # Store in database
                    try:
                        from backend.mysql_database_manager import db_manager
                        db_manager.add_sensor_reading(
                            meter_id=reading['meter_id'],
                            pressure=reading['pressure'],
                            flow_rate=reading['flow_rate'],
                            temperature=reading['temperature']
                        )
                    except Exception as e:
                        print(f"Error storing reading: {e}")

                    # Note: ML predictions are handled by the prediction_loop service
                    # Simulator only writes sensor readings, keeping concerns separate

                # Realistic leak injection: max 3 concurrent leaks, ~10% chance every 2 min
                MAX_CONCURRENT_LEAKS = 3
                leak_check_counter += 1

                # Check every 24 cycles (~2 min); 10% probability → realistic leak rate
                if len(self.leak_scenarios) < MAX_CONCURRENT_LEAKS:
                    if leak_check_counter % 24 == 0 and random.random() < 0.10:  # ~10% every 2 min
                        # Pick a random meter that doesn't already have a leak
                        available_meters = [m for m in self.meters if m not in self.leak_scenarios]
                        if available_meters:
                            target_meter = random.choice(available_meters)
                            # Choose leak type with realistic distribution (mostly small leaks)
                            leak_roll = random.random()
                            if leak_roll < 0.7:  # 70% small/slow leaks
                                leak_type = LeakType.SLOW
                                magnitude = random.uniform(0.05, 0.2)
                                duration = random.randint(30, 120)  # 30min to 2hrs
                            elif leak_roll < 0.9:  # 20% moderate leaks
                                leak_type = LeakType.MODERATE
                                magnitude = random.uniform(0.2, 0.5)
                                duration = random.randint(15, 45)
                            else:  # 10% instant/burst leaks (rare)
                                leak_type = LeakType.INSTANT
                                magnitude = random.uniform(0.5, 0.9)
                                duration = random.randint(5, 20)

                            self.trigger_leak_scenario(target_meter, leak_type, magnitude, duration)
                            meter_info = self.meters[target_meter]
                            print(f"[SIM] Leak {len(self.leak_scenarios)}/{MAX_CONCURRENT_LEAKS}: {target_meter} ({meter_info['location']}) - {leak_type.value}, mag={magnitude:.2f}, dur={duration}min")
                
                time.sleep(5)  # Generate reading every 5 seconds
            except Exception as e:
                print(f"Simulation error: {e}")
                time.sleep(5)
    
    def start_simulation(self):
        """Start the simulation thread"""
        if not self.is_running:
            self.is_running = True
            self.simulation_thread = threading.Thread(target=self._simulation_loop)
            self.simulation_thread.daemon = True
            self.simulation_thread.start()
            print(f"Simulation started with {len(self.meters)} meters")
    
    def stop_simulation(self):
        """Stop the simulation thread"""
        self.is_running = False
        if self.simulation_thread:
            self.simulation_thread.join(timeout=1)
        print("Simulation stopped")
    
    def trigger_leak_scenario(self, meter_id: str, leak_type: LeakType,
                             magnitude: float, duration_minutes: int = 30):
        """Trigger a leak scenario for testing"""
        if meter_id not in self.meters:
            print(f"Meter {meter_id} not found")
            return
        
        self.leak_scenarios[meter_id] = {
            'leak_type': leak_type,
            'magnitude': magnitude,
            'start_time': datetime.now(),
            'duration_minutes': duration_minutes
        }
        print(f"Leak scenario triggered: {meter_id} - {leak_type.value} for {duration_minutes}min")
    
    def get_recent_readings(self, meter_id: str, n: int = 20) -> pd.DataFrame:
        """Get recent readings from buffer"""
        with self._lock:
            if meter_id in self.data_buffer:
                readings = self.data_buffer[meter_id][-n:]
                return pd.DataFrame(readings)
            return pd.DataFrame()

def setup_sample_meters():
    """Setup sample meters from database"""
    from backend.mysql_database_manager import db_manager

    # Get all meters from database
    meters_df = db_manager.get_all_meters()

    if not meters_df.empty:
        for _, meter in meters_df.iterrows():
            meter_id = meter['meter_id']
            zone_id = meter['zone_id']
            location = meter['location']
            flow_rate = meter['flow_rate']

            # Use database flow rate and a reasonable pressure (from training data ~40-50)
            smart_meter_simulator.add_meter(meter_id, zone_id, location, base_pressure=45.0, base_flow=flow_rate)

# Global instance
smart_meter_simulator = SmartMeterSimulator()
