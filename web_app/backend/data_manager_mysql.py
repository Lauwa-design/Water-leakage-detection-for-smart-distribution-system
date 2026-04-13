"""
THIWASCO MySQL Data Manager
Handles data storage and retrieval for MySQL database - no business logic
"""

import mysql.connector
import pandas as pd
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Tuple
import os
from contextlib import contextmanager
import logging
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataManager:
    """Data storage and retrieval for MySQL - no business logic"""
    
    def __init__(self):
        self.mysql_config = {
            'host': os.getenv('DB_HOST', 'localhost'),
            'user': os.getenv('DB_USER', 'root'),
            'password': os.getenv('DB_PASSWORD', ''),
            'database': os.getenv('DB_NAME', 'thiwasco_leak_detection'),
            'port': int(os.getenv('DB_PORT', 3306)),
            'autocommit': True
        }
        self.init_database()
    
    @contextmanager
    def get_connection(self):
        """Context manager for MySQL database connections"""
        conn = None
        try:
            conn = mysql.connector.connect(**self.mysql_config)
            yield conn
        except Exception as e:
            if conn:
                conn.rollback()
            logger.error(f"MySQL error: {e}")
            raise
        finally:
            if conn:
                conn.close()
    
    def init_database(self):
        """Initialize MySQL database schema with proper constraints"""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                
                # Create zones table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS zones (
                        zone_id VARCHAR(20) PRIMARY KEY,
                        zone_name VARCHAR(100) NOT NULL,
                        region VARCHAR(50),
                        area_km2 DECIMAL(10,2),
                        population_served INT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # Create meters table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS meters (
                        meter_id VARCHAR(20) PRIMARY KEY,
                        zone_id VARCHAR(20),
                        location VARCHAR(200),
                        latitude DECIMAL(10,8),
                        longitude DECIMAL(11,8),
                        installation_date DATE,
                        last_maintenance DATE,
                        meter_type VARCHAR(50),
                        pipe_diameter_mm INT,
                        status VARCHAR(20) DEFAULT 'active',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                        FOREIGN KEY (zone_id) REFERENCES zones(zone_id) ON DELETE SET NULL,
                        CHECK(status IN ('active', 'inactive', 'maintenance', 'faulty'))
                    )
                """)
                
                # Create sensor_readings table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS sensor_readings (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        meter_id VARCHAR(20) NOT NULL,
                        timestamp TIMESTAMP NOT NULL,
                        pressure DECIMAL(8,3) NOT NULL,
                        flow_rate DECIMAL(8,3) NOT NULL,
                        temperature_celsius DECIMAL(5,2),
                        battery_level INT,
                        signal_strength INT,
                        reading_quality VARCHAR(20) DEFAULT 'good',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (meter_id) REFERENCES meters(meter_id) ON DELETE CASCADE,
                        CHECK(reading_quality IN ('good', 'fair', 'poor'))
                    )
                """)
                
                # Create leak_predictions table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS leak_predictions (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        meter_id VARCHAR(20) NOT NULL,
                        timestamp TIMESTAMP NOT NULL,
                        leak_detected BOOLEAN NOT NULL,
                        leak_probability DECIMAL(5,4) NOT NULL,
                        confidence DECIMAL(5,4) NOT NULL,
                        severity VARCHAR(20) NOT NULL,
                        pressure DECIMAL(8,3) NOT NULL,
                        flow_rate DECIMAL(8,3) NOT NULL,
                        pressure_delta DECIMAL(8,3),
                        flow_delta DECIMAL(8,3),
                        recommendation TEXT,
                        model_version VARCHAR(20),
                        features_json TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (meter_id) REFERENCES meters(meter_id) ON DELETE CASCADE,
                        CHECK(confidence >= 0 AND confidence <= 1),
                        CHECK(severity IN ('none', 'low', 'moderate', 'high', 'critical'))
                    )
                """)
                
                # Create alerts table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS alerts (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        meter_id VARCHAR(20) NOT NULL,
                        prediction_id INT,
                        alert_type VARCHAR(50) NOT NULL,
                        title VARCHAR(200) NOT NULL,
                        message TEXT NOT NULL,
                        severity VARCHAR(20) NOT NULL,
                        status VARCHAR(20) DEFAULT 'active',
                        acknowledged_by VARCHAR(100),
                        acknowledged_at TIMESTAMP NULL,
                        resolved_by VARCHAR(100),
                        resolved_at TIMESTAMP NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (meter_id) REFERENCES meters(meter_id) ON DELETE CASCADE,
                        FOREIGN KEY (prediction_id) REFERENCES leak_predictions(id) ON DELETE SET NULL,
                        CHECK(status IN ('active', 'acknowledged', 'resolved', 'closed')),
                        CHECK(severity IN ('low', 'moderate', 'high', 'critical'))
                    )
                """)
                
                # Create alert_notifications table
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS alert_notifications (
                        id INT AUTO_INCREMENT PRIMARY KEY,
                        alert_id INT NOT NULL,
                        notification_type VARCHAR(20) NOT NULL,
                        recipient VARCHAR(200) NOT NULL,
                        status VARCHAR(20) DEFAULT 'pending',
                        sent_at TIMESTAMP NULL,
                        error_message TEXT,
                        retry_count INT DEFAULT 0,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        FOREIGN KEY (alert_id) REFERENCES alerts(id) ON DELETE CASCADE,
                        CHECK(notification_type IN ('email', 'sms', 'push', 'webhook')),
                        CHECK(status IN ('pending', 'sent', 'failed', 'delivered'))
                    )
                """)
                
                # Create indexes for performance
                indexes = [
                    "CREATE INDEX IF NOT EXISTS idx_meters_zone_id ON meters(zone_id)",
                    "CREATE INDEX IF NOT EXISTS idx_sensor_readings_meter_timestamp ON sensor_readings(meter_id, timestamp)",
                    "CREATE INDEX IF NOT EXISTS idx_sensor_readings_timestamp ON sensor_readings(timestamp)",
                    "CREATE INDEX IF NOT EXISTS idx_leak_predictions_meter_timestamp ON leak_predictions(meter_id, timestamp)",
                    "CREATE INDEX IF NOT EXISTS idx_alerts_meter_status ON alerts(meter_id, status)",
                    "CREATE INDEX IF NOT EXISTS idx_alerts_severity_status ON alerts(severity, status)",
                    "CREATE INDEX IF NOT EXISTS idx_alert_notifications_alert_type ON alert_notifications(alert_id, notification_type)"
                ]
                
                for index_sql in indexes:
                    cursor.execute(index_sql)
                
                conn.commit()
                logger.info("MySQL database initialized successfully")
                
        except Exception as e:
            logger.error(f"Error initializing MySQL database: {e}")
            raise
    
    def add_zone(self, zone_id: str, zone_name: str, region: str = None, 
                 area_km2: float = None, population_served: int = None):
        """Add a new zone to the database"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO zones (zone_id, zone_name, region, area_km2, population_served)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                zone_name = VALUES(zone_name),
                region = VALUES(region),
                area_km2 = VALUES(area_km2),
                population_served = VALUES(population_served)
            """, (zone_id, zone_name, region, area_km2, population_served))
            conn.commit()
    
    def add_meter(self, meter_id: str, zone_id: str = None, location: str = None,
                  installation_date: str = None, last_maintenance: str = None,
                  meter_type: str = None, pipe_diameter_mm: int = None,
                  latitude: float = None, longitude: float = None):
        """Add a new meter to the database"""
        with self.get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO meters (meter_id, zone_id, location, latitude, longitude,
                                 installation_date, last_maintenance, meter_type, pipe_diameter_mm)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                zone_id = VALUES(zone_id),
                location = VALUES(location),
                latitude = VALUES(latitude),
                longitude = VALUES(longitude),
                installation_date = VALUES(installation_date),
                last_maintenance = VALUES(last_maintenance),
                meter_type = VALUES(meter_type),
                pipe_diameter_mm = VALUES(pipe_diameter_mm)
            """, (meter_id, zone_id, location, latitude, longitude,
                  installation_date, last_maintenance, meter_type, pipe_diameter_mm))
            conn.commit()
    
    def store_sensor_readings(self, readings_df: pd.DataFrame):
        """Store sensor readings in the database"""
        if readings_df.empty:
            return
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Prepare data for insertion
            data = []
            for _, row in readings_df.iterrows():
                data.append((
                    row['meter_id'],
                    row['timestamp'],
                    float(row['pressure']),
                    float(row['flow_rate']),
                    float(row.get('temperature_celsius', 22.0)),
                    int(row.get('battery_level', 95)),
                    int(row.get('signal_strength', 4)),
                    row.get('reading_quality', 'good')
                ))
            
            cursor.executemany("""
                INSERT INTO sensor_readings 
                (meter_id, timestamp, pressure, flow_rate, temperature_celsius, 
                 battery_level, signal_strength, reading_quality)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
            """, data)
            conn.commit()
    
    def get_sensor_readings(self, meter_id: str = None, hours: int = None, start_time: datetime = None, 
                          end_time: datetime = None, limit: int = None) -> pd.DataFrame:
        """Retrieve sensor readings for a meter or all meters"""
        query = "SELECT * FROM sensor_readings"
        params = []
        conditions = []
        
        if meter_id:
            conditions.append("meter_id = %s")
            params.append(meter_id)
        
        if hours:
            from datetime import datetime, timedelta
            start_time = datetime.now() - timedelta(hours=hours)
        
        if start_time:
            conditions.append("timestamp >= %s")
            params.append(start_time)
        
        if end_time:
            conditions.append("timestamp <= %s")
            params.append(end_time)
        
        if conditions:
            query += " WHERE " + " AND ".join(conditions)
        
        query += " ORDER BY timestamp DESC"
        
        if limit:
            query += f" LIMIT {limit}"
        
        with self.get_connection() as conn:
            df = pd.read_sql(query, conn, params=params)
            return df
    
    def store_leak_predictions(self, predictions_df: pd.DataFrame):
        """Store leak predictions in the database"""
        if predictions_df.empty:
            return
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            
            # Prepare data for insertion
            data = []
            for _, row in predictions_df.iterrows():
                data.append((
                    row['meter_id'],
                    row['timestamp'],
                    bool(row.get('leak_detected', False)),
                    float(row['leak_probability']),
                    float(row['confidence']),
                    row['severity'],
                    float(row['pressure']),
                    float(row['flow_rate']),
                    float(row.get('pressure_delta', 0.0)),
                    float(row.get('flow_delta', 0.0)),
                    row.get('recommendation', ''),
                    row.get('model_version', '1.0'),
                    row.get('features_used', '[]')
                ))
            
            cursor.executemany("""
                INSERT INTO leak_predictions 
                (meter_id, timestamp, leak_detected, leak_probability, confidence,
                 severity, pressure, flow_rate, pressure_delta, flow_delta,
                 recommendation, model_version, features_json)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, data)
            conn.commit()
    
    def get_leak_predictions(self, hours: int = 24, limit: int = 100) -> pd.DataFrame:
        """Get recent leak predictions"""
        from datetime import datetime, timedelta
        start_time = datetime.now() - timedelta(hours=hours)
        
        query = """
            SELECT lp.*, m.location, m.zone_id, z.zone_name
            FROM leak_predictions lp
            JOIN meters m ON lp.meter_id = m.meter_id
            LEFT JOIN zones z ON m.zone_id = z.zone_id
            WHERE lp.timestamp >= %s
            ORDER BY lp.timestamp DESC
            LIMIT %s
        """
        
        with self.get_connection() as conn:
            df = pd.read_sql(query, conn, params=(start_time, limit))
            return df
    
    def get_alerts(self, status: str = None, hours: int = 24, limit: int = 50) -> pd.DataFrame:
        """Get alerts with optional filtering"""
        from datetime import datetime, timedelta
        start_time = datetime.now() - timedelta(hours=hours)
        
        query = """
            SELECT a.*, m.location, m.zone_id, z.zone_name
            FROM alerts a
            JOIN meters m ON a.meter_id = m.meter_id
            LEFT JOIN zones z ON m.zone_id = z.zone_id
            WHERE a.created_at >= %s
        """
        params = [start_time]
        
        if status:
            query += " AND a.status = %s"
            params.append(status)
        
        query += " ORDER BY a.created_at DESC LIMIT %s"
        params.append(limit)
        
        with self.get_connection() as conn:
            df = pd.read_sql(query, conn, params=params)
            return df
    
    def get_zones(self) -> pd.DataFrame:
        """Get all zones"""
        query = "SELECT * FROM zones ORDER BY zone_id"
        
        with self.get_connection() as conn:
            df = pd.read_sql(query, conn)
            return df
    
    def get_meters(self) -> pd.DataFrame:
        """Get all meters with zone information"""
        query = """
            SELECT m.*, z.zone_name, z.region
            FROM meters m
            LEFT JOIN zones z ON m.zone_id = z.zone_id
            ORDER BY m.meter_id
        """
        
        with self.get_connection() as conn:
            df = pd.read_sql(query, conn)
            return df
    
    def get_regional_data(self) -> pd.DataFrame:
        """Get regional summary data"""
        query = """
            SELECT 
                m.zone_id,
                z.zone_name,
                z.region,
                COUNT(DISTINCT m.meter_id) as meter_count,
                COUNT(DISTINCT sr.id) as total_readings,
                MAX(sr.timestamp) as last_reading,
                COUNT(DISTINCT lp.id) as total_predictions,
                COUNT(DISTINCT CASE WHEN lp.leak_detected THEN lp.id END) as leak_count,
                MAX(lp.timestamp) as last_prediction
            FROM meters m
            LEFT JOIN zones z ON m.zone_id = z.zone_id
            LEFT JOIN sensor_readings sr ON m.meter_id = sr.meter_id
            LEFT JOIN leak_predictions lp ON m.meter_id = lp.meter_id
            GROUP BY m.zone_id, z.zone_name, z.region
            ORDER BY m.zone_id
        """
        
        with self.get_connection() as conn:
            df = pd.read_sql(query, conn)
            return df
    
    def initialize_sample_data(self):
        """Initialize sample zones and meters data for MySQL"""
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
                ('ZONE-047', 'Kang\'oki', 'Special Zone', 26.4, 6700),
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
                ('HW-THK-018', 'ZONE-017', 'Kang\'oki', -1.0332, 37.0694, '2023-02-20', '2023-11-30', 'Commercial', 150),
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
                ('HW-THK-037', 'ZONE-047', 'Kang\'oki', -1.0326, 37.0684, '2023-02-20', '2023-11-30', 'Special', 670),
                ('HW-THK-038', 'ZONE-048', 'Kamenu', -1.0325, 37.0683, '2023-02-20', '2023-11-30', 'Special', 950),
                ('HW-THK-039', 'ZONE-049', 'Kwa Jomo', -1.0324, 37.0682, '2023-02-20', '2023-11-30', 'Special', 890),
                ('HW-THK-040', 'ZONE-050', 'Landless', -1.0323, 37.0681, '2023-02-20', '2023-11-30', 'Special', 410)
            ]
            
            for meter_id, zone_id, location, lat, lon, install_date, last_maint, meter_type, pipe_dia in sample_meters:
                # Check if meter exists and needs zone_id
                with self.get_connection() as conn:
                    cursor = conn.cursor()
                    cursor.execute("SELECT zone_id FROM meters WHERE meter_id = %s", (meter_id,))
                    existing = cursor.fetchone()
                    
                    if not existing or not existing[0]:  # Meter doesn't exist or has no zone_id
                        self.add_meter(meter_id, zone_id, location, install_date, last_maint, meter_type, pipe_dia, lat, lon)
                        print(f"Added/updated meter {meter_id} with zone {zone_id}")
                    else:
                        print(f"Meter {meter_id} already exists with zone {existing[0]}")
                        
        except Exception as e:
            print(f"Error initializing sample data: {e}")
    
    def cleanup_old_data(self, days_to_keep: int = 30):
        """Clean up old data to prevent database bloat"""
        cutoff_date = datetime.now() - timedelta(days=days_to_keep)
        
        with self.get_connection() as conn:
            cursor = conn.cursor()
            # Delete old sensor readings (keep predictions for audit trail)
            cursor.execute("DELETE FROM sensor_readings WHERE timestamp < %s", (cutoff_date,))
            
            # Delete old acknowledged alerts
            cursor.execute("""
                DELETE FROM alerts 
                WHERE status = 'acknowledged' AND created_at < %s
            """, (cutoff_date,))
            
            conn.commit()
            logger.info(f"Cleaned up data older than {days_to_keep} days")

# Global instance
data_manager = DataManager()
