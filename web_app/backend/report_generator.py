"""Report Generator - Generate comprehensive reports for THIWASCO Leak Detection System"""

from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
import pandas as pd
from io import BytesIO
import json


class ReportGenerator:
    """Generate reports combining leak, alert, and team information"""
    
    def __init__(self, db_manager):
        """
        Initialize Report Generator
        
        Args:
            db_manager: Instance of MySQLDatabaseManager
        """
        self.db = db_manager
    
    # === COMPREHENSIVE REPORT ===
    
    def generate_comprehensive_report(self, start_date: datetime, end_date: datetime,
                                     team_id: Optional[int] = None,
                                     severity: Optional[str] = None) -> pd.DataFrame:
        """
        Generate comprehensive report combining leaks, alerts, and team info
        
        Args:
            start_date: Report start date
            end_date: Report end date
            team_id: Optional team filter
            severity: Optional severity filter
        
        Returns:
            DataFrame with combined data
        """
        # Calculate hours from date range
        hours = int((end_date - start_date).total_seconds() / 3600)
        
        # Get alerts with team information
        query = '''
            SELECT 
                a.id as alert_id,
                a.meter_id,
                a.zone_id,
                a.severity,
                a.status,
                a.title,
                a.message,
                a.created_at,
                a.resolved_at,
                a.resolved_by,
                t.id as team_id,
                t.name as team_name,
                u.name as resolved_by_name,
                lp.confidence,
                lp.leak_detected,
                lp.leak_type,
                lp.timestamp as leak_detected_at,
                m.location as meter_location,
                m.meter_type,
                z.name as zone_name,
                z.region as zone_region
            FROM alerts a
            LEFT JOIN teams t ON a.team_id = t.id
            LEFT JOIN users u ON a.resolved_by = u.user_id
            LEFT JOIN leak_predictions lp ON a.meter_id = lp.meter_id 
                AND lp.timestamp <= a.created_at
                AND lp.leak_detected = 1
            LEFT JOIN meters m ON a.meter_id = m.meter_id
            LEFT JOIN zones z ON a.zone_id = z.zone_id
            WHERE a.created_at BETWEEN %s AND %s
        '''
        
        params = [start_date, end_date]
        
        if team_id is not None:
            query += " AND a.team_id = %s"
            params.append(team_id)
        
        if severity:
            query += " AND a.severity = %s"
            params.append(severity)
        
        query += " ORDER BY a.created_at DESC"
        
        df = self.db._query_to_df(query, tuple(params))
        
        if not df.empty:
            # Add calculated fields
            df['response_time_hours'] = df.apply(
                lambda row: self._calculate_response_time(row['created_at'], row['resolved_at']),
                axis=1
            )
            
            # Get team members for each alert
            df['team_members'] = df['team_id'].apply(
                lambda tid: self._get_team_members_list(tid) if pd.notna(tid) else ''
            )
        
        return df
    
    # === LEAK DETECTION REPORT ===
    
    def generate_leak_report(self, start_date: datetime, end_date: datetime,
                            team_id: Optional[int] = None) -> pd.DataFrame:
        """
        Generate leak detection report
        
        Args:
            start_date: Report start date
            end_date: Report end date
            team_id: Optional team filter
        
        Returns:
            DataFrame with leak information
        """
        query = '''
            SELECT 
                lp.meter_id,
                lp.timestamp as detected_at,
                lp.confidence,
                lp.leak_type,
                m.location as meter_location,
                m.zone_id,
                z.name as zone_name,
                z.region,
                a.id as alert_id,
                a.status as alert_status,
                a.severity,
                t.name as assigned_team
            FROM leak_predictions lp
            LEFT JOIN meters m ON lp.meter_id = m.meter_id
            LEFT JOIN zones z ON m.zone_id = z.zone_id
            LEFT JOIN alerts a ON lp.meter_id = a.meter_id 
                AND a.created_at >= lp.timestamp
            LEFT JOIN teams t ON a.team_id = t.id
            WHERE lp.leak_detected = 1
                AND lp.timestamp BETWEEN %s AND %s
        '''
        
        params = [start_date, end_date]
        
        if team_id is not None:
            query += " AND a.team_id = %s"
            params.append(team_id)
        
        query += " ORDER BY lp.timestamp DESC"
        
        return self.db._query_to_df(query, tuple(params))
    
    # === TEAM PERFORMANCE REPORT ===
    
    def generate_team_performance_report(self, start_date: datetime, 
                                        end_date: datetime) -> pd.DataFrame:
        """
        Generate team performance report
        
        Args:
            start_date: Report start date
            end_date: Report end date
        
        Returns:
            DataFrame with team performance metrics
        """
        query = '''
            SELECT 
                t.id as team_id,
                t.name as team_name,
                COUNT(DISTINCT tm.user_id) as member_count,
                COUNT(DISTINCT a.id) as total_alerts,
                COUNT(DISTINCT CASE WHEN a.status = 'new' THEN a.id END) as new_alerts,
                COUNT(DISTINCT CASE WHEN a.status = 'assigned' THEN a.id END) as assigned_alerts,
                COUNT(DISTINCT CASE WHEN a.status = 'resolved' THEN a.id END) as resolved_alerts,
                COUNT(DISTINCT CASE WHEN a.severity = 'critical' THEN a.id END) as critical_alerts,
                COUNT(DISTINCT CASE WHEN a.severity = 'warning' THEN a.id END) as warning_alerts,
                AVG(CASE 
                    WHEN a.resolved_at IS NOT NULL 
                    THEN TIMESTAMPDIFF(HOUR, a.created_at, a.resolved_at)
                    ELSE NULL 
                END) as avg_resolution_time_hours
            FROM teams t
            LEFT JOIN team_members tm ON t.id = tm.team_id
            LEFT JOIN alerts a ON t.id = a.team_id 
                AND a.created_at BETWEEN %s AND %s
            WHERE t.status = 'active'
            GROUP BY t.id, t.name
            ORDER BY resolved_alerts DESC, t.name
        '''
        
        df = self.db._query_to_df(query, (start_date, end_date))
        
        if not df.empty:
            # Get team members details
            df['team_members'] = df['team_id'].apply(
                lambda tid: self._get_team_members_list(tid)
            )
        
        return df
    
    # === ALERT SUMMARY REPORT ===
    
    def generate_alert_summary_report(self, start_date: datetime, 
                                     end_date: datetime) -> Dict:
        """
        Generate alert summary statistics
        
        Args:
            start_date: Report start date
            end_date: Report end date
        
        Returns:
            Dictionary with summary statistics
        """
        query = '''
            SELECT 
                COUNT(*) as total_alerts,
                COUNT(CASE WHEN status = 'new' THEN 1 END) as new_alerts,
                COUNT(CASE WHEN status = 'assigned' THEN 1 END) as assigned_alerts,
                COUNT(CASE WHEN status = 'resolved' THEN 1 END) as resolved_alerts,
                COUNT(CASE WHEN severity = 'critical' THEN 1 END) as critical_alerts,
                COUNT(CASE WHEN severity = 'warning' THEN 1 END) as warning_alerts,
                COUNT(CASE WHEN severity = 'normal' THEN 1 END) as normal_alerts,
                COUNT(CASE WHEN team_id IS NOT NULL THEN 1 END) as assigned_to_team,
                COUNT(CASE WHEN team_id IS NULL THEN 1 END) as unassigned,
                AVG(CASE 
                    WHEN resolved_at IS NOT NULL 
                    THEN TIMESTAMPDIFF(HOUR, created_at, resolved_at)
                    ELSE NULL 
                END) as avg_resolution_time_hours
            FROM alerts
            WHERE created_at BETWEEN %s AND %s
        '''
        
        df = self.db._query_to_df(query, (start_date, end_date))
        
        if df.empty:
            return {}
        
        return df.iloc[0].to_dict()
    
    # === HELPER METHODS ===
    
    def _calculate_response_time(self, created_at, resolved_at) -> Optional[float]:
        """Calculate response time in hours"""
        if pd.isna(created_at) or pd.isna(resolved_at):
            return None
        
        delta = resolved_at - created_at
        return delta.total_seconds() / 3600
    
    def _get_team_members_list(self, team_id: int) -> str:
        """Get comma-separated list of team member names"""
        if pd.isna(team_id):
            return ''
        
        team = self.db.get_team(int(team_id))
        if not team or not team.get('members'):
            return ''
        
        member_names = [m['name'] for m in team['members']]
        return ', '.join(member_names)
    
    # === EXPORT METHODS ===
    
    def export_to_csv(self, df: pd.DataFrame) -> bytes:
        """
        Export DataFrame to CSV
        
        Args:
            df: DataFrame to export
        
        Returns:
            CSV data as bytes
        """
        return df.to_csv(index=False).encode('utf-8')
    
    def export_to_excel(self, df: pd.DataFrame, sheet_name: str = 'Report') -> bytes:
        """
        Export DataFrame to Excel
        
        Args:
            df: DataFrame to export
            sheet_name: Name of the Excel sheet
        
        Returns:
            Excel data as bytes
        """
        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            df.to_excel(writer, sheet_name=sheet_name, index=False)
        return output.getvalue()
    
    def export_summary_to_json(self, summary: Dict) -> str:
        """
        Export summary statistics to JSON
        
        Args:
            summary: Summary dictionary
        
        Returns:
            JSON string
        """
        # Convert any datetime objects to strings
        for key, value in summary.items():
            if isinstance(value, datetime):
                summary[key] = value.isoformat()
            elif pd.isna(value):
                summary[key] = None
        
        return json.dumps(summary, indent=2)


# Global report generator instance
from backend.mysql_database_manager import db_manager
report_generator = ReportGenerator(db_manager)
