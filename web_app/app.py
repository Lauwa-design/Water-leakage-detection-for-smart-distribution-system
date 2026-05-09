"""THIWASCO Leak Detection System - Streamlit application shell."""

import os
import sys

import streamlit as st

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from auth import show_login
from page_components import (
    show_alerts,
    show_leak_analysis,
    show_overview,
    show_system_status,
    show_zones_assets,
    show_teams,
    show_reports,
    show_user_management,
    show_meter_management,
    show_zone_management,
)
from page_components.data_utils import bootstrap_demo_environment
from page_components.ui import apply_theme
from backend.rbac import is_system_admin, is_nrw_officer, is_field_technician


st.set_page_config(
    page_title="THIWASCO Leak Detection",
    page_icon="\U0001F4A7",
    layout="wide",
    initial_sidebar_state="collapsed",
)


if "authenticated" not in st.session_state:
    st.session_state.authenticated = False
if "user_email" not in st.session_state:
    st.session_state.user_email = None

if not st.session_state.authenticated:
    show_login()
    st.stop()

# Force theme refresh for dark mode
st.session_state.pop("_thiwasco_theme_applied", None)
apply_theme(dark_mode=True)
bootstrap_demo_environment()

st.sidebar.title("THIWASCO")

# Build navigation menu based on user role
nav_options = ["Overview", "Leak Analysis", "Alerts", "System Status"]

# Add role-specific pages
if is_nrw_officer():
    nav_options.extend(["Teams", "Reports"])

if is_field_technician():
    # Field Technicians can view their teams
    nav_options.insert(3, "Teams")  # Insert after Alerts

if is_system_admin():
    nav_options.extend(["User Management", "Meter Management", "Zone Management", "Zones & Assets"])
else:
    nav_options.append("Zones & Assets")

page = st.sidebar.radio("Navigation", nav_options)

st.sidebar.markdown("---")
st.sidebar.write(f"Logged in as: {st.session_state.user_email}")

if st.sidebar.button("Logout"):
    st.session_state.authenticated = False
    st.session_state.user_email = None
    st.rerun()

try:
    if page == "Overview":
        show_overview()
    elif page == "Leak Analysis":
        show_leak_analysis()
    elif page == "Alerts":
        show_alerts()
    elif page == "Teams":
        show_teams()
    elif page == "Reports":
        show_reports()
    elif page == "User Management":
        show_user_management()
    elif page == "Meter Management":
        show_meter_management()
    elif page == "Zone Management":
        show_zone_management()
    elif page == "Zones & Assets":
        show_zones_assets()
    elif page == "System Status":
        show_system_status()
except Exception as e:
    st.error(f"Error rendering {page}: {e}")
    import traceback
    st.code(traceback.format_exc())
