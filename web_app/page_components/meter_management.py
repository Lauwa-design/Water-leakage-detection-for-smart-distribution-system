"""Meter Management Page - THIWASCO Leak Detection System"""

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


def show_meter_management():
    """Main meter management page (System Administrator only)"""
    st.title("Meter Management")
    
    # Check permissions
    if not is_system_admin():
        show_permission_denied("manage meters")
        st.info("Meter management is restricted to System Administrators.")
        return
    
    # Create tabs
    tab1, tab2 = st.tabs(["All Meters", "Create Meter"])
    
    with tab1:
        show_all_meters()
    
    with tab2:
        show_create_meter_form()


def show_all_meters():
    """Display all meters with management options"""
    st.subheader("All Meters")
    
    meters_df = db_manager.get_all_meters()
    
    if meters_df.empty:
        st.info("No meters found.")
        return
    
    # Filter options
    col1, col2, col3 = st.columns(3)
    
    with col1:
        zones_df = db_manager.get_all_zones()
        zone_options = ["All Zones"]
        if not zones_df.empty:
            zone_options.extend(zones_df['zone_id'].tolist())
        zone_filter = st.selectbox("Filter by Zone", zone_options)
    
    with col2:
        meter_type_filter = st.selectbox(
            "Filter by Type",
            ["All", "residential", "commercial", "industrial", "mixed", "institutional"]
        )
    
    with col3:
        status_filter = st.selectbox(
            "Filter by Status",
            ["All", "active", "inactive"]
        )
    
    # Apply filters
    filtered_df = meters_df.copy()
    if zone_filter != "All Zones":
        filtered_df = filtered_df[filtered_df['zone_id'] == zone_filter]
    if meter_type_filter != "All":
        filtered_df = filtered_df[filtered_df['meter_type'] == meter_type_filter]
    if status_filter != "All":
        filtered_df = filtered_df[filtered_df['status'] == status_filter]
    
    st.write(f"**Total Meters:** {len(filtered_df)}")

    display_df = filtered_df[['meter_id', 'location', 'zone_id', 'meter_type', 'status', 'flow_rate']].copy()
    display_df = display_df.rename(columns={
        'meter_id': 'Meter ID', 'location': 'Location', 'zone_id': 'Zone',
        'meter_type': 'Type', 'status': 'Status', 'flow_rate': 'Flow Rate (L/s)'
    })
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.subheader("Manage Meter")

    meter_options = [f"{row['meter_id']} - {row['location']}" for _, row in filtered_df.iterrows()]
    if not meter_options:
        return

    selected_label = st.selectbox("Select meter", meter_options, key="select_meter")
    selected_id = selected_label.split(" - ")[0]
    meter = filtered_df[filtered_df['meter_id'] == selected_id].iloc[0]

    col_info, col_actions = st.columns([3, 1])
    with col_info:
        st.write(f"**Meter ID:** {meter['meter_id']}")
        st.write(f"**Zone:** {meter['zone_id']}")
        st.write(f"**Location:** {meter['location']}")
        st.write(f"**Type:** {meter['meter_type']}")
        st.write(f"**Status:** {meter['status'].upper()}")
        st.write(f"**Flow Rate:** {meter['flow_rate']} L/s")
        st.write(f"**Description:** {meter['description'] or 'N/A'}")
        if pd.notna(meter.get('installation_date')):
            st.write(f"**Installed:** {meter['installation_date']}")

    with col_actions:
        if st.button("Edit", key=f"edit_meter_{meter['meter_id']}"):
            st.session_state[f'editing_meter_{meter["meter_id"]}'] = True
            st.rerun()
        if meter['status'] == 'active':
            if st.button("Deactivate", key=f"delete_meter_{meter['meter_id']}"):
                st.session_state[f'confirm_delete_{meter["meter_id"]}'] = True
                st.rerun()

    if st.session_state.get(f'editing_meter_{meter["meter_id"]}', False):
        show_edit_meter_form(meter)

    if st.session_state.get(f'confirm_delete_{meter["meter_id"]}', False):
        st.warning(f"Are you sure you want to deactivate meter **{meter['meter_id']}**?")
        col_yes, col_no = st.columns(2)
        with col_yes:
            if st.button("Yes, Deactivate", key=f"confirm_yes_{meter['meter_id']}"):
                success, msg = db_manager.delete_meter(meter['meter_id'])
                if success:
                    st.success(msg)
                    st.session_state.pop(f'confirm_delete_{meter["meter_id"]}', None)
                    st.rerun()
                else:
                    st.error(msg)
        with col_no:
            if st.button("Cancel", key=f"confirm_no_{meter['meter_id']}"):
                st.session_state.pop(f'confirm_delete_{meter["meter_id"]}', None)
                st.rerun()


