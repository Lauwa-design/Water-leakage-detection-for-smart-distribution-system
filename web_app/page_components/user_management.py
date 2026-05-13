"""User Management Page - THIWASCO Leak Detection System"""

import streamlit as st
import pandas as pd
import bcrypt
from datetime import datetime
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.mysql_database_manager import db_manager
from page_components.ui import show_glowing_table
from backend.rbac import (
    has_permission,
    Permissions,
    is_system_admin,
    get_current_user_id,
    show_permission_denied,
    Roles
)


def show_user_management():
    """Main user management page (System Administrator only)"""
    st.title("User Management")
    
    # Check permissions
    if not is_system_admin():
        show_permission_denied("manage users")
        st.info("User management is restricted to System Administrators.")
        return
    
    # Create tabs
    tab1, tab2, tab3 = st.tabs(["Active Users", "Deactivated Users", "Create User"])
    
    with tab1:
        show_users_by_status("active")
    
    with tab2:
        show_users_by_status("inactive")
    
    with tab3:
        show_create_user_form()


def show_users_by_status(status: str):
    """Display users filtered by status (active or inactive)"""
    status_label = "Active" if status == "active" else "Deactivated"
    st.subheader(f"{status_label} Users")

    users_df = db_manager.get_all_users()

    if users_df.empty:
        st.info("No users found.")
        return

    filtered_df = users_df[users_df['status'] == status].copy()

    if filtered_df.empty:
        st.info(f"No {status_label.lower()} users found.")
        return

    col1, col2 = st.columns(2)
    with col1:
        role_filter = st.selectbox(
            "Filter by Role",
            ["All"] + Roles.ALL_ROLES,
            key=f"role_filter_{status}"
        )

    if role_filter != "All":
        filtered_df = filtered_df[filtered_df['role'] == role_filter]

    st.write(f"**Total {status_label} Users:** {len(filtered_df)}")

    # Display as a table
    display_df = filtered_df[['user_id', 'name', 'role', 'email', 'status']].copy()
    display_df['created_at'] = filtered_df['created_at'].apply(
        lambda x: x.strftime('%Y-%m-%d') if pd.notna(x) else 'N/A'
    )
    display_df = display_df.rename(columns={
        'user_id': 'User ID', 'name': 'Name', 'role': 'Role',
        'email': 'Email', 'status': 'Status', 'created_at': 'Created'
    })
    show_glowing_table(display_df)

    st.markdown("---")
    st.subheader("Manage User")

    user_options = [f"{row['name']} ({row['user_id']})" for _, row in filtered_df.iterrows()]
    if not user_options:
        return

    selected_label = st.selectbox("Select user", user_options, key=f"select_user_{status}")
    selected_id = selected_label.split("(")[-1].rstrip(")")
    user = filtered_df[filtered_df['user_id'] == selected_id].iloc[0]

    col_info, col_actions = st.columns([3, 1])
    with col_info:
        st.write(f"**User ID:** {user['user_id']}")
        st.write(f"**Email:** {user['email']}")
        st.write(f"**Role:** {user['role']}")
        st.write(f"**Status:** {user['status'].upper()}")
        st.write(f"**Created:** {user['created_at'].strftime('%Y-%m-%d %H:%M') if pd.notna(user['created_at']) else 'N/A'}")
        if pd.notna(user['last_login']):
            st.write(f"**Last Login:** {user['last_login'].strftime('%Y-%m-%d %H:%M')}")

    with col_actions:
        if st.button("Edit", key=f"edit_user_{status}_{user['user_id']}"):
            st.session_state[f'editing_user_{user["user_id"]}'] = True
            st.rerun()

        if st.button("Change Role", key=f"role_user_{status}_{user['user_id']}"):
            st.session_state[f'changing_role_{user["user_id"]}'] = True
            st.rerun()

        if status == 'active':
            if st.button("Deactivate", key=f"delete_user_{status}_{user['user_id']}"):
                st.session_state[f'confirm_delete_{user["user_id"]}'] = True
                st.rerun()
        else:
            if st.button("Reactivate", key=f"reactivate_user_{status}_{user['user_id']}"):
                st.session_state[f'confirm_reactivate_{user["user_id"]}'] = True
                st.rerun()

    if st.session_state.get(f'editing_user_{user["user_id"]}', False):
        show_edit_user_form(user)

    if st.session_state.get(f'changing_role_{user["user_id"]}', False):
        show_change_role_form(user)

    if st.session_state.get(f'confirm_delete_{user["user_id"]}', False):
        st.warning(f"Are you sure you want to deactivate user **{user['name']}**?")
        col_yes, col_no = st.columns(2)
        with col_yes:
            if st.button("Yes, Deactivate", key=f"confirm_yes_{status}_{user['user_id']}"):
                success, msg = db_manager.delete_user(user['user_id'])
                if success:
                    st.success(msg)
                    st.session_state.pop(f'confirm_delete_{user["user_id"]}', None)
                    st.rerun()
                else:
                    st.error(msg)
        with col_no:
            if st.button("Cancel", key=f"confirm_no_{status}_{user['user_id']}"):
                st.session_state.pop(f'confirm_delete_{user["user_id"]}', None)
                st.rerun()

    if st.session_state.get(f'confirm_reactivate_{user["user_id"]}', False):
        st.info(f"Reactivate user **{user['name']}**?")
        col_yes, col_no = st.columns(2)
        with col_yes:
            if st.button("Yes, Reactivate", key=f"confirm_reactivate_yes_{status}_{user['user_id']}"):
                success, msg = db_manager.update_user(
                    user_id=user['user_id'],
                    email=user['email'],
                    name=user['name'],
                    role=user['role'],
                    status='active'
                )
                if success:
                    st.success(f"User '{user['name']}' reactivated successfully")
                    st.session_state.pop(f'confirm_reactivate_{user["user_id"]}', None)
                    st.rerun()
                else:
                    st.error(msg)
        with col_no:
            if st.button("Cancel", key=f"confirm_reactivate_no_{status}_{user['user_id']}"):
                st.session_state.pop(f'confirm_reactivate_{user["user_id"]}', None)
                st.rerun()


