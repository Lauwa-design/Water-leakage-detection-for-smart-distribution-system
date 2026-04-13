"""
THIWASCO Leak Intelligence Page
AI-powered leak detection and predictive analysis - pure UI logic only
"""

import streamlit as st
from ..components import render_page_heading, render_metric_card, render_section_card

def render_leak_intelligence(data_service):
    """Render the leak intelligence page"""
    # Page header
    render_page_heading(
        "Leak Intelligence Center",
        "AI-powered leak detection and predictive analysis"
    )
    
    # Get intelligence data from backend
    intelligence_data = data_service.get_intelligence_data()
    
    if intelligence_data.empty:
        st.info("No intelligence data available. Run some predictions first.")
        return
    
    # Summary metrics
    col1, col2 = st.columns(2)
    
    with col1:
        high_confidence = len(intelligence_data[intelligence_data['confidence'] > 0.8])
        render_metric_card(
            "High Confidence Predictions",
            high_confidence,
            ">90% confidence",
            "success"
        )
    
    with col2:
        detected_leaks = len(intelligence_data[intelligence_data['severity'] != 'none'])
        render_metric_card(
            "Leaks Detected",
            detected_leaks,
            "Last 48 hours",
            "critical"
        )
    
    # Intelligence table
    render_section_card(
        "ML Predictions",
        "Real-time leak detection recommendations"
    )
    
    st.dataframe(intelligence_data, use_container_width=True, hide_index=True)
