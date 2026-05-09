"""Alert Manager - Centralized alert business logic for THIWASCO Leak Detection System"""

from datetime import datetime
from typing import Dict, List, Optional, Tuple
import pandas as pd


class AlertManager:
    """Manages alert lifecycle and business logic"""
    
    def __init__(self, db_manager):
        """
        Initialize Alert Manager
        
        Args:
            db_manager: Instance of MySQLDatabaseManager
        """
        self.db = db_manager
    
    # === ALERT CREATION ===
    
    def create_alert(self, meter_id: str, zone_id: str, severity: str, 
                    title: str, message: str) -> Tuple[bool, str, Optional[int]]:
        """
        Create a new alert with status='new'
        
        Args:
            meter_id: Meter ID
            zone_id: Zone ID
            severity: 'critical', 'warning', or 'normal'
            title: Alert title
            message: Alert message
        
        Returns:
            (success, message, alert_id)
        """
        try:
            self.db.add_alert(meter_id, zone_id, severity, title, message)
            return True, "Alert created successfully", None
        except Exception as e:
            return False, f"Failed to create alert: {str(e)}", None
    
    # === ALERT ASSIGNMENT ===
    
    def assign_alert_to_team(self, alert_id: int, team_id: int, 
                            assigned_by: str) -> Tuple[bool, str]:
        """
        Assign alert to team and update status to 'assigned'
        
        Args:
            alert_id: Alert ID
            team_id: Team ID
            assigned_by: User ID of person assigning
        
        Returns:
            (success, message)
        """
        return self.db.assign_alert_to_team(alert_id, team_id, assigned_by)
    
    def bulk_assign_alerts(self, alert_ids: List[int], team_id: int, 
                          assigned_by: str) -> Tuple[int, int, List[str]]:
        """
        Assign multiple alerts to a team
        
        Args:
            alert_ids: List of alert IDs
            team_id: Team ID
            assigned_by: User ID of person assigning
        
        Returns:
            (success_count, failure_count, error_messages)
        """
        success_count = 0
        failure_count = 0
        errors = []
        
        for alert_id in alert_ids:
            success, msg = self.assign_alert_to_team(alert_id, team_id, assigned_by)
            if success:
                success_count += 1
            else:
                failure_count += 1
                errors.append(f"Alert {alert_id}: {msg}")
        
        return success_count, failure_count, errors
    
    def unassign_alert(self, alert_id: int) -> Tuple[bool, str]:
        """
        Remove team assignment and revert status to 'new'
        
        Args:
            alert_id: Alert ID
        
        Returns:
            (success, message)
        """
        return self.db.unassign_alert_from_team(alert_id)
    
    # === ALERT RESOLUTION ===
    
    def resolve_alert(self, alert_id: int, resolved_by: str) -> Tuple[bool, str]:
        """
        Mark alert as resolved
        
        Args:
            alert_id: Alert ID
            resolved_by: User ID of person resolving
        
        Returns:
            (success, message)
        """
        return self.db.resolve_alert(alert_id, resolved_by)
    
    def bulk_resolve_alerts(self, alert_ids: List[int], 
                           resolved_by: str) -> Tuple[int, int, List[str]]:
        """
        Resolve multiple alerts
        
        Args:
            alert_ids: List of alert IDs
            resolved_by: User ID of person resolving
        
        Returns:
            (success_count, failure_count, error_messages)
        """
        success_count = 0
        failure_count = 0
        errors = []
        
        for alert_id in alert_ids:
            success, msg = self.resolve_alert(alert_id, resolved_by)
            if success:
                success_count += 1
            else:
                failure_count += 1
                errors.append(f"Alert {alert_id}: {msg}")
        
        return success_count, failure_count, errors
    
    def reopen_alert(self, alert_id: int) -> Tuple[bool, str]:
        """
        Reopen a resolved alert
        
        Args:
            alert_id: Alert ID
        
        Returns:
            (success, message)
        """
        return self.db.reopen_alert(alert_id)
    
    # === ALERT RETRIEVAL ===
    
    def get_alerts_by_status(self, status: str, hours: int = 24) -> pd.DataFrame:
        """
        Get alerts filtered by status
        
        Args:
            status: 'new', 'assigned', or 'resolved'
            hours: Time window in hours
        
        Returns:
            DataFrame of alerts
        """
        return self.db.get_alerts(status=status, hours=hours)
    
    def get_alerts_by_team(self, team_id: int, status: Optional[str] = None, 
                          hours: int = 24) -> pd.DataFrame:
        """
        Get alerts for a specific team
        
        Args:
            team_id: Team ID
            status: Optional status filter
            hours: Time window in hours
        
        Returns:
            DataFrame of alerts
        """
        return self.db.get_alerts(team_id=team_id, status=status, hours=hours)
    
    def get_unassigned_alerts(self, hours: int = 24) -> pd.DataFrame:
        """
        Get alerts with status='new' (not assigned to any team)
        
        Args:
            hours: Time window in hours
        
        Returns:
            DataFrame of unassigned alerts
        """
        return self.db.get_unassigned_alerts(hours=hours)
    
    def get_all_alerts(self, hours: int = 24) -> pd.DataFrame:
        """
        Get all alerts regardless of status
        
        Args:
            hours: Time window in hours
        
        Returns:
            DataFrame of all alerts
        """
        return self.db.get_alerts_with_team_info(hours=hours)
    
    def get_alert_details(self, alert_id: int) -> Optional[Dict]:
        """
        Get full alert details including team and resolution info
        
        Args:
            alert_id: Alert ID
        
        Returns:
            Dictionary with alert details or None
        """
        alerts_df = self.db.get_alerts_with_team_info(hours=8760)  # 1 year
        alert = alerts_df[alerts_df['id'] == alert_id]
        
        if alert.empty:
            return None
        
        return alert.iloc[0].to_dict()
    
    # === ALERT STATISTICS ===
    
    def get_alert_statistics(self, hours: int = 24) -> Dict:
        """
        Get alert counts by status
        
        Args:
            hours: Time window in hours
        
        Returns:
            Dictionary with counts: {'new': X, 'assigned': Y, 'resolved': Z}
        """
        return self.db.get_alert_counts_by_status(hours=hours)
    
    def get_team_alert_summary(self) -> pd.DataFrame:
        """
        Get alert counts per team
        
        Returns:
            DataFrame with team alert statistics
        """
        return self.db.get_team_workload()
    
    # === VALIDATION ===
    
    def can_assign_alert(self, alert_id: int) -> Tuple[bool, str]:
        """
        Check if alert can be assigned
        
        Args:
            alert_id: Alert ID
        
        Returns:
            (can_assign, reason)
        """
        alert = self.get_alert_details(alert_id)
        if not alert:
            return False, "Alert not found"
        
        if alert['status'] == 'resolved':
            return False, "Cannot assign resolved alerts"
        
        return True, "OK"
    
    def can_resolve_alert(self, alert_id: int) -> Tuple[bool, str]:
        """
        Check if alert can be resolved
        
        Args:
            alert_id: Alert ID
        
        Returns:
            (can_resolve, reason)
        """
        alert = self.get_alert_details(alert_id)
        if not alert:
            return False, "Alert not found"
        
        if alert['status'] == 'resolved':
            return False, "Alert is already resolved"
        
        return True, "OK"


# Global alert manager instance
from backend.mysql_database_manager import db_manager
alert_manager = AlertManager(db_manager)
