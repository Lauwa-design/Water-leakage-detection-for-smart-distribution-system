"""
THIWASCO Leak Intelligence Setup Script
Populates leak intelligence data for testing and demonstration
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from backend.data_manager import data_manager
from backend.leak_detector import predict_leak

def populate_leak_intelligence(num_predictions=50):
    """Populate leak intelligence with sample predictions"""
    print(f"🧠 Populating leak intelligence with {num_predictions} predictions...")
    
    # Generate sample predictions with realistic data
    predictions = []
    base_time = datetime.now() - timedelta(hours=48)
    
    for i in range(num_predictions):
        timestamp = base_time + timedelta(minutes=i*30)
        
        # Generate realistic sensor features
        pressure = float(np.random.normal(3.5, 0.3))
        flow_rate = float(np.random.normal(45, 5))
        temperature = float(np.random.normal(22, 2))
        battery_level = int(np.random.randint(85, 100))
        signal_strength = int(np.random.randint(3, 5))
        
        # Create feature array for prediction
        features = np.array([pressure, flow_rate, temperature, battery_level, signal_strength])
        
        # Get ML prediction
        prediction_result = predict_leak(features)
        
        predictions.append({
            'meter_id': f'HW-THK-{(i % 4) + 1:03d}',
            'timestamp': timestamp.strftime('%Y-%m-%d %H:%M:%S'),
            'pressure': pressure,
            'flow_rate': flow_rate,
            'temperature_celsius': temperature,
            'battery_level': battery_level,
            'signal_strength': signal_strength,
            'leak_probability': float(prediction_result['probability']),
            'confidence': float(prediction_result['confidence']),
            'severity': prediction_result['severity'],
            'features_used': str(features.tolist()),
            'model_version': '1.0'
        })
    
    # Convert to DataFrame and store
    df = pd.DataFrame(predictions)
    data_manager.store_leak_predictions(df)
    
    print(f"✅ Successfully populated {len(predictions)} leak intelligence records")
    print(f"📊 High confidence predictions: {len(df[df['confidence'] > 0.8])}")
    print(f"🚨 Leak detections: {len(df[df['severity'] != 'none'])}")
    
    return df

def create_sample_leak_scenarios():
    """Create specific leak scenarios for testing"""
    print("🎯 Creating sample leak scenarios...")
    
    scenarios = [
        {
            'meter_id': 'HW-THK-001',
            'timestamp': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'pressure': 2.1,  # Low pressure - potential leak
            'flow_rate': 65.0,  # High flow - potential leak
            'temperature_celsius': 21.5,
            'battery_level': 92,
            'signal_strength': 4,
            'leak_probability': 0.89,
            'confidence': 0.94,
            'severity': 'high',
            'features_used': '[2.1, 65.0, 21.5, 92, 4]',
            'model_version': '1.0'
        },
        {
            'meter_id': 'HW-THK-002',
            'timestamp': (datetime.now() - timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S'),
            'pressure': 1.8,  # Very low pressure - definite leak
            'flow_rate': 78.5,  # Very high flow - definite leak
            'temperature_celsius': 20.8,
            'battery_level': 88,
            'signal_strength': 3,
            'leak_probability': 0.96,
            'confidence': 0.98,
            'severity': 'critical',
            'features_used': '[1.8, 78.5, 20.8, 88, 3]',
            'model_version': '1.0'
        },
        {
            'meter_id': 'HW-THK-003',
            'timestamp': (datetime.now() - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S'),
            'pressure': 3.4,  # Normal pressure
            'flow_rate': 47.2,  # Normal flow
            'temperature_celsius': 22.3,
            'battery_level': 95,
            'signal_strength': 5,
            'leak_probability': 0.12,
            'confidence': 0.85,
            'severity': 'none',
            'features_used': '[3.4, 47.2, 22.3, 95, 5]',
            'model_version': '1.0'
        }
    ]
    
    df = pd.DataFrame(scenarios)
    data_manager.store_leak_predictions(df)
    
    print(f"✅ Created {len(scenarios)} sample leak scenarios")
    return df

if __name__ == "__main__":
    # Initialize database
    data_manager.init_database()
    
    # Populate with sample data
    populate_leak_intelligence(30)
    create_sample_leak_scenarios()
    
    print("\n🎉 Leak intelligence setup complete!")
    print("📱 Check the Leak Intelligence page in the dashboard to see results.")
