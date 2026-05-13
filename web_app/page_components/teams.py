"""Team Management Page - THIWASCO Leak Detection System"""

import streamlit as st
import pandas as pd
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.mysql_database_manager import db_manager
from backend.rbac import (
    has_permission,
    Permissions,
    is_nrw_officer,
    get_current_user_id,
    get_current_user_role,
    show_permission_denied,
    can_manage_teams
)
from page_components.ui import page_header


def show_teams():
    """Main team management page"""
    page_header("Teams", "Manage field teams and assign leak response tasks.", eyebrow="Team Management")
    
    current_role = get_current_user_role()
    current_user_id = get_current_user_id()
    
    # Check if user has permission to view teams
    if not has_permission(Permissions.TEAM_READ):
        show_permission_denied("view teams")
        return
    
    # Create tabs for different views
    if is_nrw_officer():
        tab1, tab2, tab3 = st.tabs(["All Teams", "Create Team", "Team Workload"])
    else:
        tab1, tab2 = st.tabs(["My Teams", "Team Workload"])
    
    # Tab 1: View Teams
    with tab1:
        if is_nrw_officer():
            show_all_teams()
        else:
            show_my_teams(current_user_id)
    
    # Tab 2: Create Team (NRW Officer only) or Team Workload (others)
    with tab2:
        if is_nrw_officer():
            show_create_team_form()
        else:
            show_team_workload()
    
    # Tab 3: Team Workload (NRW Officer only)
    if is_nrw_officer():
        with tab3:
            show_team_workload()


def show_all_teams():
    """Display all teams with inline member lists (NRW Officer view)."""
    teams_df = db_manager.get_all_teams()

    if teams_df.empty:
        st.info("No teams have been created yet.")
        return

    active_teams = teams_df[teams_df['status'] == 'active'].copy()
    if active_teams.empty:
        st.warning("No active teams found.")
        return

    st.markdown(
        f"<p style='font-size:0.82rem;color:#94a3b8;margin:0 0 1rem;'>"
        f"{len(active_teams)} active team{'s' if len(active_teams) != 1 else ''}</p>",
        unsafe_allow_html=True,
    )

    for _, team_row in active_teams.iterrows():
        team_id   = int(team_row['id'])
        team_name = team_row['name']
        created   = team_row['created_at'].strftime('%Y-%m-%d') if pd.notna(team_row['created_at']) else '—'
        desc      = team_row.get('description') or ''

        # Fetch full details (with members) once per team
        details = db_manager.get_team(team_id)
        members = details['members'] if details and details.get('members') else []

        # Build member pills HTML
        if members:
            pills_html = " ".join(
                f"<span style='display:inline-flex;align-items:center;gap:5px;"
                f"background:rgba(34,197,94,0.08);border:1px solid rgba(34,197,94,0.22);"
                f"border-radius:5px;padding:3px 10px;font-size:0.75rem;color:#94a3b8;margin:2px;'>"
                f"<span style='color:#22c55e;font-weight:700;font-size:0.7rem;'>FT</span>"
                f"{m['name']}"
                f"<span style='color:#475569;font-size:0.68rem;'>· {m['user_id']}</span>"
                f"</span>"
                for m in members
            )
        else:
            pills_html = "<span style='color:#475569;font-size:0.78rem;font-style:italic;'>No members assigned</span>"

        desc_row = f"<p style='font-size:0.78rem;color:#64748b;margin:0 0 8px;'>{desc}</p>" if desc else ""
        member_label = 'members' if len(members) != 1 else 'member'
        st.html(
            f"<div style='background:#0d1526;border:1px solid rgba(255,255,255,0.07);"
            f"border-radius:10px;padding:14px 18px 12px;margin-bottom:10px;'>"
            f"<div style='display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:6px;'>"
            f"<div>"
            f"<span style='font-size:1rem;font-weight:700;color:#e2e8f0;'>{team_name}</span>"
            f"<span style='margin-left:10px;font-size:0.68rem;font-weight:700;"
            f"background:rgba(34,197,94,0.10);color:#22c55e;"
            f"border:1px solid rgba(34,197,94,0.35);border-radius:4px;padding:1px 8px;"
            f"box-shadow:0 0 8px 1px rgba(34,197,94,0.50),0 0 18px 2px rgba(34,197,94,0.22);'>"
            f"ACTIVE</span>"
            f"</div>"
            f"<span style='font-size:0.7rem;color:#475569;'>Created {created}"
            f"&nbsp;&middot;&nbsp; {len(members)} {member_label}</span>"
            f"</div>"
            f"{desc_row}"
            f"<div style='margin-top:6px;'>{pills_html}</div>"
            f"</div>"
        )

        # Edit / Delete buttons inline under the card
        if has_permission(Permissions.TEAM_UPDATE) or has_permission(Permissions.TEAM_DELETE):
            col_edit, col_del, col_spacer = st.columns([1, 1, 6])
            with col_edit:
                if has_permission(Permissions.TEAM_UPDATE):
                    if st.button("Edit", key=f"edit_{team_id}"):
                        st.session_state[f'editing_team_{team_id}'] = True
                        st.rerun()
            with col_del:
                if has_permission(Permissions.TEAM_DELETE):
                    if st.button("Delete", key=f"delete_{team_id}"):
                        st.session_state[f'confirm_delete_{team_id}'] = True
                        st.rerun()

        if st.session_state.get(f'editing_team_{team_id}', False):
            show_edit_team_form(team_id)

        if st.session_state.get(f'confirm_delete_{team_id}', False):
            st.warning(f"Are you sure you want to delete **{team_name}**?")
            cy, cn = st.columns(2)
            with cy:
                if st.button("Yes, Delete", key=f"confirm_yes_{team_id}"):
                    success, msg = db_manager.delete_team(team_id, get_current_user_id())
                    if success:
                        st.success(msg)
                        st.session_state.pop(f'confirm_delete_{team_id}', None)
                        st.rerun()
                    else:
                        st.error(msg)
            with cn:
                if st.button("Cancel", key=f"confirm_no_{team_id}"):
                    st.session_state.pop(f'confirm_delete_{team_id}', None)
                    st.rerun()

        st.markdown("<div style='margin-bottom:4px;'></div>", unsafe_allow_html=True)


