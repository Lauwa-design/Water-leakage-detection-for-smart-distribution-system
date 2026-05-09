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


def show_teams():
    """Main team management page"""
    st.title("Team Management")
    
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
    """Display all teams with management options (NRW Officer view)"""
    st.subheader("All Teams")
    
    teams_df = db_manager.get_all_teams()
    
    if teams_df.empty:
        st.info("No teams have been created yet.")
        return
    
    # Filter active teams
    active_teams = teams_df[teams_df['status'] == 'active']
    
    if active_teams.empty:
        st.warning("No active teams found.")
        return
    
    st.write(f"**Total Active Teams:** {len(active_teams)}")
    
    # Display teams as cards
    for idx, team in active_teams.iterrows():
        with st.expander(f"{team['name']} ({team['member_count']} members)", expanded=False):
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.write(f"**Description:** {team['description'] or 'No description'}")
                st.write(f"**Created:** {team['created_at'].strftime('%Y-%m-%d %H:%M')}")
                st.write(f"**Status:** {team['status'].upper()}")
                
                # Get team details with members
                team_details = db_manager.get_team(team['id'])
                if team_details and team_details['members']:
                    st.write("**Team Members:**")
                    for member in team_details['members']:
                        st.write(f"  • {member['name']} ({member['user_id']})")
                else:
                    st.write("**Team Members:** None")
            
            with col2:
                # Management buttons (NRW Officer only)
                if has_permission(Permissions.TEAM_UPDATE):
                    if st.button(f"Edit", key=f"edit_{team['id']}"):
                        st.session_state[f'editing_team_{team["id"]}'] = True
                        st.rerun()
                
                if has_permission(Permissions.TEAM_DELETE):
                    if st.button(f"Delete", key=f"delete_{team['id']}"):
                        st.session_state[f'confirm_delete_{team["id"]}'] = True
                        st.rerun()
            
            # Edit form (inline)
            if st.session_state.get(f'editing_team_{team["id"]}', False):
                show_edit_team_form(team['id'])
            
            # Delete confirmation
            if st.session_state.get(f'confirm_delete_{team["id"]}', False):
                st.warning(f"Are you sure you want to delete team **{team['name']}**?")
                col_yes, col_no = st.columns(2)
                with col_yes:
                    if st.button("Yes, Delete", key=f"confirm_yes_{team['id']}"):
                        success, msg = db_manager.delete_team(team['id'], get_current_user_id())
                        if success:
                            st.success(msg)
                            st.session_state.pop(f'confirm_delete_{team["id"]}', None)
                            st.rerun()
                        else:
                            st.error(msg)
                with col_no:
                    if st.button("Cancel", key=f"confirm_no_{team['id']}"):
                        st.session_state.pop(f'confirm_delete_{team["id"]}', None)
                        st.rerun()


def show_my_teams(user_id: str):
    """Display teams the current user belongs to (Field Technician view)"""
    st.subheader("My Teams")
    
    teams_df = db_manager.get_teams_by_user(user_id)
    
    if teams_df.empty:
        st.info("You are not assigned to any teams yet.")
        return
    
    st.write(f"**You are a member of {len(teams_df)} team(s)**")
    
    # Display teams as cards
    for idx, team in teams_df.iterrows():
        with st.expander(f"{team['name']} ({team['member_count']} members)", expanded=False):
            st.write(f"**Description:** {team['description'] or 'No description'}")
            st.write(f"**Created:** {team['created_at'].strftime('%Y-%m-%d %H:%M')}")
            
            # Get team details with members
            team_details = db_manager.get_team(team['id'])
            if team_details and team_details['members']:
                st.write("**Team Members:**")
                for member in team_details['members']:
                    st.write(f"  • {member['name']} ({member['user_id']})")
            
            # Show assigned alerts
            alerts_df = db_manager.get_alerts_by_team(team['id'], hours=168)  # Last 7 days
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
        
        # Get available Field Technicians
        technicians_df = db_manager.get_field_technicians()
        
        if technicians_df.empty:
            st.error("No Field Technicians available. Please create Field Technician users first.")
            st.form_submit_button("Create Team", disabled=True)
            return
        
        # Create options for multiselect
        tech_options = {f"{row['name']} ({row['user_id']})": row['user_id'] 
                       for _, row in technicians_df.iterrows()}
        
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
        
        # Get available Field Technicians
        technicians_df = db_manager.get_field_technicians()
        
        if technicians_df.empty:
            st.error("No Field Technicians available")
            st.form_submit_button("Update Team", disabled=True)
            return
        
        # Create options for multiselect
        tech_options = {f"{row['name']} ({row['user_id']})": row['user_id'] 
                       for _, row in technicians_df.iterrows()}
        
        # Pre-select current members
        current_member_ids = [m['user_id'] for m in team['members']]
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
