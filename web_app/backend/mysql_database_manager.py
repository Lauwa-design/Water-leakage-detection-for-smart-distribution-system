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
            'database': database or os.getenv('MYSQL_DATABASE', 'thiwasco_1'),
            'user': user or os.getenv('MYSQL_USER', 'root'),
            'password': password or os.getenv('MYSQL_PASSWORD', 'MyNewSecurePassword!'),
            'autocommit': False,
            'connection_timeout': 30,
        }
        self._local = threading.local()
        self._initialized = False
    
    def _get_conn(self, readonly: bool = False):
        """Get a database connection from the pool."""
        if not hasattr(self._local, 'conn') or self._local.conn is None:
            try:
                # First try to connect to the specified database
                self._local.conn = mysql.connector.connect(**self.config)
                self._init_db(self._local.conn)
            except mysql.connector.Error as e:
                # If database doesn't exist, create it and reconnect
                if "Unknown database" in str(e):
                    print(f"Database '{self.config['database']}' does not exist. Creating it...")
                    self._create_database()
                    # Retry connection after creating database
                    self._local.conn = mysql.connector.connect(**self.config)
                    self._init_db(self._local.conn)
                else:
                    print(f"Database connection error: {e}")
                    raise
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
    
    def get_field_technicians(self) -> pd.DataFrame:
        """Get all users with Field Technician role"""
        return self._query_to_df(
            "SELECT user_id, name, email, status FROM users WHERE role = 'Field Technician' AND status = 'active'"
        )
    
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
        """Add leak prediction - alias for store_leak_prediction with auto timestamp"""
        timestamp = datetime.now()
        
        # Convert numpy types to native Python types to avoid MySQL conversion errors
        import numpy as np
        if isinstance(leak_detected, (np.bool_, np.generic)):
            leak_detected = bool(leak_detected)
        if isinstance(confidence, (np.floating, np.generic)):
            confidence = float(confidence)
        
        self.store_leak_prediction(meter_id, timestamp, confidence, leak_detected, leak_type, features)
    
    def add_alert(self, meter_id: str, zone_id: str, severity: str, title: str, message: str):
        self._execute(
            "INSERT INTO alerts (meter_id, zone_id, severity, title, message) VALUES (%s, %s, %s, %s, %s)",
            (meter_id, zone_id, severity, title, message)
        )
    
    def get_active_alert_for_meter(self, meter_id: str, severity: str, hours: int = 24) -> Optional[Dict]:
        """Check if there's an active unresolved alert for a specific meter"""
        since = datetime.now() - timedelta(hours=hours)
        df = self._query_to_df('''
            SELECT id, severity, status, created_at 
            FROM alerts 
            WHERE meter_id = %s AND severity = %s AND status != 'resolved' AND created_at > %s
            ORDER BY created_at DESC
            LIMIT 1
        ''', (meter_id, severity, since))
        
        if not df.empty:
            return df.iloc[0].to_dict()
        return None
    
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
    
    def resolve_alert(self, alert_id: int):
        """Convenience method to mark an alert as resolved"""
        self.update_alert_status(alert_id, "resolved")
    
    def cleanup_old_alerts(self, days: int = 7) -> int:
        """Archive/delete resolved alerts older than specified days"""
        cutoff_date = datetime.now() - timedelta(days=days)
        conn = self._get_conn()
        cursor = conn.cursor()
        
        cursor.execute('''
            DELETE FROM alerts
            WHERE status = 'resolved'
            AND resolved_at < %s
        ''', (cutoff_date,))
        
        deleted_count = cursor.rowcount
        conn.commit()
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
        
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            # Insert team
            cursor.execute(
                "INSERT INTO teams (name, description, created_by) VALUES (%s, %s, %s)",
                (name, description, created_by)
            )
            team_id = cursor.lastrowid
            
            # Insert team members
            for member_id in member_ids:
                cursor.execute(
                    "INSERT INTO team_members (team_id, user_id, added_by) VALUES (%s, %s, %s)",
                    (team_id, member_id, created_by)
                )
            
            conn.commit()
            cursor.close()
            
            return True, f"Team '{name}' created successfully", team_id
            
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
        
        try:
            conn = self._get_conn()
            cursor = conn.cursor()
            
            # Update team details
            cursor.execute(
                "UPDATE teams SET name = %s, description = %s WHERE id = %s",
                (name, description, team_id)
            )
            
            # Remove all existing members
            cursor.execute("DELETE FROM team_members WHERE team_id = %s", (team_id,))
            
            # Add new members
            for member_id in member_ids:
                cursor.execute(
                    "INSERT INTO team_members (team_id, user_id, added_by) VALUES (%s, %s, %s)",
                    (team_id, member_id, updated_by)
                )
            
            conn.commit()
            cursor.close()
            
            return True, f"Team '{name}' updated successfully"
            
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
        Assign an alert to a team
        Returns: (success, message)
        """
        # Verify alert exists
        alert_df = self._query_to_df("SELECT id FROM alerts WHERE id = %s", (alert_id,))
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
                "UPDATE alerts SET team_id = %s WHERE id = %s",
                (team_id, alert_id)
            )
            return True, f"Alert assigned to team '{team['name']}'"
            
        except mysql.connector.Error as e:
            return False, f"Database error: {str(e)}"
    
    def unassign_alert_from_team(self, alert_id: int) -> tuple[bool, str]:
        """
        Remove team assignment from an alert
        Returns: (success, message)
        """
        try:
            self._execute(
                "UPDATE alerts SET team_id = NULL WHERE id = %s",
                (alert_id,)
            )
            return True, "Alert unassigned from team"
            
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
    
    def get_unassigned_alerts(self, hours: int = 24) -> pd.DataFrame:
        """Get all alerts without team assignment"""
        since = datetime.now() - timedelta(hours=hours)
        return self._query_to_df('''
            SELECT *
            FROM alerts
            WHERE team_id IS NULL AND created_at > %s
            ORDER BY created_at DESC
        ''', (since,))
    
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
