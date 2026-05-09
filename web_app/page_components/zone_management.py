"""Zone Management Page - THIWASCO Leak Detection System"""

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
    is_system_admin,
    show_permission_denied
)


def show_zone_management():
    """Main zone management page (System Administrator only)"""
    st.title("Zone Management")
    
    # Check permissions
    if not is_system_admin():
        show_permission_denied("manage zones")
        st.info("Zone management is restricted to System Administrators.")
        return
    
    # Create tabs
    tab1, tab2 = st.tabs(["All Zones", "Create Zone"])
    
    with tab1:
        show_all_zones()
    
    with tab2:
        show_create_zone_form()


def show_all_zones():
    """Display all zones with management options"""
    st.subheader("All Zones")
    
    zones_df = db_manager.get_all_zones()
    
    if zones_df.empty:
        st.info("No zones found.")
        return
    
    # Filter options
    col1, col2, col3 = st.columns(3)
    
    with col1:
        region_filter = st.selectbox(
            "Filter by Region",
            ["All"] + sorted(zones_df['region'].unique().tolist())
        )
    
    with col2:
        type_filter = st.selectbox(
            "Filter by Type",
            ["All", "residential", "commercial", "industrial", "mixed", "central", "institutional"]
        )
    
    with col3:
        status_filter = st.selectbox(
            "Filter by Status",
            ["All", "active", "inactive"]
        )
    
    # Apply filters
    filtered_df = zones_df.copy()
    if region_filter != "All":
        filtered_df = filtered_df[filtered_df['region'] == region_filter]
    if type_filter != "All":
        filtered_df = filtered_df[filtered_df['type'] == type_filter]
    if status_filter != "All":
        filtered_df = filtered_df[filtered_df['status'] == status_filter]
    
    st.write(f"**Total Zones:** {len(filtered_df)}")
    
    # Display zones as cards
    for idx, zone in filtered_df.iterrows():
        with st.expander(f"{zone['zone_id']} - {zone['name']}", expanded=False):
            col1, col2 = st.columns([3, 1])
            
            with col1:
                st.write(f"**Zone ID:** {zone['zone_id']}")
                st.write(f"**Name:** {zone['name']}")
                st.write(f"**Region:** {zone['region']}")
                st.write(f"**Type:** {zone['type']}")
                st.write(f"**Status:** {zone['status'].upper()}")
                st.write(f"**Estimated Connections:** {zone['estimated_connections']}")
                st.write(f"**Description:** {zone['description'] or 'N/A'}")
                if pd.notna(zone.get('created_at')):
                    st.write(f"**Created:** {zone['created_at'].strftime('%Y-%m-%d %H:%M')}")
                
                # Show meter count
                meters_df = db_manager.get_meters(zone['zone_id'])
                active_meters = len(meters_df[meters_df['status'] == 'active']) if not meters_df.empty else 0
                st.write(f"**Active Meters:** {active_meters}")
            
            with col2:
                # Management buttons
                if st.button("Edit", key=f"edit_zone_{zone['zone_id']}"):
                    st.session_state[f'editing_zone_{zone["zone_id"]}'] = True
                    st.rerun()
                
                if zone['status'] == 'active':
                    if st.button("Deactivate", key=f"delete_zone_{zone['zone_id']}"):
                        st.session_state[f'confirm_delete_{zone["zone_id"]}'] = True
                        st.rerun()
            
            # Edit form (inline)
            if st.session_state.get(f'editing_zone_{zone["zone_id"]}', False):
                show_edit_zone_form(zone)
            
            # Delete confirmation
            if st.session_state.get(f'confirm_delete_{zone["zone_id"]}', False):
                st.warning(f"Are you sure you want to deactivate zone **{zone['name']}**?")
                st.info("Note: Zone cannot be deleted if it has active meters.")
                col_yes, col_no = st.columns(2)
                with col_yes:
                    if st.button("Yes, Deactivate", key=f"confirm_yes_{zone['zone_id']}"):
                        success, msg = db_manager.delete_zone(zone['zone_id'])
                        if success:
                            st.success(msg)
                            st.session_state.pop(f'confirm_delete_{zone["zone_id"]}', None)
                            st.rerun()
                        else:
                            st.error(msg)
                with col_no:
                    if st.button("Cancel", key=f"confirm_no_{zone['zone_id']}"):
                        st.session_state.pop(f'confirm_delete_{zone["zone_id"]}', None)
                        st.rerun()


