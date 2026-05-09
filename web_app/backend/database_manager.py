"""Database Manager - Handles all SQLite operations"""
import sqlite3
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import threading
import os
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = REPO_ROOT / "data" / "leak_detection.db"
LEGACY_DB_PATH = Path(__file__).resolve().parents[1] / "data" / "leak_detection.db"

class DatabaseManager:
    def __init__(self, db_path: Optional[str] = None):
        selected_path = Path(db_path) if db_path else DEFAULT_DB_PATH
        if not selected_path.exists() and LEGACY_DB_PATH.exists():
            selected_path = LEGACY_DB_PATH

        self.db_path = str(selected_path)
        self._local = threading.local()
        # Ensure directory exists
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        # Don't initialize database here - do it lazily on first use
        self._initialized = False

    def _prepare_connection(self, conn: sqlite3.Connection, readonly: bool = False) -> sqlite3.Connection:
        """Apply SQLite settings that behave better with concurrent readers/writers."""
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 5000")
        if not readonly:
            conn.execute("PRAGMA journal_mode = WAL")
            conn.execute("PRAGMA synchronous = NORMAL")
        return conn

    def _open_connection(self, readonly: bool = False) -> sqlite3.Connection:
        """Open a new SQLite connection with safe defaults."""
        if readonly:
            db_uri = "file:" + str(Path(self.db_path).resolve()).replace("\\", "/") + "?mode=ro&immutable=1"
            conn = sqlite3.connect(db_uri, uri=True, timeout=5, check_same_thread=False)
            return self._prepare_connection(conn, readonly=True)

        conn = sqlite3.connect(self.db_path, timeout=5, check_same_thread=False)
        return self._prepare_connection(conn, readonly=False)

    def _get_user_via_snapshot(self, user_id: str) -> Optional[Dict]:
        """Fallback reader for authentication when the live SQLite file is heavily contended."""
        db_uri = "file:" + str(Path(self.db_path).resolve()).replace("\\", "/") + "?mode=ro&immutable=1"
        conn = sqlite3.connect(db_uri, uri=True, timeout=1, check_same_thread=False)
        try:
            cursor = conn.cursor()
            cursor.execute(
                '''
                    SELECT user_id, username, email, name, role, password_hash, status, last_login
                    FROM users WHERE user_id = ?
                ''',
                (user_id.upper(),),
            )
            row = cursor.fetchone()
            if row:
                return {
                    'user_id': row[0],
                    'username': row[1],
                    'email': row[2],
                    'name': row[3],
                    'role': row[4],
                    'password_hash': row[5],
                    'status': row[6],
                    'last_login': row[7]
                }
            return None
        finally:
            conn.close()
    
    def _get_conn(self):
        """Get or create database connection for current thread"""
        # Initialize database on first connection
        if not self._initialized:
            try:
                self._init_db()
                self._initialized = True
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e):
                    print(f"Database locked, will retry on next operation: {e}")
                else:
                    raise

        if not hasattr(self._local, 'conn') or self._local.conn is None:
            self._local.conn = self._open_connection()
        try:
            # Test if connection is still open
            self._local.conn.execute("SELECT 1")
        except sqlite3.ProgrammingError:
            # Connection was closed, create new one
            self._local.conn = self._open_connection()
        return self._local.conn
    
    def _init_db(self):
        conn = self._open_connection()
        cursor = conn.cursor()
        
        # Zones table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS zones (
                zone_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                region TEXT NOT NULL,
                type TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                estimated_connections INTEGER DEFAULT 0,
                description TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Meters table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS meters (
                meter_id TEXT PRIMARY KEY,
                zone_id TEXT,
                location TEXT,
                meter_type TEXT,
                status TEXT DEFAULT 'active',
                flow_rate REAL DEFAULT 0.0,
                description TEXT,
                installation_date DATE,
                FOREIGN KEY (zone_id) REFERENCES zones(zone_id)
            )
        ''')
        
        # Sensor readings table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS sensor_readings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                meter_id TEXT,
                timestamp TIMESTAMP,
                pressure REAL,
                flow_rate REAL,
                temperature REAL,
                FOREIGN KEY (meter_id) REFERENCES meters(meter_id)
            )
        ''')
        
        # Leak predictions table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS leak_predictions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                meter_id TEXT,
                timestamp TIMESTAMP,
                confidence REAL,
                leak_detected BOOLEAN,
                leak_type TEXT,
                features TEXT,
                FOREIGN KEY (meter_id) REFERENCES meters(meter_id)
            )
        ''')
        
        # Alerts table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS alerts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                meter_id TEXT,
                zone_id TEXT,
                severity TEXT,
                status TEXT DEFAULT 'new',
                title TEXT,
                message TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                resolved_at TIMESTAMP,
                FOREIGN KEY (meter_id) REFERENCES meters(meter_id)
            )
        ''')
        
        # Users table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id TEXT PRIMARY KEY,
                username TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                name TEXT NOT NULL,
                role TEXT NOT NULL,
                password_hash TEXT NOT NULL,
                status TEXT DEFAULT 'active',
                last_login TIMESTAMP,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        conn.close()
    
    def get_zones(self) -> pd.DataFrame:
        conn = self._get_conn()
        return pd.read_sql_query("SELECT * FROM zones", conn)
    
    def get_meters(self, zone_id: Optional[str] = None) -> pd.DataFrame:
        conn = self._get_conn()
        if zone_id:
            return pd.read_sql_query(
                "SELECT * FROM meters WHERE zone_id = ?", conn, params=(zone_id,)
            )
        return pd.read_sql_query("SELECT * FROM meters", conn)
    
    def get_sensor_readings(self, meter_id: Optional[str] = None, 
                           hours: int = 24) -> pd.DataFrame:
        import sqlite3
        max_retries = 3
        for attempt in range(max_retries):
            try:
                conn = self._get_conn()
                since = datetime.now() - timedelta(hours=hours)
                
                if meter_id:
                    query = """
                        SELECT * FROM sensor_readings 
                        WHERE meter_id = ? AND timestamp > ?
                        ORDER BY timestamp DESC
                    """
                    return pd.read_sql_query(query, conn, params=(meter_id, since))
                
                query = """
                    SELECT * FROM sensor_readings 
                    WHERE timestamp > ?
                    ORDER BY timestamp DESC
                """
                return pd.read_sql_query(query, conn, params=(since,))
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    import time
                    time.sleep(0.1 * (attempt + 1))  # Exponential backoff
                    continue
                if "database is locked" in str(e):
                    return self._get_user_via_snapshot(user_id)
                raise
    
    def get_leak_predictions(self, hours: int = 24) -> pd.DataFrame:
        conn = self._get_conn()
        since = datetime.now() - timedelta(hours=hours)
        return pd.read_sql_query(
            "SELECT * FROM leak_predictions WHERE timestamp > ?",
            conn, params=(since,)
        )
    
    def get_alerts(self, severity: Optional[str] = None, 
                   status: Optional[str] = None,
                   hours: int = 24) -> pd.DataFrame:
        conn = self._get_conn()
        since = datetime.now() - timedelta(hours=hours)
        
        query = "SELECT * FROM alerts WHERE created_at > ?"
        params = [since]
        
        if severity:
            query += " AND severity = ?"
            params.append(severity)
        if status:
            query += " AND status = ?"
            params.append(status)
        
        query += " ORDER BY created_at DESC"
        
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        conn.close()
        
        return pd.DataFrame([dict(row) for row in rows])
    
    def get_active_alert_for_meter(self, meter_id: str, severity: str, hours: int = 24) -> Optional[Dict]:
        """Check if there's an active unresolved alert for a specific meter"""
        conn = self._get_conn()
        since = datetime.now() - timedelta(hours=hours)
        
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, severity, status, created_at 
            FROM alerts 
            WHERE meter_id = ? AND severity = ? AND status != 'resolved' AND created_at > ?
            ORDER BY created_at DESC
            LIMIT 1
        ''', (meter_id, severity, since))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return {'id': row[0], 'severity': row[1], 'status': row[2], 'created_at': row[3]}
        return None
    
    def clear_all_alerts(self):
        """Clear all alerts from database (useful for cleaning up false positives)"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM alerts")
        conn.commit()
        conn.close()
        print("All alerts cleared from database")
    
    def clear_all_leak_predictions(self):
        """Clear all leak predictions from database (useful for cleaning up false positives)"""
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM leak_predictions")
        conn.commit()
        conn.close()
        print("All leak predictions cleared from database")
    
    def add_sensor_reading(self, meter_id: str, pressure: float, 
                          flow_rate: float, temperature: float = 20.0):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO sensor_readings (meter_id, timestamp, pressure, flow_rate, temperature)
            VALUES (?, ?, ?, ?, ?)
        ''', (meter_id, datetime.now(), pressure, flow_rate, temperature))
        conn.commit()
    
    def add_leak_prediction(self, meter_id: str, confidence: float,
                           leak_detected: bool, leak_type: str, features: str):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO leak_predictions (meter_id, timestamp, confidence, leak_detected, leak_type, features)
            VALUES (?, ?, ?, ?, ?, ?)
        ''', (meter_id, datetime.now(), confidence, leak_detected, leak_type, features))
        conn.commit()
    
    def add_alert(self, meter_id: str, zone_id: str, severity: str,
                 title: str, message: str):
        conn = self._get_conn()
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO alerts (meter_id, zone_id, severity, title, message)
            VALUES (?, ?, ?, ?, ?)
        ''', (meter_id, zone_id, severity, title, message))
        conn.commit()
    
    def update_alert_status(self, alert_id: int, status: str):
        conn = self._get_conn()
        cursor = conn.cursor()
        if status == 'resolved':
            cursor.execute('''
                UPDATE alerts SET status = ?, resolved_at = ? WHERE id = ?
            ''', (status, datetime.now(), alert_id))
        else:
            cursor.execute('''
                UPDATE alerts SET status = ? WHERE id = ?
            ''', (status, alert_id))
        conn.commit()
    
    def resolve_alert(self, alert_id: int):
        """Convenience method to mark an alert as resolved"""
        self.update_alert_status(alert_id, "resolved")

    def cleanup_old_alerts(self, days: int = 7) -> int:
        """Archive/delete resolved alerts older than specified days"""
        from datetime import timedelta
        conn = self._get_conn()
        cursor = conn.cursor()
        cutoff_date = datetime.now() - timedelta(days=days)

        # Delete resolved alerts older than cutoff
        cursor.execute('''
            DELETE FROM alerts
            WHERE status = 'resolved'
            AND resolved_at < ?
        ''', (cutoff_date,))

        deleted_count = cursor.rowcount
        conn.commit()
        conn.close()

        if deleted_count > 0:
            print(f"Cleaned up {deleted_count} resolved alerts older than {days} days")
        return deleted_count

    def get_dashboard_stats(self) -> Dict:
        """Get comprehensive dashboard statistics - consistent across all pages"""
        conn = self._get_conn()
        cursor = conn.cursor()
        
        # Basic counts
        cursor.execute("SELECT COUNT(*) FROM meters WHERE status = 'active'")
        active_meters = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM meters")
        total_meters = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM zones WHERE status = 'active'")
        active_zones = cursor.fetchone()[0]
        
        cursor.execute("SELECT COUNT(*) FROM zones")
        total_zones = cursor.fetchone()[0]
        
        # Alert counts (last 24h)
        since = datetime.now() - timedelta(hours=24)
        cursor.execute(
            "SELECT COUNT(*) FROM alerts WHERE severity = 'critical' AND created_at > ? AND status != 'resolved'",
            (since,)
        )
        critical_alerts = cursor.fetchone()[0]
        
        cursor.execute(
            "SELECT COUNT(*) FROM alerts WHERE severity = 'warning' AND created_at > ? AND status != 'resolved'",
            (since,)
        )
        warning_alerts = cursor.fetchone()[0]
        
        # Leak detections (unique meters, not all predictions)
        cursor.execute(
            """SELECT COUNT(DISTINCT meter_id) FROM leak_predictions 
               WHERE leak_detected = 1 AND timestamp > ?""",
            (since,)
        )
        leaks_24h = cursor.fetchone()[0]
        
        conn.close()
        
        return {
            'active_meters': active_meters,
            'total_meters': total_meters,
            'active_zones': active_zones,
            'total_zones': total_zones,
            'critical_alerts': critical_alerts,
            'warning_alerts': warning_alerts,
            'leaks_detected_24h': leaks_24h
        }
    
    def get_system_stats(self) -> Dict:
        """Get system statistics - alias for dashboard stats for consistency"""
        return self.get_dashboard_stats()
    
    def get_recent_alerts(self, hours: int = 24) -> pd.DataFrame:
        """Get recent alerts for display"""
        conn = self._get_conn()
        since = datetime.now() - timedelta(hours=hours)

        query = """
            SELECT id, created_at, severity, title, message, zone_id, status
            FROM alerts
            WHERE created_at > ?
            ORDER BY created_at DESC
        """
        df = pd.read_sql_query(query, conn, params=(since,))
        conn.close()
        return df

    def get_all_zones(self) -> pd.DataFrame:
        """Get all zones from database"""
        try:
            conn = self._get_conn()
            query = "SELECT * FROM zones ORDER BY region, name"
            df = pd.read_sql_query(query, conn)
            conn.close()
            return df
        except Exception as e:
            print(f"Error getting zones: {e}")
            return pd.DataFrame()

    def get_all_meters(self) -> pd.DataFrame:
        """Get all meters from database"""
        conn = self._get_conn()
        query = "SELECT * FROM meters ORDER BY zone_id, meter_id"
        df = pd.read_sql_query(query, conn)
        conn.close()
        return df
    
    def add_user(self, user_id: str, username: str, email: str, name: str, role: str, password_hash: str) -> bool:
        """Add a new user to the database"""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO users (user_id, username, email, name, role, password_hash)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id.upper(), username, email, name, role, password_hash))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()
    
    def get_user(self, user_id: str) -> Optional[Dict]:
        """Get user by ID"""
        import sqlite3
        max_retries = 3
        for attempt in range(max_retries):
            try:
                # Use a short-lived read-only connection so login reads are not blocked by writer threads.
                conn = self._open_connection(readonly=True)
                cursor = conn.cursor()
                cursor.execute('''
                    SELECT user_id, username, email, name, role, password_hash, status, last_login 
                    FROM users WHERE user_id = ?
                ''', (user_id.upper(),))
                row = cursor.fetchone()
                conn.close()
                if row:
                    return {
                        'user_id': row[0],
                        'username': row[1],
                        'email': row[2],
                        'name': row[3],
                        'role': row[4],
                        'password_hash': row[5],
                        'status': row[6],
                        'last_login': row[7]
                    }
                return None
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    import time
                    time.sleep(0.1 * (attempt + 1))  # Exponential backoff
                    continue
                raise
    
    def update_last_login(self, user_id: str):
        """Update user's last login timestamp"""
        import sqlite3
        max_retries = 3
        for attempt in range(max_retries):
            try:
                conn = self._open_connection()
                cursor = conn.cursor()
                cursor.execute('''
                    UPDATE users SET last_login = CURRENT_TIMESTAMP 
                    WHERE user_id = ?
                ''', (user_id.upper(),))
                conn.commit()
                conn.close()
                return
            except sqlite3.OperationalError as e:
                if "database is locked" in str(e) and attempt < max_retries - 1:
                    import time
                    time.sleep(0.2 * (attempt + 1))
                    continue
                raise
    
    def get_all_users(self) -> pd.DataFrame:
        """Get all users as DataFrame"""
        conn = self._get_conn()
        df = pd.read_sql_query(
            "SELECT user_id, name, email, role, status, last_login FROM users", 
            conn
        )
        conn.close()
        return df
    
    def seed_default_users(self):
        """Seed the 4 default THW users with hashed passwords"""
        import bcrypt
        
        # Default password for all demo users (they should change this)
        default_password = "Thiwasco2024!"
        password_hash = bcrypt.hashpw(default_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        default_users = [
            ("THW-001", "thiwasco", "j.kamau@thiwasco.co.ke", "John Kamau", "Operator", password_hash),
            ("THW-002", "thiwasco", "g.ochieng@thiwasco.co.ke", "Grace Ochieng", "Manager", password_hash),
            ("THW-003", "thiwasco", "p.mwangi@thiwasco.co.ke", "Peter Mwangi", "Engineer", password_hash),
            ("THW-004", "thiwasco", "a.wanjiku@thiwasco.co.ke", "Alice Wanjiku", "Technician", password_hash),
        ]
        for user in default_users:
            self.add_user(*user)

    def add_zone(self, zone_id: str, name: str, region: str, zone_type: str,
                 status: str, estimated_connections: int, description: str) -> bool:
        """Add a new zone to the database"""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO zones (zone_id, name, region, type, status, estimated_connections, description)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (zone_id.upper(), name, region, zone_type, status, estimated_connections, description))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def add_meter(self, meter_id: str, zone_id: str, location: str, meter_type: str,
                  status: str, flow_rate: float, description: str) -> bool:
        """Add a new meter to the database"""
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute('''
                INSERT INTO meters (meter_id, zone_id, location, meter_type, status, flow_rate, description)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            ''', (meter_id, zone_id.upper(), location, meter_type, status, flow_rate, description))
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
        finally:
            conn.close()

    def seed_default_zones(self):
        """Seed Thika zones with subdivisions"""
        print("Seeding default zones...")
        default_zones = [
            # Thika Central (Urban Core)
            ("THK-CEN-001", "Thika Town Central - CBD", "thika_central", "central", "active", 250, "Thika central business district main supply"),
            ("THK-CEN-002", "Thika Town Central - Market", "thika_central", "commercial", "active", 180, "Main market and surrounding commercial area"),
            ("THK-CEN-003", "Thika Town Central - Railway", "thika_central", "mixed", "active", 120, "Railway station and adjacent residential"),
            
            # Thika West
            ("THK-WST-001", "Thika West - Makongeni East", "thika_west", "residential", "active", 320, "Makongeni eastern residential zone"),
            ("THK-WST-002", "Thika West - Makongeni West", "thika_west", "residential", "active", 280, "Makongeni western residential zone"),
            ("THK-WST-003", "Thika West - Section 9", "thika_west", "residential", "active", 350, "Section 9 residential and light commercial"),
            ("THK-WST-004", "Thika West - Section 2", "thika_west", "residential", "active", 220, "Section 2 residential area"),
            ("THK-WST-005", "Thika West - Thika Greens", "thika_west", "residential", "active", 180, "Thika Greens estate area"),
            ("THK-WST-006", "Thika West - Chania", "thika_west", "mixed", "active", 200, "Chania area near the river"),
            ("THK-WST-007", "Thika West - Blue Posts", "thika_west", "commercial", "active", 150, "Blue Posts hotel and tourism area"),
            
            # Thika East
            ("THK-EST-001", "Thika East - Kiganjo North", "thika_east", "residential", "active", 290, "Kiganjo northern residential area"),
            ("THK-EST-002", "Thika East - Kiganjo South", "thika_east", "residential", "active", 310, "Kiganjo southern residential area"),
            ("THK-EST-003", "Thika East - Ngoingwa", "thika_east", "residential", "active", 260, "Ngoingwa residential zone"),
            ("THK-EST-004", "Thika East - Landless", "thika_east", "residential", "active", 190, "Landless area residential"),
            ("THK-EST-005", "Thika East - Karatu", "thika_east", "mixed", "active", 170, "Karatu mixed use area"),
            ("THK-EST-006", "Thika East - Kamakis", "thika_east", "residential", "active", 240, "Kamakis residential estates"),
            ("THK-EST-007", "Thika East - Riverside", "thika_east", "residential", "active", 210, "Riverside residential area"),
            
            # Thika North
            ("THK-NTH-001", "Thika North - Witeithie", "thika_north", "residential", "active", 380, "Witeithie main residential zone"),
            ("THK-NTH-002", "Thika North - Witeithie Industrial", "thika_north", "industrial", "active", 140, "Witeithie light industrial area"),
            ("THK-NTH-003", "Thika North - Mang'u", "thika_north", "mixed", "active", 200, "Mangu area mixed residential and commercial"),
            ("THK-NTH-004", "Thika North - Gatuanyaga", "thika_north", "residential", "active", 230, "Gatuanyaga residential zone"),
            ("THK-NTH-005", "Thika North - Ngoliba", "thika_north", "residential", "active", 160, "Ngoliba residential area"),
            ("THK-NTH-006", "Thika North - Kisii", "thika_north", "residential", "active", 190, "Kisii residential zone"),
            ("THK-NTH-007", "Thika North - Kiang'ombe", "thika_north", "residential", "active", 250, "Kiang'ombe residential area"),
            
            # Industrial Areas
            ("THK-IND-001", "Thika Industrial - Main", "thika_industrial", "industrial", "active", 120, "Main Thika industrial zone"),
            ("THK-IND-002", "Thika Industrial - Del Monte", "thika_industrial", "industrial", "active", 85, "Del Monte and surrounding industrial"),
            ("THK-IND-003", "Thika Industrial - Bata", "thika_industrial", "industrial", "active", 95, "Bata area industrial zone"),
            
            # Special Areas
            ("THK-SPL-001", "Thika Barracks", "thika_special", "institutional", "active", 80, "Kenya Army Thika Barracks"),
            ("THK-SPL-002", "Makadara", "thika_special", "commercial", "active", 110, "Makadara commercial zone"),
            ("THK-SPL-003", "Slaughterhouse", "thika_special", "industrial", "active", 65, "Thika slaughterhouse and meat processing"),
        ]
        for zone in default_zones:
            self.add_zone(*zone)
    
    def seed_default_meters(self):
        """Seed default meters - multiple meters per zone for realistic deployment (flow rates match training data ~4.8-16.0)"""
        default_meters = [
            # Thika Central - CBD (250 connections, 25 meters ~10 each - smaller DMAs)
            ("MTR-001", "THK-CEN-001", "CBD Block A1", "commercial", "active", 8.5, "CBD block A1 DMA"),
            ("MTR-002", "THK-CEN-001", "CBD Block A2", "commercial", "active", 8.2, "CBD block A2 DMA"),
            ("MTR-003", "THK-CEN-001", "CBD Block A3", "commercial", "active", 7.8, "CBD block A3 DMA"),
            ("MTR-124", "THK-CEN-001", "CBD Block B1", "commercial", "active", 8.5, "CBD block B1 DMA"),
            ("MTR-125", "THK-CEN-001", "CBD Block B2", "commercial", "active", 8.2, "CBD block B2 DMA"),
            ("MTR-126", "THK-CEN-001", "CBD Block B3", "commercial", "active", 7.8, "CBD block B3 DMA"),
            ("MTR-127", "THK-CEN-001", "CBD Block C1", "commercial", "active", 8.5, "CBD block C1 DMA"),
            ("MTR-128", "THK-CEN-001", "CBD Block C2", "commercial", "active", 8.2, "CBD block C2 DMA"),
            ("MTR-129", "THK-CEN-001", "CBD Block C3", "commercial", "active", 7.8, "CBD block C3 DMA"),
            ("MTR-130", "THK-CEN-001", "CBD North Main", "commercial", "active", 9.2, "CBD north main DMA"),
            ("MTR-131", "THK-CEN-001", "CBD North Extension", "commercial", "active", 8.5, "CBD north extension DMA"),
            ("MTR-132", "THK-CEN-001", "CBD South Main", "commercial", "active", 9.2, "CBD south main DMA"),
            ("MTR-133", "THK-CEN-001", "CBD South Extension", "commercial", "active", 8.5, "CBD south extension DMA"),
            ("MTR-134", "THK-CEN-001", "CBD East Main", "commercial", "active", 9.2, "CBD east main DMA"),
            ("MTR-135", "THK-CEN-001", "CBD East Extension", "commercial", "active", 8.5, "CBD east extension DMA"),
            ("MTR-136", "THK-CEN-001", "CBD West Main", "commercial", "active", 9.2, "CBD west main DMA"),
            ("MTR-137", "THK-CEN-001", "CBD West Extension", "commercial", "active", 8.5, "CBD west extension DMA"),
            ("MTR-138", "THK-CEN-001", "CBD Central Plaza", "commercial", "active", 9.5, "CBD central plaza DMA"),
            ("MTR-139", "THK-CEN-001", "CBD Central Market", "commercial", "active", 8.8, "CBD central market DMA"),
            ("MTR-140", "THK-CEN-001", "CBD CBD Mall", "commercial", "active", 9.2, "CBD mall DMA"),
            ("MTR-141", "THK-CEN-001", "CBD CBD Office Park", "commercial", "active", 8.5, "CBD office park DMA"),
            ("MTR-142", "THK-CEN-001", "CBD CBD Industrial", "commercial", "active", 8.2, "CBD industrial DMA"),
            ("MTR-143", "THK-CEN-001", "CBD CBD Mixed Zone", "commercial", "active", 7.8, "CBD mixed zone DMA"),
            ("MTR-144", "THK-CEN-001", "CBD CBD Residential", "commercial", "active", 7.5, "CBD residential DMA"),
            ("MTR-145", "THK-CEN-001", "CBD CBD Outskirts", "commercial", "active", 7.2, "CBD outskirts DMA"),

            # Thika Central - Market (180 connections, 18 meters ~10 each - smaller DMAs)
            ("MTR-004", "THK-CEN-002", "Market Block A", "commercial", "active", 8.5, "Market block A DMA"),
            ("MTR-005", "THK-CEN-002", "Market Block B", "commercial", "active", 8.2, "Market block B DMA"),
            ("MTR-006", "THK-CEN-002", "Market Block C", "commercial", "active", 7.8, "Market block C DMA"),
            ("MTR-146", "THK-CEN-002", "Market Block D", "commercial", "active", 7.5, "Market block D DMA"),
            ("MTR-147", "THK-CEN-002", "Market Block E", "commercial", "active", 7.2, "Market block E DMA"),
            ("MTR-148", "THK-CEN-002", "Market North Main", "commercial", "active", 8.8, "Market north main DMA"),
            ("MTR-149", "THK-CEN-002", "Market North Extension", "commercial", "active", 8.2, "Market north extension DMA"),
            ("MTR-150", "THK-CEN-002", "Market South Main", "commercial", "active", 8.8, "Market south main DMA"),
            ("MTR-151", "THK-CEN-002", "Market South Extension", "commercial", "active", 8.2, "Market south extension DMA"),
            ("MTR-152", "THK-CEN-002", "Market East Main", "commercial", "active", 8.5, "Market east main DMA"),
            ("MTR-153", "THK-CEN-002", "Market East Extension", "commercial", "active", 7.8, "Market east extension DMA"),
            ("MTR-154", "THK-CEN-002", "Market West Main", "commercial", "active", 8.5, "Market west main DMA"),
            ("MTR-155", "THK-CEN-002", "Market West Extension", "commercial", "active", 7.8, "Market west extension DMA"),
            ("MTR-156", "THK-CEN-002", "Market Storage A", "commercial", "active", 8.2, "Market storage A DMA"),
            ("MTR-157", "THK-CEN-002", "Market Storage B", "commercial", "active", 7.8, "Market storage B DMA"),
            ("MTR-158", "THK-CEN-002", "Market Storage C", "commercial", "active", 7.5, "Market storage C DMA"),
            ("MTR-159", "THK-CEN-002", "Market Loading Bay", "commercial", "active", 8.8, "Market loading bay DMA"),
            ("MTR-160", "THK-CEN-002", "Market Parking Area", "commercial", "active", 7.5, "Market parking DMA"),

            # Thika Central - Railway (120 connections, 12 meters ~10 each - smaller DMAs)
            ("MTR-007", "THK-CEN-003", "Railway Station Main", "mixed", "active", 9.2, "Station main DMA"),
            ("MTR-008", "THK-CEN-003", "Railway Platform A", "mixed", "active", 8.5, "Platform A DMA"),
            ("MTR-009", "THK-CEN-003", "Railway Platform B", "mixed", "active", 8.2, "Platform B DMA"),
            ("MTR-161", "THK-CEN-003", "Railway Platform C", "mixed", "active", 7.8, "Platform C DMA"),
            ("MTR-162", "THK-CEN-003", "Railway Platform D", "mixed", "active", 7.5, "Platform D DMA"),
            ("MTR-163", "THK-CEN-003", "Railway North Zone", "mixed", "active", 8.2, "Railway north zone DMA"),
            ("MTR-164", "THK-CEN-003", "Railway South Zone", "mixed", "active", 8.2, "Railway south zone DMA"),
            ("MTR-165", "THK-CEN-003", "Railway East Zone", "mixed", "active", 7.8, "Railway east zone DMA"),
            ("MTR-166", "THK-CEN-003", "Railway West Zone", "mixed", "active", 7.8, "Railway west zone DMA"),
            ("MTR-167", "THK-CEN-003", "Railway Parking A", "mixed", "active", 7.5, "Railway parking A DMA"),
            ("MTR-168", "THK-CEN-003", "Railway Parking B", "mixed", "active", 7.2, "Railway parking B DMA"),
            ("MTR-169", "THK-CEN-003", "Railway Service Area", "mixed", "active", 8.5, "Railway service area DMA"),

            # Thika West - Makongeni East (320 connections, 32 meters ~10 each - smaller DMAs)
            ("MTR-010", "THK-WST-001", "Makongeni East A1", "residential", "active", 8.5, "Makongeni A1 DMA"),
            ("MTR-011", "THK-WST-001", "Makongeni East A2", "residential", "active", 8.2, "Makongeni A2 DMA"),
            ("MTR-012", "THK-WST-001", "Makongeni East A3", "residential", "active", 7.8, "Makongeni A3 DMA"),
            ("MTR-013", "THK-WST-001", "Makongeni East B1", "residential", "active", 8.5, "Makongeni B1 DMA"),
            ("MTR-018", "THK-WST-001", "Makongeni East B2", "residential", "active", 8.2, "Makongeni B2 DMA"),
            ("MTR-019", "THK-WST-001", "Makongeni East B3", "residential", "active", 7.8, "Makongeni B3 DMA"),
            ("MTR-170", "THK-WST-001", "Makongeni East C1", "residential", "active", 7.5, "Makongeni C1 DMA"),
            ("MTR-171", "THK-WST-001", "Makongeni East C2", "residential", "active", 7.2, "Makongeni C2 DMA"),
            ("MTR-172", "THK-WST-001", "Makongeni East C3", "residential", "active", 6.8, "Makongeni C3 DMA"),
            ("MTR-173", "THK-WST-001", "Makongeni East D1", "residential", "active", 7.5, "Makongeni D1 DMA"),
            ("MTR-174", "THK-WST-001", "Makongeni East D2", "residential", "active", 7.2, "Makongeni D2 DMA"),
            ("MTR-175", "THK-WST-001", "Makongeni East D3", "residential", "active", 6.8, "Makongeni D3 DMA"),
            ("MTR-176", "THK-WST-001", "Makongeni East E1", "residential", "active", 7.2, "Makongeni E1 DMA"),
            ("MTR-177", "THK-WST-001", "Makongeni East E2", "residential", "active", 6.8, "Makongeni E2 DMA"),
            ("MTR-178", "THK-WST-001", "Makongeni East F1", "residential", "active", 6.8, "Makongeni F1 DMA"),
            ("MTR-179", "THK-WST-001", "Makongeni East F2", "residential", "active", 6.5, "Makongeni F2 DMA"),
            ("MTR-180", "THK-WST-001", "Makongeni North Main", "residential", "active", 8.2, "Makongeni north main DMA"),
            ("MTR-181", "THK-WST-001", "Makongeni South Main", "residential", "active", 8.2, "Makongeni south main DMA"),
            ("MTR-182", "THK-WST-001", "Makongeni East Main", "residential", "active", 7.8, "Makongeni east main DMA"),
            ("MTR-183", "THK-WST-001", "Makongeni West Main", "residential", "active", 7.8, "Makongeni west main DMA"),
            ("MTR-184", "THK-WST-001", "Makongeni Central", "residential", "active", 8.5, "Makongeni central DMA"),
            ("MTR-185", "THK-WST-001", "Makongeni Outskirts", "residential", "active", 7.2, "Makongeni outskirts DMA"),
            ("MTR-186", "THK-WST-001", "Makongeni Extension A", "residential", "active", 6.8, "Makongeni extension A DMA"),
            ("MTR-187", "THK-WST-001", "Makongeni Extension B", "residential", "active", 6.5, "Makongeni extension B DMA"),
            ("MTR-188", "THK-WST-001", "Makongeni Extension C", "residential", "active", 6.2, "Makongeni extension C DMA"),
            ("MTR-189", "THK-WST-001", "Makongeni Mixed Zone A", "residential", "active", 7.5, "Makongeni mixed A DMA"),
            ("MTR-190", "THK-WST-001", "Makongeni Mixed Zone B", "residential", "active", 7.2, "Makongeni mixed B DMA"),
            ("MTR-191", "THK-WST-001", "Makongeni Commercial", "residential", "active", 8.2, "Makongeni commercial DMA"),
            ("MTR-192", "THK-WST-001", "Makongeni Institutional", "residential", "active", 7.5, "Makongeni institutional DMA"),
            ("MTR-193", "THK-WST-001", "Makongeni Service Area", "residential", "active", 6.8, "Makongeni service DMA"),

            # Thika West - Makongeni West (280 connections, 28 meters ~10 each - smaller DMAs)
            ("MTR-014", "THK-WST-002", "Makongeni West A1", "residential", "active", 8.5, "Makongeni W A1 DMA"),
            ("MTR-020", "THK-WST-002", "Makongeni West A2", "residential", "active", 8.2, "Makongeni W A2 DMA"),
            ("MTR-021", "THK-WST-002", "Makongeni West A3", "residential", "active", 7.8, "Makongeni W A3 DMA"),
            ("MTR-022", "THK-WST-002", "Makongeni West B1", "residential", "active", 8.5, "Makongeni W B1 DMA"),
            ("MTR-023", "THK-WST-002", "Makongeni West B2", "residential", "active", 8.2, "Makongeni W B2 DMA"),
            ("MTR-194", "THK-WST-002", "Makongeni West B3", "residential", "active", 7.8, "Makongeni W B3 DMA"),
            ("MTR-195", "THK-WST-002", "Makongeni West C1", "residential", "active", 7.5, "Makongeni W C1 DMA"),
            ("MTR-196", "THK-WST-002", "Makongeni West C2", "residential", "active", 7.2, "Makongeni W C2 DMA"),
            ("MTR-197", "THK-WST-002", "Makongeni West C3", "residential", "active", 6.8, "Makongeni W C3 DMA"),
            ("MTR-198", "THK-WST-002", "Makongeni West D1", "residential", "active", 7.5, "Makongeni W D1 DMA"),
            ("MTR-199", "THK-WST-002", "Makongeni West D2", "residential", "active", 7.2, "Makongeni W D2 DMA"),
            ("MTR-200", "THK-WST-002", "Makongeni West E1", "residential", "active", 7.2, "Makongeni W E1 DMA"),
            ("MTR-201", "THK-WST-002", "Makongeni West E2", "residential", "active", 6.8, "Makongeni W E2 DMA"),
            ("MTR-202", "THK-WST-002", "Makongeni West North", "residential", "active", 8.2, "Makongeni W north DMA"),
            ("MTR-203", "THK-WST-002", "Makongeni West South", "residential", "active", 8.2, "Makongeni W south DMA"),
            ("MTR-204", "THK-WST-002", "Makongeni West East", "residential", "active", 7.8, "Makongeni W east DMA"),
            ("MTR-205", "THK-WST-002", "Makongeni West West", "residential", "active", 7.8, "Makongeni W west DMA"),
            ("MTR-206", "THK-WST-002", "Makongeni West Central", "residential", "active", 8.5, "Makongeni W central DMA"),
            ("MTR-207", "THK-WST-002", "Makongeni West Outskirts", "residential", "active", 7.2, "Makongeni W outskirts DMA"),
            ("MTR-208", "THK-WST-002", "Makongeni West Extension A", "residential", "active", 6.8, "Makongeni W extension A DMA"),
            ("MTR-209", "THK-WST-002", "Makongeni West Extension B", "residential", "active", 6.5, "Makongeni W extension B DMA"),
            ("MTR-210", "THK-WST-002", "Makongeni West Mixed Zone", "residential", "active", 7.5, "Makongeni W mixed DMA"),
            ("MTR-211", "THK-WST-002", "Makongeni West Commercial", "residential", "active", 8.2, "Makongeni W commercial DMA"),
            ("MTR-212", "THK-WST-002", "Makongeni West Service Area", "residential", "active", 6.8, "Makongeni W service DMA"),

            # Thika West - Section 9 (350 connections, 35 meters ~10 each - smaller DMAs)
            ("MTR-024", "THK-WST-003", "Section 9 A1", "mixed", "active", 9.2, "Section 9 A1 DMA"),
            ("MTR-025", "THK-WST-003", "Section 9 A2", "mixed", "active", 8.8, "Section 9 A2 DMA"),
            ("MTR-026", "THK-WST-003", "Section 9 A3", "mixed", "active", 8.5, "Section 9 A3 DMA"),
            ("MTR-027", "THK-WST-003", "Section 9 B1", "mixed", "active", 8.5, "Section 9 B1 DMA"),
            ("MTR-028", "THK-WST-003", "Section 9 B2", "mixed", "active", 8.2, "Section 9 B2 DMA"),
            ("MTR-029", "THK-WST-003", "Section 9 B3", "mixed", "active", 7.8, "Section 9 B3 DMA"),
            ("MTR-030", "THK-WST-003", "Section 9 C1", "mixed", "active", 8.2, "Section 9 C1 DMA"),
            ("MTR-213", "THK-WST-003", "Section 9 C2", "mixed", "active", 7.8, "Section 9 C2 DMA"),
            ("MTR-214", "THK-WST-003", "Section 9 C3", "mixed", "active", 7.5, "Section 9 C3 DMA"),
            ("MTR-215", "THK-WST-003", "Section 9 D1", "mixed", "active", 7.8, "Section 9 D1 DMA"),
            ("MTR-216", "THK-WST-003", "Section 9 D2", "mixed", "active", 7.5, "Section 9 D2 DMA"),
            ("MTR-217", "THK-WST-003", "Section 9 D3", "mixed", "active", 7.2, "Section 9 D3 DMA"),
            ("MTR-218", "THK-WST-003", "Section 9 E1", "mixed", "active", 7.5, "Section 9 E1 DMA"),
            ("MTR-219", "THK-WST-003", "Section 9 E2", "mixed", "active", 7.2, "Section 9 E2 DMA"),
            ("MTR-220", "THK-WST-003", "Section 9 F1", "mixed", "active", 7.2, "Section 9 F1 DMA"),
            ("MTR-221", "THK-WST-003", "Section 9 F2", "mixed", "active", 6.8, "Section 9 F2 DMA"),
            ("MTR-222", "THK-WST-003", "Section 9 G1", "mixed", "active", 6.8, "Section 9 G1 DMA"),
            ("MTR-223", "THK-WST-003", "Section 9 G2", "mixed", "active", 6.5, "Section 9 G2 DMA"),
            ("MTR-224", "THK-WST-003", "Section 9 North Main", "mixed", "active", 8.5, "Section 9 north main DMA"),
            ("MTR-225", "THK-WST-003", "Section 9 South Main", "mixed", "active", 8.5, "Section 9 south main DMA"),
            ("MTR-226", "THK-WST-003", "Section 9 East Main", "mixed", "active", 8.2, "Section 9 east main DMA"),
            ("MTR-227", "THK-WST-003", "Section 9 West Main", "mixed", "active", 8.2, "Section 9 west main DMA"),
            ("MTR-228", "THK-WST-003", "Section 9 Central", "mixed", "active", 8.8, "Section 9 central DMA"),
            ("MTR-229", "THK-WST-003", "Section 9 Outskirts", "mixed", "active", 7.2, "Section 9 outskirts DMA"),
            ("MTR-230", "THK-WST-003", "Section 9 Extension A", "mixed", "active", 6.8, "Section 9 extension A DMA"),
            ("MTR-231", "THK-WST-003", "Section 9 Extension B", "mixed", "active", 6.5, "Section 9 extension B DMA"),
            ("MTR-232", "THK-WST-003", "Section 9 Mixed Zone", "mixed", "active", 7.5, "Section 9 mixed DMA"),
            ("MTR-233", "THK-WST-003", "Section 9 Commercial", "mixed", "active", 8.2, "Section 9 commercial DMA"),
            ("MTR-234", "THK-WST-003", "Section 9 Service Area", "mixed", "active", 6.8, "Section 9 service DMA"),

            # Thika West - Section 2 (220 connections, 4 meters ~55 each)
            ("MTR-031", "THK-WST-004", "Section 2 North", "residential", "active", 9.5, "Section 2 north supply"),
            ("MTR-032", "THK-WST-004", "Section 2 South", "residential", "active", 8.8, "Section 2 south supply"),
            ("MTR-033", "THK-WST-004", "Section 2 East", "residential", "active", 8.2, "Section 2 east supply"),
            ("MTR-034", "THK-WST-004", "Section 2 West", "residential", "active", 7.5, "Section 2 west supply"),

            # Thika West - Thika Greens (180 connections, 4 meters ~45 each)
            ("MTR-035", "THK-WST-005", "Thika Greens Estate A", "residential", "active", 8.5, "Estate A supply"),
            ("MTR-036", "THK-WST-005", "Thika Greens Estate B", "residential", "active", 7.8, "Estate B supply"),
            ("MTR-037", "THK-WST-005", "Thika Greens Estate C", "residential", "active", 7.2, "Estate C supply"),
            ("MTR-038", "THK-WST-005", "Thika Greens Estate D", "residential", "active", 6.5, "Estate D supply"),

            # Thika West - Chania (200 connections, 4 meters ~50 each)
            ("MTR-055", "THK-WST-006", "Chania North", "mixed", "active", 9.8, "Chania north supply"),
            ("MTR-056", "THK-WST-006", "Chania South", "mixed", "active", 8.5, "Chania south supply"),
            ("MTR-057", "THK-WST-006", "Chania East", "residential", "active", 7.8, "Chania east supply"),
            ("MTR-058", "THK-WST-006", "Chania West", "residential", "active", 7.2, "Chania west supply"),

            # Thika West - Blue Posts (150 connections, 3 meters ~50 each)
            ("MTR-059", "THK-WST-007", "Blue Posts Main", "commercial", "active", 9.2, "Blue Posts main supply"),
            ("MTR-060", "THK-WST-007", "Blue Posts Hotel", "commercial", "active", 8.5, "Hotel area supply"),
            ("MTR-061", "THK-WST-007", "Blue Posts Tourism", "commercial", "active", 7.8, "Tourism area supply"),

            # Thika East - Kiganjo North (290 connections, 5 meters ~58 each)
            ("MTR-039", "THK-EST-001", "Kiganjo North Zone 1", "residential", "active", 9.8, "Zone 1 supply"),
            ("MTR-040", "THK-EST-001", "Kiganjo North Zone 2", "residential", "active", 9.2, "Zone 2 supply"),
            ("MTR-041", "THK-EST-001", "Kiganjo North Zone 3", "residential", "active", 8.5, "Zone 3 supply"),
            ("MTR-042", "THK-EST-001", "Kiganjo North Zone 4", "residential", "active", 7.8, "Zone 4 supply"),
            ("MTR-043", "THK-EST-001", "Kiganjo North Zone 5", "residential", "active", 7.2, "Zone 5 supply"),

            # Thika East - Kiganjo South (310 connections, 6 meters ~52 each)
            ("MTR-044", "THK-EST-002", "Kiganjo South Sector A", "residential", "active", 10.2, "Sector A supply"),
            ("MTR-045", "THK-EST-002", "Kiganjo South Sector B", "residential", "active", 9.5, "Sector B supply"),
            ("MTR-046", "THK-EST-002", "Kiganjo South Sector C", "residential", "active", 8.8, "Sector C supply"),
            ("MTR-047", "THK-EST-002", "Kiganjo South Sector D", "residential", "active", 8.2, "Sector D supply"),
            ("MTR-048", "THK-EST-002", "Kiganjo South Sector E", "residential", "active", 7.5, "Sector E supply"),
            ("MTR-049", "THK-EST-002", "Kiganjo South Sector F", "residential", "active", 6.8, "Sector F supply"),

            # Thika East - Ngoingwa (260 connections, 5 meters ~52 each)
            ("MTR-050", "THK-EST-003", "Ngoingwa Central", "residential", "active", 9.2, "Central distribution"),
            ("MTR-051", "THK-EST-003", "Ngoingwa North", "residential", "active", 8.5, "North supply"),
            ("MTR-052", "THK-EST-003", "Ngoingwa South", "residential", "active", 7.8, "South supply"),
            ("MTR-053", "THK-EST-003", "Ngoingwa East", "residential", "active", 7.2, "East supply"),
            ("MTR-054", "THK-EST-003", "Ngoingwa West", "residential", "active", 6.5, "West supply"),

            # Thika East - Landless (100 connections, 4 meters ~25 each)
            ("MTR-062", "THK-EST-004", "Landless Main", "residential", "active", 8.5, "Landless main supply"),
            ("MTR-063", "THK-EST-004", "Landless North", "residential", "active", 7.8, "Landless north supply"),
            ("MTR-114", "THK-EST-004", "Landless South", "residential", "active", 7.2, "Landless south supply"),
            ("MTR-115", "THK-EST-004", "Landless East", "residential", "active", 6.8, "Landless east supply"),

            # Thika East - Karatu (150 connections, 6 meters ~25 each)
            ("MTR-064", "THK-EST-005", "Karatu Center", "residential", "active", 9.2, "Karatu center supply"),
            ("MTR-065", "THK-EST-005", "Karatu North", "residential", "active", 8.2, "Karatu north supply"),
            ("MTR-066", "THK-EST-005", "Karatu South", "residential", "active", 7.5, "Karatu south supply"),
            ("MTR-116", "THK-EST-005", "Karatu East", "residential", "active", 7.2, "Karatu east supply"),
            ("MTR-117", "THK-EST-005", "Karatu West", "residential", "active", 6.8, "Karatu west supply"),
            ("MTR-118", "THK-EST-005", "Karatu Extension", "residential", "active", 6.5, "Karatu extension supply"),

            # Thika East - Kamakis (180 connections, 7 meters ~26 each)
            ("MTR-067", "THK-EST-006", "Kamakis Main", "residential", "active", 9.5, "Kamakis main supply"),
            ("MTR-068", "THK-EST-006", "Kamakis East", "residential", "active", 8.5, "Kamakis east supply"),
            ("MTR-069", "THK-EST-006", "Kamakis West", "residential", "active", 7.8, "Kamakis west supply"),
            ("MTR-070", "THK-EST-006", "Kamakis North", "residential", "active", 7.2, "Kamakis north supply"),
            ("MTR-119", "THK-EST-006", "Kamakis South", "residential", "active", 6.8, "Kamakis south supply"),
            ("MTR-120", "THK-EST-006", "Kamakis Central", "residential", "active", 6.5, "Kamakis central supply"),
            ("MTR-121", "THK-EST-006", "Kamakis Outskirts", "residential", "active", 6.2, "Kamakis outskirts supply"),

            # Thika East - Riverside (120 connections, 5 meters ~24 each)
            ("MTR-071", "THK-EST-007", "Riverside Main", "residential", "active", 8.8, "Riverside main supply"),
            ("MTR-072", "THK-EST-007", "Riverside North", "residential", "active", 7.5, "Riverside north supply"),
            ("MTR-073", "THK-EST-007", "Riverside South", "residential", "active", 6.8, "Riverside south supply"),
            ("MTR-122", "THK-EST-007", "Riverside East", "residential", "active", 6.5, "Riverside east supply"),
            ("MTR-123", "THK-EST-007", "Riverside West", "residential", "active", 6.2, "Riverside west supply"),

            # Thika North - Witeithie (200 connections, 4 meters ~50 each)
            ("MTR-074", "THK-NTH-001", "Witeithie Main", "residential", "active", 9.8, "Witeithie main supply"),
            ("MTR-075", "THK-NTH-001", "Witeithie East", "residential", "active", 8.5, "Witeithie east supply"),
            ("MTR-076", "THK-NTH-001", "Witeithie West", "residential", "active", 7.8, "Witeithie west supply"),
            ("MTR-077", "THK-NTH-001", "Witeithie Central", "residential", "active", 7.2, "Witeithie central supply"),

            # Thika North - Witeithie Industrial (150 connections, 3 meters ~50 each)
            ("MTR-078", "THK-NTH-002", "Witeithie Industrial A", "industrial", "active", 10.5, "Industrial A supply"),
            ("MTR-079", "THK-NTH-002", "Witeithie Industrial B", "industrial", "active", 9.2, "Industrial B supply"),
            ("MTR-080", "THK-NTH-002", "Witeithie Industrial C", "industrial", "active", 8.5, "Industrial C supply"),

            # Thika North - Mang'u (120 connections, 3 meters ~40 each)
            ("MTR-081", "THK-NTH-003", "Mang'u Main", "residential", "active", 8.8, "Mang'u main supply"),
            ("MTR-082", "THK-NTH-003", "Mang'u North", "residential", "active", 7.5, "Mang'u north supply"),
            ("MTR-083", "THK-NTH-003", "Mang'u South", "residential", "active", 6.8, "Mang'u south supply"),

            # Thika North - Gatuanyaga (100 connections, 4 meters ~25 each)
            ("MTR-084", "THK-NTH-004", "Gatuanyaga Center", "residential", "active", 8.5, "Gatuanyaga center supply"),
            ("MTR-085", "THK-NTH-004", "Gatuanyaga North", "residential", "active", 7.8, "Gatuanyaga north supply"),
            ("MTR-112", "THK-NTH-004", "Gatuanyaga South", "residential", "active", 7.2, "Gatuanyaga south supply"),
            ("MTR-113", "THK-NTH-004", "Gatuanyaga East", "residential", "active", 6.8, "Gatuanyaga east supply"),

            # Thika North - Ngoliba (80 connections, 4 meters ~20 each)
            ("MTR-086", "THK-NTH-005", "Ngoliba Sector A", "residential", "active", 7.8, "Ngoliba sector A supply"),
            ("MTR-087", "THK-NTH-005", "Ngoliba Sector B", "residential", "active", 7.2, "Ngoliba sector B supply"),
            ("MTR-108", "THK-NTH-005", "Ngoliba Sector C", "residential", "active", 6.8, "Ngoliba sector C supply"),
            ("MTR-109", "THK-NTH-005", "Ngoliba Sector D", "residential", "active", 6.5, "Ngoliba sector D supply"),

            # Thika North - Kisii (70 connections, 3 meters ~23 each)
            ("MTR-088", "THK-NTH-006", "Kisii Main", "residential", "active", 7.2, "Kisii main supply"),
            ("MTR-089", "THK-NTH-006", "Kisii North", "residential", "active", 6.8, "Kisii north supply"),
            ("MTR-110", "THK-NTH-006", "Kisii South", "residential", "active", 6.2, "Kisii south supply"),

            # Thika North - Kiang'ombe (60 connections, 3 meters ~20 each)
            ("MTR-090", "THK-NTH-007", "Kiang'ombe Center", "residential", "active", 6.8, "Kiang'ombe center supply"),
            ("MTR-091", "THK-NTH-007", "Kiang'ombe North", "residential", "active", 6.2, "Kiang'ombe north supply"),
            ("MTR-111", "THK-NTH-007", "Kiang'ombe South", "residential", "active", 5.8, "Kiang'ombe south supply"),

            # Thika Industrial - Main (150 connections, 3 meters ~50 each)
            ("MTR-092", "THK-IND-001", "Industrial Main A", "industrial", "active", 11.5, "Industrial main A supply"),
            ("MTR-093", "THK-IND-001", "Industrial Main B", "industrial", "active", 10.2, "Industrial main B supply"),
            ("MTR-094", "THK-IND-001", "Industrial Main C", "industrial", "active", 9.5, "Industrial main C supply"),

            # Thika Industrial - Del Monte (200 connections, 4 meters ~50 each)
            ("MTR-095", "THK-IND-002", "Del Monte Farm A", "industrial", "active", 12.5, "Del Monte farm A supply"),
            ("MTR-096", "THK-IND-002", "Del Monte Farm B", "industrial", "active", 11.2, "Del Monte farm B supply"),
            ("MTR-097", "THK-IND-002", "Del Monte Processing", "industrial", "active", 10.5, "Processing plant supply"),
            ("MTR-098", "THK-IND-002", "Del Monte Storage", "industrial", "active", 9.8, "Storage facility supply"),

            # Thika Industrial - Bata (100 connections, 2 meters ~50 each)
            ("MTR-099", "THK-IND-003", "Bata Factory Main", "industrial", "active", 10.8, "Bata factory main supply"),
            ("MTR-100", "THK-IND-003", "Bata Factory Extension", "industrial", "active", 9.2, "Bata factory extension supply"),

            # Thika Barracks (80 connections, 2 meters ~40 each)
            ("MTR-101", "THK-SPL-001", "Barracks Main", "institutional", "active", 8.5, "Barracks main supply"),
            ("MTR-102", "THK-SPL-001", "Barracks Residential", "institutional", "active", 7.2, "Barracks residential supply"),

            # Makadara (110 connections, 3 meters ~37 each)
            ("MTR-103", "THK-SPL-002", "Makadara Main", "commercial", "active", 8.8, "Makadara main supply"),
            ("MTR-104", "THK-SPL-002", "Makadara Market", "commercial", "active", 7.5, "Makadara market supply"),
            ("MTR-105", "THK-SPL-002", "Makadara Residential", "commercial", "active", 6.8, "Makadara residential supply"),

            # Slaughterhouse (65 connections, 2 meters ~32 each)
            ("MTR-106", "THK-SPL-003", "Slaughterhouse Main", "industrial", "active", 7.8, "Slaughterhouse main supply"),
            ("MTR-107", "THK-SPL-003", "Slaughterhouse Processing", "industrial", "active", 6.5, "Processing plant supply"),
        ]
        for meter in default_meters:
            self.add_meter(*meter)

