"""
THIWASCO Real-Time Detection Simulator
Start real-time leak detection simulation
"""

import time
import threading
from backend.realtime_simulator import realtime_simulator
from backend.data_manager import data_manager

def main():
    """Main simulation controller"""
    print("🚀 THIWASCO Real-Time Leak Detection Simulator")
    print("=" * 50)
    
    # Initialize database
    print("📊 Initializing database...")
    data_manager.init_database()
    print("✅ Database initialized")
    
    # Start real-time simulation
    print("\n🔄 Starting real-time simulation...")
    print("📡 Generating sensor data every 5 seconds")
    print("🤖 Performing ML leak detection")
    print("📬 Sending alerts when leaks detected")
    print("\nPress Ctrl+C to stop simulation")
    print("-" * 50)
    
    try:
        realtime_simulator.start_simulation()
        
        # Keep main thread alive
        while realtime_simulator.running:
            time.sleep(1)
            
    except KeyboardInterrupt:
        print("\n\n⏹️  Stopping simulation...")
        realtime_simulator.stop_simulation()
        print("✅ Simulation stopped successfully")
    
    print("\n📈 Simulation Summary:")
    print(f"📊 Total sensor readings generated: {len(data_manager.get_sensor_readings().index)}")
    print(f"🚨 Total leak predictions: {len(data_manager.get_leak_predictions().index)}")
    print(f"📬 Total alerts created: {len(data_manager.get_alerts().index)}")
    
    print("\n🎉 Simulation complete! Check the dashboard for results.")

if __name__ == "__main__":
    main()