def show_all_users():
    """Display all users with management options - DEPRECATED, use show_users_by_status instead"""
    st.subheader("All Users")
    
    users_df = db_manager.get_all_users()
    
    if users_df.empty:
        st.info("No users found.")
        return
    
    # Filter options
    col1, col2 = st.columns(2)
    with col1:
        role_filter = st.selectbox(
            "Filter by Role",
            ["All"] + Roles.ALL_ROLES
        )
    with col2:
        status_filter = st.selectbox(
            "Filter by Status",
            ["All", "active", "inactive"]
        )
    
    # Apply filters
    filtered_df = users_df.copy()
    if role_filter != "All":
        filtered_df = filtered_df[filtered_df['role'] == role_filter]
    if status_filter != "All":
        filtered_df = filtered_df[filtered_df['status'] == status_filter]
    
    st.write(f"**Total Users:** {len(filtered_df)}")
    
    # Display users as cards
    for idx, user in filtered_df.iterrows():
        with st.expander(f"{user['name']} ({user['user_id']}) - {user['role']}", expanded=False):
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.write(f"**User ID:** {user['user_id']}")
                st.write(f"**Email:** {user['email']}")
                st.write(f"**Role:** {user['role']}")
                st.write(f"**Status:** {user['status'].upper()}")
                st.write(f"**Created:** {user['created_at'].strftime('%Y-%m-%d %H:%M') if pd.notna(user['created_at']) else 'N/A'}")
                if pd.notna(user['last_login']):
                    st.write(f"**Last Login:** {user['last_login'].strftime('%Y-%m-%d %H:%M')}")
            
            with col2:
                # Management buttons
                if st.button("Edit", key=f"edit_user_{user['user_id']}"):
                    st.session_state[f'editing_user_{user["user_id"]}'] = True
                    st.rerun()
                
                if st.button("Change Role", key=f"role_user_{user['user_id']}"):
                    st.session_state[f'changing_role_{user["user_id"]}'] = True
                    st.rerun()
                
                if user['status'] == 'active':
                    if st.button("Deactivate", key=f"delete_user_{user['user_id']}"):
                        st.session_state[f'confirm_delete_{user["user_id"]}'] = True
                        st.rerun()
            
            # Edit form (inline)
            if st.session_state.get(f'editing_user_{user["user_id"]}', False):
                show_edit_user_form(user)
            
            # Change role form (inline)
            if st.session_state.get(f'changing_role_{user["user_id"]}', False):
                show_change_role_form(user)
            
            # Delete confirmation
            if st.session_state.get(f'confirm_delete_{user["user_id"]}', False):
                st.warning(f"Are you sure you want to deactivate user **{user['name']}**?")
                col_yes, col_no = st.columns(2)
                with col_yes:
                    if st.button("Yes, Deactivate", key=f"confirm_yes_{user['user_id']}"):
                        success, msg = db_manager.delete_user(user['user_id'])
                        if success:
                            st.success(msg)
                            st.session_state.pop(f'confirm_delete_{user["user_id"]}', None)
                            st.rerun()
                        else:
                            st.error(msg)
                with col_no:
                    if st.button("Cancel", key=f"confirm_no_{user['user_id']}"):
                        st.session_state.pop(f'confirm_delete_{user["user_id"]}', None)
                        st.rerun()


