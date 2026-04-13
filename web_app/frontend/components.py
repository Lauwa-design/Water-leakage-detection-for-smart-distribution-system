"""
THIWASCO Frontend Components
Reusable UI components
"""

import streamlit as st
import time
from datetime import datetime
from .styles import load_css

def render_sidebar():
    """Render the sidebar navigation"""
    with st.sidebar:
        st.markdown("""
        <div class="brand-lockup">
            <div class="brand-mark">T</div>
            <div>
                <div class="brand-title">THIWASCO</div>
                <div class="brand-subtitle">Smart Water Grid</div>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Navigation
        st.markdown("---")
        
        if st.button("Dashboard", key="nav_dashboard", use_container_width=True):
            st.session_state.current_page = "dashboard"
            st.rerun()
        
        if st.button("Leak Intelligence", key="nav_intelligence", use_container_width=True):
            st.session_state.current_page = "intelligence"
            st.rerun()
        
        if st.button("Regional Management", key="nav_regional", use_container_width=True):
            st.session_state.current_page = "regional"
            st.rerun()
        
        if st.button("Real-Time Monitoring", key="nav_monitoring", use_container_width=True):
            st.session_state.current_page = "monitoring"
            st.rerun()
        
        if st.button("Alert Management", key="nav_alerts", use_container_width=True):
            st.session_state.current_page = "alerts"
            st.rerun()
        
        st.markdown("---")
        
        # Real-time controls
        st.markdown("**Real-Time Controls**")
        
        # Import here to avoid circular imports
        import sys
        from pathlib import Path
        sys.path.append(str(Path(__file__).parent.parent / "backend"))
        from backend import realtime_simulator
        
        # Simulation status
        status = realtime_simulator.get_simulation_status()
        
        if status['running']:
            st.success("Simulation Running")
            st.caption(f"Updates every {status['interval']}s")
        else:
            st.error("Simulation Stopped")
        
        # Quick test controls
        st.markdown("**Quick Test**")
        if st.button("Test Random Leak", key="force_leak", use_container_width=True):
            # Test on random meter with moderate severity
            import random
            test_meter = random.choice(status['active_meters'])
            success = realtime_simulator.force_leak_simulation(test_meter, "moderate")
            if success:
                st.success(f"Leak test initiated for {test_meter}")
            else:
                st.error("Failed to initiate leak test")
        
        st.markdown("---")
        
        # Logout button
        if st.button("Logout", key="logout", use_container_width=True, type="secondary"):
            # Stop simulation when logging out
            realtime_simulator.stop_simulation()
            st.session_state['logged_in'] = False
            st.rerun()
        
        st.markdown("""
        <style>
        div[data-testid="stVerticalBlock"] > div:nth-child(8) > div > button {
            background: rgba(220, 38, 38, 0.15) !important;
            color: #fca5a5 !important;
            border: 1px solid rgba(220, 38, 38, 0.25) !important;
        }
        div[data-testid="stVerticalBlock"] > div:nth-child(8) > div > button:hover {
            background: rgba(220, 38, 38, 0.25) !important;
            color: #ffffff !important;
            border-color: rgba(220, 38, 38, 0.4) !important;
        }
        </style>
        """, unsafe_allow_html=True)
        
        if st.button("Logout", use_container_width=True):
            st.session_state['logged_in'] = False
            st.rerun()

def render_topbar():
    """Render the top bar with time and user info"""
    st.markdown(f"""
    <div class="topbar">
        <div class="topbar-time">{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</div>
        <div class="topbar-user">
            <div>
                <div style="text-align: right; color: #0e2242; font-weight: 800; font-size: 1.1rem;">Admin User</div>
                <div style="text-align: right; color: var(--slate-500); font-size: 0.92rem;">System Administrator</div>
            </div>
            <div style="width: 44px; height: 44px; border-radius: 999px; background: var(--navy-950); color: white; display: grid; place-items: center; font-weight: 800;">A</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_breadcrumb(page_name):
    """Render breadcrumb navigation"""
    st.markdown(f"""
    <div class="breadcrumb">
        <span>Home</span>
        <span class="breadcrumb-separator">></span>
        <span class="breadcrumb-active">{page_name}</span>
    </div>
    """, unsafe_allow_html=True)

def render_page_heading(title, subtitle):
    """Render page heading with title and subtitle"""
    st.markdown(f"""
    <div class="page-heading page-transition">
        <h1>{title}</h1>
        <p>{subtitle}</p>
    </div>
    """, unsafe_allow_html=True)

def render_metric_card(title, value, status_text, accent_color="neutral"):
    """Render a metric card"""
    accent_classes = {
        "critical": "accent-critical",
        "moderate": "accent-moderate", 
        "success": "accent-success",
        "neutral": "accent-neutral"
    }
    
    accent_class = accent_classes.get(accent_color, "accent-neutral")
    
    st.markdown(f"""
    <div class="metric-card">
        <div class="metric-header">
            <div class="metric-title">{title}</div>
            <div class="metric-accent {accent_class}"></div>
        </div>
        <div class="metric-value">{value}</div>
        <div class="metric-foot">
            <span style="color: var(--slate-500); font-weight: 700; font-size: 0.94rem;">{status_text}</span>
        </div>
    </div>
    """, unsafe_allow_html=True)

def render_section_card(title, subtitle=""):
    """Render a section card"""
    subtitle_html = f'<div class="section-subtitle">{subtitle}</div>' if subtitle else ""
    
    st.markdown(f"""
    <div class="section-card">
        <div class="section-title">{title}</div>
        {subtitle_html}
    </div>
    """, unsafe_allow_html=True)

def render_login_page():
    """Render the login page"""
    # Hide sidebar during login
    st.markdown("<style>[data-testid='stSidebar'] {display: none !important;}</style>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.markdown("""
        <div class="login-container">
            <div class="login-header">
                <div class="login-icon">T</div>
                <h1 class="login-title">THIWASCO</h1>
                <p class="login-subtitle">Thika Water &amp; Sewerage Company</p>
                <p class="login-subtitle" style="margin-top: -8px; margin-bottom: 0;">Smart Leak Detection Portal</p>
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        with st.form("login", clear_on_submit=True):
            username = st.text_input(
                "Username",
                placeholder="Enter your username",
                key="login_user",
                help="Enter your system username"
            )
            
            password = st.text_input(
                "Password",
                type="password",
                placeholder="Enter your password",
                key="login_pass",
                help="Enter your system password"
            )
            
            if st.form_submit_button("Access System", use_container_width=True):
                if username == "admin" and password == "1234":
                    st.session_state['logged_in'] = True
                    st.session_state['current_page'] = "dashboard"
                    st.success("Access Granted - Loading Dashboard...")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Invalid credentials - Please try again")
            
            st.markdown("""
            <div class="login-footer">
                Need help? Contact IT Support or call +254-700-000-000
            </div>
            """, unsafe_allow_html=True)
