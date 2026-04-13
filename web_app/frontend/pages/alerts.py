"""
THIWASCO Alerts Management Page
Real-time alert monitoring and notification management - pure UI logic only
"""

import streamlit as st
import pandas as pd
from datetime import datetime, timedelta
from ..components import render_page_heading, render_section_card

def render_alerts_management(data_service):
    """Render the alerts management page"""
    # Page header
    render_page_heading(
        "Alert Management",
        "Real-time leak detection alerts and notification system"
    )
    
    # Get alert manager
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent.parent / "backend"))
    from backend import alert_manager
    
    # Alert statistics
    render_section_card(
        "Alert Statistics",
        "Overview of current alert status"
    )
    
    active_alerts = alert_manager.get_active_alerts(limit=100)
    
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Active Alerts", len([a for a in active_alerts if a['status'] == 'active']))
    with col2:
        st.metric("Acknowledged", len([a for a in active_alerts if a['status'] == 'acknowledged']))
    with col3:
        st.metric("Critical", len([a for a in active_alerts if a['severity'] == 'critical']))
    with col4:
        st.metric("Last 24 Hours", len([a for a in active_alerts if 
            datetime.fromisoformat(a['created_at'].replace('Z', '+00:00')) > datetime.now() - timedelta(hours=24)]))
    
    # Alert management controls
    render_section_card(
        "Alert Controls",
        "Manage alert notifications and acknowledgments"
    )
    
    col1, col2, col3 = st.columns(3)
    with col1:
        if st.button("Refresh Alerts", key="refresh_alerts", use_container_width=True):
            st.rerun()
    
    with col2:
        # Alert notification test
        if st.button("Test Alert System", key="test_alert", use_container_width=True):
            test_alert_id = alert_manager.create_alert(
                meter_id="TEST-001",
                alert_type="info",
                title="Test Alert",
                message="This is a test alert to verify the notification system is working properly.",
                severity="low"
            )
            if test_alert_id:
                alert_manager.send_notifications(test_alert_id, ['email'])
                st.success("Test alert sent!")
            else:
                st.error("Failed to create test alert")
    
    with col3:
        # Clear resolved alerts
        if st.button("Clear Resolved", key="clear_resolved", use_container_width=True):
            st.info("Feature coming soon - clear resolved alerts")
    
    # Active alerts display
    render_section_card(
        "Active Alerts",
        "Current leak detection alerts requiring attention"
    )
    
    if active_alerts:
        # Filter options
        col1, col2, col3 = st.columns(3)
        with col1:
            status_filter = st.selectbox("Filter by Status", ["All", "active", "acknowledged", "resolved"], key="status_filter")
        with col2:
            severity_filter = st.selectbox("Filter by Severity", ["All", "low", "medium", "high", "critical"], key="severity_filter")
        with col3:
            zone_filter = st.selectbox("Filter by Zone", ["All"] + list(set([a.get('zone_name', 'Unknown') for a in active_alerts])), key="zone_filter")
        
        # Apply filters
        filtered_alerts = active_alerts
        if status_filter != "All":
            filtered_alerts = [a for a in filtered_alerts if a['status'] == status_filter]
        if severity_filter != "All":
            filtered_alerts = [a for a in filtered_alerts if a['severity'] == severity_filter]
        if zone_filter != "All":
            filtered_alerts = [a for a in filtered_alerts if a.get('zone_name', 'Unknown') == zone_filter]
        
        # Display alerts
        for alert in filtered_alerts:
            severity_colors = {
                'low': '#28a745',
                'medium': '#ffc107', 
                'high': '#fd7e14',
                'critical': '#dc3545'
            }
            
            status_colors = {
                'active': '#dc3545',
                'acknowledged': '#fd7e14',
                'resolved': '#28a745',
                'false_positive': '#6c757d'
            }
            
            severity_color = severity_colors.get(alert['severity'], '#6c757d')
            status_color = status_colors.get(alert['status'], '#6c757d')
            
            # Alert card
            with st.container():
                st.markdown(f"""
                <div style="border: 1px solid #dee2e6; border-radius: 8px; padding: 20px; margin: 10px 0; background: white;">
                    <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px;">
                        <div>
                            <span style="background: {severity_color}; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold;">
                                {alert['severity'].upper()}
                            </span>
                            <span style="background: {status_color}; color: white; padding: 4px 8px; border-radius: 4px; font-size: 12px; font-weight: bold; margin-left: 8px;">
                                {alert['status'].upper()}
                            </span>
                        </div>
                        <small style="color: #6c757d;">{alert['created_at']}</small>
                    </div>
                    
                    <h4 style="color: #0d2b52; margin: 0 0 10px 0;">{alert['title']}</h4>
                    <p style="color: #495057; margin: 0 0 15px 0;">{alert['message']}</p>
                    
                    <div style="display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 15px; margin: 15px 0;">
                        <div>
                            <strong>Meter:</strong> {alert['meter_id']}<br>
                            <strong>Location:</strong> {alert.get('location', 'N/A')}
                        </div>
                        <div>
                            <strong>Zone:</strong> {alert.get('zone_name', 'N/A')}<br>
                            <strong>Type:</strong> {alert['alert_type']}
                        </div>
                        <div>
                            <strong>Acknowledged:</strong> {alert.get('acknowledged_by', 'No')}<br>
                            <strong>Resolved:</strong> {alert.get('resolved_by', 'No')}
                        </div>
                    </div>
                </div>
                """, unsafe_allow_html=True)
                
                # Action buttons
                col1, col2, col3 = st.columns(3)
                with col1:
                    if alert['status'] == 'active':
                        if st.button(f"Acknowledge", key=f"ack_{alert['id']}", use_container_width=True):
                            alert_manager.acknowledge_alert(alert['id'], 'operator')
                            st.rerun()
                
                with col2:
                    if alert['status'] in ['active', 'acknowledged']:
                        if st.button(f"Resolve", key=f"resolve_{alert['id']}", use_container_width=True):
                            alert_manager.resolve_alert(alert['id'], 'operator')
                            st.rerun()
                
                with col3:
                    if st.button(f"Details", key=f"details_{alert['id']}", use_container_width=True):
                        with st.expander(f"Alert Details - {alert['id']}", expanded=True):
                            st.json(alert)
    
    else:
        st.info("No active alerts. System is operating normally.")
    
    # Notification history
    render_section_card(
        "Recent Notifications",
        "History of sent notifications"
    )
    
    try:
        # Get recent notifications (this would need to be implemented in data_manager)
        st.info("Notification history feature coming soon...")
        
        # Sample notification data for demonstration
        sample_notifications = [
            {
                'timestamp': datetime.now() - timedelta(minutes=5),
                'type': 'email',
                'recipient': 'operations@thiwasco.co.ke',
                'status': 'sent',
                'alert_title': 'Leak Detected - MODERATE'
            },
            {
                'timestamp': datetime.now() - timedelta(minutes=15),
                'type': 'email', 
                'recipient': 'maintenance@thiwasco.co.ke',
                'status': 'sent',
                'alert_title': 'Leak Detected - SLOW'
            }
        ]
        
        for notif in sample_notifications:
            status_colors = {
                'sent': '#28a745',
                'pending': '#ffc107',
                'failed': '#dc3545'
            }
            status_color = status_colors.get(notif['status'], '#6c757d')
            
            st.markdown(f"""
            <div style="border-left: 3px solid {status_color}; padding: 10px; margin: 5px 0; background: #f8f9fa;">
                <div style="display: flex; justify-content: space-between;">
                    <strong>{notif['alert_title']}</strong>
                    <span style="color: {status_color}; font-size: 12px;">{notif['status'].upper()}</span>
                </div>
                <small style="color: #6c757d;">
                    {notif['type']} to {notif['recipient']} at {notif['timestamp'].strftime('%H:%M:%S')}
                </small>
            </div>
            """, unsafe_allow_html=True)
    
    except Exception as e:
        st.info(f"Notification history: {e}")
