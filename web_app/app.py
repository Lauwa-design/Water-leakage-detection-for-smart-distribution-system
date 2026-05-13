"""THIWASCO Leak Detection System - Streamlit application shell."""

import base64
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
from backend.mysql_database_manager import db_manager
from backend.session_manager import SessionManager

session_manager = SessionManager(db_manager)

st.set_page_config(
    page_title="THIWASCO Leak Detection",
    page_icon="\U0001F4A7",
    layout="wide",
    initial_sidebar_state="expanded",
)


# ── Session restoration ───────────────────────────────────────────────────────
# Runs on every page load (including browser refresh).
# If session_state lost its auth flag (new WebSocket), check the URL token.
def _restore_session() -> bool:
    """Try to restore an authenticated session from the URL token.

    Returns True if a valid session was found and restored.
    Clears the token and returns False if it is invalid, expired, or missing
    required fields — triggering a redirect to the login page.
    """
    if st.session_state.get("authenticated"):
        return True

    token = st.query_params.get("_t")
    if not token:
        return False

    user = session_manager.validate_session(token)

    if not user:
        # Token expired, invalid, or user deactivated — clear and go to login
        st.query_params.clear()
        return False

    # All required fields must be present
    required = {"user_id", "email", "name", "role"}
    if not required.issubset(set(k for k, v in user.items() if v)):
        session_manager.invalidate_session(token)
        st.query_params.clear()
        return False

    # Restore session state from DB-verified user data
    st.session_state.authenticated = True
    st.session_state.user_id       = user["user_id"]
    st.session_state.user_email    = user["email"]
    st.session_state.user_name     = user["name"]
    st.session_state.user_role     = user["role"]
    return True


if not _restore_session():
    show_login()
    st.stop()

st.session_state.pop("_thiwasco_theme_applied", None)
apply_theme(dark_mode=True)
bootstrap_demo_environment()

# ── Auto-start background services ───────────────────────────────────────────
# These are global singletons (daemon threads); the check prevents double-starts
# across Streamlit reruns or multiple browser sessions.
try:
    from backend.smart_meter_simulator import smart_meter_simulator, setup_sample_meters
    from prediction_loop import prediction_loop as _pl

    if not smart_meter_simulator.is_running:
        if not smart_meter_simulator.meters:
            setup_sample_meters()
        smart_meter_simulator.start_simulation()

    if not _pl.is_running:
        _pl.start()
except Exception as _svc_err:
    pass  # Non-fatal — services can be started manually via System Status

st.sidebar.markdown(
    "<div style='padding:0.6rem 0 0.4rem;'>"
    "<span style='font-size:1.1rem;font-weight:800;letter-spacing:0.08em;color:#e2e8f0;'>THIWASCO</span><br>"
    "<span style='font-size:0.65rem;font-weight:600;letter-spacing:0.18em;text-transform:uppercase;color:#475569;'>Leak Detection System</span>"
    "</div>",
    unsafe_allow_html=True,
)
st.sidebar.markdown("<hr style='border:none;border-top:1px solid rgba(255,255,255,0.07);margin:0 0 0.5rem;'>", unsafe_allow_html=True)

# Build navigation menu based on user role
nav_options = ["Overview", "Leak Analysis", "Alerts"]

if is_nrw_officer():
    nav_options.extend(["Teams", "Reports"])

if is_field_technician():
    nav_options.insert(3, "Teams")

if is_system_admin():
    nav_options.extend(["System Status", "User Management", "Meter Management", "Zone Management", "Zones & Assets"])
else:
    nav_options.append("Zones & Assets")

# ── Sidebar icon injection ────────────────────────────────────────────────────
_ICONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "page_components", "thiwasco_icons")

_PAGE_ICONS = {
    "Overview":         "overview.png",
    "Leak Analysis":    "leak_analysis.png",
    "Alerts":           "alerts.png",
    "Teams":            "teams.png",
    "Reports":          "reports.png",
    "Zones & Assets":   "zone.png",
    "User Management":  "user_management.png",
    "Meter Management": "zone.png",
    "Zone Management":  "zone.png",
}

def _icon_b64(filename: str) -> str:
    path = os.path.join(_ICONS_DIR, filename)
    if not os.path.exists(path):
        return ""
    with open(path, "rb") as f:
        return base64.b64encode(f.read()).decode()

_css_parts = ["<style>"]
_radio_base = "[data-testid='stSidebar'] [data-testid='stRadio'] [role='radiogroup'] > label"

for _idx, _pg in enumerate(nav_options, start=1):
    _icon_file = _PAGE_ICONS.get(_pg)
    if not _icon_file:
        continue
    _b64 = _icon_b64(_icon_file)
    if not _b64:
        continue
    _sel = f"{_radio_base}:nth-child({_idx})"
    _css_parts.append(f"""
    {_sel} {{
        padding-left: 40px !important;
        position: relative !important;
    }}
    {_sel}::before {{
        content: '';
        position: absolute;
        left: 10px;
        top: 50%;
        transform: translateY(-50%);
        width: 18px;
        height: 18px;
        background: url('data:image/png;base64,{_b64}') center / contain no-repeat;
        opacity: 0.85;
        filter: drop-shadow(0 0 5px rgba(34,197,94,0.65)) drop-shadow(0 0 10px rgba(34,197,94,0.35));
        transition: opacity 0.15s, filter 0.15s;
    }}
    {_sel}:hover::before {{
        opacity: 0.95;
        filter: drop-shadow(0 0 7px rgba(34,197,94,0.85)) drop-shadow(0 0 14px rgba(34,197,94,0.50));
    }}
    {_sel}:has(input:checked)::before {{
        opacity: 1.0;
        filter: drop-shadow(0 0 8px rgba(34,197,94,1.0)) drop-shadow(0 0 16px rgba(34,197,94,0.70)) brightness(1.15);
    }}
""")

_css_parts.append("</style>")
st.sidebar.markdown("\n".join(_css_parts), unsafe_allow_html=True)

page = st.sidebar.radio("Navigation", nav_options)

st.sidebar.markdown("<hr style='border:none;border-top:1px solid rgba(255,255,255,0.07);margin:0.5rem 0 0.6rem;'>", unsafe_allow_html=True)
st.sidebar.markdown(
    f"<div style='font-size:0.72rem;color:#475569;padding:0 0 0.4rem;'>"
    f"<span style='color:#64748b;font-weight:600;'>Signed in as</span><br>"
    f"<span style='color:#94a3b8;'>{st.session_state.user_email}</span><br>"
    f"<span style='color:#475569;font-size:0.68rem;'>{st.session_state.get('user_role','')}</span>"
    f"</div>",
    unsafe_allow_html=True,
)

if st.sidebar.button("Sign Out", use_container_width=True):
    token = st.query_params.get("_t")
    if token:
        session_manager.invalidate_session(token)
    st.query_params.clear()
    for key in ["authenticated", "user_id", "user_email", "user_name", "user_role"]:
        st.session_state.pop(key, None)
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
