"""
THIWASCO Dashboard Page
Main dashboard view - pure UI logic only
"""

import streamlit as st
import plotly.express as px
from ..components import render_page_heading, render_metric_card, render_section_card

def render_dashboard(data_service):
    """Render the main dashboard page"""
    # Page header
    render_page_heading(
        "Leak Detection Dashboard",
        "Real-time monitoring and analysis of water distribution system"
    )
    
    # Get data from backend
    stats = data_service.get_dashboard_stats()
    
    # KPI Cards
    col1, col2, col3, col4 = st.columns(4)
    
    with col1:
        render_metric_card(
            "Critical Leaks",
            stats['critical_leaks'],
            "Requires attention",
            "critical"
        )
    
    with col2:
        render_metric_card(
            "Active Meters",
            stats['total_meters'],
            "All online",
            "success"
        )
    
    with col3:
        render_metric_card(
            "Active Alerts",
            stats['active_alerts'],
            "Pending review",
            "moderate"
        )
    
    with col4:
        render_metric_card(
            "System Health",
            "94%",
            "Operating normally",
            "success"
        )
    
    # Recent detections
    render_section_card(
        "Recent Leak Detections",
        "Latest sensor readings and anomaly detection"
    )
    
    if not stats['recent_detections'].empty:
        st.dataframe(stats['recent_detections'], use_container_width=True)
    else:
        st.info("No recent detections available")
    
    # Chart section
    render_section_card(
        "Regional Distribution",
        "Leak incidents by geographical area"
    )
    
    # Get regional data for chart
    regional_data = data_service.get_regional_data()
    if not regional_data.empty:
        chart_data = regional_data.groupby('location').agg({
            'leak_count': 'sum'
        }).reset_index()
        
        fig = px.bar(chart_data, x='location', y='leak_count', color='leak_count',
                     color_continuous_scale=['#2e7d32', '#f17a0a', '#cd2b2b'])
        fig.update_layout(
            plot_bgcolor='white',
            paper_bgcolor='white',
            font=dict(color="#08254b", family="Aptos"),
            margin=dict(t=0, b=0, l=0, r=0)
        )
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
    else:
        st.info("No regional data available")
