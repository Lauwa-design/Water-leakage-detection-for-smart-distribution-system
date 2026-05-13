"""Alerts page - operational queue for leak response."""

from __future__ import annotations

import pandas as pd
import streamlit as st

from backend.mysql_database_manager import db_manager
from backend.rbac import has_permission, Permissions, can_assign_alerts
from page_components.data_utils import build_meter_snapshot, get_cached_data, load_static_data
from page_components.ui import empty_state, metric_card, page_header, section_header


def _format_datetime_safe(series: pd.Series) -> pd.Series:
    """Safely format datetime series, handling non-datetime values."""
    if series.empty:
        return series
    # Convert to datetime, coercing errors to NaT
    dt_series = pd.to_datetime(series, errors="coerce")
    # Format valid datetimes, leave NaT as empty string
    return dt_series.apply(lambda x: x.strftime("%Y-%m-%d %H:%M") if pd.notna(x) else "")


def show_alerts() -> None:
    """Render the alerts management page."""
    page_header(
        "Alerts",
        "Review active leak alerts, filter by severity, and close resolved cases.",
    )

    # Load static data first (fast - zones, meters)
    static_data = load_static_data()
    
    # Load dynamic data with session state caching (ultra-fast on page switches)
    data = get_cached_data(hours=24)
    
    # Build snapshot for consistent leak metrics
    snapshot = build_meter_snapshot(
        static_data["meters"],
        static_data["zones"],
        data["readings"],
        data["predictions"],
        data["alerts"],
    )

    # Calculate leak metrics from snapshot (consistent with Overview and Leak Analysis)
    if not snapshot.empty:
        # Get unique meters with leaks
        unique_leaks = snapshot[snapshot["leak_detected"] == True].drop_duplicates("meter_id")
        total_detected = len(unique_leaks)
        critical_count = len(unique_leaks[unique_leaks["severity"] == "critical"])
        warning_count = len(unique_leaks[unique_leaks["severity"] == "warning"])
    else:
        total_detected = 0
        critical_count = 0
        warning_count = 0

    summary_columns = st.columns(4)
    with summary_columns[0]:
        metric_card("Critical", str(critical_count), "Meters with critical leaks (≥95% confidence)", "danger")
    with summary_columns[1]:
        metric_card("Warnings", str(warning_count), "Meters with warning leaks (85-94% confidence)", "warning")
    with summary_columns[2]:
        metric_card("Detected Leaks", str(total_detected), "Total unique meters with leaks", "neutral")
    with summary_columns[3]:
        metric_card("Active Meters", str(len(static_data["meters"])), "Meters under watch", "success")

    # Filter options
    filter_columns = st.columns([1, 1])
    with filter_columns[0]:
        severity_filter = st.selectbox("Severity", ["All", "critical", "warning", "normal"], format_func=str.title)
    with filter_columns[1]:
        # Team filter (if user has permission)
        if has_permission(Permissions.TEAM_READ):
            teams_df = db_manager.get_all_teams()
            if not teams_df.empty:
                active_teams = teams_df[teams_df['status'] == 'active']
                team_options = ["All Teams"] + active_teams['name'].tolist() + ["Unassigned"]
                team_filter = st.selectbox("Team Assignment", team_options)
            else:
                team_filter = "All Teams"
        else:
            team_filter = "All Teams"

    # Get leak data from snapshot (consistent with other pages)
    if not snapshot.empty:
        # Get all leaks (no confidence filter - show all detected)
        leak_alerts = snapshot[snapshot["leak_detected"] == True].copy()

        # Apply severity filter
        if severity_filter != "All":
            leak_alerts = leak_alerts[leak_alerts["severity"] == severity_filter]

        # Sort and get most recent per meter
        leak_alerts = leak_alerts.sort_values("prediction_time", ascending=False)
        leak_alerts = leak_alerts.drop_duplicates(subset=["meter_id"], keep="first")
        total_unique = len(leak_alerts)
    else:
        leak_alerts = pd.DataFrame()
        total_unique = 0

    section_header(f"Active Leak Alerts ({total_unique} unique meters)", "Most recent alert per meter. Resolved alerts are auto-archived after 7 days.")
    
    # Team assignment section (NRW Officer only)
    if can_assign_alerts() and not leak_alerts.empty:
        with st.expander("🎯 Assign Alerts to Teams", expanded=False):
            show_team_assignment_ui(leak_alerts)
    
    if leak_alerts.empty:
        empty_state("No alerts match the selected filters.")
        return

    # Display leak alerts from snapshot data
    display = leak_alerts[["meter_id", "zone", "location", "leak_type", "confidence", "severity", "status", "prediction_time"]].copy()
    display["confidence"] = (display["confidence"] * 100).round(1).astype(str) + "%"
    display = display.rename(
        columns={
            "meter_id": "Meter",
            "zone": "Zone",
            "location": "Location",
            "leak_type": "Leak Type",
            "confidence": "Confidence",
            "severity": "Severity",
            "status": "Status",
            "prediction_time": "Detected At",
        }
    )
    st.dataframe(display, width='stretch', hide_index=True)