def show_create_meter_form():
    """Display form to create a new meter"""
    st.subheader("Create New Meter")
    
    # Get available zones
    zones_df = db_manager.get_all_zones()
    if zones_df.empty:
        st.error("No zones available. Please create a zone first before creating meters.")
        return
    
    active_zones = zones_df[zones_df['status'] == 'active']
    if active_zones.empty:
        st.error("No active zones available. Please create an active zone first.")
        return
    
    with st.form("create_meter_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            meter_id = st.text_input("Meter ID *", placeholder="e.g., MTR-999", help="Unique identifier for the meter")
            
            # Zone selection with zone info
            zone_options = {f"{row['zone_id']} - {row['name']}": row['zone_id'] 
                          for _, row in active_zones.iterrows()}
            selected_zone_display = st.selectbox("Zone *", list(zone_options.keys()))
            zone_id = zone_options[selected_zone_display]
            
            location = st.text_input("Location *", placeholder="e.g., Block A, Street 5")
            meter_type = st.selectbox("Meter Type *", ["residential", "commercial", "industrial", "mixed", "institutional"])
        
        with col2:
            status = st.selectbox("Status *", ["active", "inactive"])
            flow_rate = st.number_input("Flow Rate (L/s) *", min_value=0.0, max_value=50.0, value=8.0, step=0.1)
            description = st.text_area("Description", placeholder="Brief description of meter location and purpose")
        
        st.info("Note: Zone must exist before creating a meter. The selected zone will be validated.")
        
        submitted = st.form_submit_button("Create Meter")
        
        if submitted:
            # Validation
            if not all([meter_id.strip(), zone_id.strip(), location.strip()]):
                st.error("Meter ID, Zone, and Location are required")
            else:
                # Create meter
                success, msg = db_manager.create_meter(
                    meter_id=meter_id.strip().upper(),
                    zone_id=zone_id,
                    location=location.strip(),
                    meter_type=meter_type,
                    status=status,
                    flow_rate=flow_rate,
                    description=description.strip() if description else ""
                )
                
                if success:
                    st.success(msg)
                    st.rerun()
                else:
                    st.error(msg)


def show_edit_meter_form(meter: pd.Series):
    """Display inline form to edit a meter"""
    st.markdown("---")
    st.subheader("Edit Meter")
    
    # Get available zones
    zones_df = db_manager.get_all_zones()
    active_zones = zones_df[zones_df['status'] == 'active']
    
    with st.form(f"edit_meter_form_{meter['meter_id']}"):
        col1, col2 = st.columns(2)
        
        with col1:
            # Zone selection
            zone_options = {f"{row['zone_id']} - {row['name']}": row['zone_id'] 
                          for _, row in active_zones.iterrows()}
            
            # Find current zone index
            current_zone_display = None
            for display, zid in zone_options.items():
                if zid == meter['zone_id']:
                    current_zone_display = display
                    break
            
            if current_zone_display:
                zone_index = list(zone_options.keys()).index(current_zone_display)
            else:
                zone_index = 0
            
            selected_zone_display = st.selectbox("Zone *", list(zone_options.keys()), index=zone_index)
            zone_id = zone_options[selected_zone_display]
            
            location = st.text_input("Location *", value=meter['location'])
            meter_type = st.selectbox(
                "Meter Type *",
                ["residential", "commercial", "industrial", "mixed", "institutional"],
                index=["residential", "commercial", "industrial", "mixed", "institutional"].index(meter['meter_type'])
            )
        
        with col2:
            status = st.selectbox(
                "Status *",
                ["active", "inactive"],
                index=0 if meter['status'] == 'active' else 1
            )
            flow_rate = st.number_input("Flow Rate (L/s) *", min_value=0.0, max_value=50.0, value=float(meter['flow_rate']), step=0.1)
            description = st.text_area("Description", value=meter['description'] or "")
        
        col_submit, col_cancel = st.columns(2)
        with col_submit:
            submitted = st.form_submit_button("Update Meter")
        with col_cancel:
            cancelled = st.form_submit_button("Cancel")
        
        if cancelled:
            st.session_state.pop(f'editing_meter_{meter["meter_id"]}', None)
            st.rerun()
        
        if submitted:
            # Validation
            if not all([zone_id.strip(), location.strip()]):
                st.error("Zone and Location are required")
            else:
                # Update meter
                success, msg = db_manager.update_meter(
                    meter_id=meter['meter_id'],
                    zone_id=zone_id,
                    location=location.strip(),
                    meter_type=meter_type,
                    status=status,
                    flow_rate=flow_rate,
                    description=description.strip() if description else ""
                )
                
                if success:
                    st.success(msg)
                    st.session_state.pop(f'editing_meter_{meter["meter_id"]}', None)
                    st.rerun()
                else:
                    st.error(msg)
