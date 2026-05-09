"""MySQL Database Manager - Replaces SQLite with MySQL"""
import mysql.connector
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import threading
import os
from pathlib import Path


class MySQLDatabaseManager:
    """MySQL-backed database manager for THIWASCO leak detection system."""
    
    def __init__(self, host=None, port=None, database=None, user=None, password=None):
        # Allow environment variables or direct parameters
        self.config = {
            'host': host or os.getenv('MYSQL_HOST', 'localhost'),
            'port': port or int(os.getenv('MYSQL_PORT', '3306')),
            'database': database or os.getenv('MYSQL_DATABASE', 'thiwasco_05092026'),
            'user': user or os.getenv('MYSQL_USER', 'root'),
            'password': password or os.getenv('MYSQL_PASSWORD', 'MyNewSecurePassword!'),
            'autocommit': False,
            'connection_timeout': 30,
        }
        self._local = threading.local()
        self._initialized = False
    
    def _get_conn(self):
        """Get or create MySQL connection for current thread."""
        if not hasattr(self._local, 'conn') or self._local.conn is None or not self._local.conn.is_connected():
            self._local.conn = mysql.connector.connect(**self.config)
            # Initialize database on first connection
            if not self._initialized:
                try:
                    self._init_db(self._local.conn)
                    self._initialized = True
                except Exception as e:
                    print(f"Database init error: {e}")
                    raise
        
        return self._local.conn
    
    def _init_db(self, conn):
        """Create tables if they don't exist."""
        cursor = conn.cursor()
        
        # Zones table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS zones (
                zone_id VARCHAR(50) PRIMARY KEY,
                name VARCHAR(100) NOT NULL,
                region VARCHAR(100) NOT NULL,
                type VARCHAR(50) NOT NULL,
                status VARCHAR(20) DEFAULT 'active',
                estimated_connections INT DEFAULT 0,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Meters table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS meters (
                meter_id VARCHAR(50) PRIMARY KEY,
                zone_id VARCHAR(50),
                location VARCHAR(200),
                meter_type VARCHAR(50),
                status VARCHAR(20) DEFAULT 'active',
                flow_rate DOUBLE DEFAULT 0.0,
                description TEXT,
                installation_date DATE,
                FOREIGN KEY (zone_id) REFERENCES zones(zone_id)
            )
        ''')
        
        # Sensor readings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sensor_readings (
                id INT AUTO_INCREMENT PRIMARY KEY,
                meter_id VARCHAR(50),
                timestamp TIMESTAMP,
                pressure DOUBLE,
                flow_rate DOUBLE,
                temperature DOUBLE,
                FOREIGN KEY (meter_id) REFERENCES meters(meter_id)
            )
        ''')
        
        # Leak predictions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS leak_predictions (
                id INT AUTO_INCREMENT PRIMARY KEY,
                meter_id VARCHAR(50),
                timestamp TIMESTAMP,
                confidence DOUBLE,
                leak_detected BOOLEAN,
                leak_type VARCHAR(50),
                features TEXT,
                FOREIGN KEY (meter_id) REFERENCES meters(meter_id)
            )
        ''')
        
        # Alerts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alerts (
                id INT AUTO_INCREMENT PRIMARY KEY,
                meter_id VARCHAR(50),
                zone_id VARCHAR(50),
                severity VARCHAR(20),
                status VARCHAR(20) DEFAULT 'new',
                title VARCHAR(200),
                message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP,
                FOREIGN KEY (meter_id) REFERENCES meters(meter_id)
            )
        ''')
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id VARCHAR(50) PRIMARY KEY,
                username VARCHAR(100) NOT NULL,
                email VARCHAR(100) NOT NULL UNIQUE,
                name VARCHAR(100) NOT NULL,
                role VARCHAR(50) NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                status VARCHAR(20) DEFAULT 'active',
                last_login TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        cursor.close()
    
    def _query_to_df(self, query, params=None) -> pd.DataFrame:
        """Execute query and return DataFrame."""
        conn = self._get_conn()
        cursor = conn.cursor(dictionary=True)
        cursor.execute(query, params or ())
        results = cursor.fetchall()
        cursor.close()
        if results:
            return pd.DataFrame(results)
        return pd.DataFrame()
    
    def _execute(self, query, params=None):
        """Execute a write operation."""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute(query, params or ())
        conn.commit()
        cursor.close()
    
    # === READ OPERATIONS ===
    
    def get_zones(self) -> pd.DataFrame:
        return self._query_to_df("SELECT * FROM zones")
    
    def get_all_zones(self) -> pd.DataFrame:
        return self.get_zones()
    
    def get_meters(self, zone_id: Optional[str] = None) -> pd.DataFrame:
        if zone_id:
            return self._query_to_df("SELECT * FROM meters WHERE zone_id = %s", (zone_id,))
        return self._query_to_df("SELECT * FROM meters")
    
    def get_all_meters(self) -> pd.DataFrame:
        return self.get_meters()
    
    def get_sensor_readings(self, meter_id: Optional[str] = None, hours: int = 24) -> pd.DataFrame:
        since = datetime.now() - timedelta(hours=hours)
        if meter_id:
            return self._query_to_df(
                "SELECT * FROM sensor_readings WHERE meter_id = %s AND timestamp > %s ORDER BY timestamp DESC",
                (meter_id, since)
            )
        return self._query_to_df(
            "SELECT * FROM sensor_readings WHERE timestamp > %s ORDER BY timestamp DESC",
            (since,)
        )
    
    def get_leak_predictions(self, hours: int = 24) -> pd.DataFrame:
        since = datetime.now() - timedelta(hours=hours)
        return self._query_to_df(
            "SELECT * FROM leak_predictions WHERE timestamp > %s",
            (since,)
        )
    
    def get_alerts(self, severity: Optional[str] = None, status: Optional[str] = None, hours: int = 24) -> pd.DataFrame:
        since = datetime.now() - timedelta(hours=hours)
        query = "SELECT * FROM alerts WHERE created_at > %s"
        params = [since]
        
        if severity:
            query += " AND severity = %s"
            params.append(severity)
        if status:
            query += " AND status = %s"
            params.append(status)
        
        return self._query_to_df(query, tuple(params))
    
    def get_user(self, user_id: str) -> Optional[Dict]:
        df = self._query_to_df("SELECT * FROM users WHERE user_id = %s", (user_id,))
        if not df.empty:
            return df.iloc[0].to_dict()
        return None
    
    def update_last_login(self, user_id: str):
        self._execute(
            "UPDATE users SET last_login = CURRENT_TIMESTAMP WHERE user_id = %s",
            (user_id,)
        )
    
    # === WRITE OPERATIONS ===
    
    def add_user(self, user_id: str, username: str, email: str, name: str, role: str, password_hash: str) -> bool:
        try:
            self._execute(
                "INSERT INTO users (user_id, username, email, name, role, password_hash) VALUES (%s, %s, %s, %s, %s, %s)",
                (user_id.upper(), username, email, name, role, password_hash)
            )
            return True
        except mysql.connector.IntegrityError:
            return False
    
    def add_zone(self, zone_id: str, name: str, region: str, zone_type: str,
                 status: str, estimated_connections: int, description: str) -> bool:
        try:
            self._execute(
                "INSERT INTO zones (zone_id, name, region, type, status, estimated_connections, description) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (zone_id.upper(), name, region, zone_type, status, estimated_connections, description)
            )
            return True
        except mysql.connector.IntegrityError:
            return False
    
    def add_meter(self, meter_id: str, zone_id: str, location: str, meter_type: str,
                  status: str, flow_rate: float, description: str) -> bool:
        try:
            self._execute(
                "INSERT INTO meters (meter_id, zone_id, location, meter_type, status, flow_rate, description) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (meter_id.upper(), zone_id, location, meter_type, status, flow_rate, description)
            )
            return True
        except mysql.connector.IntegrityError:
            return False
    
    def store_sensor_reading(self, meter_id: str, timestamp: datetime, pressure: float, 
                             flow_rate: float, temperature: float):
        self._execute(
            "INSERT INTO sensor_readings (meter_id, timestamp, pressure, flow_rate, temperature) VALUES (%s, %s, %s, %s, %s)",
            (meter_id, timestamp, pressure, flow_rate, temperature)
        )
    
    # Alias for compatibility with smart_meter_simulator
    def add_sensor_reading(self, meter_id: str, pressure: float, flow_rate: float, temperature: float, timestamp=None):
        if timestamp is None:
            timestamp = datetime.now()
        self.store_sensor_reading(meter_id, timestamp, pressure, flow_rate, temperature)
    
    def store_leak_prediction(self, meter_id: str, timestamp: datetime, confidence: float,
                              leak_detected: bool, leak_type: str, features: str):
        self._execute(
            "INSERT INTO leak_predictions (meter_id, timestamp, confidence, leak_detected, leak_type, features) VALUES (%s, %s, %s, %s, %s, %s)",
            (meter_id, timestamp, confidence, leak_detected, leak_type, features)
        )
    
    def add_alert(self, meter_id: str, zone_id: str, severity: str, title: str, message: str):
        self._execute(
            "INSERT INTO alerts (meter_id, zone_id, severity, title, message) VALUES (%s, %s, %s, %s, %s)",
            (meter_id, zone_id, severity, title, message)
        )
    
    # === SEED DATA ===
    
    def seed_default_users(self):
        """Seed the 4 default THW users with hashed passwords - Updated for MySQL"""
        import bcrypt
        
        default_password = "Thiwasco2024!"
        password_hash = bcrypt.hashpw(default_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        default_users = [
            ("THW-001", "thiwasco", "j.kamau@thiwasco.co.ke", "John Kamau", "Operator", password_hash),
            ("THW-002", "thiwasco", "g.ochieng@thiwasco.co.ke", "Grace Ochieng", "Manager", password_hash),
            ("THW-003", "thiwasco", "p.mwangi@thiwasco.co.ke", "Peter Mwangi", "Engineer", password_hash),
            ("THW-004", "thiwasco", "a.wanjiku@thiwasco.co.ke", "Alice Wanjiku", "Technician", password_hash),
        ]
        
        created_count = 0
        for user in default_users:
            try:
                if self.add_user(*user):
                    created_count += 1
                    print(f"  - Created user: {user[0]} ({user[3]})")
            except mysql.connector.IntegrityError:
                print(f"  - User already exists: {user[0]}")
                pass  # User already exists
        
        if created_count > 0:
            print(f"  - Created {created_count} new users")
        else:
            print("  - All default users already exist")
    
    def seed_default_zones(self):
        """Seed default zones"""
        zones = [
            ("Z01", "Zone 1", "Residential", "residential", "active", 150, "Main residential area"),
            ("Z02", "Zone 2", "Commercial", "commercial", "active", 75, "Business district"),
            ("Z03", "Zone 3", "Industrial", "industrial", "active", 45, "Factory area"),
        ]
        for zone in zones:
            try:
                self.add_zone(*zone)
            except mysql.connector.IntegrityError:
                pass
    
    def seed_default_meters(self):
        """Seed default meters"""
        meters = [
            ("M001", "Z01", "Location 1", "residential", "active", 0.5, "Residential meter 1"),
            ("M002", "Z01", "Location 2", "residential", "active", 0.3, "Residential meter 2"),
            ("M003", "Z02", "Location 3", "commercial", "active", 1.2, "Commercial meter 1"),
            ("M004", "Z03", "Location 4", "industrial", "active", 2.5, "Industrial meter 1"),
        ]
        for meter in meters:
            try:
                self.add_meter(*meter)
            except mysql.connector.IntegrityError:
                pass


# Global instance - configure with your MySQL credentials
db_manager = MySQLDatabaseManager()


def seed_demo_data():
    """Seed all demo data for MySQL"""
    db_manager.seed_default_users()
    db_manager.seed_default_zones()
    db_manager.seed_default_meters()
    print("MySQL demo data seeded!")
