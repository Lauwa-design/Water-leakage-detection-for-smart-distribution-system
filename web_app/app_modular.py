"""
THIWASCO Leak Detection Dashboard - Proper Modular Architecture
Clean separation: Backend (logic) vs Frontend (display) vs Data Service (coordination)
"""

import streamlit as st
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import sys
from pathlib import Path
import time

# Add paths for imports
sys.path.append(str(Path(__file__).parent / "backend"))
sys.path.append(str(Path(__file__).parent / "frontend"))

# Import backend - NO UI logic
from backend import data_manager, prediction_service, realtime_simulator

# Import frontend - NO business logic
from frontend import (
    load_css,
    render_sidebar,
    render_topbar,
    render_breadcrumb,
    render_login_page,
    render_dashboard,
    render_leak_intelligence,
    render_regional_management,
    render_real_time_monitoring,
    render_alerts_management
)

# Set page configuration
st.set_page_config(
    page_title="THIWASCO Leak Detection Dashboard",
    page_icon="T",
    layout="wide",
    initial_sidebar_state="expanded",
)

# Data service layer - NO business logic, NO UI logic
class DataService:
    """Data service layer - only coordinates between backend and UI"""
    
    @staticmethod
    def get_dashboard_stats():
        """Get dashboard statistics from backend"""
        try:
            # Generate real-time predictions first
            prediction_service.generate_realtime_predictions()
            
            # Get recent predictions
            predictions_df = data_manager.get_recent_predictions(hours=24)
            
            # Get active alerts
            alerts_df = data_manager.get_active_alerts(acknowledged=False)
            
            # Get meter summary
            meters_df = data_manager.get_meter_summary()
            
            # Calculate stats
            critical_leaks = len(predictions_df[predictions_df['leak_detected'] & 
                                              (predictions_df['severity'] == 'instant')])
            total_meters = len(meters_df) if not meters_df.empty else 4
            active_alerts = len(alerts_df)
            
            # Get recent detections for display
            if not predictions_df.empty:
                recent_detections = predictions_df.head(10)[['meter_id', 'location', 'timestamp', 
                                                             'pressure', 'flow_rate', 'severity', 'confidence']]
            else:
                recent_detections = pd.DataFrame()
            
            return {
                'critical_leaks': critical_leaks,
                'total_meters': total_meters,
                'active_alerts': active_alerts,
                'recent_detections': recent_detections
            }
        except Exception as e:
            st.error(f"Error loading dashboard data: {e}")
            return {
                'critical_leaks': 0,
                'total_meters': 4,
                'active_alerts': 0,
                'recent_detections': pd.DataFrame()
            }
    
    @staticmethod
    def get_intelligence_data():
        """Get leak intelligence data from backend"""
        try:
            # Generate real-time predictions first
            prediction_service.generate_realtime_predictions()
            
            predictions_df = data_manager.get_recent_predictions(hours=48)
            
            if predictions_df.empty:
                return pd.DataFrame()
            
            # Format for UI display
            intelligence_df = predictions_df[['meter_id', 'location', 'timestamp', 'severity', 
                                            'confidence', 'recommendation']].copy()
            
            return intelligence_df
        except Exception as e:
            st.error(f"Error loading intelligence data: {e}")
            return pd.DataFrame()
    
    @staticmethod
    def get_regional_data():
        """Get regional management data from backend"""
        try:
            meters_df = data_manager.get_meter_summary()
            
            if meters_df.empty:
                # Add sample meters if none exist
                sample_meters = pd.DataFrame([
                    {'meter_id': 'HW-THK-001', 'location': 'Thika West', 'zone_id': 'ZONE-001', 'total_readings': 100, 'leak_count': 2},
                    {'meter_id': 'HW-THK-002', 'location': 'Thika East', 'zone_id': 'ZONE-002', 'total_readings': 95, 'leak_count': 3},
                    {'meter_id': 'HW-THK-003', 'location': 'Thika North', 'zone_id': 'ZONE-003', 'total_readings': 88, 'leak_count': 1},
                    {'meter_id': 'HW-THK-004', 'location': 'Thika Central', 'zone_id': 'ZONE-004', 'total_readings': 102, 'leak_count': 2}
                ])
                return sample_meters
            
            # Add zone_id if it doesn't exist in the database data
            if 'zone_id' not in meters_df.columns:
                # Generate zone_id based on meter_id
                meters_df['zone_id'] = meters_df['meter_id'].apply(
                    lambda x: f"ZONE-{x.split('-')[-1]}" if '-' in str(x) else f"ZONE-{str(x)[-3:]}"
                )
            
            return meters_df
        except Exception as e:
            st.error(f"Error loading regional data: {e}")
            return pd.DataFrame()
    
    @staticmethod
    def get_realtime_data(meter_id: str = None):
        """Get real-time monitoring data from backend"""
        try:
            if meter_id:
                # Get specific meter data
                readings_df = data_manager.get_sensor_readings(meter_id, hours=2, limit=100)
            else:
                # Get all recent predictions for chart
                predictions_df = data_manager.get_recent_predictions(hours=2, limit=100)
                
                if predictions_df.empty:
                    # Generate sample data for demo
                    timestamps = pd.date_range(
                        start=datetime.now() - timedelta(hours=2),
                        periods=100,
                        freq='1min'
                    )
                    
                    readings_df = pd.DataFrame({
                        'timestamp': timestamps,
                        'pressure': np.random.normal(3.5, 0.5, 100),
                        'flow_rate': np.random.normal(45, 8, 100)
                    })
                else:
                    readings_df = predictions_df[['timestamp', 'pressure', 'flow_rate']]
            
            return readings_df
        except Exception as e:
            st.error(f"Error loading real-time data: {e}")
            return pd.DataFrame()

def main():
    """Main application entry point"""
    # Load CSS styling
    st.markdown(load_css(), unsafe_allow_html=True)
    
    # Session state
    if 'logged_in' not in st.session_state:
        st.session_state['logged_in'] = False
    
    # Login screen
    if not st.session_state['logged_in']:
        render_login_page()
        st.stop()
    
    # Only proceed if logged in
    if st.session_state['logged_in']:
        # Initialize sample data if needed
        try:
            from backend import data_manager
            # Check if zones exist, if not initialize sample data
            with data_manager.get_connection() as conn:
                cursor = conn.execute("SELECT COUNT(*) FROM zones")
                zone_count = cursor.fetchone()[0]
                if zone_count == 0:
                    data_manager.initialize_sample_data()
        except Exception as e:
            st.error(f"Error initializing sample data: {e}")
        
        # Start real-time simulation if not running
        if not realtime_simulator.running:
            realtime_simulator.start_simulation()
        
        # Render sidebar navigation
        render_sidebar()
        
        # Render topbar
        render_topbar()
        
        # Page routing
        if 'current_page' not in st.session_state:
            st.session_state.current_page = "dashboard"
        
        current_page = st.session_state.get('current_page', 'dashboard')
        
        # Initialize data service
        data_service = DataService()
        
        # Render appropriate page
        if current_page == "dashboard":
            render_dashboard(data_service)
        elif current_page == "intelligence":
            render_leak_intelligence(data_service)
        elif current_page == "regional":
            render_regional_management(data_service)
        elif current_page == "monitoring":
            render_real_time_monitoring(data_service)
        elif current_page == "alerts":
            render_alerts_management(data_service)
        else:
            render_dashboard(data_service)

if __name__ == "__main__":
    main()
