"""Enhanced Alerts Page - THIWASCO Leak Detection System (No Emojis)"""

import streamlit as st
import pandas as pd
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.mysql_database_manager import db_manager
from backend.alert_manager import alert_manager
from backend.rbac import (
    has_permission,
    Permissions,
    can_assign_alerts,
    can_resolve_alerts,
    get_current_user_id
)


def show_alerts():
    """Enhanced alerts management page with status workflow"""
    st.title("Alerts Management")
    st.write("Review and manage leak alerts, assign to teams, and track resolution status.")
    
    # Get alert statistics
    stats = alert_manager.get_alert_statistics(hours=24)
    
    # Display summary metrics
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("New Alerts", stats['new'])
    with col2:
        st.metric("Assigned Alerts", stats['assigned'])
    with col3:
        st.metric("Resolved Alerts", stats['resolved'])
    with col4:
        total = stats['new'] + stats['assigned'] + stats['resolved']
        st.metric("Total Alerts (24h)", total)
    
    # Filters
    st.markdown("---")
    col_filter1, col_filter2, col_filter3 = st.columns(3)
    
    with col_filter1:
        severity_filter = st.selectbox(
            "Severity",
            ["All", "critical", "warning", "normal"],
            format_func=str.title
        )
    
    with col_filter2:
        # Team filter
        teams_df = db_manager.get_all_teams()
        team_options = ["All Teams"]
        if not teams_df.empty:
            active_teams = teams_df[teams_df['status'] == 'active']
            team_options.extend(active_teams['name'].tolist())
        team_filter = st.selectbox("Team", team_options)
    
    with col_filter3:
        time_filter = st.selectbox(
            "Time Range",
            [("Last 24 hours", 24), ("Last 48 hours", 48), ("Last 7 days", 168)],
            format_func=lambda x: x[0]
        )
        hours = time_filter[1]
    
    # Status tabs
    st.markdown("---")
    tab1, tab2, tab3, tab4 = st.tabs([
        f"New ({stats['new']})",
        f"Assigned ({stats['assigned']})",
        f"Resolved ({stats['resolved']})",
        "All Alerts"
    ])
    
    with tab1:
        show_alerts_by_status("new", severity_filter, team_filter, hours)
    
    with tab2:
        show_alerts_by_status("assigned", severity_filter, team_filter, hours)
    
    with tab3:
        show_alerts_by_status("resolved", severity_filter, team_filter, hours)
    
    with tab4:
        show_all_alerts_view(severity_filter, team_filter, hours)


def show_alerts_by_status(status: str, severity_filter: str, team_filter: str, hours: int):
    """Display alerts filtered by status"""
    
    # Get alerts
    alerts_df = alert_manager.get_all_alerts(hours=hours)
    
    if alerts_df.empty:
        st.info(f"No {status} alerts found.")
        return
    
    # Filter by status
    alerts_df = alerts_df[alerts_df['status'] == status]
    
    # Apply severity filter
    if severity_filter != "All":
        alerts_df = alerts_df[alerts_df['severity'] == severity_filter]
    
    # Apply team filter
    if team_filter != "All Teams":
        alerts_df = alerts_df[alerts_df['team_name'] == team_filter]
    
    if alerts_df.empty:
        st.info(f"No {status} alerts match the selected filters.")
        return
    
    st.write(f"**{len(alerts_df)} {status.upper()} alert(s)**")
    
    # Assignment section for NEW alerts (NRW Officer only)
    if status == "new" and can_assign_alerts():
        with st.expander("Assign Alerts to Teams", expanded=False):
            show_bulk_assignment_ui(alerts_df)
    
    # Display alerts
    for idx, alert in alerts_df.iterrows():
        show_alert_card(alert, status)


def show_all_alerts_view(severity_filter: str, team_filter: str, hours: int):
    """Display all alerts regardless of status"""
    
    alerts_df = alert_manager.get_all_alerts(hours=hours)
    
    if alerts_df.empty:
        st.info("No alerts found.")
        return
    
    # Apply severity filter
    if severity_filter != "All":
        alerts_df = alerts_df[alerts_df['severity'] == severity_filter]
    
    # Apply team filter
    if team_filter != "All Teams":
        alerts_df = alerts_df[alerts_df['team_name'] == team_filter]
    
    if alerts_df.empty:
        st.info("No alerts match the selected filters.")
        return
    
    st.write(f"**{len(alerts_df)} alert(s) found**")
    
    # Display alerts grouped by status
    for status in ['new', 'assigned', 'resolved']:
        status_alerts = alerts_df[alerts_df['status'] == status]
        if not status_alerts.empty:
            st.subheader(f"{status.upper()} ({len(status_alerts)})")
            for idx, alert in status_alerts.iterrows():
                show_alert_card(alert, status)


