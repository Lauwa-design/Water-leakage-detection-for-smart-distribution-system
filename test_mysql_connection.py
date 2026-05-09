#!/usr/bin/env python3
"""Test script to verify MySQL database connection and basic operations."""

import os
import sys
from pathlib import Path

# Add web_app to path
sys.path.insert(0, str(Path(__file__).parent / "web_app"))

def test_mysql_connection():
    """Test MySQL database connection and basic operations."""
    print("Testing MySQL Database Connection...")
    print("=" * 50)
    
    try:
        # Import MySQL database manager
        from backend.mysql_database_manager import db_manager
        
        print("✅ Successfully imported MySQL database manager")
        
        # Test basic connection
        print("\n1. Testing database connection...")
        zones = db_manager.get_all_zones()
        print(f"✅ Connected successfully! Found {len(zones)} zones")
        
        # Test meters
        print("\n2. Testing meters query...")
        meters = db_manager.get_all_meters()
        print(f"✅ Found {len(meters)} meters")
        
        # Test sensor readings
        print("\n3. Testing sensor readings query...")
        readings = db_manager.get_sensor_readings(hours=1)
        print(f"✅ Found {len(readings)} sensor readings in last hour")
        
        # Test alerts
        print("\n4. Testing alerts query...")
        alerts = db_manager.get_alerts(hours=24)
        print(f"✅ Found {len(alerts)} alerts in last 24 hours")
        
        # Test dashboard stats
        print("\n5. Testing dashboard stats...")
        stats = db_manager.get_dashboard_stats()
        print(f"✅ Dashboard stats: {stats}")
        
        # Test seed demo data
        print("\n6. Testing demo data seeding...")
        db_manager.seed_default_users()
        db_manager.seed_default_zones() 
        db_manager.seed_default_meters()
        print("✅ Demo data seeded successfully")
        
        print("\n" + "=" * 50)
        print("🎉 ALL TESTS PASSED! MySQL migration is working correctly.")
        
        return True
        
    except Exception as e:
        print(f"\n❌ ERROR: {type(e).__name__}: {e}")
        print("\nTroubleshooting:")
        print("1. Ensure MySQL server is running")
        print("2. Check environment variables:")
        print("   - MYSQL_HOST (default: localhost)")
        print("   - MYSQL_PORT (default: 3306)")
        print("   - MYSQL_DATABASE (default: thiwasco_05092026)")
        print("   - MYSQL_USER (default: root)")
        print("   - MYSQL_PASSWORD (default: MyNewSecurePassword!)")
        print("3. Ensure database 'thiwasco_05092026' exists")
        print("4. Check MySQL user permissions")
        
        return False

if __name__ == "__main__":
    success = test_mysql_connection()
    sys.exit(0 if success else 1)