db_manager = DatabaseManager()
# Note: Demo data seeding is no longer automatic.
# Call db_manager.seed_demo_data() explicitly when needed (e.g., setup script or demo env)

# Keep for backward compatibility during transition - will be removed
_db_seeded = False

def seed_demo_data():
    """Seed all demo data (users, zones, meters) - call explicitly when needed"""
    global _db_seeded
    if _db_seeded:
        print("Demo data already seeded, skipping...")
        return
    
    print("Seeding demo data...")
    try:
        db_manager.seed_default_users()
        print("  - Users seeded")
    except sqlite3.OperationalError as e:
        if "database is locked" in str(e):
            print(f"  - Users: Database locked, will retry: {e}")
        else:
            raise
    
    try:
        db_manager.seed_default_zones()
        print("  - Zones seeded")
    except sqlite3.OperationalError as e:
        if "database is locked" in str(e):
            print(f"  - Zones: Database locked, will retry: {e}")
        else:
            raise
    
    try:
        db_manager.seed_default_meters()
        print("  - Meters seeded")
    except sqlite3.OperationalError as e:
        if "database is locked" in str(e):
            print(f"  - Meters: Database locked, will retry: {e}")
        else:
            raise
    
    _db_seeded = True
    print("Demo data seeding complete!")

# For backward compatibility - auto-seed on first actual DB operation
# This will be phased out in favor of explicit seed_demo_data() calls
_seed_on_first_use = True