def show_create_zone_form():
    """Display form to create a new zone"""
    st.subheader("Create New Zone")
    
    with st.form("create_zone_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            zone_id = st.text_input("Zone ID *", placeholder="e.g., THK-NEW-001", help="Unique identifier for the zone")
            name = st.text_input("Zone Name *", placeholder="e.g., Thika New Area")
            region = st.text_input("Region *", placeholder="e.g., thika_new", help="Region identifier (lowercase, underscores)")
            zone_type = st.selectbox("Zone Type *", ["residential", "commercial", "industrial", "mixed", "central", "institutional"])
        
        with col2:
            status = st.selectbox("Status *", ["active", "inactive"])
            estimated_connections = st.number_input("Estimated Connections *", min_value=0, max_value=10000, value=100, step=10)
            description = st.text_area("Description", placeholder="Brief description of the zone")
        
        submitted = st.form_submit_button("Create Zone")
        
        if submitted:
            # Validation
            if not all([zone_id.strip(), name.strip(), region.strip()]):
                st.error("Zone ID, Name, and Region are required")
            else:
                # Create zone
                success, msg = db_manager.create_zone(
                    zone_id=zone_id.strip().upper(),
                    name=name.strip(),
                    region=region.strip().lower(),
                    zone_type=zone_type,
                    status=status,
                    estimated_connections=estimated_connections,
                    description=description.strip() if description else ""
                )
                
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)


def show_edit_zone_form(zone: pd.Series):
    """Display inline form to edit a zone"""
    st.markdown("---")
    st.subheader("Edit Zone")
    
    with st.form(f"edit_zone_form_{zone['zone_id']}"):
        col1, col2 = st.columns(2)
        
        with col1:
            name = st.text_input("Zone Name *", value=zone['name'])
            region = st.text_input("Region *", value=zone['region'])
            zone_type = st.selectbox(
                "Zone Type *",
                ["residential", "commercial", "industrial", "mixed", "central", "institutional"],
                index=["residential", "commercial", "industrial", "mixed", "central", "institutional"].index(zone['type'])
            )
        
        with col2:
            status = st.selectbox(
                "Status *",
                ["active", "inactive"],
                index=0 if zone['status'] == 'active' else 1
            )
            estimated_connections = st.number_input(
                "Estimated Connections *",
                min_value=0,
                max_value=10000,
                value=int(zone['estimated_connections']),
                step=10
            )
            description = st.text_area("Description", value=zone['description'] or "")
        
        col_submit, col_cancel = st.columns(2)
        with col_submit:
            submitted = st.form_submit_button("Update Zone")
        with col_cancel:
            cancelled = st.form_submit_button("Cancel")
        
        if cancelled:
            st.session_state.pop(f'editing_zone_{zone["zone_id"]}', None)
            st.rerun()
        
        if submitted:
            # Validation
            if not all([name.strip(), region.strip()]):
                st.error("Name and Region are required")
            else:
                # Update zone
                success, msg = db_manager.update_zone(
                    zone_id=zone['zone_id'],
                    name=name.strip(),
                    region=region.strip().lower(),
                    zone_type=zone_type,
                    status=status,
                    estimated_connections=estimated_connections,
                    description=description.strip() if description else ""
                )
                
                if success:
                    st.success(msg)
                    st.session_state.pop(f'editing_zone_{zone["zone_id"]}', None)
                    st.rerun()
                else:
                    st.error(msg)
