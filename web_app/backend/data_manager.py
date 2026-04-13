"""
THIWASCO Data Manager
Handles data storage and retrieval - no business logic
"""

import sqlite3
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import os
from contextlib import contextmanager
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataManager:
    """Data storage and retrieval - no business logic"""
    
    def __init__(self, db_path: str = "thiwasco_leak_detection.db"):
        self.db_path = db_path
        self.init_database()
    
    @contextmanager
    def get_connection(self):
        """Context manager for database connections"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # Enable dict-like access
        try:
            yield conn
        except Exception as e:
            conn.rollback()
            logger.error(f"Database error: {e}")
            raise
        finally:
            conn.close()
    
    def init_database(self):
        """Initialize database schema with proper constraints"""
        with self.get_connection() as conn:
            # Create zones table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS zones (
                    zone_id TEXT PRIMARY KEY,
                    zone_name TEXT NOT NULL,
                    region TEXT,
                    area_km2 REAL,
                    population_served INTEGER,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            
            # Create meters table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS meters (
                    meter_id TEXT PRIMARY KEY,
                    zone_id TEXT NOT NULL,
                    location TEXT NOT NULL,
                    latitude REAL,
                    longitude REAL,
                    installation_date TEXT NOT NULL,
                    last_maintenance TEXT,
                    meter_type TEXT,
                    pipe_diameter_mm INTEGER,
                    status TEXT DEFAULT 'active',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (zone_id) REFERENCES zones(zone_id),
                    CHECK(status IN ('active', 'inactive', 'maintenance', 'retired'))
                )
            """)
            
            # Create sensor readings table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sensor_readings (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    meter_id TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    pressure REAL NOT NULL,
                    flow_rate REAL NOT NULL,
                    temperature_celsius REAL,
                    battery_level INTEGER,
                    signal_strength INTEGER,
                    reading_quality TEXT DEFAULT 'good',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (meter_id) REFERENCES meters(meter_id),
                    UNIQUE(meter_id, timestamp),
                    CHECK(pressure >= 0 AND flow_rate >= 0),
                    CHECK(reading_quality IN ('good', 'fair', 'poor'))
                )
            """)
            
            # Create leak predictions table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS leak_predictions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    meter_id TEXT NOT NULL,
                    timestamp TIMESTAMP NOT NULL,
                    leak_detected BOOLEAN NOT NULL,
                    severity TEXT NOT NULL,
                    confidence REAL NOT NULL,
                    pressure REAL NOT NULL,
                    flow_rate REAL NOT NULL,
                    pressure_delta REAL,
                    flow_delta REAL,
                    recommendation TEXT,
                    model_version TEXT,
                    features_json TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (meter_id) REFERENCES meters(meter_id),
                    CHECK(confidence >= 0 AND confidence <= 1),
                    CHECK(severity IN ('none', 'slow', 'moderate', 'instant'))
                )
            """)
            
            # Create alerts table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alerts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    meter_id TEXT NOT NULL,
                    prediction_id INTEGER,
                    alert_type TEXT NOT NULL,
                    title TEXT NOT NULL,
                    message TEXT NOT NULL,
                    severity TEXT NOT NULL,
                    status TEXT DEFAULT 'active',
                    acknowledged_by TEXT,
                    acknowledged_at TIMESTAMP,
                    resolved_by TEXT,
                    resolved_at TIMESTAMP,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (meter_id) REFERENCES meters(meter_id),
                    FOREIGN KEY (prediction_id) REFERENCES leak_predictions(id),
                    CHECK(alert_type IN ('critical', 'warning', 'info', 'maintenance')),
                    CHECK(status IN ('active', 'acknowledged', 'resolved', 'false_positive'))
                )
            """)
            
            # Create alert notifications table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS alert_notifications (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    alert_id INTEGER NOT NULL,
                    notification_type TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    status TEXT DEFAULT 'pending',
                    sent_at TIMESTAMP,
                    error_message TEXT,
                    retry_count INTEGER DEFAULT 0,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (alert_id) REFERENCES alerts(id),
                    CHECK(notification_type IN ('email', 'sms', 'push', 'webhook')),
                    CHECK(status IN ('pending', 'sent', 'failed', 'delivered'))
                )
            """)
            
            # Database migration - add missing columns to existing tables
            self._migrate_database(conn)
            
            # Create indexes for performance
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sensor_readings_meter_time ON sensor_readings(meter_id, timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_predictions_meter_time ON leak_predictions(meter_id, timestamp)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_meter_ack ON alerts(meter_id, acknowledged)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_alerts_created_at ON alerts(created_at DESC)")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_alert_notifications_status ON alert_notifications(status)")
            
            # Only create zone_id index if column exists
            if self._column_exists(conn, 'meters', 'zone_id'):
                conn.execute("CREATE INDEX IF NOT EXISTS idx_meters_zone_id ON meters(zone_id)")
            
            conn.commit()
    
    def _migrate_database(self, conn):
        """Handle database migration for existing databases"""
        try:
            # Check and add missing columns to meters table
            meters_columns = self._get_table_columns(conn, 'meters')
            
            if 'zone_id' not in meters_columns:
                conn.execute("ALTER TABLE meters ADD COLUMN zone_id TEXT")
                print("Added zone_id column to meters table")
            
            if 'latitude' not in meters_columns:
                conn.execute("ALTER TABLE meters ADD COLUMN latitude REAL")
                print("Added latitude column to meters table")
            
            if 'longitude' not in meters_columns:
                conn.execute("ALTER TABLE meters ADD COLUMN longitude REAL")
                print("Added longitude column to meters table")
            
            if 'meter_type' not in meters_columns:
                conn.execute("ALTER TABLE meters ADD COLUMN meter_type TEXT")
                print("Added meter_type column to meters table")
            
            if 'pipe_diameter_mm' not in meters_columns:
                conn.execute("ALTER TABLE meters ADD COLUMN pipe_diameter_mm INTEGER")
                print("Added pipe_diameter_mm column to meters table")
            
            # Check and add missing columns to sensor_readings table
            sensor_columns = self._get_table_columns(conn, 'sensor_readings')
            
            if 'temperature_celsius' not in sensor_columns:
                conn.execute("ALTER TABLE sensor_readings ADD COLUMN temperature_celsius REAL")
                print("Added temperature_celsius column to sensor_readings table")
            
            if 'battery_level' not in sensor_columns:
                conn.execute("ALTER TABLE sensor_readings ADD COLUMN battery_level INTEGER")
                print("Added battery_level column to sensor_readings table")
            
            if 'signal_strength' not in sensor_columns:
                conn.execute("ALTER TABLE sensor_readings ADD COLUMN signal_strength INTEGER")
                print("Added signal_strength column to sensor_readings table")
            
            if 'reading_quality' not in sensor_columns:
                conn.execute("ALTER TABLE sensor_readings ADD COLUMN reading_quality TEXT DEFAULT 'good'")
                print("Added reading_quality column to sensor_readings table")
            
            # Check and add missing columns to alerts table
            alerts_columns = self._get_table_columns(conn, 'alerts')
            
            if 'title' not in alerts_columns:
                conn.execute("ALTER TABLE alerts ADD COLUMN title TEXT")
                print("Added title column to alerts table")
            
            if 'severity' not in alerts_columns:
                conn.execute("ALTER TABLE alerts ADD COLUMN severity TEXT")
                print("Added severity column to alerts table")
            
            if 'status' not in alerts_columns:
                conn.execute("ALTER TABLE alerts ADD COLUMN status TEXT DEFAULT 'active'")
                print("Added status column to alerts table")
            
            if 'acknowledged_by' not in alerts_columns:
                conn.execute("ALTER TABLE alerts ADD COLUMN acknowledged_by TEXT")
                print("Added acknowledged_by column to alerts table")
            
            if 'acknowledged_at' not in alerts_columns:
                conn.execute("ALTER TABLE alerts ADD COLUMN acknowledged_at TIMESTAMP")
                print("Added acknowledged_at column to alerts table")
            
            if 'resolved_by' not in alerts_columns:
                conn.execute("ALTER TABLE alerts ADD COLUMN resolved_by TEXT")
                print("Added resolved_by column to alerts table")
            
            if 'resolved_at' not in alerts_columns:
                conn.execute("ALTER TABLE alerts ADD COLUMN resolved_at TIMESTAMP")
                print("Added resolved_at column to alerts table")
            
        except Exception as e:
            print(f"Migration error: {e}")
    
    def _get_table_columns(self, conn, table_name):
        """Get column names for a table"""
        try:
            cursor = conn.execute(f"PRAGMA table_info({table_name})")
            return [row[1] for row in cursor.fetchall()]
        except:
            return []
    
    def _column_exists(self, conn, table_name, column_name):
        """Check if a column exists in a table"""
        return column_name in self._get_table_columns(conn, table_name)
    
    def add_zone(self, zone_id: str, zone_name: str, region: str = None, area_km2: float = None, population_served: int = None):
        """Add a new zone"""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO zones (zone_id, zone_name, region, area_km2, population_served)
                VALUES (?, ?, ?, ?, ?)
            """, (zone_id, zone_name, region, area_km2, population_served))
            conn.commit()
    
    def add_meter(self, meter_id: str, zone_id: str = None, location: str = None, installation_date: str = None, 
                  last_maintenance: str = None, meter_type: str = None, pipe_diameter_mm: int = None,
                  latitude: float = None, longitude: float = None):
        """Add a new meter with zone information (zone_id optional for existing meters)"""
        with self.get_connection() as conn:
            # Check if meter exists and has zone_id
            if zone_id is None:
                cursor = conn.execute("SELECT zone_id FROM meters WHERE meter_id = ?", (meter_id,))
                existing = cursor.fetchone()
                if existing and existing[0]:
                    zone_id = existing[0]  # Use existing zone_id
                else:
                    zone_id = 'ZONE-001'  # Default zone if none exists
            
            # Handle missing location/date for existing meters
            if location is None:
                cursor = conn.execute("SELECT location FROM meters WHERE meter_id = ?", (meter_id,))
                existing = cursor.fetchone()
                location = existing[0] if existing else 'Unknown Location'
            
            if installation_date is None:
                cursor = conn.execute("SELECT installation_date FROM meters WHERE meter_id = ?", (meter_id,))
                existing = cursor.fetchone()
                installation_date = existing[0] if existing else '2023-01-01'
            
            conn.execute("""
                INSERT OR REPLACE INTO meters 
                (meter_id, zone_id, location, latitude, longitude, installation_date, last_maintenance, meter_type, pipe_diameter_mm)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (meter_id, zone_id, location, latitude, longitude, installation_date, last_maintenance, meter_type, pipe_diameter_mm))
            conn.commit()
    
    def store_sensor_reading(self, meter_id: str, timestamp: datetime, pressure: float, flow_rate: float,
                         temperature_celsius: float = None, battery_level: int = None, 
                         signal_strength: int = None, reading_quality: str = 'good'):
        """Store a single sensor reading with additional fields"""
        with self.get_connection() as conn:
            conn.execute("""
                INSERT OR REPLACE INTO sensor_readings 
                (meter_id, timestamp, pressure, flow_rate, temperature_celsius, battery_level, signal_strength, reading_quality)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """, (meter_id, timestamp, pressure, flow_rate, temperature_celsius, battery_level, signal_strength, reading_quality))
            conn.commit()
    
    def store_sensor_readings(self, readings_df: pd.DataFrame):
        """Store sensor readings from DataFrame"""
        if readings_df.empty:
            return
        
        with self.get_connection() as conn:
            data = [
                (row['meter_id'], row['timestamp'], row['pressure'], row['flow_rate'])
                for _, row in readings_df.iterrows()
            ]
            
            conn.executemany("""
                INSERT OR REPLACE INTO sensor_readings (meter_id, timestamp, pressure, flow_rate)
                VALUES (?, ?, ?, ?)
            """, data)
            conn.commit()
    
    def initialize_sample_data(self):
        """Initialize sample zones and meters data"""
        try:
            # Add sample zones covering entire THIWASCO service area
            sample_zones = [
                # Thika Urban Core Zones
                ('ZONE-001', 'Thika West', 'Central Region', 15.5, 45000),
                ('ZONE-002', 'Thika East', 'Central Region', 12.3, 38000),
                ('ZONE-003', 'Thika North', 'Central Region', 18.7, 52000),
                ('ZONE-004', 'Thika South', 'Central Region', 10.2, 31000),
                ('ZONE-005', 'Thika Central', 'Central Region', 8.9, 28000),
                
                # Major Estates & Key Areas
                ('ZONE-006', 'Makongeni Estate', 'Central Region', 25.3, 85000),
                ('ZONE-007', 'Section 9', 'Central Region', 18.9, 120000),
                ('ZONE-008', 'Kisii', 'Central Region', 22.4, 95000),
                ('ZONE-009', 'Umoja', 'Central Region', 31.2, 180000),
                ('ZONE-010', 'Nanasi', 'Central Region', 28.7, 75000),
                ('ZONE-011', 'UTI/USAID', 'Central Region', 19.8, 65000),
                ('ZONE-012', 'Kiboko', 'Central Region', 16.5, 45000),
                ('ZONE-013', 'TUDC', 'North Region', 35.6, 55000),
                ('ZONE-014', 'Ofafa', 'North Region', 42.1, 38000),
                ('ZONE-015', 'Starehe (JAMAFOSTA)', 'North Region', 28.9, 62000),
                ('ZONE-016', 'Kimathi', 'North Region', 24.7, 48000),
                ('ZONE-017', 'Kang\'oki', 'North Region', 33.2, 51000),
                ('ZONE-018', 'Kamuthi Farmers', 'North Region', 45.8, 35000),
                ('ZONE-019', 'Kimunye', 'North Region', 38.4, 42000),
                ('ZONE-020', 'Kiganjo', 'North Region', 29.6, 58000),
                ('ZONE-021', 'Kamenu', 'North Region', 31.8, 67000),
                ('ZONE-022', 'Kwa Jomo', 'North Region', 27.3, 89000),
                ('ZONE-023', 'Landless', 'North Region', 36.1, 41000),
                ('ZONE-024', 'Gatundu Phase II', 'North Region', 41.7, 73000),
                ('ZONE-025', 'Mwana Wi Kio', 'North Region', 33.9, 95000),
                ('ZONE-026', 'Gachagi', 'North Region', 39.4, 86000),
                ('ZONE-027', '12th Battalion', 'North Region', 22.1, 12000),
                ('ZONE-028', 'Abduba', 'North Region', 30.5, 28000),
                ('ZONE-029', 'Kamenu', 'South Region', 26.8, 92000),
                ('ZONE-030', 'Kimunye', 'South Region', 34.2, 78000),
                ('ZONE-031', 'Kiganjo', 'South Region', 29.1, 65000),
                ('ZONE-032', 'Kamuthi', 'South Region', 37.6, 84000),
                ('ZONE-033', 'Kimunye', 'South Region', 32.4, 71000),
                ('ZONE-034', 'Kwa Jomo', 'South Region', 28.9, 95000),
                ('ZONE-035', 'Landless', 'South Region', 35.7, 52000),
                ('ZONE-036', 'Gatundu Phase II', 'South Region', 40.1, 88000),
                ('ZONE-037', 'Mwana Wi Kio', 'South Region', 31.5, 91000),
                ('ZONE-038', 'Gachagi', 'South Region', 38.2, 83000),
                ('ZONE-039', '12th Battalion', 'South Region', 25.4, 15000),
                ('ZONE-040', 'Abduba', 'South Region', 29.8, 31000),
                
                # Facebook & Special Areas
                ('ZONE-041', 'Facebook', 'Special Zone', 15.6, 2500),
                ('ZONE-042', 'Pilot', 'Special Zone', 8.9, 1800),
                ('ZONE-043', 'YMCA/Runda', 'Special Zone', 12.3, 3500),
                ('ZONE-044', 'Kiganjo', 'Special Zone', 18.7, 4200),
                ('ZONE-045', 'Kamuthi Farmers', 'Special Zone', 22.1, 2800),
                ('ZONE-046', 'Kimunye', 'Special Zone', 19.8, 5100),
                ('ZONE-047', 'Kang'oki', 'Special Zone', 26.4, 6700),
                ('ZONE-048', 'Kamenu', 'Special Zone', 31.2, 8900),
                ('ZONE-049', 'Kwa Jomo', 'Special Zone', 27.3, 9500),
                ('ZONE-050', 'Landless', 'Special Zone', 36.1, 4100)
            ]
            
            for zone_id, zone_name, region, area_km2, population in sample_zones:
                self.add_zone(zone_id, zone_name, region, area_km2, population)
            
            # Add sample meters distributed across all THIWASCO service areas
            sample_meters = [
                # Thika Urban Core Zones
                ('HW-THK-001', 'ZONE-001', 'Makongeni Primary School', -1.0331, 37.0714, '2023-01-15', '2023-12-01', 'Residential', 100),
                ('HW-THK-002', 'ZONE-001', 'Thika Town Market', -1.0345, 37.0723, '2023-01-20', '2023-11-15', 'Commercial', 150),
                ('HW-THK-003', 'ZONE-002', 'Nairobi Highway Junction', -1.0356, 37.0689, '2023-02-01', '2023-12-10', 'Industrial', 200),
                ('HW-THK-004', 'ZONE-002', 'Residential Estate Phase 2', -1.0367, 37.0678, '2023-02-10', None, 'Residential', 100),
                ('HW-THK-005', 'ZONE-003', 'Thika North Industrial', -1.0342, 37.0695, '2023-03-01', '2023-12-15', 'Industrial', 250),
                ('HW-THK-006', 'ZONE-003', 'North Residential Estate', -1.0338, 37.0701, '2023-03-15', '2023-12-01', 'Residential', 120),
                
                # Major Estates & Key Areas
                ('HW-THK-007', 'ZONE-006', 'Makongeni Estate', -1.0335, 37.0712, '2023-01-15', '2023-12-01', 'Residential', 200),
                ('HW-THK-008', 'ZONE-007', 'Section 9 HQ', -1.0342, 37.0720, '2023-01-20', '2023-11-15', 'Commercial', 300),
                ('HW-THK-009', 'ZONE-008', 'Kisii Township', -1.0356, 37.0685, '2023-02-01', '2023-12-10', 'Commercial', 250),
                ('HW-THK-010', 'ZONE-009', 'Umoja Center', -1.0348, 37.0690, '2023-02-10', '2023-12-01', 'Commercial', 200),
                ('HW-THK-011', 'ZONE-010', 'Nanasi Tech Hub', -1.0339, 37.0695, '2023-02-20', '2023-11-30', 'Commercial', 180),
                ('HW-THK-012', 'ZONE-011', 'UTI/USAID', -1.0341, 37.0710, '2023-02-10', '2023-12-01', 'Commercial', 220),
                ('HW-THK-013', 'ZONE-012', 'Kiboko', -1.0343, 37.0697, '2023-02-20', '2023-11-30', 'Commercial', 190),
                ('HW-THK-014', 'ZONE-013', 'TUDC', -1.0337, 37.0692, '2023-02-20', '2023-11-30', 'Commercial', 210),
                ('HW-THK-015', 'ZONE-014', 'Ofafa', -1.0336, 37.0688, '2023-02-20', '2023-11-30', 'Commercial', 160),
                ('HW-THK-016', 'ZONE-015', 'Starehe (JAMAFOSTA)', -1.0334, 37.0691, '2023-02-20', '2023-11-30', 'Commercial', 140),
                ('HW-THK-017', 'ZONE-016', 'Kimathi', -1.0335, 37.0693, '2023-02-20', '2023-11-30', 'Commercial', 170),
                ('HW-THK-018', 'ZONE-017', 'Kang'oki', -1.0332, 37.0694, '2023-02-20', '2023-11-30', 'Commercial', 150),
                ('HW-THK-019', 'ZONE-018', 'Kamenu', -1.0333, 37.0695, '2023-02-20', '2023-11-30', 'Commercial', 130),
                ('HW-THK-020', 'ZONE-019', 'Kimunye', -1.0331, 37.0696, '2023-02-20', '2023-11-30', 'Commercial', 120),
                ('HW-THK-021', 'ZONE-020', 'Kiganjo', -1.0330, 37.0697, '2023-02-20', '2023-11-30', 'Commercial', 110),
                ('HW-THK-022', 'ZONE-021', 'Kamuthi', -1.0332, 37.0693, '2023-02-20', '2023-11-30', 'Commercial', 100),
                ('HW-THK-023', 'ZONE-022', 'Kwa Jomo', -1.0331, 37.0694, '2023-02-20', '2023-11-30', 'Commercial', 90),
                ('HW-THK-024', 'ZONE-023', 'Landless', -1.0330, 37.0695, '2023-02-20', '2023-11-30', 'Commercial', 80),
                ('HW-THK-025', 'ZONE-024', 'Gatundu Phase II', -1.0329, 37.0698, '2023-02-20', '2023-11-30', 'Commercial', 70),
                ('HW-THK-026', 'ZONE-025', 'Mwana Wi Kio', -1.0331, 37.0696, '2023-02-20', '2023-11-30', 'Commercial', 95),
                ('HW-THK-027', 'ZONE-026', 'Gachagi', -1.0328, 37.0697, '2023-02-20', '2023-11-30', 'Commercial', 86),
                ('HW-THK-028', 'ZONE-027', '12th Battalion', -1.0330, 37.0695, '2023-02-20', '2023-11-30', 'Commercial', 60),
                ('HW-THK-029', 'ZONE-028', 'Abduba', -1.0327, 37.0694, '2023-02-20', '2023-11-30', 'Commercial', 50),
                ('HW-THK-030', 'ZONE-029', 'Kamenu', -1.0326, 37.0693, '2023-02-20', '2023-11-30', 'Commercial', 40),
                
                # Facebook & Special Areas
                ('HW-THK-031', 'ZONE-041', 'Facebook Campus', -1.0332, 37.0692, '2023-02-20', '2023-11-30', 'Special', 250),
                ('HW-THK-032', 'ZONE-042', 'Pilot', -1.0331, 37.0691, '2023-02-20', '2023-11-30', 'Special', 180),
                ('HW-THK-033', 'ZONE-043', 'YMCA/Runda', -1.0329, 37.0690, '2023-02-20', '2023-11-30', 'Special', 350),
                ('HW-THK-034', 'ZONE-044', 'Kiganjo', -1.0325, 37.0687, '2023-02-20', '2023-11-30', 'Special', 420),
                ('HW-THK-035', 'ZONE-045', 'Kamuthi Farmers', -1.0328, 37.0686, '2023-02-20', '2023-11-30', 'Special', 280),
                ('HW-THK-036', 'ZONE-046', 'Kimunye', -1.0327, 37.0685, '2023-02-20', '2023-11-30', 'Special', 510),
                ('HW-THK-037', 'ZONE-047', 'Kang'oki', -1.0326, 37.0684, '2023-02-20', '2023-11-30', 'Special', 670),
                ('HW-THK-038', 'ZONE-048', 'Kamenu', -1.0325, 37.0683, '2023-02-20', '2023-11-30', 'Special', 950),
                ('HW-THK-039', 'ZONE-049', 'Kwa Jomo', -1.0324, 37.0682, '2023-02-20', '2023-11-30', 'Special', 890),
                ('HW-THK-040', 'ZONE-050', 'Landless', -1.0323, 37.0681, '2023-02-20', '2023-11-30', 'Special', 410)
            ]
            
            for meter_id, zone_id, location, lat, lon, install_date, last_maint, meter_type, pipe_dia in sample_meters:
                # Check if meter exists and needs zone_id
                with self.get_connection() as conn:
                    cursor = conn.execute("SELECT zone_id FROM meters WHERE meter_id = ?", (meter_id,))
                    existing = cursor.fetchone()
                    
                    if not existing or not existing[0]:  # Meter doesn't exist or has no zone_id
                        self.add_meter(meter_id, zone_id, location, install_date, last_maint, meter_type, pipe_dia, lat, lon)
                        print(f"Added/updated meter {meter_id} with zone {zone_id}")
                    else:
                        print(f"Meter {meter_id} already exists with zone {existing[0]}")
                        
        except Exception as e:
            print(f"Error initializing sample data: {e}")
    
    def store_sensor_readings_batch(self, readings: List[Dict]):
        """Store multiple sensor readings efficiently"""
        if not readings:
            return
        
        with self.get_connection() as conn:
            data = [(r['meter_id'], r['timestamp'], r['pressure'], r['flow_rate']) 
                   for r in readings]
            
            conn.executemany("""
                INSERT OR REPLACE INTO sensor_readings (meter_id, timestamp, pressure, flow_rate)
                VALUES (?, ?, ?, ?)
            """, data)
            conn.commit()
    
    def get_sensor_readings(self, meter_id: str = None, hours: int = None, start_time: datetime = None, 
                          end_time: datetime = None, limit: int = None) -> pd.DataFrame:
        """Retrieve sensor readings for a meter or all meters"""
        if meter_id:
            query = "SELECT * FROM sensor_readings WHERE meter_id = ?"
            params = [meter_id]
        else:
            query = "SELECT * FROM sensor_readings"
            params = []
        
        if hours:
            from datetime import datetime, timedelta
            start_time = datetime.now() - timedelta(hours=hours)
            query += " AND timestamp >= ?"
            params.append(start_time)
        elif start_time:
            query += " AND timestamp >= ?"
            params.append(start_time)
        
        if end_time:
            query += " AND timestamp <= ?"
            params.append(end_time)
        
        query += " ORDER BY timestamp DESC"
        
        if limit:
            query += f" LIMIT {limit}"
        
        with self.get_connection() as conn:
            df = pd.read_sql_query(query, conn, params=params)
            return df
    
    def store_leak_prediction(self, prediction):
        """Store a leak prediction result"""
        with self.get_connection() as conn:
            import json
            features_json = json.dumps(prediction.features_used)
            
            # Convert datetime to string if needed
            timestamp = prediction.timestamp
            if hasattr(timestamp, 'strftime'):
                timestamp = timestamp.strftime('%Y-%m-%d %H:%M:%S')
            
            # Convert numpy types to Python native types
            confidence = float(prediction.confidence) if hasattr(prediction.confidence, 'item') else prediction.confidence
            pressure = float(prediction.pressure) if hasattr(prediction.pressure, 'item') else prediction.pressure
            flow_rate = float(prediction.flow_rate) if hasattr(prediction.flow_rate, 'item') else prediction.flow_rate
            
            pressure_delta = None
            if prediction.pressure_delta is not None:
                pressure_delta = float(prediction.pressure_delta) if hasattr(prediction.pressure_delta, 'item') else prediction.pressure_delta
            
            flow_delta = None
            if prediction.flow_delta is not None:
                flow_delta = float(prediction.flow_delta) if hasattr(prediction.flow_delta, 'item') else prediction.flow_delta
            
            conn.execute("""
                INSERT INTO leak_predictions 
                (meter_id, timestamp, leak_detected, severity, confidence, pressure, 
                 flow_rate, pressure_delta, flow_delta, recommendation, model_version, features_json)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                prediction.meter_id,
                timestamp,
                bool(prediction.leak_detected),
                prediction.severity.value,
                confidence,
                pressure,
                flow_rate,
                pressure_delta,
                flow_delta,
                prediction.recommendation,
                prediction.model_version,
                features_json
            ))
            
            prediction_id = conn.lastrowid
            conn.commit()
            
            # Create alert if leak detected
            if prediction.leak_detected:
                self._create_alert(conn, prediction.meter_id, prediction_id, prediction.severity, prediction.recommendation)
            
            return prediction_id
    
    def _create_alert(self, conn, meter_id: str, prediction_id: int, severity, message: str):
        """Create an alert for a leak prediction"""
        alert_type = "critical" if severity.value == "instant" else "warning" if severity.value in ["moderate", "slow"] else "info"
        
        conn.execute("""
            INSERT INTO alerts (meter_id, prediction_id, alert_type, message)
            VALUES (?, ?, ?, ?)
        """, (meter_id, prediction_id, alert_type, message))
    
    def get_recent_predictions(self, meter_id: str = None, hours: int = 24, limit: int = 100) -> pd.DataFrame:
        """Get recent leak predictions"""
        query = """
            SELECT lp.*, m.location 
            FROM leak_predictions lp
            LEFT JOIN meters m ON lp.meter_id = m.meter_id
            WHERE lp.timestamp >= datetime('now', '-{} hours')
        """.format(hours)
        
        params = []
        if meter_id:
            query += " AND lp.meter_id = ?"
            params.append(meter_id)
        
        query += " ORDER BY lp.timestamp DESC LIMIT {}".format(limit)
        
        with self.get_connection() as conn:
            return pd.read_sql_query(query, conn, params=params)
    
    def get_active_alerts(self, acknowledged: bool = False) -> pd.DataFrame:
        """Get active alerts"""
        query = """
            SELECT a.*, lp.severity, lp.confidence, m.location
            FROM alerts a
            JOIN leak_predictions lp ON a.prediction_id = lp.id
            LEFT JOIN meters m ON a.meter_id = m.meter_id
            WHERE a.acknowledged = ?
            ORDER BY a.created_at DESC
        """
        
        with self.get_connection() as conn:
            return pd.read_sql_query(query, conn, params=[acknowledged])
    
    def acknowledge_alert(self, alert_id: int, acknowledged_by: str):
        """Acknowledge an alert"""
        with self.get_connection() as conn:
            conn.execute("""
                UPDATE alerts 
                SET acknowledged = TRUE, acknowledged_by = ?, acknowledged_at = CURRENT_TIMESTAMP
                WHERE id = ?
            """, (acknowledged_by, alert_id))
            conn.commit()
    
    def get_meter_summary(self) -> pd.DataFrame:
        """Get summary statistics for all meters"""
        query = """
            SELECT 
                m.meter_id,
                m.location,
                m.status,
                COUNT(DISTINCT sr.id) as total_readings,
                MAX(sr.timestamp) as last_reading,
                COUNT(DISTINCT lp.id) as total_predictions,
                COUNT(DISTINCT CASE WHEN lp.leak_detected THEN lp.id END) as leak_count,
                MAX(lp.timestamp) as last_prediction
            FROM meters m
            LEFT JOIN sensor_readings sr ON m.meter_id = sr.meter_id
            LEFT JOIN leak_predictions lp ON m.meter_id = lp.meter_id
            GROUP BY m.meter_id, m.location, m.status
            ORDER BY m.meter_id
        """
        
        with self.get_connection() as conn:
            return pd.read_sql_query(query, conn)
    
    def cleanup_old_data(self, days_to_keep: int = 30):
        """Clean up old data to prevent database bloat"""
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        
        with self.get_connection() as conn:
            # Delete old sensor readings (keep predictions for audit trail)
            conn.execute("DELETE FROM sensor_readings WHERE timestamp < ?", (cutoff_date,))
            
            # Delete old acknowledged alerts
            conn.execute("""
                DELETE FROM alerts 
                WHERE acknowledged = TRUE AND created_at < ?
            """, (cutoff_date,))
            
            conn.commit()
            logger.info(f"Cleaned up data older than {days_to_keep} days")

# Global instance
data_manager = DataManager()
