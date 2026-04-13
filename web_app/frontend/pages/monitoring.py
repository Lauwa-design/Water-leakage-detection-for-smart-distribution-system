"""
THIWASCO Real-Time Monitoring Page
Live sensor data streams and continuous leak detection - pure UI logic only
"""

import streamlit as st
import plotly.graph_objects as go
import time
from datetime import datetime
from ..components import render_page_heading, render_section_card

def render_real_time_monitoring(data_service):
    """Render the real-time monitoring page"""
    # Page header
    render_page_heading(
        "Real-Time Monitoring",
        "Live sensor data streams and continuous leak detection"
    )
    
    # Get simulation status
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent.parent / "backend"))
    from backend import realtime_simulator
    
    status = realtime_simulator.get_simulation_status()
    
    # Simulation status card
    render_section_card(
        "Simulation Status",
        f"Real-time data generation and leak detection"
    )
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Status", "Running" if status['running'] else "Stopped")
    with col2:
        st.metric("Update Interval", f"{status['interval']}s")
    with col3:
        st.metric("Active Meters", len(status['active_meters']))
    with col4:
        st.metric("Last Update", datetime.now().strftime("%H:%M:%S"))
    
    # Controls
    render_section_card(
        "Monitoring Controls",
        "Configure real-time data display"
    )
    
    col1, col2 = st.columns(2)
    with col1:
        selected_meter = st.selectbox("Select Meter", ["All Meters"] + status['active_meters'], key="monitor_meter")
    with col2:
        auto_refresh = st.checkbox("Auto-refresh (5s)", value=True, key="auto_refresh")
    
    # Get real-time data from backend
    meter_id = None if selected_meter == "All Meters" else selected_meter
    realtime_data = data_service.get_realtime_data(meter_id)
    
    render_section_card(
        "Real-time Sensor Data",
        "Live flow rate and pressure monitoring with leak detection"
    )
    
    if not realtime_data.empty:
        # Create dual-axis chart
        fig = go.Figure()
        
        fig.add_trace(go.Scatter(
            x=realtime_data['timestamp'],
            y=realtime_data['flow_rate'],
            mode='lines+markers',
            name='Flow Rate (L/s)',
            line=dict(color='#2e7d32', width=3),
            marker=dict(size=4)
        ))
        
        fig.add_trace(go.Scatter(
            x=realtime_data['timestamp'],
            y=realtime_data['pressure'],
            mode='lines+markers',
            name='Pressure (bar)',
            yaxis='y2',
            line=dict(color='#f17a0a', width=3),
            marker=dict(size=4)
        ))
        
        fig.update_layout(
            title="",
            xaxis_title="Time",
            yaxis_title="Flow (L/s)",
            yaxis2=dict(title="Pressure (bar)", overlaying='y', side='right'),
            height=400,
            showlegend=True,
            plot_bgcolor='white',
            paper_bgcolor='white',
            font=dict(color="#08254b", family="Aptos"),
            margin=dict(t=0, b=0, l=0, r=0),
            hovermode='x unified'
        )
        
        st.plotly_chart(fig, use_container_width=True, config={'displayModeBar': False})
        
        # Recent leak detections
        render_section_card(
            "Recent Leak Detections",
            "Latest leak predictions from the system"
        )
        
        recent_predictions = data_service.get_intelligence_data()
        if not recent_predictions.empty:
            # Show only recent leak detections
            leak_detections = recent_predictions[recent_predictions['leak_detected'] == True].head(5)
            
            if not leak_detections.empty:
                for _, detection in leak_detections.iterrows():
                    severity_color = {
                        'slow': 'orange',
                        'moderate': 'red', 
                        'instant': 'darkred'
                    }.get(detection['severity'], 'gray')
                    
                    st.markdown(f"""
                    <div style="border-left: 4px solid {severity_color}; padding: 10px; margin: 5px 0; background: rgba(0,0,0,0.02);">
                        <strong>{detection['meter_id']}</strong> - {detection['location']}<br>
                        <small>Time: {detection['timestamp'].strftime('%H:%M:%S')} | 
                        Severity: {detection['severity']} | 
                        Confidence: {detection['confidence']:.1%}</small><br>
                        <small>{detection['recommendation']}</small>
                    </div>
                    """, unsafe_allow_html=True)
            else:
                st.info("No leak detections in recent data")
        else:
            st.info("No leak detection data available")
    else:
        st.warning("Waiting for sensor data... Simulation may be starting.")
        st.info("The real-time simulator generates data every 5 seconds. Please wait a moment for data to appear.")
    
    # Auto-refresh logic
    if auto_refresh:
        time.sleep(5)
        st.rerun()