def show_create_user_form():
    """Display form to create a new user"""
    st.subheader("Create New User")
    
    with st.form("create_user_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            user_id = st.text_input("User ID *", placeholder="e.g., THW-005", help="Unique identifier for the user")
            name = st.text_input("Full Name *", placeholder="e.g., John Doe")
            email = st.text_input("Email *", placeholder="e.g., john.doe@thiwasco.co.ke")
        
        with col2:
            username = st.text_input("Username *", placeholder="e.g., thiwasco")
            role = st.selectbox("Role *", Roles.ALL_ROLES)
            password = st.text_input("Password *", type="password", help="Default password for the user")
        
        submitted = st.form_submit_button("Create User")
        
        if submitted:
            # Validation
            if not all([user_id.strip(), name.strip(), email.strip(), username.strip(), password.strip()]):
                st.error("All fields are required")
            elif '@' not in email:
                st.error("Invalid email format")
            elif len(password) < 8:
                st.error("Password must be at least 8 characters")
            else:
                # Hash password
                password_hash = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')
                
                # Create user
                success, msg = db_manager.create_user(
                    user_id=user_id.strip().upper(),
                    username=username.strip(),
                    email=email.strip(),
                    name=name.strip(),
                    role=role,
                    password_hash=password_hash
                )
                
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)


def show_edit_user_form(user: pd.Series):
    """Display inline form to edit a user"""
    st.markdown("---")
    st.subheader("Edit User")
    
    with st.form(f"edit_user_form_{user['user_id']}"):
        col1, col2 = st.columns(2)
        
        with col1:
            email = st.text_input("Email *", value=user['email'])
            name = st.text_input("Full Name *", value=user['name'])
        
        with col2:
            role = st.selectbox("Role *", Roles.ALL_ROLES, index=Roles.ALL_ROLES.index(user['role']))
            status = st.selectbox("Status *", ["active", "inactive"], index=0 if user['status'] == 'active' else 1)
        
        col_submit, col_cancel = st.columns(2)
        with col_submit:
            submitted = st.form_submit_button("Update User")
        with col_cancel:
            cancelled = st.form_submit_button("Cancel")
        
        if cancelled:
            st.session_state.pop(f'editing_user_{user["user_id"]}', None)
            st.rerun()
        
        if submitted:
            # Validation
            if not all([email.strip(), name.strip()]):
                st.error("Email and name are required")
            elif '@' not in email:
                st.error("Invalid email format")
            else:
                # Update user
                success, msg = db_manager.update_user(
                    user_id=user['user_id'],
                    email=email.strip(),
                    name=name.strip(),
                    role=role,
                    status=status
                )
                
                if success:
                    st.success(msg)
                    st.session_state.pop(f'editing_user_{user["user_id"]}', None)
                    st.rerun()
                else:
                    st.error(msg)


def show_change_role_form(user: pd.Series):
    """Display inline form to change user role"""
    st.markdown("---")
    st.subheader("Change User Role")
    
    with st.form(f"change_role_form_{user['user_id']}"):
        st.write(f"**Current Role:** {user['role']}")
        
        new_role = st.selectbox(
            "New Role *",
            Roles.ALL_ROLES,
            index=Roles.ALL_ROLES.index(user['role'])
        )
        
        st.info("Changing a user's role will affect their permissions immediately.")
        
        col_submit, col_cancel = st.columns(2)
        with col_submit:
            submitted = st.form_submit_button("Change Role")
        with col_cancel:
            cancelled = st.form_submit_button("Cancel")
        
        if cancelled:
            st.session_state.pop(f'changing_role_{user["user_id"]}', None)
            st.rerun()
        
        if submitted:
            if new_role == user['role']:
                st.warning("New role is the same as current role")
            else:
                # Update role
                success, msg = db_manager.update_user_role(
                    user_id=user['user_id'],
                    new_role=new_role,
                    updated_by=get_current_user_id()
                )
                
                if success:
                    st.success(msg)
                    st.session_state.pop(f'changing_role_{user["user_id"]}', None)
                    st.rerun()
                else:
                    st.error(msg)
