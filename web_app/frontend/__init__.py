"""
THIWASCO Frontend Package
Clean modular frontend structure
"""

from .styles import load_css
from .components import render_sidebar, render_topbar, render_breadcrumb, render_login_page
from .pages.dashboard import render_dashboard
from .pages.intelligence import render_leak_intelligence
from .pages.regional import render_regional_management
from .pages.monitoring import render_real_time_monitoring
from .pages.alerts import render_alerts_management

__all__ = [
    'load_css',
    'render_sidebar',
    'render_topbar', 
    'render_breadcrumb',
    'render_login_page',
    'render_dashboard',
    'render_leak_intelligence',
    'render_regional_management',
    'render_real_time_monitoring',
    'render_alerts_management'
]
