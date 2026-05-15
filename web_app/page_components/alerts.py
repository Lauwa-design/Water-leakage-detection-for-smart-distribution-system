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
    get_current_user_id,
    get_current_user_role,
    is_field_technician
)
from page_components.ui import page_header
from page_components.data_utils import clear_alert_cache


def show_alerts():
    """Enhanced alerts management page with status workflow"""
    page_header("Alerts", "Review, assign and resolve active leak alerts.", eyebrow="Alerts Management")

    current_user_id = get_current_user_id()
    current_role = get_current_user_role()

    # Check if Field Technician - show only their team's alerts
    if is_field_technician():
        st.write("View alerts assigned to your teams.")
        show_field_technician_alerts(current_user_id)
        return

    _live_alerts_body()


@st.fragment(run_every=30)
def _live_alerts_body():

    # For NRW Officer and System Admin - show all alerts
    st.write("Review and manage leak alerts, assign to teams, and track resolution status.")

    # Filters
    st.markdown("---")
    col_filter1, col_filter2, col_filter3 = st.columns(3)

    with col_filter3:
        time_filter = st.selectbox(
            "Time Range",
            [("Last 24 hours", 24), ("Last 48 hours", 48), ("Last 7 days", 168)],
            format_func=lambda x: x[0]
        )
        hours = time_filter[1]

    with col_filter1:
        severity_filter = st.selectbox(
            "Severity",
            ["All", "critical", "warning", "normal"],
            format_func=str.title
        )

    with col_filter2:
        teams_df = db_manager.get_all_teams()
        team_options = ["All Teams"]
        if not teams_df.empty:
            active_teams = teams_df[teams_df['status'] == 'active']
            team_options.extend(active_teams['name'].tolist())
        team_filter = st.selectbox("Team", team_options)

    # Load once, filter once — counts always match displayed data
    all_alerts_df = alert_manager.get_all_alerts(hours=hours)
    filtered_df = all_alerts_df.copy()
    if severity_filter != "All":
        filtered_df = filtered_df[filtered_df['severity'] == severity_filter]
    if team_filter != "All Teams":
        filtered_df = filtered_df[filtered_df['team_name'] == team_filter]

    n_new      = int((filtered_df['status'] == 'new').sum())      if not filtered_df.empty else 0
    n_assigned = int((filtered_df['status'] == 'assigned').sum()) if not filtered_df.empty else 0
    n_resolved = int((filtered_df['status'] == 'resolved').sum()) if not filtered_df.empty else 0
    n_total    = n_new + n_assigned + n_resolved

    # Summary metrics — derived from same filtered set as the tabs
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("New Alerts", n_new)
    with col2:
        st.metric("Assigned Alerts", n_assigned)
    with col3:
        st.metric("Resolved Alerts", n_resolved)
    with col4:
        st.metric(f"Total ({time_filter[0]})", n_total)

    # Stable tab labels (no counts) so the active tab persists across reruns.
    # Counts are already visible in the metrics row above.
    st.markdown("---")
    tab1, tab2, tab3, tab4 = st.tabs(["New", "Assigned", "Resolved", "All Alerts"])

    with tab1:
        _show_status_tab(filtered_df, "new")
    with tab2:
        _show_status_tab(filtered_df, "assigned")
    with tab3:
        _show_status_tab(filtered_df, "resolved")
    with tab4:
        _show_all_tab(filtered_df)


def _show_status_tab(filtered_df: pd.DataFrame, status: str):
    """Display pre-filtered alerts for a given status tab."""
    subset = filtered_df[filtered_df['status'] == status] if not filtered_df.empty else filtered_df

    if subset.empty:
        st.info(f"No {status} alerts match the selected filters.")
        return

    st.write(f"**{len(subset)} {status.upper()} alert(s)**")

    if status == "new" and can_assign_alerts():
        show_zone_grouped_new_alerts(subset)
    else:
        for _, alert in subset.iterrows():
            show_alert_card(alert, status)


def _show_all_tab(filtered_df: pd.DataFrame):
    """Display all pre-filtered alerts grouped by status."""
    if filtered_df.empty:
        st.info("No alerts match the selected filters.")
        return

    st.write(f"**{len(filtered_df)} alert(s) found**")
    for status in ['new', 'assigned', 'resolved']:
        subset = filtered_df[filtered_df['status'] == status]
        if not subset.empty:
            st.subheader(f"{status.upper()} ({len(subset)})")
            for _, alert in subset.iterrows():
                show_alert_card(alert, f"all_{status}")


