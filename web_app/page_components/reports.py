"""Reports Page - THIWASCO Leak Detection System"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.mysql_database_manager import db_manager
from backend.report_generator import report_generator
from backend.rbac import (
    has_permission,
    Permissions,
    is_nrw_officer,
    show_permission_denied
)


def show_reports():
    """Main reports page"""
    st.title("Reports")
    st.write("Generate comprehensive reports combining leak detection, alerts, and team information.")
    
    # Check permissions
    if not is_nrw_officer():
        show_permission_denied("generate reports")
        st.info("Report generation is restricted to Non-Revenue Water Officers.")
        return
    
    # Report type selection
    st.markdown("---")
    report_type = st.selectbox(
        "Select Report Type",
        [
            "Comprehensive Report",
            "Leak Detection Report",
            "Team Performance Report",
            "Alert Summary Report"
        ]
    )
    
    # Common filters
    st.markdown("### Report Filters")
    col1, col2 = st.columns(2)
    
    with col1:
        # Date range
        date_range = st.selectbox(
            "Date Range",
            [
                ("Last 24 Hours", 1),
                ("Last 7 Days", 7),
                ("Last 30 Days", 30),
                ("Last 90 Days", 90),
                ("Custom Range", 0)
            ],
            format_func=lambda x: x[0]
        )
        
        if date_range[1] == 0:  # Custom range
            start_date = st.date_input("Start Date", datetime.now() - timedelta(days=30))
            end_date = st.date_input("End Date", datetime.now())
            start_datetime = datetime.combine(start_date, datetime.min.time())
            end_datetime = datetime.combine(end_date, datetime.max.time())
        else:
            end_datetime = datetime.now()
            start_datetime = end_datetime - timedelta(days=date_range[1])
    
    with col2:
        # Team filter (for applicable reports)
        if report_type in ["Comprehensive Report", "Leak Detection Report"]:
            teams_df = db_manager.get_all_teams()
            team_options = {"All Teams": None}
            if not teams_df.empty:
                active_teams = teams_df[teams_df['status'] == 'active']
                for _, team in active_teams.iterrows():
                    team_options[team['name']] = team['id']
            
            selected_team_name = st.selectbox("Filter by Team", list(team_options.keys()))
            selected_team_id = team_options[selected_team_name]
        else:
            selected_team_id = None
        
        # Severity filter (for comprehensive report)
        if report_type == "Comprehensive Report":
            severity_filter = st.selectbox(
                "Filter by Severity",
                ["All", "critical", "warning", "normal"],
                format_func=str.title
            )
            severity = None if severity_filter == "All" else severity_filter
        else:
            severity = None
    
    # Generate report button
    st.markdown("---")
    if st.button("Generate Report", type="primary"):
        with st.spinner("Generating report..."):
            generate_report(
                report_type,
                start_datetime,
                end_datetime,
                selected_team_id,
                severity
            )


def generate_report(report_type: str, start_date: datetime, end_date: datetime,
                   team_id: int = None, severity: str = None):
    """Generate and display the selected report"""
    
    try:
        if report_type == "Comprehensive Report":
            df = report_generator.generate_comprehensive_report(
                start_date, end_date, team_id, severity
            )
            display_comprehensive_report(df, start_date, end_date)
        
        elif report_type == "Leak Detection Report":
            df = report_generator.generate_leak_report(
                start_date, end_date, team_id
            )
            display_leak_report(df, start_date, end_date)
        
        elif report_type == "Team Performance Report":
            df = report_generator.generate_team_performance_report(
                start_date, end_date
            )
            display_team_performance_report(df, start_date, end_date)
        
        elif report_type == "Alert Summary Report":
            summary = report_generator.generate_alert_summary_report(
                start_date, end_date
            )
            display_alert_summary_report(summary, start_date, end_date)
    
    except Exception as e:
        st.error(f"Error generating report: {str(e)}")
        import traceback
        st.code(traceback.format_exc())


def display_comprehensive_report(df: pd.DataFrame, start_date: datetime, end_date: datetime):
    """Display comprehensive report"""
    st.success("Report generated successfully!")
    
    st.markdown("### Comprehensive Leak & Alert Report")
    st.write(f"**Period:** {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    
    if df.empty:
        st.info("No data found for the selected period and filters.")
        return
    
    # Summary statistics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Alerts", len(df))
    with col2:
        resolved = len(df[df['status'] == 'resolved'])
        st.metric("Resolved", resolved)
    with col3:
        critical = len(df[df['severity'] == 'critical'])
        st.metric("Critical", critical)
    with col4:
        avg_response = df['response_time_hours'].mean()
        st.metric("Avg Response (hrs)", f"{avg_response:.1f}" if pd.notna(avg_response) else "N/A")
    
    # Display data
    st.markdown("---")
    st.markdown("### Detailed Data")
    
    # Select columns to display
    display_columns = [
        'alert_id', 'meter_id', 'zone_name', 'severity', 'status',
        'team_name', 'team_members', 'leak_type', 'confidence',
        'created_at', 'resolved_at', 'resolved_by_name', 'response_time_hours'
    ]
    
    # Filter to only existing columns
    display_columns = [col for col in display_columns if col in df.columns]
    
    display_df = df[display_columns].copy()
    
    # Format datetime columns
    for col in ['created_at', 'resolved_at']:
        if col in display_df.columns:
            display_df[col] = display_df[col].apply(
                lambda x: x.strftime('%Y-%m-%d %H:%M') if pd.notna(x) else ''
            )
    
    # Format numeric columns
    if 'confidence' in display_df.columns:
        display_df['confidence'] = display_df['confidence'].apply(
            lambda x: f"{x*100:.1f}%" if pd.notna(x) else ''
        )
    
    if 'response_time_hours' in display_df.columns:
        display_df['response_time_hours'] = display_df['response_time_hours'].apply(
            lambda x: f"{x:.1f}" if pd.notna(x) else ''
        )
    
    # Rename columns for display
    column_names = {
        'alert_id': 'Alert ID',
        'meter_id': 'Meter',
        'zone_name': 'Zone',
        'severity': 'Severity',
        'status': 'Status',
        'team_name': 'Team',
        'team_members': 'Team Members',
        'leak_type': 'Leak Type',
        'confidence': 'Confidence',
        'created_at': 'Created',
        'resolved_at': 'Resolved',
        'resolved_by_name': 'Resolved By',
        'response_time_hours': 'Response Time (hrs)'
    }
    
    display_df = display_df.rename(columns=column_names)
    
    st.dataframe(display_df, use_container_width=True, hide_index=True)
    
    # Export options
    st.markdown("---")
    st.markdown("### Export Report")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        csv_data = report_generator.export_to_csv(df)
        st.download_button(
            label="Download CSV",
            data=csv_data,
            file_name=f"comprehensive_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv"
        )
    
    with col2:
        try:
            excel_data = report_generator.export_to_excel(df, "Comprehensive Report")
            st.download_button(
                label="Download Excel",
                data=excel_data,
                file_name=f"comprehensive_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            )
        except Exception as e:
            st.warning(f"Excel export not available: {str(e)}")


def display_leak_report(df: pd.DataFrame, start_date: datetime, end_date: datetime):
    """Display leak detection report"""
    st.success("Report generated successfully!")
    
    st.markdown("### Leak Detection Report")
    st.write(f"**Period:** {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    
    if df.empty:
        st.info("No leaks detected for the selected period and filters.")
        return
    
    # Summary statistics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Leaks Detected", len(df))
    with col2:
        with_alerts = len(df[df['alert_id'].notna()])
        st.metric("With Alerts", with_alerts)
    with col3:
        assigned = len(df[df['assigned_team'].notna()])
        st.metric("Assigned to Teams", assigned)
    
    # Display data
    st.markdown("---")
    st.dataframe(df, use_container_width=True, hide_index=True)
    
    # Export
    st.markdown("---")
    csv_data = report_generator.export_to_csv(df)
    st.download_button(
        label="Download CSV",
        data=csv_data,
        file_name=f"leak_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )


def display_team_performance_report(df: pd.DataFrame, start_date: datetime, end_date: datetime):
    """Display team performance report"""
    st.success("Report generated successfully!")
    
    st.markdown("### Team Performance Report")
    st.write(f"**Period:** {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    
    if df.empty:
        st.info("No team data found for the selected period.")
        return
    
    # Summary statistics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Teams", len(df))
    with col2:
        total_resolved = df['resolved_alerts'].sum()
        st.metric("Total Resolved", int(total_resolved))
    with col3:
        avg_resolution = df['avg_resolution_time_hours'].mean()
        st.metric("Avg Resolution Time (hrs)", f"{avg_resolution:.1f}" if pd.notna(avg_resolution) else "N/A")
    
    # Display data
    st.markdown("---")
    
    # Format for display
    display_df = df.copy()
    if 'avg_resolution_time_hours' in display_df.columns:
        display_df['avg_resolution_time_hours'] = display_df['avg_resolution_time_hours'].apply(
            lambda x: f"{x:.1f}" if pd.notna(x) else 'N/A'
        )
    
    # Rename columns
    display_df = display_df.rename(columns={
        'team_name': 'Team Name',
        'member_count': 'Members',
        'total_alerts': 'Total Alerts',
        'new_alerts': 'New',
        'assigned_alerts': 'Assigned',
        'resolved_alerts': 'Resolved',
        'critical_alerts': 'Critical',
        'warning_alerts': 'Warning',
        'avg_resolution_time_hours': 'Avg Resolution (hrs)',
        'team_members': 'Team Members'
    })
    
    # Select columns to display
    display_columns = [
        'Team Name', 'Members', 'Team Members', 'Total Alerts',
        'New', 'Assigned', 'Resolved', 'Critical', 'Warning',
        'Avg Resolution (hrs)'
    ]
    
    display_columns = [col for col in display_columns if col in display_df.columns]
    
    st.dataframe(display_df[display_columns], use_container_width=True, hide_index=True)
    
    # Export
    st.markdown("---")
    csv_data = report_generator.export_to_csv(df)
    st.download_button(
        label="Download CSV",
        data=csv_data,
        file_name=f"team_performance_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
        mime="text/csv"
    )


def display_alert_summary_report(summary: dict, start_date: datetime, end_date: datetime):
    """Display alert summary report"""
    st.success("Report generated successfully!")
    
    st.markdown("### Alert Summary Report")
    st.write(f"**Period:** {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
    
    if not summary:
        st.info("No alert data found for the selected period.")
        return
    
    # Display metrics
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        st.metric("Total Alerts", int(summary.get('total_alerts', 0)))
        st.metric("New", int(summary.get('new_alerts', 0)))
    
    with col2:
        st.metric("Assigned", int(summary.get('assigned_alerts', 0)))
        st.metric("Resolved", int(summary.get('resolved_alerts', 0)))
    
    with col3:
        st.metric("Critical", int(summary.get('critical_alerts', 0)))
        st.metric("Warning", int(summary.get('warning_alerts', 0)))
    
    with col4:
        st.metric("Normal", int(summary.get('normal_alerts', 0)))
        avg_time = summary.get('avg_resolution_time_hours')
        st.metric("Avg Resolution (hrs)", f"{avg_time:.1f}" if avg_time else "N/A")
    
    # Team assignment stats
    st.markdown("---")
    st.markdown("### Team Assignment")
    
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Assigned to Teams", int(summary.get('assigned_to_team', 0)))
    with col2:
        st.metric("Unassigned", int(summary.get('unassigned', 0)))
    
    # Export
    st.markdown("---")
    json_data = report_generator.export_summary_to_json(summary)
    st.download_button(
        label="Download JSON",
        data=json_data,
        file_name=f"alert_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json",
        mime="application/json"
    )
