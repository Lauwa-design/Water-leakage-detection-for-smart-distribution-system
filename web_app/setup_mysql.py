"""
THIWASCO MySQL Database Setup Script
Creates MySQL database and initializes with sample data
"""

import mysql.connector
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def create_database():
    """Create the MySQL database if it doesn't exist"""
    try:
        # Connect to MySQL server without specifying database
        config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'user': os.getenv('DB_USER', 'root'),
            'password': os.getenv('DB_PASSWORD', ''),
            'port': int(os.getenv('DB_PORT', 3306))
        }
        
        conn = mysql.connector.connect(**config)
        cursor = conn.cursor()
        
        # Create database if it doesn't exist
        cursor.execute(f"CREATE DATABASE IF NOT EXISTS {os.getenv('DB_NAME', 'thiwasco_leak_detection')}")
        print(f"Database '{os.getenv('DB_NAME', 'thiwasco_leak_detection')}' created successfully")
        
        conn.close()
        return True
        
    except Exception as e:
        print(f"Error creating database: {e}")
        return False

def initialize_mysql_data():
    """Initialize MySQL database with sample data"""
    try:
        from backend.data_manager_mysql import data_manager
        
        print("Initializing MySQL database with sample data...")
        data_manager.init_database()
        data_manager.initialize_sample_data()
        
        print("MySQL database setup completed successfully!")
        print(f"Created {len(data_manager.get_zones())} zones")
        print(f"Added {len(data_manager.get_meters())} meters")
        
        return True
        
    except Exception as e:
        print(f"Error initializing data: {e}")
        return False

def main():
    """Main setup function"""
    print("=== THIWASCO MySQL Database Setup ===")
    print()
    
    # Check environment variables
    required_vars = ['DB_HOST', 'DB_USER', 'DB_PASSWORD', 'DB_NAME']
    missing_vars = []
    
    for var in required_vars:
        if not os.getenv(var):
            missing_vars.append(var)
    
    if missing_vars:
        print("Missing required environment variables:")
        for var in missing_vars:
            print(f"  - {var}")
        print()
        print("Please copy .env.example to .env and update with your MySQL credentials")
        return False
    
    print("Environment variables found:")
    print(f"  - MySQL Host: {os.getenv('DB_HOST')}")
    print(f"  - MySQL User: {os.getenv('DB_USER')}")
    print(f"  - MySQL Database: {os.getenv('DB_NAME')}")
    print(f"  - MySQL Port: {os.getenv('DB_PORT', 3306)}")
    print()
    
    # Create database
    if not create_database():
        print("Failed to create database")
        return False
    
    # Initialize data
    if not initialize_mysql_data():
        print("Failed to initialize data")
        return False
    
    print()
    print("=== MySQL Setup Complete ===")
    print("Your THIWASCO leak detection system is now ready with MySQL!")
    print()
    print("Next steps:")
    print("1. Start the web app: streamlit run app_modular.py")
    print("2. Run simulation: python start_simulation.py")
    print("3. Populate intelligence: python setup_intelligence.py")
    
    return True

if __name__ == "__main__":
    main()