# Legacy kept for field-tech path which still calls this directly
def show_alerts_by_status(status: str, severity_filter: str, team_filter: str, hours: int):
    alerts_df = alert_manager.get_all_alerts(hours=hours)
    if alerts_df.empty:
        st.info(f"No {status} alerts found.")
        return
    alerts_df = alerts_df[alerts_df['status'] == status]
    if severity_filter != "All":
        alerts_df = alerts_df[alerts_df['severity'] == severity_filter]
    if team_filter != "All Teams":
        alerts_df = alerts_df[alerts_df['team_name'] == team_filter]
    if alerts_df.empty:
        st.info(f"No {status} alerts match the selected filters.")
        return
    st.write(f"**{len(alerts_df)} {status.upper()} alert(s)**")
    if status == "new" and can_assign_alerts():
        show_zone_grouped_new_alerts(alerts_df)
    else:
        for _, alert in alerts_df.iterrows():
            show_alert_card(alert, status)


def show_zone_grouped_new_alerts(alerts_df: pd.DataFrame):
    """Group unassigned alerts by zone; one team picker assigns all alerts in a zone at once."""
    teams_df = db_manager.get_all_teams()
    active_teams = teams_df[teams_df['status'] == 'active'] if not teams_df.empty else pd.DataFrame()
    team_options = {row['name']: int(row['id']) for _, row in active_teams.iterrows()} if not active_teams.empty else {}
    team_names   = list(team_options.keys())

    # Sort zones so critical-heavy zones surface first
    zone_order = (
        alerts_df.groupby('zone_id')['severity']
        .apply(lambda s: (s == 'critical').sum())
        .sort_values(ascending=False)
        .index.tolist()
    )

    for zone in zone_order:
        zone_alerts = alerts_df[alerts_df['zone_id'] == zone].copy()
        n_total    = len(zone_alerts)
        n_critical = (zone_alerts['severity'] == 'critical').sum()
        n_warning  = (zone_alerts['severity'] == 'warning').sum()

        # Severity summary text
        parts = []
        if n_critical: parts.append(f"<span style='color:#ef4444;font-weight:700;'>{n_critical} critical</span>")
        if n_warning:  parts.append(f"<span style='color:#f59e0b;font-weight:700;'>{n_warning} warning</span>")
        sev_html = " &middot; ".join(parts) if parts else f"{n_total} alert{'s' if n_total != 1 else ''}"

        st.markdown(f"""
        <div style="background:rgba(255,255,255,0.04);border:1px solid rgba(255,255,255,0.09);
                    border-radius:8px;padding:12px 16px;margin:18px 0 6px;">
            <span style="font-size:0.7rem;font-weight:700;text-transform:uppercase;
                         letter-spacing:0.12em;color:#64748b;">Zone</span>
            <span style="color:#f1f5f9;font-size:1rem;font-weight:700;margin-left:8px;">{zone}</span>
            <span style="color:#64748b;font-size:0.85rem;margin-left:12px;">
                {n_total} alert{'s' if n_total != 1 else ''} &nbsp;&middot;&nbsp; {sev_html}
            </span>
        </div>
        """, unsafe_allow_html=True)

        # Assignment + resolve row
        if team_names:
            # Suggest the team that most recently handled an alert in this zone
            suggested = db_manager.get_last_assigned_team_for_zone(zone)
            suggested_idx = 0
            suggested_label = None
            if suggested and suggested['name'] in team_names:
                suggested_idx = team_names.index(suggested['name'])
                suggested_label = f"Previously assigned: {suggested['name']}"

            col_lbl, col_team, col_assign, col_resolve = st.columns([1.4, 3, 1.4, 1.4])
            with col_lbl:
                st.markdown(
                    "<div style='padding-top:6px;color:#94a3b8;font-size:0.82rem;font-weight:600;'>"
                    "Assign zone to:</div>",
                    unsafe_allow_html=True,
                )
            with col_team:
                selected_team = st.selectbox(
                    "team",
                    options=team_names,
                    index=suggested_idx,
                    key=f"zone_team_{zone}",
                    label_visibility="collapsed",
                    help=suggested_label,
                )
            with col_assign:
                if st.button(f"Assign all ({n_total})", key=f"zone_assign_{zone}"):
                    team_id   = team_options[selected_team]
                    alert_ids = [int(a['id']) for _, a in zone_alerts.iterrows()]
                    ok, fail, _ = alert_manager.bulk_assign_alerts(
                        alert_ids, team_id, get_current_user_id()
                    )
                    if ok:
                        st.success(f"Assigned {ok} alert(s) in {zone} to {selected_team}")
                        st.cache_data.clear()
                        clear_alert_cache()
                        st.rerun()
                    if fail:
                        st.warning(f"{fail} assignment(s) failed")
            with col_resolve:
                n_assigned = int((zone_alerts['status'] == 'assigned').sum())
                if can_resolve_alerts() and n_assigned > 0:
                    if st.button(f"Resolve assigned ({n_assigned})", key=f"zone_resolve_{zone}"):
                        for _, a in zone_alerts[zone_alerts['status'] == 'assigned'].iterrows():
                            alert_manager.resolve_alert(int(a['id']), get_current_user_id())
                        st.success(f"Resolved {n_assigned} assigned alert(s) in {zone}")
                        st.cache_data.clear()
                        clear_alert_cache()
                        st.rerun()
                elif can_resolve_alerts():
                    st.caption("Assign first to resolve.")
        else:
            st.info("No active teams — create teams first in the Teams page.")

        # Individual alert cards inside an expander
        with st.expander(f"View {n_total} alert detail{'s' if n_total != 1 else ''}", expanded=(n_total <= 3)):
            for _, alert in zone_alerts.iterrows():
                show_alert_card(alert, "new")