def show_my_teams(user_id: str):
    """Display teams the current user belongs to (Field Technician view)"""
    st.subheader("My Teams")

    teams_df = db_manager.get_teams_by_user(user_id)

    if teams_df.empty:
        st.info("You are not assigned to any teams yet.")
        return

    st.write(f"**You are a member of {len(teams_df)} team(s)**")

    display_df = teams_df[['name', 'member_count']].copy()
    display_df = display_df.rename(columns={'name': 'Team Name', 'member_count': 'Members'})
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.markdown("---")
    team_options = [f"{row['name']}" for _, row in teams_df.iterrows()]
    selected_name = st.selectbox("View team details", team_options, key="select_my_team")
    team = teams_df[teams_df['name'] == selected_name].iloc[0]

    st.write(f"**Description:** {team['description'] or 'No description'}")
    st.write(f"**Created:** {team['created_at'].strftime('%Y-%m-%d %H:%M')}")

    team_details = db_manager.get_team(int(team['id']))
    if team_details and team_details['members']:
        st.write("**Team Members:**")
        for member in team_details['members']:
            st.write(f"  • {member['name']} ({member['user_id']})")

    alerts_df = db_manager.get_alerts_by_team(int(team['id']), hours=168)
    if not alerts_df.empty:
        active_alerts = alerts_df[alerts_df['status'] != 'resolved']
        st.write(f"**Active Alerts:** {len(active_alerts)}")
        st.write(f"**Total Alerts (7 days):** {len(alerts_df)}")


def show_create_team_form():
    """Display form to create a new team (NRW Officer only)"""
    st.subheader("Create New Team")
    
    if not has_permission(Permissions.TEAM_CREATE):
        show_permission_denied("create teams")
        return
    
    with st.form("create_team_form"):
        team_name = st.text_input("Team Name *", placeholder="e.g., Thika Central Response Team")
        team_description = st.text_area("Description", placeholder="Brief description of team responsibilities")
        
        # Get available Field Technicians — only those not already in a team
        technicians_df = db_manager.get_field_technicians()

        if technicians_df.empty:
            st.error("No Field Technicians available. Please create Field Technician users first.")
            st.form_submit_button("Create Team", disabled=True)
            return

        available = technicians_df[technicians_df['current_team'].isna()]
        assigned_count = len(technicians_df) - len(available)
        if assigned_count:
            st.info(f"{assigned_count} technician(s) are already in a team and cannot be added to a new one.")
        if available.empty:
            st.error("All Field Technicians are currently assigned to teams. A technician can only be in one team.")
            st.form_submit_button("Create Team", disabled=True)
            return

        # Create options for multiselect
        tech_options = {f"{row['name']} ({row['user_id']})": row['user_id']
                        for _, row in available.iterrows()}

        st.write("**Select Team Members (2-6 Field Technicians) ***")
        selected_members = st.multiselect(
            "Team Members",
            options=list(tech_options.keys()),
            help="Select between 2 and 6 Field Technicians"
        )
        
        submitted = st.form_submit_button("Create Team")
        
        if submitted:
            if not team_name.strip():
                st.error("Team name is required")
            elif len(selected_members) < 2:
                st.error("Team must have at least 2 members")
            elif len(selected_members) > 6:
                st.error("Team cannot have more than 6 members")
            else:
                # Convert selected names to user IDs
                member_ids = [tech_options[name] for name in selected_members]
                
                # Create team
                success, msg, team_id = db_manager.create_team(
                    name=team_name.strip(),
                    description=team_description.strip(),
                    created_by=get_current_user_id(),
                    member_ids=member_ids
                )
                
                if success:
                    st.success(f"{msg}")
                    st.rerun()
                else:
                    st.error(f"{msg}")


