"""MySQL Database Manager - Replaces SQLite with MySQL"""
import mysql.connector
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, List, Optional
import threading
import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()


class MySQLDatabaseManager:
    """MySQL-backed database manager for THIWASCO leak detection system."""
    
    def __init__(self, host=None, port=None, database=None, user=None, password=None):
        # Railway MySQL plugin exposes MYSQLPASSWORD (no underscore); also accept MYSQL_PASSWORD.
        resolved_password = (
            password
            or os.getenv('MYSQL_PASSWORD')
            or os.getenv('MYSQLPASSWORD')
        )
        if resolved_password is None:
            raise ValueError(
                "MySQL password not set. Pass the 'password' argument or set the "
                "MYSQL_PASSWORD environment variable."
            )
        self.config = {
            'host': host or os.getenv('MYSQL_HOST') or os.getenv('MYSQLHOST', 'localhost'),
            'port': int(port or os.getenv('MYSQL_PORT') or os.getenv('MYSQLPORT', '3306')),
            'database': database or os.getenv('MYSQL_DATABASE') or os.getenv('MYSQLDATABASE', 'thiwasco_1'),
            'user': user or os.getenv('MYSQL_USER') or os.getenv('MYSQLUSER', 'root'),
            'password': resolved_password,
            'autocommit': True,
            'connection_timeout': 10,
        }
        self._local = threading.local()
        self._initialized = False
        # _init_db fires 16+ round-trips (CREATE TABLE, CREATE INDEX, information_schema
        # queries). On Railway, each round-trip is ~50–100 ms, adding up to 1–2 s on
        # every reconnect. Guard with a process-level flag so it only runs once.
        self._schema_ready = False
        self._schema_lock  = threading.Lock()

    def _new_conn(self):
        """Open a fresh connection; initialise the schema only on the first call."""
        try:
            conn = mysql.connector.connect(**self.config)
        except mysql.connector.Error as e:
            if "Unknown database" in str(e):
                print(f"Database '{self.config['database']}' does not exist. Creating it...")
                self._create_database()
                conn = mysql.connector.connect(**self.config)
            else:
                print(f"Database connection error: {e}")
                raise

        # Run the 16-round-trip schema initialisation exactly once per process.
        # Subsequent connections (reconnects, new threads) skip it entirely.
        if not self._schema_ready:
            with self._schema_lock:
                if not self._schema_ready:
                    self._init_db(conn)
                    self._schema_ready = True

        return conn

    def _get_conn(self, readonly: bool = False):
        """Return a healthy per-thread connection, reconnecting if necessary."""
        conn = getattr(self._local, 'conn', None)
        if conn is None:
            self._local.conn = self._new_conn()
        else:
            try:
                if not conn.is_connected():
                    conn.reconnect(attempts=2, delay=1)
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass
                self._local.conn = self._new_conn()
        return self._local.conn
    
    def _create_database(self):
        """Create the database if it doesn't exist."""
        config_without_db = self.config.copy()
        db_name = config_without_db.pop('database')
        
        try:
            # Connect to MySQL server without specifying database
            conn = mysql.connector.connect(**config_without_db)
            cursor = conn.cursor()
            
            # Create database
            cursor.execute(f"CREATE DATABASE IF NOT EXISTS `{db_name}` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
            print(f"Database '{db_name}' created successfully!")
            
            cursor.close()
            conn.close()
        except mysql.connector.Error as e:
            print(f"Error creating database: {e}")
            raise
    
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
        
        # Users table — must precede alerts and teams (both have FKs to users)
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

        # Alerts table — depends on meters (meter_id FK) and users (resolved_by FK)
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
                resolved_by VARCHAR(50),
                FOREIGN KEY (meter_id) REFERENCES meters(meter_id),
                FOREIGN KEY (resolved_by) REFERENCES users(user_id)
            )
        ''')

        # Teams table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS teams (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(100) NOT NULL UNIQUE,
                description TEXT,
                created_by VARCHAR(50) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                status VARCHAR(20) DEFAULT 'active',
                FOREIGN KEY (created_by) REFERENCES users(user_id)
            )
        ''')
        
        # Team members junction table
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS team_members (
                id INT AUTO_INCREMENT PRIMARY KEY,
                team_id INT NOT NULL,
                user_id VARCHAR(50) NOT NULL,
                added_by VARCHAR(50) NOT NULL,
                added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE CASCADE,
                FOREIGN KEY (user_id) REFERENCES users(user_id),
                FOREIGN KEY (added_by) REFERENCES users(user_id),
                UNIQUE KEY unique_team_member (team_id, user_id)
            )
        ''')
        
        # Add team_id to alerts table if it doesn't exist
        # Check if column exists first
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s
            AND TABLE_NAME = 'alerts'
            AND COLUMN_NAME = 'team_id'
        """, (self.config['database'],))
        
        result = cursor.fetchone()
        if result[0] == 0:
            cursor.execute('''
                ALTER TABLE alerts 
                ADD COLUMN team_id INT,
                ADD FOREIGN KEY (team_id) REFERENCES teams(id) ON DELETE SET NULL
            ''')
        
        # Add resolved_by to alerts table if it doesn't exist
        cursor.execute("""
            SELECT COUNT(*) as count
            FROM information_schema.COLUMNS
            WHERE TABLE_SCHEMA = %s
            AND TABLE_NAME = 'alerts'
            AND COLUMN_NAME = 'resolved_by'
        """, (self.config['database'],))
        
        result = cursor.fetchone()
        if result[0] == 0:
            cursor.execute('''
                ALTER TABLE alerts 
                ADD COLUMN resolved_by VARCHAR(50),
                ADD FOREIGN KEY (resolved_by) REFERENCES users(user_id)
            ''')
        
        # User sessions table — persists login tokens across page reloads
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_sessions (
                token       VARCHAR(64)  PRIMARY KEY,
                user_id     VARCHAR(50)  NOT NULL,
                created_at  TIMESTAMP    DEFAULT CURRENT_TIMESTAMP,
                expires_at  TIMESTAMP    NOT NULL,
                last_activity TIMESTAMP  DEFAULT CURRENT_TIMESTAMP,
                remember_me BOOLEAN      DEFAULT FALSE,
                FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
            )
        ''')

        # Performance indexes — silently skip if already exist (errno 1061)
        for idx_sql in [
            "CREATE INDEX idx_sr_ts         ON sensor_readings (timestamp)",
            "CREATE INDEX idx_sr_meter_ts   ON sensor_readings (meter_id, timestamp)",
            "CREATE INDEX idx_lp_ts         ON leak_predictions (timestamp)",
            "CREATE INDEX idx_lp_meter_ts   ON leak_predictions (meter_id, timestamp)",
            "CREATE INDEX idx_al_created    ON alerts (created_at)",
            "CREATE INDEX idx_al_meter_stat ON alerts (meter_id, status)",
        ]:
            try:
                cursor.execute(idx_sql)
            except mysql.connector.Error:
                pass  # index already exists

        conn.commit()
        cursor.close()

    def _query_to_df(self, query, params=None) -> pd.DataFrame:
        """Execute query and return DataFrame, reconnecting on a dead connection."""
        for attempt in range(2):
            try:
                conn = self._get_conn()
                cursor = conn.cursor(dictionary=True)
                cursor.execute(query, params or ())
                results = cursor.fetchall()
                cursor.close()
                return pd.DataFrame(results) if results else pd.DataFrame()
            except mysql.connector.errors.DatabaseError as exc:
                if attempt == 0:
                    try:
                        self._local.conn.close()
                    except Exception:
                        pass
                    self._local.conn = None
                    continue
                raise
    
    def _execute(self, query, params=None, _retries: int = 2):
        """Execute a write operation, retrying once on lock-wait timeout (1205)."""
        for attempt in range(_retries):
            try:
                conn = self._get_conn()
                cursor = conn.cursor()
                cursor.execute(query, params or ())
                cursor.close()
                return
            except mysql.connector.errors.DatabaseError as exc:
                if exc.errno == 1205 and attempt < _retries - 1:
                    try:
                        self._local.conn.close()
                    except Exception:
                        pass
                    self._local.conn = None
                    import time as _time
                    _time.sleep(0.5)
                    continue
                raise
    
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
    
    def get_alerts(self, severity: Optional[str] = None, status: Optional[str] = None, team_id: Optional[int] = None, hours: int = 24) -> pd.DataFrame:
        since = datetime.now() - timedelta(hours=hours)
        query = "SELECT * FROM alerts WHERE created_at > %s"
        params = [since]
        
        if severity:
            query += " AND severity = %s"
            params.append(severity)
        if status:
            query += " AND status = %s"
            params.append(status)
        if team_id is not None:
            query += " AND team_id = %s"
            params.append(team_id)
        
        query += " ORDER BY created_at DESC"
        
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
    
    def get_field_technicians(self) -> pd.DataFrame:
        """Get all active Field Technicians with their current team assignment (if any)."""
        return self._query_to_df("""
            SELECT u.user_id, u.name, u.email, u.status,
                   (SELECT t.name FROM team_members tm
                    JOIN teams t ON tm.team_id = t.id
                    WHERE tm.user_id = u.user_id AND t.status = 'active'
                    LIMIT 1) AS current_team
            FROM users u
            WHERE u.role = 'Field Technician' AND u.status = 'active'
            ORDER BY u.name
        """)
    
    def get_users_by_role(self, role: str) -> pd.DataFrame:
        """Get all users with a specific role"""
        return self._query_to_df(
            "SELECT user_id, name, email, role, status FROM users WHERE role = %s AND status = 'active'",
            (role,)
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
        """Add a new meter - validates zone exists first"""
        # Verify zone exists before creating meter
        zone_df = self._query_to_df("SELECT * FROM zones WHERE zone_id = %s", (zone_id,))
        if zone_df.empty:
            print(f"Warning: Zone '{zone_id}' does not exist. Meter '{meter_id}' not created.")
            return False
        
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
    
    def add_leak_prediction(self, meter_id: str, confidence: float,
                           leak_detected: bool, leak_type: str, features: str):
        """Upsert leak prediction — one row per meter, replaced on every state change."""
        import numpy as np
        if isinstance(leak_detected, (np.bool_, np.generic)):
            leak_detected = bool(leak_detected)
        if isinstance(confidence, (np.floating, np.generic)):
            confidence = float(confidence)

        timestamp = datetime.now()
        self._execute("DELETE FROM leak_predictions WHERE meter_id = %s", (meter_id,))
        self._execute(
            "INSERT INTO leak_predictions (meter_id, timestamp, confidence, leak_detected, leak_type, features) "
            "VALUES (%s, %s, %s, %s, %s, %s)",
            (meter_id, timestamp, confidence, leak_detected, leak_type, features)
        )
    
    def add_alert(self, meter_id: str, zone_id: str, severity: str, title: str, message: str):
        self._execute(
            "INSERT INTO alerts (meter_id, zone_id, severity, title, message) VALUES (%s, %s, %s, %s, %s)",
            (meter_id, zone_id, severity, title, message)
        )
    
    def get_active_alert_for_meter(self, meter_id: str, severity: str = None, hours: int = None) -> Optional[Dict]:
        """Return the most recent unresolved alert for a meter, regardless of severity.

        One active alert per meter at any time — the severity parameter is ignored
        so that a confidence change (warning → critical) does not create a second alert.
        """
        df = self._query_to_df('''
            SELECT id, severity, status, created_at
            FROM alerts
            WHERE meter_id = %s AND status != 'resolved'
            ORDER BY created_at DESC
            LIMIT 1
        ''', (meter_id,))

        if not df.empty:
            return df.iloc[0].to_dict()
        return None
    
    def get_recent_zone_alert(self, zone_id: str, within_minutes: int = 15) -> Optional[Dict]:
        """Return the most recent alert in a zone created within `within_minutes`.

        Used by the prediction loop to detect same-source leaks — if another meter
        in the same zone was already flagged recently, the new detection is likely
        the same pipe rupture propagating hydraulically, not a separate leak.

        Purely time-based: status is ignored so that an unassigned (unresolvable)
        alert does not permanently hold the zone open.
        """
        df = self._query_to_df('''
            SELECT id, meter_id, severity, created_at
            FROM alerts
            WHERE zone_id = %s
              AND created_at >= NOW() - INTERVAL %s MINUTE
            ORDER BY created_at DESC
            LIMIT 1
        ''', (zone_id, within_minutes))
        return df.iloc[0].to_dict() if not df.empty else None

    def clear_all_alerts(self):
        """Clear all alerts from database (useful for cleaning up false positives)"""
        self._execute("DELETE FROM alerts")
        print("All alerts cleared from database")
    
    def clear_all_leak_predictions(self):
        """Clear all leak predictions from database (useful for cleaning up false positives)"""
        self._execute("DELETE FROM leak_predictions")
        print("All leak predictions cleared from database")
    
    def update_alert_status(self, alert_id: int, status: str):
        if status == 'resolved':
            self._execute(
                "UPDATE alerts SET status = %s, resolved_at = %s WHERE id = %s",
                (status, datetime.now(), alert_id)
            )
        else:
            self._execute(
                "UPDATE alerts SET status = %s WHERE id = %s",
                (status, alert_id)
            )
    
    def cleanup_old_alerts(self, days: int = 7) -> int:
        """Archive/delete resolved alerts older than specified days"""
        cutoff_date = datetime.now() - timedelta(days=days)
        conn = self._get_conn()
        cursor = conn.cursor()
        try:
            cursor.execute(
                "DELETE FROM alerts WHERE status = 'resolved' AND resolved_at < %s",
                (cutoff_date,)
            )
            deleted_count = cursor.rowcount
        finally:
            cursor.close()
        if deleted_count > 0:
            print(f"Cleaned up {deleted_count} resolved alerts older than {days} days")
        return deleted_count
    
    def get_dashboard_stats(self) -> Dict:
        """Get comprehensive dashboard statistics - consistent across all pages"""
        # Basic counts
        active_meters_df = self._query_to_df("SELECT COUNT(*) as count FROM meters WHERE status = 'active'")
        active_meters = active_meters_df.iloc[0]['count'] if not active_meters_df.empty else 0
        
        total_meters_df = self._query_to_df("SELECT COUNT(*) as count FROM meters")
        total_meters = total_meters_df.iloc[0]['count'] if not total_meters_df.empty else 0
        
        active_zones_df = self._query_to_df("SELECT COUNT(*) as count FROM zones WHERE status = 'active'")
        active_zones = active_zones_df.iloc[0]['count'] if not active_zones_df.empty else 0
        
        total_zones_df = self._query_to_df("SELECT COUNT(*) as count FROM zones")
        total_zones = total_zones_df.iloc[0]['count'] if not total_zones_df.empty else 0
        
        # Alert counts (last 24h)
        since = datetime.now() - timedelta(hours=24)
        critical_alerts_df = self._query_to_df(
            "SELECT COUNT(*) as count FROM alerts WHERE severity = 'critical' AND created_at > %s AND status != 'resolved'",
            (since,)
        )
        critical_alerts = critical_alerts_df.iloc[0]['count'] if not critical_alerts_df.empty else 0
        
        warning_alerts_df = self._query_to_df(
            "SELECT COUNT(*) as count FROM alerts WHERE severity = 'warning' AND created_at > %s AND status != 'resolved'",
            (since,)
        )
        warning_alerts = warning_alerts_df.iloc[0]['count'] if not warning_alerts_df.empty else 0
        
        # Leak detections (unique meters, not all predictions)
        leaks_24h_df = self._query_to_df(
            """SELECT COUNT(DISTINCT meter_id) as count FROM leak_predictions 
               WHERE leak_detected = 1 AND timestamp > %s""",
            (since,)
        )
        leaks_24h = leaks_24h_df.iloc[0]['count'] if not leaks_24h_df.empty else 0
        
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
        since = datetime.now() - timedelta(hours=hours)
        return self._query_to_df('''
            SELECT id, created_at, severity, title, message, zone_id, status
            FROM alerts
            WHERE created_at > %s
            ORDER BY created_at DESC
        ''', (since,))
    
    # === TEAM MANAGEMENT OPERATIONS ===
    
    def validate_team_members(self, member_ids: List[str]) -> tuple[bool, str]:
        """Validate that all member IDs are Field Technicians and active"""
        if not member_ids:
            return False, "Team must have at least one member"
        
        # Check team size constraints
        if len(member_ids) < 2:
            return False, "Team must have at least 2 members"
        if len(member_ids) > 6:
            return False, "Team cannot have more than 6 members"
        
        # Check for duplicates
        if len(member_ids) != len(set(member_ids)):
            return False, "Duplicate members are not allowed"
        
        # Verify all members exist and are Field Technicians
        placeholders = ','.join(['%s'] * len(member_ids))
        query = f"""
            SELECT user_id, role, status 
            FROM users 
            WHERE user_id IN ({placeholders})
        """
        df = self._query_to_df(query, tuple(member_ids))
        
        if df.empty or len(df) != len(member_ids):
            return False, "One or more user IDs are invalid"
        
        # Check all are Field Technicians
        non_technicians = df[df['role'] != 'Field Technician']
        if not non_technicians.empty:
            return False, "All team members must be Field Technicians"
        
        # Check all are active
        inactive = df[df['status'] != 'active']
        if not inactive.empty:
            return False, "All team members must have active status"
        
        return True, "Valid"
    
    def create_team(self, name: str, description: str, created_by: str, member_ids: List[str]) -> tuple[bool, str, Optional[int]]:
        """
        Create a new team with members
        Returns: (success, message, team_id)
        """
        # Validate members
        valid, msg = self.validate_team_members(member_ids)
        if not valid:
            return False, msg, None
        
        # Check if team name already exists
        existing = self._query_to_df("SELECT id FROM teams WHERE name = %s", (name,))
        if not existing.empty:
            return False, "Team name already exists", None

        # Enforce: each field technician can only be in one active team
        for uid in member_ids:
            row = self._query_to_df(
                "SELECT t.name FROM team_members tm "
                "JOIN teams t ON tm.team_id = t.id "
                "WHERE tm.user_id = %s AND t.status = 'active' LIMIT 1",
                (uid,)
            )
            if not row.empty:
                return False, (
                    f"Technician {uid} is already assigned to team '{row.iloc[0]['name']}'. "
                    "A Field Technician can only be in one team at a time."
                ), None

        try:
            conn = self._get_conn()
            conn.autocommit = False
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "INSERT INTO teams (name, description, created_by) VALUES (%s, %s, %s)",
                    (name, description, created_by)
                )
                team_id = cursor.lastrowid
                for member_id in member_ids:
                    cursor.execute(
                        "INSERT INTO team_members (team_id, user_id, added_by) VALUES (%s, %s, %s)",
                        (team_id, member_id, created_by)
                    )
                conn.commit()
                return True, f"Team '{name}' created successfully", team_id
            except mysql.connector.Error:
                conn.rollback()
                raise
            finally:
                cursor.close()
                conn.autocommit = True
        except mysql.connector.Error as e:
            return False, f"Database error: {str(e)}", None
    
    def get_team(self, team_id: int) -> Optional[Dict]:
        """Get team details with members"""
        team_df = self._query_to_df(
            "SELECT * FROM teams WHERE id = %s",
            (team_id,)
        )
        
        if team_df.empty:
            return None
        
        team = team_df.iloc[0].to_dict()
        
        # Get team members
        members_df = self._query_to_df('''
            SELECT u.user_id, u.name, u.email, tm.added_at
            FROM team_members tm
            JOIN users u ON tm.user_id = u.user_id
            WHERE tm.team_id = %s
            ORDER BY u.name
        ''', (team_id,))
        
        team['members'] = members_df.to_dict('records') if not members_df.empty else []
        team['member_count'] = len(team['members'])
        
        return team
    
    def get_all_teams(self) -> pd.DataFrame:
        """Get all teams with member counts"""
        return self._query_to_df('''
            SELECT 
                t.id,
                t.name,
                t.description,
                t.status,
                t.created_by,
                t.created_at,
                t.updated_at,
                COUNT(tm.user_id) as member_count
            FROM teams t
            LEFT JOIN team_members tm ON t.id = tm.team_id
            GROUP BY t.id, t.name, t.description, t.status, t.created_by, t.created_at, t.updated_at
            ORDER BY t.created_at DESC
        ''')
    
    def get_teams_by_user(self, user_id: str) -> pd.DataFrame:
        """Get all teams a user belongs to"""
        return self._query_to_df('''
            SELECT 
                t.id,
                t.name,
                t.description,
                t.status,
                t.created_at,
                COUNT(tm2.user_id) as member_count
            FROM teams t
            JOIN team_members tm ON t.id = tm.team_id
            LEFT JOIN team_members tm2 ON t.id = tm2.team_id
            WHERE tm.user_id = %s AND t.status = 'active'
            GROUP BY t.id, t.name, t.description, t.status, t.created_at
            ORDER BY t.name
        ''', (user_id,))
    
    def update_team(self, team_id: int, name: str, description: str, member_ids: List[str], updated_by: str) -> tuple[bool, str]:
        """
        Update team details and members
        Returns: (success, message)
        """
        # Validate members
        valid, msg = self.validate_team_members(member_ids)
        if not valid:
            return False, msg
        
        # Check if team exists
        team = self.get_team(team_id)
        if not team:
            return False, "Team not found"
        
        # Check if new name conflicts with another team
        if name != team['name']:
            existing = self._query_to_df(
                "SELECT id FROM teams WHERE name = %s AND id != %s",
                (name, team_id)
            )
            if not existing.empty:
                return False, "Team name already exists"

        # Enforce: newly-added members cannot already be in another active team
        current_member_ids = {m['user_id'] for m in team['members']}
        for uid in member_ids:
            if uid not in current_member_ids:
                row = self._query_to_df(
                    "SELECT t.name FROM team_members tm "
                    "JOIN teams t ON tm.team_id = t.id "
                    "WHERE tm.user_id = %s AND t.status = 'active' LIMIT 1",
                    (uid,)
                )
                if not row.empty:
                    return False, (
                        f"Technician {uid} is already assigned to team '{row.iloc[0]['name']}'. "
                        "A Field Technician can only be in one team at a time."
                    )

        try:
            conn = self._get_conn()
            conn.autocommit = False
            cursor = conn.cursor()
            try:
                cursor.execute(
                    "UPDATE teams SET name = %s, description = %s WHERE id = %s",
                    (name, description, team_id)
                )
                cursor.execute("DELETE FROM team_members WHERE team_id = %s", (team_id,))
                for member_id in member_ids:
                    cursor.execute(
                        "INSERT INTO team_members (team_id, user_id, added_by) VALUES (%s, %s, %s)",
                        (team_id, member_id, updated_by)
                    )
                conn.commit()
                return True, f"Team '{name}' updated successfully"
            except mysql.connector.Error:
                conn.rollback()
                raise
            finally:
                cursor.close()
                conn.autocommit = True
        except mysql.connector.Error as e:
            return False, f"Database error: {str(e)}"
    
    def delete_team(self, team_id: int, deleted_by: str) -> tuple[bool, str]:
        """
        Delete a team (soft delete by setting status to inactive)
        Returns: (success, message)
        """
        # Check if team exists
        team = self.get_team(team_id)
        if not team:
            return False, "Team not found"
        
        try:
            # Soft delete - set status to inactive
            self._execute(
                "UPDATE teams SET status = 'inactive' WHERE id = %s",
                (team_id,)
            )
            
            # Unassign all alerts from this team
            self._execute(
                "UPDATE alerts SET team_id = NULL WHERE team_id = %s",
                (team_id,)
            )
            
            return True, f"Team '{team['name']}' deleted successfully"
            
        except mysql.connector.Error as e:
            return False, f"Database error: {str(e)}"
    
    def assign_alert_to_team(self, alert_id: int, team_id: int, assigned_by: str) -> tuple[bool, str]:
        """
        Assign an alert to a team and update status to 'assigned'
        Returns: (success, message)
        """
        # Verify alert exists
        alert_df = self._query_to_df("SELECT id, status FROM alerts WHERE id = %s", (alert_id,))
        if alert_df.empty:
            return False, "Alert not found"
        
        # Verify team exists and is active
        team = self.get_team(team_id)
        if not team:
            return False, "Team not found"
        if team['status'] != 'active':
            return False, "Team is not active"
        
        try:
            self._execute(
                "UPDATE alerts SET team_id = %s, status = 'assigned' WHERE id = %s",
                (team_id, alert_id)
            )
            return True, f"Alert assigned to team '{team['name']}'"
            
        except mysql.connector.Error as e:
            return False, f"Database error: {str(e)}"
    
    def unassign_alert_from_team(self, alert_id: int) -> tuple[bool, str]:
        """
        Remove team assignment from an alert and revert status to 'new'
        Returns: (success, message)
        """
        try:
            self._execute(
                "UPDATE alerts SET team_id = NULL, status = 'new' WHERE id = %s",
                (alert_id,)
            )
            return True, "Alert unassigned from team"
            
        except mysql.connector.Error as e:
            return False, f"Database error: {str(e)}"
    
    def resolve_alert(self, alert_id: int, resolved_by: str) -> tuple[bool, str]:
        """
        Mark an alert as resolved
        Returns: (success, message)
        """
        # Verify alert exists
        alert_df = self._query_to_df("SELECT id, status FROM alerts WHERE id = %s", (alert_id,))
        if alert_df.empty:
            return False, "Alert not found"
        
        try:
            meter_id = alert_df.iloc[0].get("meter_id") if "meter_id" in alert_df.columns else None
            if not meter_id:
                full = self._query_to_df("SELECT meter_id FROM alerts WHERE id = %s", (alert_id,))
                meter_id = full.iloc[0]["meter_id"] if not full.empty else None

            self._execute(
                "UPDATE alerts SET status = 'resolved', resolved_at = %s, resolved_by = %s WHERE id = %s",
                (datetime.now(), resolved_by, alert_id)
            )
            # Clear the leak flag so the meter disappears from the leak queues immediately
            if meter_id:
                self.store_leak_prediction(
                    meter_id=meter_id,
                    timestamp=datetime.now(),
                    confidence=0.0,
                    leak_detected=False,
                    leak_type="none",
                    features="{}",
                )
            return True, "Alert marked as resolved"

        except mysql.connector.Error as e:
            return False, f"Database error: {str(e)}"
    
    def reopen_alert(self, alert_id: int) -> tuple[bool, str]:
        """
        Reopen a resolved alert (set status back to 'new')
        Returns: (success, message)
        """
        try:
            self._execute(
                "UPDATE alerts SET status = 'new', resolved_at = NULL, resolved_by = NULL, team_id = NULL WHERE id = %s",
                (alert_id,)
            )
            return True, "Alert reopened"
            
        except mysql.connector.Error as e:
            return False, f"Database error: {str(e)}"
    
    def get_alerts_by_team(self, team_id: int, hours: int = 24) -> pd.DataFrame:
        """Get all alerts assigned to a specific team"""
        since = datetime.now() - timedelta(hours=hours)
        return self._query_to_df('''
            SELECT a.*, t.name as team_name
            FROM alerts a
            JOIN teams t ON a.team_id = t.id
            WHERE a.team_id = %s AND a.created_at > %s
            ORDER BY a.created_at DESC
        ''', (team_id, since))
    
    def get_last_assigned_team_for_zone(self, zone_id: str) -> Optional[Dict]:
        """Return the most recently assigned active team for a given zone."""
        df = self._query_to_df("""
            SELECT t.id, t.name
            FROM alerts a
            JOIN teams t ON a.team_id = t.id
            WHERE a.zone_id = %s
              AND a.team_id IS NOT NULL
              AND t.status = 'active'
            ORDER BY a.created_at DESC
            LIMIT 1
        """, (zone_id,))
        if df.empty:
            return None
        row = df.iloc[0]
        return {'id': int(row['id']), 'name': str(row['name'])}

    def get_unassigned_alerts(self, hours: int = 24) -> pd.DataFrame:
        """Get all alerts without team assignment (status='new')"""
        since = datetime.now() - timedelta(hours=hours)
        return self._query_to_df('''
            SELECT *
            FROM alerts
            WHERE status = 'new' AND created_at > %s
            ORDER BY created_at DESC
        ''', (since,))
    
    def get_alert_counts_by_status(self, hours: int = 24) -> Dict:
        """Get count of alerts by status"""
        since = datetime.now() - timedelta(hours=hours)
        
        new_count_df = self._query_to_df(
            "SELECT COUNT(*) as count FROM alerts WHERE status = 'new' AND created_at > %s",
            (since,)
        )
        assigned_count_df = self._query_to_df(
            "SELECT COUNT(*) as count FROM alerts WHERE status = 'assigned' AND created_at > %s",
            (since,)
        )
        resolved_count_df = self._query_to_df(
            "SELECT COUNT(*) as count FROM alerts WHERE status = 'resolved' AND created_at > %s",
            (since,)
        )
        
        return {
            'new': new_count_df.iloc[0]['count'] if not new_count_df.empty else 0,
            'assigned': assigned_count_df.iloc[0]['count'] if not assigned_count_df.empty else 0,
            'resolved': resolved_count_df.iloc[0]['count'] if not resolved_count_df.empty else 0
        }
    
    def get_alerts_with_team_info(self, status: Optional[str] = None, hours: int = 24) -> pd.DataFrame:
        """Get alerts with team information joined"""
        since = datetime.now() - timedelta(hours=hours)
        query = '''
            SELECT 
                a.*,
                t.name as team_name,
                u.name as resolved_by_name
            FROM alerts a
            LEFT JOIN teams t ON a.team_id = t.id
            LEFT JOIN users u ON a.resolved_by = u.user_id
            WHERE a.created_at > %s
        '''
        params = [since]
        
        if status:
            query += " AND a.status = %s"
            params.append(status)
        
        query += " ORDER BY a.created_at DESC"
        
        return self._query_to_df(query, tuple(params))
    
    def get_team_workload(self) -> pd.DataFrame:
        """Get workload statistics for all teams"""
        return self._query_to_df('''
            SELECT 
                t.id,
                t.name,
                COUNT(DISTINCT tm.user_id) as member_count,
                COUNT(DISTINCT CASE WHEN a.status != 'resolved' THEN a.id END) as active_alerts,
                COUNT(DISTINCT CASE WHEN a.status = 'resolved' THEN a.id END) as resolved_alerts
            FROM teams t
            LEFT JOIN team_members tm ON t.id = tm.team_id
            LEFT JOIN alerts a ON t.id = a.team_id
            WHERE t.status = 'active'
            GROUP BY t.id, t.name
            ORDER BY active_alerts DESC, t.name
        ''')
    
    def get_zone_leak_summary(self, start_dt: datetime, end_dt: datetime) -> pd.DataFrame:
        """Zone-level leak aggregation for the NRW session summary report."""
        return self._query_to_df("""
            SELECT
                z.zone_id,
                z.name                                                          AS zone_name,
                z.region,
                COUNT(DISTINCT a.id)                                            AS total_leaks,
                SUM(CASE WHEN a.status = 'resolved' THEN 1 ELSE 0 END)         AS resolved,
                SUM(CASE WHEN a.status != 'resolved' THEN 1 ELSE 0 END)        AS active,
                SUM(CASE WHEN a.severity = 'critical' THEN 1 ELSE 0 END)       AS critical,
                SUM(CASE WHEN a.severity = 'warning'  THEN 1 ELSE 0 END)       AS warning,
                SUM(CASE WHEN a.severity = 'normal'   THEN 1 ELSE 0 END)       AS suspected,
                GROUP_CONCAT(DISTINCT t.name ORDER BY t.name SEPARATOR ' | ')  AS assigned_teams
            FROM alerts a
            JOIN zones z ON a.zone_id = z.zone_id
            LEFT JOIN teams t ON a.team_id = t.id
            WHERE a.created_at BETWEEN %s AND %s
            GROUP BY z.zone_id, z.name, z.region
            ORDER BY total_leaks DESC
        """, (start_dt, end_dt))

    def get_zone_leak_detail(self, start_dt: datetime, end_dt: datetime) -> pd.DataFrame:
        """Individual alert rows with zone + team assignment for the session report."""
        return self._query_to_df("""
            SELECT
                z.name                                                                      AS zone_name,
                a.id                                                                        AS alert_id,
                a.meter_id,
                a.severity,
                a.status,
                a.title,
                a.created_at,
                a.resolved_at,
                ROUND(TIMESTAMPDIFF(MINUTE, a.created_at,
                      COALESCE(a.resolved_at, NOW())) / 60.0, 1)                           AS response_hrs,
                t.name                                                                      AS team_name,
                GROUP_CONCAT(DISTINCT u.name ORDER BY u.name SEPARATOR ', ')               AS team_members
            FROM alerts a
            JOIN zones z ON a.zone_id = z.zone_id
            LEFT JOIN teams t ON a.team_id = t.id
            LEFT JOIN team_members tm ON t.id = tm.team_id
            LEFT JOIN users u ON tm.user_id = u.user_id
            WHERE a.created_at BETWEEN %s AND %s
            GROUP BY z.name, a.id, a.meter_id, a.severity, a.status,
                     a.title, a.created_at, a.resolved_at, t.name
            ORDER BY z.name, a.created_at DESC
        """, (start_dt, end_dt))

    def get_alerts_for_user_teams(self, user_id: str, status: Optional[str] = None, hours: int = 24) -> pd.DataFrame:
        """
        Get all alerts assigned to teams that the user belongs to
        Used for Field Technicians to view their team's alerts
        """
        since = datetime.now() - timedelta(hours=hours)
        query = '''
            SELECT DISTINCT
                a.*,
                t.name as team_name,
                u.name as resolved_by_name
            FROM alerts a
            JOIN teams t ON a.team_id = t.id
            JOIN team_members tm ON t.id = tm.team_id
            LEFT JOIN users u ON a.resolved_by = u.user_id
            WHERE tm.user_id = %s 
            AND a.created_at > %s
        '''
        params = [user_id, since]
        
        if status:
            query += " AND a.status = %s"
            params.append(status)
        
        query += " ORDER BY a.created_at DESC"
        
        return self._query_to_df(query, tuple(params))
    
    # === DATA MANAGEMENT OPERATIONS ===

    def get_dynamic_data_counts(self) -> dict:
        """Return row counts for sensor_readings, leak_predictions, and alerts by status."""
        readings = self._query_to_df("SELECT COUNT(*) AS cnt FROM sensor_readings")
        predictions = self._query_to_df("SELECT COUNT(*) AS cnt FROM leak_predictions")
        alerts_all = self._query_to_df("SELECT status, COUNT(*) AS cnt FROM alerts GROUP BY status")
        oldest_r = self._query_to_df("SELECT MIN(timestamp) AS ts FROM sensor_readings")
        oldest_p = self._query_to_df("SELECT MIN(timestamp) AS ts FROM leak_predictions")

        alert_counts = {}
        if not alerts_all.empty:
            for _, row in alerts_all.iterrows():
                alert_counts[row['status']] = int(row['cnt'])

        return {
            'sensor_readings': int(readings.iloc[0]['cnt']) if not readings.empty else 0,
            'predictions': int(predictions.iloc[0]['cnt']) if not predictions.empty else 0,
            'alerts_new': alert_counts.get('new', 0),
            'alerts_assigned': alert_counts.get('assigned', 0),
            'alerts_resolved': alert_counts.get('resolved', 0),
            'oldest_reading': oldest_r.iloc[0]['ts'] if not oldest_r.empty else None,
            'oldest_prediction': oldest_p.iloc[0]['ts'] if not oldest_p.empty else None,
        }

    def clear_sensor_readings(self, older_than_hours: int = None) -> tuple[bool, str, int]:
        """Delete sensor readings. Pass older_than_hours to limit scope."""
        try:
            if older_than_hours:
                cutoff = datetime.now() - timedelta(hours=older_than_hours)
                before = self._query_to_df(
                    "SELECT COUNT(*) AS cnt FROM sensor_readings WHERE timestamp < %s", (cutoff,)
                )
                count = int(before.iloc[0]['cnt']) if not before.empty else 0
                self._execute("DELETE FROM sensor_readings WHERE timestamp < %s", (cutoff,))
            else:
                before = self._query_to_df("SELECT COUNT(*) AS cnt FROM sensor_readings")
                count = int(before.iloc[0]['cnt']) if not before.empty else 0
                self._execute("DELETE FROM sensor_readings")
            return True, f"Cleared {count} sensor reading(s).", count
        except Exception as e:
            return False, f"Error: {e}", 0

    def clear_leak_predictions(self, older_than_hours: int = None) -> tuple[bool, str, int]:
        """Delete leak predictions. Pass older_than_hours to limit scope."""
        try:
            if older_than_hours:
                cutoff = datetime.now() - timedelta(hours=older_than_hours)
                before = self._query_to_df(
                    "SELECT COUNT(*) AS cnt FROM leak_predictions WHERE timestamp < %s", (cutoff,)
                )
                count = int(before.iloc[0]['cnt']) if not before.empty else 0
                self._execute("DELETE FROM leak_predictions WHERE timestamp < %s", (cutoff,))
            else:
                before = self._query_to_df("SELECT COUNT(*) AS cnt FROM leak_predictions")
                count = int(before.iloc[0]['cnt']) if not before.empty else 0
                self._execute("DELETE FROM leak_predictions")
            return True, f"Cleared {count} prediction(s).", count
        except Exception as e:
            return False, f"Error: {e}", 0

    def clear_alerts(self, scope: str = "resolved") -> tuple[bool, str, int]:
        """Delete alerts. scope: 'resolved' | 'all'."""
        try:
            if scope == "resolved":
                before = self._query_to_df(
                    "SELECT COUNT(*) AS cnt FROM alerts WHERE status = 'resolved'"
                )
                count = int(before.iloc[0]['cnt']) if not before.empty else 0
                self._execute("DELETE FROM alerts WHERE status = 'resolved'")
            else:
                before = self._query_to_df("SELECT COUNT(*) AS cnt FROM alerts")
                count = int(before.iloc[0]['cnt']) if not before.empty else 0
                self._execute("DELETE FROM alerts")
            return True, f"Cleared {count} alert(s).", count
        except Exception as e:
            return False, f"Error: {e}", 0

    def clear_all_dynamic_data(self) -> tuple[bool, str]:
        """Wipe sensor_readings, leak_predictions, and alerts tables entirely."""
        try:
            r = self._query_to_df("SELECT COUNT(*) AS cnt FROM sensor_readings")
            p = self._query_to_df("SELECT COUNT(*) AS cnt FROM leak_predictions")
            a = self._query_to_df("SELECT COUNT(*) AS cnt FROM alerts")
            n_r = int(r.iloc[0]['cnt']) if not r.empty else 0
            n_p = int(p.iloc[0]['cnt']) if not p.empty else 0
            n_a = int(a.iloc[0]['cnt']) if not a.empty else 0
            self._execute("DELETE FROM alerts")
            self._execute("DELETE FROM leak_predictions")
            self._execute("DELETE FROM sensor_readings")
            return True, f"Cleared {n_r} readings, {n_p} predictions, {n_a} alerts."
        except Exception as e:
            return False, f"Error: {e}"

    # === USER MANAGEMENT OPERATIONS ===
    
    def get_all_users(self) -> pd.DataFrame:
        """Get all users with their details"""
        return self._query_to_df('''
            SELECT user_id, username, email, name, role, status, last_login, created_at
            FROM users
            ORDER BY created_at DESC
        ''')
    
    def update_user(self, user_id: str, email: str, name: str, role: str, status: str) -> tuple[bool, str]:
        """
        Update user details
        Returns: (success, message)
        """
        # Verify user exists
        user = self.get_user(user_id)
        if not user:
            return False, "User not found"
        
        # Check if new email conflicts with another user
        if email != user['email']:
            existing = self._query_to_df(
                "SELECT user_id FROM users WHERE email = %s AND user_id != %s",
                (email, user_id)
            )
            if not existing.empty:
                return False, "Email already in use by another user"
        
        try:
            self._execute(
                "UPDATE users SET email = %s, name = %s, role = %s, status = %s WHERE user_id = %s",
                (email, name, role, status, user_id)
            )
            return True, f"User '{name}' updated successfully"
            
        except mysql.connector.Error as e:
            return False, f"Database error: {str(e)}"
    
    def update_user_role(self, user_id: str, new_role: str, updated_by: str) -> tuple[bool, str]:
        """
        Update user role (for role assignment)
        Returns: (success, message)
        """
        # Verify user exists
        user = self.get_user(user_id)
        if not user:
            return False, "User not found"
        
        # Validate role
        from backend.rbac import Roles
        if new_role not in Roles.ALL_ROLES:
            return False, f"Invalid role: {new_role}"
        
        try:
            self._execute(
                "UPDATE users SET role = %s WHERE user_id = %s",
                (new_role, user_id)
            )
            return True, f"User role updated to '{new_role}'"
            
        except mysql.connector.Error as e:
            return False, f"Database error: {str(e)}"
    
    def delete_user(self, user_id: str) -> tuple[bool, str]:
        """
        Delete a user (soft delete by setting status to inactive)
        Returns: (success, message)
        """
        # Verify user exists
        user = self.get_user(user_id)
        if not user:
            return False, "User not found"
        
        # Check if user has active team memberships
        team_memberships = self._query_to_df(
            "SELECT COUNT(*) as count FROM team_members WHERE user_id = %s",
            (user_id,)
        )
        if not team_memberships.empty and team_memberships.iloc[0]['count'] > 0:
            return False, "Cannot delete user with active team memberships. Remove from teams first."
        
        # Check if user has created teams
        created_teams = self._query_to_df(
            "SELECT COUNT(*) as count FROM teams WHERE created_by = %s AND status = 'active'",
            (user_id,)
        )
        if not created_teams.empty and created_teams.iloc[0]['count'] > 0:
            return False, "Cannot delete user who has created active teams"
        
        try:
            # Soft delete - set status to inactive
            self._execute(
                "UPDATE users SET status = 'inactive' WHERE user_id = %s",
                (user_id,)
            )
            return True, f"User '{user['name']}' deleted successfully"
            
        except mysql.connector.Error as e:
            return False, f"Database error: {str(e)}"
    
    def create_user(self, user_id: str, username: str, email: str, name: str, role: str, password_hash: str) -> tuple[bool, str]:
        """
        Create a new user
        Returns: (success, message)
        """
        # Validate role
        from backend.rbac import Roles
        if role not in Roles.ALL_ROLES:
            return False, f"Invalid role: {role}"
        
        # Check if user_id already exists
        existing_id = self.get_user(user_id)
        if existing_id:
            return False, f"User ID '{user_id}' already exists"
        
        # Check if email already exists
        existing_email = self._query_to_df(
            "SELECT user_id FROM users WHERE email = %s",
            (email,)
        )
        if not existing_email.empty:
            return False, f"Email '{email}' already in use"
        
        try:
            self._execute(
                "INSERT INTO users (user_id, username, email, name, role, password_hash) VALUES (%s, %s, %s, %s, %s, %s)",
                (user_id.upper(), username, email, name, role, password_hash)
            )
            return True, f"User '{name}' created successfully"
            
        except mysql.connector.IntegrityError as e:
            return False, f"Database error: {str(e)}"
    
    # === METER MANAGEMENT OPERATIONS ===
    
    def update_meter(self, meter_id: str, zone_id: str, location: str, meter_type: str,
                    status: str, flow_rate: float, description: str) -> tuple[bool, str]:
        """
        Update meter details
        Returns: (success, message)
        """
        # Verify meter exists
        meter_df = self._query_to_df("SELECT * FROM meters WHERE meter_id = %s", (meter_id,))
        if meter_df.empty:
            return False, "Meter not found"
        
        # Verify zone exists
        zone_df = self._query_to_df("SELECT * FROM zones WHERE zone_id = %s", (zone_id,))
        if zone_df.empty:
            return False, f"Zone '{zone_id}' does not exist. Please create the zone first."
        
        try:
            self._execute(
                "UPDATE meters SET zone_id = %s, location = %s, meter_type = %s, status = %s, flow_rate = %s, description = %s WHERE meter_id = %s",
                (zone_id, location, meter_type, status, flow_rate, description, meter_id)
            )
            return True, f"Meter '{meter_id}' updated successfully"
            
        except mysql.connector.Error as e:
            return False, f"Database error: {str(e)}"
    
    def delete_meter(self, meter_id: str) -> tuple[bool, str]:
        """
        Delete a meter (soft delete by setting status to inactive)
        Returns: (success, message)
        """
        # Verify meter exists
        meter_df = self._query_to_df("SELECT * FROM meters WHERE meter_id = %s", (meter_id,))
        if meter_df.empty:
            return False, "Meter not found"
        
        # Check if meter has active alerts
        active_alerts = self._query_to_df(
            "SELECT COUNT(*) as count FROM alerts WHERE meter_id = %s AND status != 'resolved'",
            (meter_id,)
        )
        if not active_alerts.empty and active_alerts.iloc[0]['count'] > 0:
            return False, "Cannot delete meter with active alerts. Resolve alerts first."
        
        try:
            # Soft delete - set status to inactive
            self._execute(
                "UPDATE meters SET status = 'inactive' WHERE meter_id = %s",
                (meter_id,)
            )
            return True, f"Meter '{meter_id}' deleted successfully"
            
        except mysql.connector.Error as e:
            return False, f"Database error: {str(e)}"
    
    def create_meter(self, meter_id: str, zone_id: str, location: str, meter_type: str,
                    status: str, flow_rate: float, description: str) -> tuple[bool, str]:
        """
        Create a new meter (with zone validation)
        Returns: (success, message)
        """
        # Verify zone exists
        zone_df = self._query_to_df("SELECT * FROM zones WHERE zone_id = %s", (zone_id,))
        if zone_df.empty:
            return False, f"Zone '{zone_id}' does not exist. Please create the zone first."
        
        # Check if meter_id already exists
        existing = self._query_to_df("SELECT * FROM meters WHERE meter_id = %s", (meter_id,))
        if not existing.empty:
            return False, f"Meter ID '{meter_id}' already exists"
        
        try:
            self._execute(
                "INSERT INTO meters (meter_id, zone_id, location, meter_type, status, flow_rate, description) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (meter_id.upper(), zone_id, location, meter_type, status, flow_rate, description)
            )
            return True, f"Meter '{meter_id}' created successfully"
            
        except mysql.connector.IntegrityError as e:
            return False, f"Database error: {str(e)}"
    
    # === ZONE MANAGEMENT OPERATIONS ===
    
    def update_zone(self, zone_id: str, name: str, region: str, zone_type: str,
                   status: str, estimated_connections: int, description: str) -> tuple[bool, str]:
        """
        Update zone details
        Returns: (success, message)
        """
        # Verify zone exists
        zone_df = self._query_to_df("SELECT * FROM zones WHERE zone_id = %s", (zone_id,))
        if zone_df.empty:
            return False, "Zone not found"
        
        try:
            self._execute(
                "UPDATE zones SET name = %s, region = %s, type = %s, status = %s, estimated_connections = %s, description = %s WHERE zone_id = %s",
                (name, region, zone_type, status, estimated_connections, description, zone_id)
            )
            return True, f"Zone '{name}' updated successfully"
            
        except mysql.connector.Error as e:
            return False, f"Database error: {str(e)}"
    
    def delete_zone(self, zone_id: str) -> tuple[bool, str]:
        """
        Delete a zone (soft delete by setting status to inactive)
        Returns: (success, message)
        """
        # Verify zone exists
        zone_df = self._query_to_df("SELECT * FROM zones WHERE zone_id = %s", (zone_id,))
        if zone_df.empty:
            return False, "Zone not found"
        
        # Check if zone has active meters
        active_meters = self._query_to_df(
            "SELECT COUNT(*) as count FROM meters WHERE zone_id = %s AND status = 'active'",
            (zone_id,)
        )
        if not active_meters.empty and active_meters.iloc[0]['count'] > 0:
            return False, "Cannot delete zone with active meters. Delete or reassign meters first."
        
        try:
            # Soft delete - set status to inactive
            self._execute(
                "UPDATE zones SET status = 'inactive' WHERE zone_id = %s",
                (zone_id,)
            )
            return True, f"Zone '{zone_df.iloc[0]['name']}' deleted successfully"
            
        except mysql.connector.Error as e:
            return False, f"Database error: {str(e)}"
    
    def create_zone(self, zone_id: str, name: str, region: str, zone_type: str,
                   status: str, estimated_connections: int, description: str) -> tuple[bool, str]:
        """
        Create a new zone
        Returns: (success, message)
        """
        # Check if zone_id already exists
        existing = self._query_to_df("SELECT * FROM zones WHERE zone_id = %s", (zone_id,))
        if not existing.empty:
            return False, f"Zone ID '{zone_id}' already exists"
        
        try:
            self._execute(
                "INSERT INTO zones (zone_id, name, region, type, status, estimated_connections, description) VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (zone_id.upper(), name, region, zone_type, status, estimated_connections, description)
            )
            return True, f"Zone '{name}' created successfully"
            
        except mysql.connector.IntegrityError as e:
            return False, f"Database error: {str(e)}"
    
    # === SEED DATA ===
    
    def seed_default_users(self):
        """Seed the 4 default THW users with hashed passwords - Updated for MySQL"""
        import bcrypt
        
        default_password = "Thiwasco2024!"
        password_hash = bcrypt.hashpw(default_password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
        
        default_users = [
            ("THW-001", "thiwasco", "j.kamau@thiwasco.co.ke", "John Kamau", "Non-Revenue Water Officer", password_hash),
            ("THW-002", "thiwasco", "g.ochieng@thiwasco.co.ke", "Grace Ochieng", "Field Technician", password_hash),
            ("THW-003", "thiwasco", "p.mwangi@thiwasco.co.ke", "Peter Mwangi", "System Administrator", password_hash),
            ("THW-004", "thiwasco", "a.wanjiku@thiwasco.co.ke", "Alice Wanjiku", "Field Technician", password_hash),
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
            try:
                self.add_zone(*zone)
            except mysql.connector.IntegrityError:
                pass
    
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

            # Key Thika West - Section 9 meters (350 connections, representative sample)
            ("MTR-024", "THK-WST-003", "Section 9 A1", "mixed", "active", 9.2, "Section 9 A1 DMA"),
            ("MTR-025", "THK-WST-003", "Section 9 A2", "mixed", "active", 8.8, "Section 9 A2 DMA"),
            ("MTR-026", "THK-WST-003", "Section 9 A3", "mixed", "active", 8.5, "Section 9 A3 DMA"),
            ("MTR-027", "THK-WST-003", "Section 9 B1", "mixed", "active", 8.5, "Section 9 B1 DMA"),
            ("MTR-028", "THK-WST-003", "Section 9 B2", "mixed", "active", 8.2, "Section 9 B2 DMA"),
            ("MTR-029", "THK-WST-003", "Section 9 B3", "mixed", "active", 7.8, "Section 9 B3 DMA"),
            ("MTR-030", "THK-WST-003", "Section 9 C1", "mixed", "active", 8.2, "Section 9 C1 DMA"),

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

            # Thika East - Key zones (representative sample)
            ("MTR-039", "THK-EST-001", "Kiganjo North Zone 1", "residential", "active", 9.8, "Zone 1 supply"),
            ("MTR-040", "THK-EST-001", "Kiganjo North Zone 2", "residential", "active", 9.2, "Zone 2 supply"),
            ("MTR-041", "THK-EST-001", "Kiganjo North Zone 3", "residential", "active", 8.5, "Zone 3 supply"),
            ("MTR-042", "THK-EST-001", "Kiganjo North Zone 4", "residential", "active", 7.8, "Zone 4 supply"),
            ("MTR-043", "THK-EST-001", "Kiganjo North Zone 5", "residential", "active", 7.2, "Zone 5 supply"),

            ("MTR-044", "THK-EST-002", "Kiganjo South Sector A", "residential", "active", 10.2, "Sector A supply"),
            ("MTR-045", "THK-EST-002", "Kiganjo South Sector B", "residential", "active", 9.5, "Sector B supply"),
            ("MTR-046", "THK-EST-002", "Kiganjo South Sector C", "residential", "active", 8.8, "Sector C supply"),
            ("MTR-047", "THK-EST-002", "Kiganjo South Sector D", "residential", "active", 8.2, "Sector D supply"),
            ("MTR-048", "THK-EST-002", "Kiganjo South Sector E", "residential", "active", 7.5, "Sector E supply"),
            ("MTR-049", "THK-EST-002", "Kiganjo South Sector F", "residential", "active", 6.8, "Sector F supply"),

            ("MTR-050", "THK-EST-003", "Ngoingwa Central", "residential", "active", 9.2, "Central distribution"),
            ("MTR-051", "THK-EST-003", "Ngoingwa North", "residential", "active", 8.5, "North supply"),
            ("MTR-052", "THK-EST-003", "Ngoingwa South", "residential", "active", 7.8, "South supply"),
            ("MTR-053", "THK-EST-003", "Ngoingwa East", "residential", "active", 7.2, "East supply"),
            ("MTR-054", "THK-EST-003", "Ngoingwa West", "residential", "active", 6.5, "West supply"),

            # Thika North - Key zones
            ("MTR-074", "THK-NTH-001", "Witeithie Main", "residential", "active", 9.8, "Witeithie main supply"),
            ("MTR-075", "THK-NTH-001", "Witeithie East", "residential", "active", 8.5, "Witeithie east supply"),
            ("MTR-076", "THK-NTH-001", "Witeithie West", "residential", "active", 7.8, "Witeithie west supply"),
            ("MTR-077", "THK-NTH-001", "Witeithie Central", "residential", "active", 7.2, "Witeithie central supply"),

            # Thika Industrial - High flow areas
            ("MTR-092", "THK-IND-001", "Industrial Main A", "industrial", "active", 11.5, "Industrial main A supply"),
            ("MTR-093", "THK-IND-001", "Industrial Main B", "industrial", "active", 10.2, "Industrial main B supply"),
            ("MTR-094", "THK-IND-001", "Industrial Main C", "industrial", "active", 9.5, "Industrial main C supply"),

            ("MTR-095", "THK-IND-002", "Del Monte Farm A", "industrial", "active", 12.5, "Del Monte farm A supply"),
            ("MTR-096", "THK-IND-002", "Del Monte Farm B", "industrial", "active", 11.2, "Del Monte farm B supply"),
            ("MTR-097", "THK-IND-002", "Del Monte Processing", "industrial", "active", 10.5, "Processing plant supply"),
            ("MTR-098", "THK-IND-002", "Del Monte Storage", "industrial", "active", 9.8, "Storage facility supply"),

            ("MTR-099", "THK-IND-003", "Bata Factory Main", "industrial", "active", 10.8, "Bata factory main supply"),
            ("MTR-100", "THK-IND-003", "Bata Factory Extension", "industrial", "active", 9.2, "Bata factory extension supply"),

            # Special Areas
            ("MTR-101", "THK-SPL-001", "Barracks Main", "institutional", "active", 8.5, "Barracks main supply"),
            ("MTR-102", "THK-SPL-001", "Barracks Residential", "institutional", "active", 7.2, "Barracks residential supply"),

            ("MTR-103", "THK-SPL-002", "Makadara Main", "commercial", "active", 8.8, "Makadara main supply"),
            ("MTR-104", "THK-SPL-002", "Makadara Market", "commercial", "active", 7.5, "Makadara market supply"),
            ("MTR-105", "THK-SPL-002", "Makadara Residential", "commercial", "active", 6.8, "Makadara residential supply"),

            ("MTR-106", "THK-SPL-003", "Slaughterhouse Main", "industrial", "active", 7.8, "Slaughterhouse main supply"),
            ("MTR-107", "THK-SPL-003", "Slaughterhouse Processing", "industrial", "active", 6.5, "Processing plant supply"),
        ]
        for meter in default_meters:
            try:
                self.add_meter(*meter)
            except mysql.connector.IntegrityError:
                pass
    
    def seed_default_teams(self):
        """Seed default teams with Field Technicians"""
        print("Seeding default teams...")
        
        # Get Field Technicians
        technicians = self.get_field_technicians()
        if technicians.empty or len(technicians) < 2:
            print("  - Not enough Field Technicians to create teams (need at least 2)")
            return
        
        tech_ids = technicians['user_id'].tolist()
        
        # Create default teams
        default_teams = [
            {
                "name": "Thika Central Response Team",
                "description": "Primary response team for Thika Central zones (CBD, Market, Railway)",
                "members": tech_ids[:min(2, len(tech_ids))]  # First 2 technicians
            },
            {
                "name": "Thika West Response Team",
                "description": "Response team covering Thika West residential and commercial zones",
                "members": tech_ids[:min(3, len(tech_ids))]  # First 3 technicians if available
            }
        ]
        
        created_count = 0
        for team_data in default_teams:
            # Check if team already exists
            existing = self._query_to_df("SELECT id FROM teams WHERE name = %s", (team_data["name"],))
            if not existing.empty:
                print(f"  - Team already exists: {team_data['name']}")
                continue
            
            # Create team (using THW-001 as creator - Non-Revenue Water Officer)
            success, msg, team_id = self.create_team(
                name=team_data["name"],
                description=team_data["description"],
                created_by="THW-001",
                member_ids=team_data["members"]
            )
            
            if success:
                created_count += 1
                print(f"  - Created team: {team_data['name']} (ID: {team_id})")
            else:
                print(f"  - Failed to create team {team_data['name']}: {msg}")
        
        if created_count > 0:
            print(f"  - Created {created_count} new teams")
        else:
            print("  - All default teams already exist")


# Global instance - configure with your MySQL credentials
db_manager = MySQLDatabaseManager()


def seed_demo_data():
    """Seed all demo data for MySQL"""
    db_manager.seed_default_users()
    db_manager.seed_default_zones()
    db_manager.seed_default_meters()
    db_manager.seed_default_teams()
    print("MySQL demo data seeded!")