def show_alert_card(alert: pd.Series, status: str):
    """Display individual alert card"""
    
    # Create unique key prefix based on alert ID and status
    key_prefix = f"{status}_{alert['id']}"
    
    severity_border = {
        'critical': '#ef4444',
        'warning':  '#f59e0b',
        'normal':   '#94a3b8',
    }
    severity_bg = {
        'critical': 'rgba(239,68,68,0.12)',
        'warning':  'rgba(245,158,11,0.12)',
        'normal':   'rgba(148,163,184,0.08)',
    }

    with st.container():
        border_c = severity_border.get(alert['severity'], '#94a3b8')
        bg_c     = severity_bg.get(alert['severity'], 'rgba(148,163,184,0.08)')
        st.markdown(f"""
        <div style="padding: 14px 16px; border-left: 4px solid {border_c};
                    background: {bg_c}; margin-bottom: 10px; border-radius: 6px;">
            <strong style="color:#f1f5f9;">{alert['meter_id']}</strong>
            <span style="color:#cbd5e1;"> — {alert.get('title', 'Leak Detected')}</span>
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
                _btn_label = "Reassign" if alert['status'] == 'assigned' else "Assign to Team"
                if st.button(_btn_label, key=f"assign_{key_prefix}"):
                    st.session_state[f'assigning_{key_prefix}'] = True
                    st.rerun()
            
            if can_resolve_alerts() and alert['status'] == 'assigned':
                if st.button("Mark as Resolved", key=f"resolve_{key_prefix}"):
                    success, msg = alert_manager.resolve_alert(
                        alert['id'],
                        get_current_user_id()
                    )
                    if success:
                        st.success(msg)
                        st.cache_data.clear()
                        clear_alert_cache()
                        st.rerun()
                    else:
                        st.error(msg)
            elif can_resolve_alerts() and alert['status'] == 'new':
                st.caption("Assign to a team before resolving.")

        # Inline assignment form
        if st.session_state.get(f'assigning_{key_prefix}', False):
            show_inline_assignment_form(alert['id'], key_prefix)
        
        st.markdown("---")


def show_inline_assignment_form(alert_id: int, key_prefix: str):
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
            key=f"team_select_{key_prefix}"
        )
    
    with col2:
        if st.button("Assign", key=f"confirm_assign_{key_prefix}"):
            team_id = team_options[selected_team]
            success, msg = alert_manager.assign_alert_to_team(
                alert_id,
                team_id,
                get_current_user_id()
            )
            if success:
                st.success(msg)
                st.session_state.pop(f'assigning_{key_prefix}', None)
                st.cache_data.clear()
                clear_alert_cache()
                st.rerun()
            else:
                st.error(msg)
        
        if st.button("Cancel", key=f"cancel_assign_{key_prefix}"):
            st.session_state.pop(f'assigning_{key_prefix}', None)
            st.rerun()





def show_field_technician_alerts(user_id: str):
    """Display alerts for Field Technician - only their team's alerts"""
    
    # Get user's teams
    teams_df = db_manager.get_teams_by_user(user_id)
    
    if teams_df.empty:
        st.info("You are not assigned to any teams yet. Contact your supervisor to be added to a team.")
        return
    
    # Display team membership
    st.markdown("### Your Teams")
    team_names = teams_df['name'].tolist()
    st.write(f"**Member of:** {', '.join(team_names)}")
    
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
        status_filter = st.selectbox(
            "Status",
            ["All", "new", "assigned", "resolved"],
            format_func=str.title
        )
    
    with col_filter3:
        time_filter = st.selectbox(
            "Time Range",
            [("Last 24 hours", 24), ("Last 48 hours", 48), ("Last 7 days", 168)],
            format_func=lambda x: x[0]
        )
        hours = time_filter[1]
    
    # Get alerts for user's teams
    alerts_df = db_manager.get_alerts_for_user_teams(
        user_id=user_id,
        status=None if status_filter == "All" else status_filter,
        hours=hours
    )
    
    # Apply severity filter
    if severity_filter != "All":
        alerts_df = alerts_df[alerts_df['severity'] == severity_filter]
    
    if alerts_df.empty:
        st.info("No alerts found for your teams with the selected filters.")
        return
    
    # Display summary metrics
    st.markdown("---")
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        total_alerts = len(alerts_df)
        st.metric("Total Alerts", total_alerts)
    
    with col2:
        new_count = len(alerts_df[alerts_df['status'] == 'new'])
        st.metric("New", new_count)
    
    with col3:
        assigned_count = len(alerts_df[alerts_df['status'] == 'assigned'])
        st.metric("Assigned", assigned_count)
    
    with col4:
        resolved_count = len(alerts_df[alerts_df['status'] == 'resolved'])
        st.metric("Resolved", resolved_count)
    
    # Display alerts grouped by status
    st.markdown("---")
    st.markdown("### Alerts")
    
    # Group by status
    for status in ['new', 'assigned', 'resolved']:
        status_alerts = alerts_df[alerts_df['status'] == status]
        if not status_alerts.empty:
            st.subheader(f"{status.upper()} ({len(status_alerts)})")
            
            for idx, alert in status_alerts.iterrows():
                show_field_tech_alert_card(alert, status)


def show_field_tech_alert_card(alert: pd.Series, status: str):
    """Display alert card for Field Technician (read-only)"""
    
    # Create unique key prefix
    key_prefix = f"ft_{status}_{alert['id']}"
    
    severity_border = {
        'critical': '#ef4444',
        'warning':  '#f59e0b',
        'normal':   '#94a3b8',
    }
    severity_bg = {
        'critical': 'rgba(239,68,68,0.12)',
        'warning':  'rgba(245,158,11,0.12)',
        'normal':   'rgba(148,163,184,0.08)',
    }

    with st.container():
        border_c = severity_border.get(alert['severity'], '#94a3b8')
        bg_c     = severity_bg.get(alert['severity'], 'rgba(148,163,184,0.08)')
        st.markdown(f"""
        <div style="padding: 14px 16px; border-left: 4px solid {border_c};
                    background: {bg_c}; margin-bottom: 10px; border-radius: 6px;">
            <strong style="color:#f1f5f9;">{alert['meter_id']}</strong>
            <span style="color:#cbd5e1;"> — {alert.get('title', 'Leak Detected')}</span>
        </div>
        """, unsafe_allow_html=True)

        col1, col2 = st.columns([3, 1])

        with col1:
            st.write(f"**Status:** {alert['status'].upper()}")
            st.write(f"**Severity:** {alert['severity'].upper()}")
            st.write(f"**Zone:** {alert.get('zone_id', 'N/A')}")
            st.write(f"**Assigned Team:** {alert.get('team_name', 'N/A')}")
            st.write(f"**Created:** {alert['created_at'].strftime('%Y-%m-%d %H:%M') if pd.notna(alert['created_at']) else 'N/A'}")
            
            if alert['status'] == 'resolved' and pd.notna(alert.get('resolved_at')):
                st.write(f"**Resolved:** {alert['resolved_at'].strftime('%Y-%m-%d %H:%M')}")
                if alert.get('resolved_by_name'):
                    st.write(f"**Resolved By:** {alert['resolved_by_name']}")
            
            # Show message if available
            if alert.get('message'):
                st.write(f"**Details:** {alert['message']}")
        
        with col2:
            # Status badge
            if status == 'new':
                st.info("NEW")
            elif status == 'assigned':
                st.warning("ASSIGNED")
            else:
                st.success("RESOLVED")
        
        st.markdown("---")