def show_team_assignment_ui(leak_alerts: pd.DataFrame) -> None:
    """Display UI for assigning alerts to teams (NRW Officer only)"""
    st.write("**Assign leak alerts to field teams for investigation**")
    
    # Get all active teams
    teams_df = db_manager.get_all_teams()
    if teams_df.empty:
        st.info("📭 No teams available. Create teams first in the Teams page.")
        return
    
    active_teams = teams_df[teams_df['status'] == 'active']
    if active_teams.empty:
        st.info("📭 No active teams available.")
        return
    
    # Get alerts from database to check team assignments
    db_alerts = db_manager.get_alerts(hours=24)
    
    # Create team assignment form
    with st.form("assign_alerts_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            # Select meters to assign
            meter_options = leak_alerts['meter_id'].tolist()
            selected_meters = st.multiselect(
                "Select Meters",
                options=meter_options,
                help="Select one or more meters to assign to a team"
            )
        
        with col2:
            # Select team
            team_options = {row['name']: row['id'] for _, row in active_teams.iterrows()}
            selected_team_name = st.selectbox(
                "Assign to Team",
                options=list(team_options.keys()),
                help="Select the team to handle these alerts"
            )
        
        submitted = st.form_submit_button("📌 Assign to Team")
        
        if submitted:
            if not selected_meters:
                st.error("❌ Please select at least one meter")
            else:
                team_id = team_options[selected_team_name]
                success_count = 0
                error_count = 0
                
                # For each selected meter, find its alert and assign to team
                for meter_id in selected_meters:
                    # Find the alert ID for this meter from database
                    meter_alerts = db_alerts[db_alerts['meter_id'] == meter_id]
                    if not meter_alerts.empty:
                        # Get the most recent alert
                        alert_id = meter_alerts.iloc[0]['id']
                        success, msg = db_manager.assign_alert_to_team(
                            alert_id=alert_id,
                            team_id=team_id,
                            assigned_by=st.session_state.get('user_id')
                        )
                        if success:
                            success_count += 1
                        else:
                            error_count += 1
                            st.error(f"Failed to assign {meter_id}: {msg}")
                
                if success_count > 0:
                    st.success(f"✅ Successfully assigned {success_count} alert(s) to {selected_team_name}")
                    st.rerun()
                if error_count > 0:
                    st.warning(f"⚠️ Failed to assign {error_count} alert(s)")
    
    # Show current team assignments
    st.markdown("---")
    st.write("**Current Team Assignments**")
    
    if not db_alerts.empty and 'team_id' in db_alerts.columns:
        assigned_alerts = db_alerts[db_alerts['team_id'].notna()]
        if not assigned_alerts.empty:
            # Merge with team names
            assigned_with_teams = assigned_alerts.merge(
                active_teams[['id', 'name']],
                left_on='team_id',
                right_on='id',
                how='left'
            )
            
            display_assignments = assigned_with_teams[['meter_id', 'name', 'severity', 'status', 'created_at']].copy()
            display_assignments = display_assignments.rename(columns={
                'meter_id': 'Meter',
                'name': 'Assigned Team',
                'severity': 'Severity',
                'status': 'Status',
                'created_at': 'Created'
            })
            st.dataframe(display_assignments, width='stretch', hide_index=True)
        else:
            st.info("No alerts have been assigned to teams yet.")
    else:
        st.info("No alerts have been assigned to teams yet.")
