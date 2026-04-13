"""
THIWASCO Real-Time Data Simulator
Continuously generates sensor data and performs leak detection
"""

import pandas as pd
import numpy as np
import time
import threading
from datetime import datetime, timedelta
from typing import Dict, List
from .leak_detector import predict_leak
from .data_manager import data_manager
from .prediction_service import prediction_service

class RealTimeSimulator:
    """Real-time data simulation and leak detection"""
    
    def __init__(self):
        self.running = False
        self.thread = None
        self.simulation_interval = 5  # seconds
        
        # Base sensor values for each meter
        self.base_values = {
            'HW-THK-001': {'pressure': 3.5, 'flow': 45.0, 'location': 'Thika West'},
            'HW-THK-002': {'pressure': 3.8, 'flow': 48.0, 'location': 'Thika East'},
            'HW-THK-003': {'pressure': 3.2, 'flow': 42.0, 'location': 'Thika North'},
            'HW-THK-004': {'pressure': 3.6, 'flow': 46.0, 'location': 'Thika Central'}
        }
        
        # Leak simulation parameters
        self.leak_probability = 0.15  # 15% chance of leak per cycle
        self.leak_duration = 3  # cycles
    
    def start_simulation(self):
        """Start the real-time simulation in background thread"""
        if not self.running:
            self.running = True
            self.thread = threading.Thread(target=self._simulation_loop, daemon=True)
            self.thread.start()
            print("Real-time simulation started")
    
    def stop_simulation(self):
        """Stop the real-time simulation"""
        self.running = False
        if self.thread:
            self.thread.join()
        print("Real-time simulation stopped")
    
    def _simulation_loop(self):
        """Main simulation loop running in background thread"""
        while self.running:
            try:
                self._generate_sensor_data()
                time.sleep(self.simulation_interval)
            except Exception as e:
                print(f"Simulation error: {e}")
                time.sleep(self.simulation_interval)
    
    def _generate_sensor_data(self):
        """Generate realistic sensor data and perform leak detection"""
        timestamp = datetime.now()
        
        for meter_id, base_data in self.base_values.items():
            # Generate realistic sensor readings with noise
            pressure = float(self._generate_pressure_reading(base_data['pressure']))
            flow = float(self._generate_flow_reading(base_data['flow']))
            
            # Generate additional sensor data
            temperature = float(np.random.normal(22, 2))  # Water temp ~22°C ± 2°C
            battery = int(np.random.randint(85, 100))     # Battery level 85-100%
            signal = int(np.random.randint(3, 5))         # Signal strength 3-5 bars
            quality = 'good' if signal >= 4 else ('fair' if signal == 3 else 'poor')
            
            # Store sensor reading with proper type conversion
            sensor_data = pd.DataFrame([{
                'meter_id': meter_id,
                'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S'),  # Convert datetime to string
                'pressure': pressure,
                'flow_rate': flow,
                'temperature_celsius': temperature,
                'battery_level': battery,
                'signal_strength': signal,
                'reading_quality': quality
            }])
            
            data_manager.store_sensor_readings(sensor_data)
            
            # Perform leak detection
            self._perform_leak_detection(meter_id, pressure, flow, timestamp)
    
    def _generate_pressure_reading(self, base_pressure):
        """Generate realistic pressure reading with noise and potential leak effects"""
        # Add normal noise
        noise = float(np.random.normal(0, 0.1))
        reading = float(base_pressure + noise)
        
        # Simulate occasional pressure drops (potential leaks)
        if np.random.random() < 0.05:  # 5% chance of pressure anomaly
            drop = float(np.random.uniform(0.3, 1.2))
            reading -= drop
        
        return max(0.0, reading)  # Ensure non-negative float
    
    def _generate_flow_reading(self, base_flow):
        """Generate realistic flow reading with noise and potential leak effects"""
        # Add normal noise
        noise = float(np.random.normal(0, 1.5))
        reading = float(base_flow + noise)
        
        # Simulate flow increases (potential leaks)
        if np.random.random() < 0.05:  # 5% chance of flow anomaly
            increase = float(np.random.uniform(5, 15))
            reading += increase
        
        return max(0.0, reading)  # Ensure non-negative float
    
    def _perform_leak_detection(self, meter_id, pressure, flow, timestamp):
        """Perform leak detection for current readings"""
        try:
            # Get recent sensor data for feature extraction
            recent_data = data_manager.get_sensor_readings(meter_id, hours=1, limit=20)
            
            if len(recent_data) >= 5:  # Need minimum data for prediction
                prediction = predict_leak(recent_data, meter_id)
                
                # Ensure prediction has proper timestamp format
                if hasattr(prediction, 'timestamp') and isinstance(prediction.timestamp, datetime):
                    prediction.timestamp = prediction.timestamp.strftime('%Y-%m-%d %H:%M:%S')
                
                prediction_id = data_manager.store_leak_prediction(prediction)
                
                # Create alert if leak detected
                if prediction.leak_detected:
                    self._create_leak_alert(prediction, prediction_id)
                    print(f"LEAK DETECTED: {meter_id} at {timestamp.strftime('%Y-%m-%d %H:%M:%S')} - Severity: {prediction.severity.value}")
                
        except Exception as e:
            print(f"Leak detection error for {meter_id}: {e}")
    
    def _create_leak_alert(self, prediction, prediction_id):
        """Create alert and send notifications for leak detection"""
        try:
            from .alert_manager import alert_manager
            
            # Determine alert type and severity based on prediction
            alert_type = 'critical' if prediction.severity.value == 'instant' else 'warning'
            severity_map = {
                'slow': 'medium',
                'moderate': 'high', 
                'instant': 'critical'
            }
            alert_severity = severity_map.get(prediction.severity.value, 'medium')
            
            # Create alert
            alert_id = alert_manager.create_alert(
                meter_id=prediction.meter_id,
                prediction_id=prediction_id,
                alert_type=alert_type,
                title=f"Leak Detected - {prediction.severity.value.upper()}",
                message=f"Leak detected at {prediction.meter_id}. {prediction.recommendation}",
                severity=alert_severity
            )
            
            if alert_id:
                # Send notifications through multiple channels
                channels = ['email']  # Start with email, can add SMS/webhook later
                alert_manager.send_notifications(alert_id, channels)
                
        except Exception as e:
            print(f"Alert creation error: {e}")
    
    def get_simulation_status(self):
        """Get current simulation status"""
        return {
            'running': self.running,
            'interval': self.simulation_interval,
            'active_meters': list(self.base_values.keys())
        }
    
    def force_leak_simulation(self, meter_id: str, severity: str = 'moderate'):
        """Force a leak simulation for testing"""
        if meter_id in self.base_values:
            # Create leak scenario
            base_data = self.base_values[meter_id]
            
            # Generate leak data
            for i in range(5):  # Generate 5 readings with leak
                timestamp = datetime.now() + timedelta(minutes=i)
                
                # Simulate leak effects
                pressure_drop = np.random.uniform(0.5, 1.5) if severity == 'moderate' else np.random.uniform(1.0, 2.5)
                flow_increase = np.random.uniform(10, 20) if severity == 'moderate' else np.random.uniform(20, 35)
                
                pressure = max(0, base_data['pressure'] - pressure_drop)
                flow = base_data['flow'] + flow_increase
                
                # Store sensor data
                sensor_data = pd.DataFrame([{
                    'meter_id': meter_id,
                    'timestamp': timestamp,
                    'pressure': pressure,
                    'flow_rate': flow,
                    'location': base_data['location']
                }])
                
                data_manager.store_sensor_readings(sensor_data)
            
            # Trigger leak detection
            recent_data = data_manager.get_sensor_readings(meter_id, hours=1, limit=20)
            if len(recent_data) >= 5:
                prediction = predict_leak(recent_data, meter_id)
                data_manager.store_leak_prediction(prediction)
                
                print(f"Forced leak simulation: {meter_id} - {prediction.severity.value}")
                return True
        
        return False

# Global simulator instance
realtime_simulator = RealTimeSimulator()