def show_edit_team_form(team_id: int):
    """Display inline form to edit a team"""
    st.markdown("---")
    st.subheader("Edit Team")
    
    if not has_permission(Permissions.TEAM_UPDATE):
        show_permission_denied("edit teams")
        return
    
    # Get current team details
    team = db_manager.get_team(team_id)
    if not team:
        st.error("Team not found")
        return
    
    with st.form(f"edit_team_form_{team_id}"):
        team_name = st.text_input("Team Name *", value=team['name'])
        team_description = st.text_area("Description", value=team['description'] or "")
        
        # Get available Field Technicians:
        # show current team members + technicians not in any active team
        technicians_df = db_manager.get_field_technicians()

        if technicians_df.empty:
            st.error("No Field Technicians available")
            st.form_submit_button("Update Team", disabled=True)
            return

        current_member_ids = [m['user_id'] for m in team['members']]
        available = technicians_df[
            technicians_df['current_team'].isna() |
            technicians_df['user_id'].isin(current_member_ids)
        ]

        # Create options for multiselect
        tech_options = {f"{row['name']} ({row['user_id']})": row['user_id']
                        for _, row in available.iterrows()}

        default_selection = [name for name, uid in tech_options.items() if uid in current_member_ids]

        st.write("**Select Team Members (2-6 Field Technicians) ***")
        selected_members = st.multiselect(
            "Team Members",
            options=list(tech_options.keys()),
            default=default_selection,
            help="Select between 2 and 6 Field Technicians"
        )
        
        col1, col2 = st.columns(2)
        with col1:
            submitted = st.form_submit_button("Update Team")
        with col2:
            cancelled = st.form_submit_button("Cancel")
        
        if cancelled:
            st.session_state.pop(f'editing_team_{team_id}', None)
            st.rerun()
        
        if submitted:
            if not team_name.strip():
                st.error("Team name is required")
            elif len(selected_members) < 2:
                st.error("Team must have at least 2 members")
            elif len(selected_members) > 6:
                st.error("Team cannot have more than 6 members")
            else:
                # Convert selected names to user IDs
                member_ids = [tech_options[name] for name in selected_members]
                
                # Update team
                success, msg = db_manager.update_team(
                    team_id=team_id,
                    name=team_name.strip(),
                    description=team_description.strip(),
                    member_ids=member_ids,
                    updated_by=get_current_user_id()
                )
                
                if success:
                    st.success(f"{msg}")
                    st.session_state.pop(f'editing_team_{team_id}', None)
                    st.rerun()
                else:
                    st.error(f"{msg}")


def show_team_workload():
    """Display team workload statistics"""
    st.subheader("Team Workload Overview")
    
    workload_df = db_manager.get_team_workload()
    
    if workload_df.empty:
        st.info("No teams with workload data available.")
        return
    
    # Display as a table
    st.dataframe(
        workload_df[['name', 'member_count', 'active_alerts', 'resolved_alerts']].rename(columns={
            'name': 'Team Name',
            'member_count': 'Members',
            'active_alerts': 'Active Alerts',
            'resolved_alerts': 'Resolved Alerts'
        }),
        use_container_width=True,
        hide_index=True
    )
    
    # Summary metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Total Teams", len(workload_df))
    with col2:
        st.metric("Total Active Alerts", workload_df['active_alerts'].sum())
    with col3:
        st.metric("Total Resolved Alerts", workload_df['resolved_alerts'].sum())
