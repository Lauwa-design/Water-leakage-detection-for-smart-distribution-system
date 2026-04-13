"""
THIWASCO SQLite to MySQL Migration Script
Migrates existing SQLite data to MySQL database
"""

import sqlite3
import mysql.connector
import pandas as pd
from datetime import datetime
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def get_sqlite_connection():
    """Get SQLite connection to existing database"""
    return sqlite3.connect("thiwasco_leak_detection.db")

def get_mysql_connection():
    """Get MySQL connection"""
    config = {
        'host': os.getenv('DB_HOST', 'localhost'),
        'user': os.getenv('DB_USER', 'root'),
        'password': os.getenv('DB_PASSWORD', ''),
        'database': os.getenv('DB_NAME', 'thiwasco_leak_detection'),
        'port': int(os.getenv('DB_PORT', 3306))
    }
    return mysql.connector.connect(**config)

def check_existing_data():
    """Check what data exists in SQLite database"""
    try:
        with get_sqlite_connection() as sqlite_conn:
            cursor = sqlite_conn.cursor()
            
            # Check tables and row counts
            tables = ['zones', 'meters', 'sensor_readings', 'leak_predictions', 'alerts']
            data_summary = {}
            
            for table in tables:
                try:
                    cursor.execute(f"SELECT COUNT(*) FROM {table}")
                    count = cursor.fetchone()[0]
                    data_summary[table] = count
                    print(f"SQLite {table}: {count} records")
                except sqlite3.OperationalError:
                    data_summary[table] = 0
                    print(f"SQLite {table}: Table doesn't exist")
            
            return data_summary
            
    except Exception as e:
        print(f"Error checking SQLite data: {e}")
        return {}

def migrate_table(table_name, sqlite_conn, mysql_conn):
    """Migrate a single table from SQLite to MySQL"""
    try:
        print(f"Migrating {table_name}...")
        
        # Read data from SQLite
        df = pd.read_sql_query(f"SELECT * FROM {table_name}", sqlite_conn)
        
        if df.empty:
            print(f"No data to migrate in {table_name}")
            return 0
        
        # Handle timestamp conversions
        if 'timestamp' in df.columns:
            df['timestamp'] = pd.to_datetime(df['timestamp'])
        if 'created_at' in df.columns:
            df['created_at'] = pd.to_datetime(df['created_at'])
        if 'updated_at' in df.columns:
            df['updated_at'] = pd.to_datetime(df['updated_at'])
        if 'installation_date' in df.columns:
            df['installation_date'] = pd.to_datetime(df['installation_date'])
        if 'last_maintenance' in df.columns:
            df['last_maintenance'] = pd.to_datetime(df['last_maintenance'], errors='coerce')
        if 'acknowledged_at' in df.columns:
            df['acknowledged_at'] = pd.to_datetime(df['acknowledged_at'], errors='coerce')
        if 'resolved_at' in df.columns:
            df['resolved_at'] = pd.to_datetime(df['resolved_at'], errors='coerce')
        if 'sent_at' in df.columns:
            df['sent_at'] = pd.to_datetime(df['sent_at'], errors='coerce')
        
        # Insert into MySQL
        cursor = mysql_conn.cursor()
        
        # Prepare column names and placeholders
        columns = df.columns.tolist()
        placeholders = ', '.join(['%s'] * len(columns))
        column_names = ', '.join(columns)
        
        # Prepare data for insertion
        data = [tuple(row) for row in df.itertuples(index=False)]
        
        # Insert data
        insert_query = f"INSERT INTO {table_name} ({column_names}) VALUES ({placeholders})"
        cursor.executemany(insert_query, data)
        
        mysql_conn.commit()
        print(f"Migrated {len(data)} records from {table_name}")
        
        return len(data)
        
    except Exception as e:
        print(f"Error migrating {table_name}: {e}")
        return 0

def migrate_all_data():
    """Migrate all data from SQLite to MySQL"""
    try:
        # Check existing data
        print("=== Checking existing SQLite data ===")
        sqlite_data = check_existing_data()
        
        if not any(sqlite_data.values()):
            print("No data found in SQLite database")
            return False
        
        print(f"\nTotal SQLite records: {sum(sqlite_data.values())}")
        
        # Connect to MySQL
        print("\n=== Connecting to MySQL ===")
        mysql_conn = get_mysql_connection()
        
        # Connect to SQLite
        sqlite_conn = get_sqlite_connection()
        
        # Migrate tables in order of dependencies
        migration_order = ['zones', 'meters', 'sensor_readings', 'leak_predictions', 'alerts']
        total_migrated = 0
        
        for table in migration_order:
            if sqlite_data.get(table, 0) > 0:
                migrated = migrate_table(table, sqlite_conn, mysql_conn)
                total_migrated += migrated
        
        sqlite_conn.close()
        mysql_conn.close()
        
        print(f"\n=== Migration Complete ===")
        print(f"Total records migrated: {total_migrated}")
        
        return True
        
    except Exception as e:
        print(f"Migration error: {e}")
        return False

def backup_sqlite_database():
    """Create backup of existing SQLite database"""
    try:
        import shutil
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_path = f"thiwasco_leak_detection_backup_{timestamp}.db"
        shutil.copy2("thiwasco_leak_detection.db", backup_path)
        print(f"SQLite database backed up to: {backup_path}")
        return backup_path
    except Exception as e:
        print(f"Error creating backup: {e}")
        return None

def main():
    """Main migration function"""
    print("=== THIWASCO SQLite to MySQL Migration ===")
    print()
    
    # Check if SQLite database exists
    if not os.path.exists("thiwasco_leak_detection.db"):
        print("SQLite database not found. No migration needed.")
        print("Proceeding with fresh MySQL setup...")
        return True
    
    # Check MySQL connection
    try:
        mysql_conn = get_mysql_connection()
        mysql_conn.close()
        print("MySQL connection successful")
    except Exception as e:
        print(f"MySQL connection failed: {e}")
        print("Please check your .env configuration")
        return False
    
    # Ask user about migration
    print("\nExisting SQLite database found.")
    print("Options:")
    print("1. Migrate existing data to MySQL")
    print("2. Skip migration (use fresh MySQL setup)")
    print("3. Cancel")
    
    choice = input("\nEnter your choice (1-3): ").strip()
    
    if choice == "1":
        # Create backup
        backup_path = backup_sqlite_database()
        
        # Perform migration
        print("\n=== Starting Migration ===")
        success = migrate_all_data()
        
        if success:
            print("\nMigration completed successfully!")
            print(f"Backup created: {backup_path}")
            print("\nYou can now:")
            print("1. Test the MySQL-based application")
            print("2. Remove the old SQLite database if everything works")
        else:
            print("\nMigration failed. Check the error messages above.")
            return False
            
    elif choice == "2":
        print("\nSkipping migration. Using fresh MySQL setup...")
        # Create backup anyway
        backup_sqlite_database()
        
    elif choice == "3":
        print("\nMigration cancelled.")
        return False
        
    else:
        print("\nInvalid choice. Migration cancelled.")
        return False
    
    return True

if __name__ == "__main__":
    main()