def show_alert_card(alert: pd.Series, status: str):
    """Display individual alert card"""
    
    # Status badge color
    if status == 'new':
        status_color = "🔵"
        status_bg = "#E3F2FD"
    elif status == 'assigned':
        status_color = "🟡"
        status_bg = "#FFF9C4"
    else:  # resolved
        status_color = "🟢"
        status_bg = "#E8F5E9"
    
    # Severity badge
    severity_colors = {
        'critical': '#FFEBEE',
        'warning': '#FFF3E0',
        'normal': '#F5F5F5'
    }
    
    with st.container():
        st.markdown(f"""
        <div style="padding: 15px; border-left: 4px solid {'#F44336' if alert['severity']=='critical' else '#FF9800' if alert['severity']=='warning' else '#9E9E9E'}; 
                    background-color: {severity_colors.get(alert['severity'], '#F5F5F5')}; margin-bottom: 10px; border-radius: 5px;">
            <strong>{alert['meter_id']}</strong> - {alert.get('title', 'Leak Detected')}
        </div>
        """, unsafe_allow_html=True)
        
        col1, col2 = st.columns([3, 1])
        
        with col1:
            st.write(f"**Status:** {alert['status'].upper()}")
            st.write(f"**Severity:** {alert['severity'].upper()}")
            st.write(f"**Zone:** {alert.get('zone_id', 'N/A')}")
            
            if alert.get('team_name'):
                st.write(f"**Assigned Team:** {alert['team_name']}")
            
            st.write(f"**Created:** {alert['created_at'].strftime('%Y-%m-%d %H:%M') if pd.notna(alert['created_at']) else 'N/A'}")
            
            if alert['status'] == 'resolved' and pd.notna(alert.get('resolved_at')):
                st.write(f"**Resolved:** {alert['resolved_at'].strftime('%Y-%m-%d %H:%M')}")
                if alert.get('resolved_by_name'):
                    st.write(f"**Resolved By:** {alert['resolved_by_name']}")
        
        with col2:
            # Action buttons (NRW Officer only)
            if can_assign_alerts() and alert['status'] in ['new', 'assigned']:
                if st.button("Assign to Team", key=f"assign_{alert['id']}"):
                    st.session_state[f'assigning_{alert["id"]}'] = True
                    st.rerun()
            
            if can_resolve_alerts() and alert['status'] != 'resolved':
                if st.button("Mark as Resolved", key=f"resolve_{alert['id']}"):
                    success, msg = alert_manager.resolve_alert(
                        alert['id'],
                        get_current_user_id()
                    )
                    if success:
                        st.success(msg)
                        # Clear cache and refresh
                        st.cache_data.clear()
                        if 'monitoring_data_24' in st.session_state:
                            del st.session_state['monitoring_data_24']
                        st.rerun()
                    else:
                        st.error(msg)
        
        # Inline assignment form
        if st.session_state.get(f'assigning_{alert["id"]}', False):
            show_inline_assignment_form(alert['id'])
        
        st.markdown("---")


def show_inline_assignment_form(alert_id: int):
    """Show inline form to assign alert to team"""
    st.markdown("**Assign to Team:**")
    
    teams_df = db_manager.get_all_teams()
    if teams_df.empty:
        st.warning("No teams available.")
        return
    
    active_teams = teams_df[teams_df['status'] == 'active']
    if active_teams.empty:
        st.warning("No active teams available.")
        return
    
    team_options = {row['name']: row['id'] for _, row in active_teams.iterrows()}
    
    col1, col2 = st.columns([3, 1])
    with col1:
        selected_team = st.selectbox(
            "Select Team",
            options=list(team_options.keys()),
            key=f"team_select_{alert_id}"
        )
    
    with col2:
        if st.button("Assign", key=f"confirm_assign_{alert_id}"):
            team_id = team_options[selected_team]
            success, msg = alert_manager.assign_alert_to_team(
                alert_id,
                team_id,
                get_current_user_id()
            )
            if success:
                st.success(msg)
                st.session_state.pop(f'assigning_{alert_id}', None)
                # Clear cache and refresh
                st.cache_data.clear()
                if 'monitoring_data_24' in st.session_state:
                    del st.session_state['monitoring_data_24']
                st.rerun()
            else:
                st.error(msg)
        
        if st.button("Cancel", key=f"cancel_assign_{alert_id}"):
            st.session_state.pop(f'assigning_{alert_id}', None)
            st.rerun()


def show_bulk_assignment_ui(alerts_df: pd.DataFrame):
    """Show UI for bulk alert assignment"""
    st.write("**Assign multiple alerts to a team**")
    
    # Get active teams
    teams_df = db_manager.get_all_teams()
    if teams_df.empty:
        st.info("No teams available. Create teams first in the Teams page.")
        return
    
    active_teams = teams_df[teams_df['status'] == 'active']
    if active_teams.empty:
        st.info("No active teams available.")
        return
    
    with st.form("bulk_assign_form"):
        # Select alerts
        alert_options = {f"{row['meter_id']} - {row.get('title', 'Leak')}": row['id'] 
                        for _, row in alerts_df.iterrows()}
        
        selected_alerts = st.multiselect(
            "Select Alerts",
            options=list(alert_options.keys()),
            help="Select one or more alerts to assign"
        )
        
        # Select team
        team_options = {row['name']: row['id'] for _, row in active_teams.iterrows()}
        selected_team = st.selectbox(
            "Assign to Team",
            options=list(team_options.keys())
        )
        
        submitted = st.form_submit_button("Assign Selected Alerts")
        
        if submitted:
            if not selected_alerts:
                st.error("Please select at least one alert")
            else:
                alert_ids = [alert_options[alert] for alert in selected_alerts]
                team_id = team_options[selected_team]
                
                success_count, failure_count, errors = alert_manager.bulk_assign_alerts(
                    alert_ids,
                    team_id,
                    get_current_user_id()
                )
                
                if success_count > 0:
                    st.success(f"Successfully assigned {success_count} alert(s) to {selected_team}")
                    # Clear cache and refresh
                    st.cache_data.clear()
                    if 'monitoring_data_24' in st.session_state:
                        del st.session_state['monitoring_data_24']
                    st.rerun()
                
                if failure_count > 0:
                    st.warning(f"Failed to assign {failure_count} alert(s)")
                    for error in errors:
                        st.error(error)
