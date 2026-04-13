"""
THIWASCO Alert Manager
Multi-channel notification system for leak detection alerts
"""

import smtplib
import json
import requests
from datetime import datetime
from typing import List, Dict, Optional
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from .data_manager import data_manager
import logging

logger = logging.getLogger(__name__)

class AlertManager:
    """Manages alerts and multi-channel notifications"""
    
    def __init__(self, config: Dict = None):
        self.config = config or self._get_default_config()
        self.notification_channels = {
            'email': EmailNotifier(self.config.get('email', {})),
            'sms': SMSNotifier(self.config.get('sms', {})),
            'webhook': WebhookNotifier(self.config.get('webhook', {}))
        }
    
    def _get_default_config(self) -> Dict:
        """Get default configuration"""
        return {
            'email': {
                'smtp_server': 'smtp.gmail.com',
                'smtp_port': 587,
                'username': 'thiwasco-alerts@gmail.com',
                'password': 'your-app-password',
                'from_email': 'thiwasco-alerts@gmail.com'
            },
            'sms': {
                'provider': 'twilio',
                'account_sid': 'your-twilio-sid',
                'auth_token': 'your-twilio-token',
                'from_number': '+1234567890'
            },
            'webhook': {
                'url': 'https://your-webhook-url.com/alerts',
                'timeout': 10
            }
        }
    
    def create_alert(self, meter_id: str, prediction_id: int = None, 
                   alert_type: str = 'warning', title: str = '', 
                   message: str = '', severity: str = 'medium') -> int:
        """Create a new alert"""
        try:
            with data_manager.get_connection() as conn:
                cursor = conn.execute("""
                    INSERT INTO alerts 
                    (meter_id, prediction_id, alert_type, title, message, severity, status)
                    VALUES (?, ?, ?, ?, ?, ?, 'active')
                """, (meter_id, prediction_id, alert_type, title, message, severity))
                
                alert_id = cursor.lastrowid
                conn.commit()
                
                logger.info(f"Created alert {alert_id} for meter {meter_id}")
                return alert_id
                
        except Exception as e:
            logger.error(f"Failed to create alert: {e}")
            return None
    
    def send_notifications(self, alert_id: int, channels: List[str] = None) -> bool:
        """Send notifications through specified channels"""
        if not channels:
            channels = ['email']  # Default to email only
        
        try:
            # Get alert details
            alert_data = self._get_alert_details(alert_id)
            if not alert_data:
                return False
            
            success_count = 0
            for channel in channels:
                if channel in self.notification_channels:
                    notifier = self.notification_channels[channel]
                    try:
                        if notifier.send_alert(alert_data):
                            self._log_notification(alert_id, channel, 'sent')
                            success_count += 1
                        else:
                            self._log_notification(alert_id, channel, 'failed')
                    except Exception as e:
                        logger.error(f"Failed to send {channel} notification: {e}")
                        self._log_notification(alert_id, channel, 'failed', str(e))
            
            return success_count > 0
            
        except Exception as e:
            logger.error(f"Failed to send notifications: {e}")
            return False
    
    def _get_alert_details(self, alert_id: int) -> Optional[Dict]:
        """Get alert details for notification"""
        try:
            with data_manager.get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT a.*, m.location, m.zone_id, z.zone_name
                    FROM alerts a
                    LEFT JOIN meters m ON a.meter_id = m.meter_id
                    LEFT JOIN zones z ON m.zone_id = z.zone_id
                    WHERE a.id = ?
                """, (alert_id,))
                
                row = cursor.fetchone()
                if row:
                    return dict(row)
                return None
                
        except Exception as e:
            logger.error(f"Failed to get alert details: {e}")
            return None
    
    def _log_notification(self, alert_id: int, channel: str, status: str, error: str = None):
        """Log notification attempt"""
        try:
            with data_manager.get_connection() as conn:
                conn.execute("""
                    INSERT INTO alert_notifications 
                    (alert_id, notification_type, status, error_message)
                    VALUES (?, ?, ?, ?)
                """, (alert_id, channel, status, error))
                conn.commit()
                
        except Exception as e:
            logger.error(f"Failed to log notification: {e}")
    
    def get_active_alerts(self, limit: int = 50) -> List[Dict]:
        """Get all active alerts"""
        try:
            with data_manager.get_connection() as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.execute("""
                    SELECT a.*, m.location, m.zone_id, z.zone_name
                    FROM alerts a
                    LEFT JOIN meters m ON a.meter_id = m.meter_id
                    LEFT JOIN zones z ON m.zone_id = z.zone_id
                    WHERE a.status = 'active'
                    ORDER BY a.created_at DESC
                    LIMIT ?
                """, (limit,))
                
                return [dict(row) for row in cursor.fetchall()]
                
        except Exception as e:
            logger.error(f"Failed to get active alerts: {e}")
            return []
    
    def acknowledge_alert(self, alert_id: int, user: str = 'system') -> bool:
        """Acknowledge an alert"""
        try:
            with data_manager.get_connection() as conn:
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                conn.execute("""
                    UPDATE alerts 
                    SET status = 'acknowledged', acknowledged_by = ?, acknowledged_at = ?
                    WHERE id = ?
                """, (user, timestamp, alert_id))
                conn.commit()
                
                logger.info(f"Alert {alert_id} acknowledged by {user}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to acknowledge alert: {e}")
            return False
    
    def resolve_alert(self, alert_id: int, user: str = 'system') -> bool:
        """Resolve an alert"""
        try:
            with data_manager.get_connection() as conn:
                timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                conn.execute("""
                    UPDATE alerts 
                    SET status = 'resolved', resolved_by = ?, resolved_at = ?
                    WHERE id = ?
                """, (user, timestamp, alert_id))
                conn.commit()
                
                logger.info(f"Alert {alert_id} resolved by {user}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to resolve alert: {e}")
            return False

class EmailNotifier:
    """Email notification handler"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.recipients = [
            'operations@thiwasco.co.ke',
            'maintenance@thiwasco.co.ke',
            'manager@thiwasco.co.ke'
        ]
    
    def send_alert(self, alert_data: Dict) -> bool:
        """Send email alert"""
        try:
            msg = MIMEMultipart()
            msg['From'] = self.config['from_email']
            msg['To'] = ', '.join(self.recipients)
            msg['Subject'] = f"THIWASCO Alert: {alert_data['title']}"
            
            # Create HTML email body
            body = self._create_email_body(alert_data)
            msg.attach(MIMEText(body, 'html'))
            
            # Send email
            server = smtplib.SMTP(self.config['smtp_server'], self.config['smtp_port'])
            server.starttls()
            server.login(self.config['username'], self.config['password'])
            server.send_message(msg)
            server.quit()
            
            logger.info(f"Email alert sent for {alert_data['meter_id']}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send email: {e}")
            return False
    
    def _create_email_body(self, alert_data: Dict) -> str:
        """Create HTML email body"""
        severity_colors = {
            'low': '#28a745',
            'medium': '#ffc107', 
            'high': '#fd7e14',
            'critical': '#dc3545'
        }
        
        color = severity_colors.get(alert_data['severity'], '#6c757d')
        
        return f"""
        <html>
        <body style="font-family: Arial, sans-serif; margin: 0; padding: 20px; background-color: #f8f9fa;">
            <div style="max-width: 600px; margin: 0 auto; background: white; padding: 30px; border-radius: 8px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                <div style="text-align: center; margin-bottom: 30px;">
                    <h1 style="color: #0d2b52; margin: 0;">THIWASCO</h1>
                    <p style="color: #6c757d; margin: 5px 0;">Water Leak Detection System</p>
                </div>
                
                <div style="border-left: 4px solid {color}; padding: 20px; margin: 20px 0; background-color: #f8f9fa;">
                    <h2 style="color: {color}; margin: 0 0 10px 0;">{alert_data['title']}</h2>
                    <p style="color: #495057; margin: 0; font-size: 16px;">{alert_data['message']}</p>
                </div>
                
                <div style="background: #f8f9fa; padding: 20px; border-radius: 5px; margin: 20px 0;">
                    <h3 style="color: #495057; margin: 0 0 15px 0;">Alert Details</h3>
                    <table style="width: 100%; border-collapse: collapse;">
                        <tr>
                            <td style="padding: 8px; border-bottom: 1px solid #dee2e6; font-weight: bold;">Meter ID:</td>
                            <td style="padding: 8px; border-bottom: 1px solid #dee2e6;">{alert_data['meter_id']}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; border-bottom: 1px solid #dee2e6; font-weight: bold;">Location:</td>
                            <td style="padding: 8px; border-bottom: 1px solid #dee2e6;">{alert_data.get('location', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; border-bottom: 1px solid #dee2e6; font-weight: bold;">Zone:</td>
                            <td style="padding: 8px; border-bottom: 1px solid #dee2e6;">{alert_data.get('zone_name', 'N/A')}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; border-bottom: 1px solid #dee2e6; font-weight: bold;">Severity:</td>
                            <td style="padding: 8px; border-bottom: 1px solid #dee2e6; color: {color}; font-weight: bold;">{alert_data['severity'].upper()}</td>
                        </tr>
                        <tr>
                            <td style="padding: 8px; border-bottom: 1px solid #dee2e6; font-weight: bold;">Time:</td>
                            <td style="padding: 8px; border-bottom: 1px solid #dee2e6;">{alert_data['created_at']}</td>
                        </tr>
                    </table>
                </div>
                
                <div style="text-align: center; margin-top: 30px;">
                    <p style="color: #6c757d; font-size: 14px;">
                        This is an automated alert from the THIWASCO Leak Detection System.<br>
                        Please check the dashboard for more details.
                    </p>
                </div>
            </div>
        </body>
        </html>
        """

class SMSNotifier:
    """SMS notification handler"""
    
    def __init__(self, config: Dict):
        self.config = config
        self.recipients = [
            '+254712345678',  # Operations Manager
            '+254723456789',  # Maintenance Team
            '+254734567890'   # System Administrator
        ]
    
    def send_alert(self, alert_data: Dict) -> bool:
        """Send SMS alert"""
        try:
            # For demo purposes, just log the SMS
            message = self._create_sms_message(alert_data)
            
            for recipient in self.recipients:
                logger.info(f"SMS to {recipient}: {message}")
                # In production, integrate with Twilio or other SMS service
                # self._send_twilio_sms(recipient, message)
            
            return True
            
        except Exception as e:
            logger.error(f"Failed to send SMS: {e}")
            return False
    
    def _create_sms_message(self, alert_data: Dict) -> str:
        """Create SMS message"""
        return f"""
THIWASCO ALERT: {alert_data['title']}
Meter: {alert_data['meter_id']}
Location: {alert_data.get('location', 'N/A')}
Severity: {alert_data['severity'].upper()}
Time: {alert_data['created_at']}
Check dashboard for details.
        """.strip()
    
    def _send_twilio_sms(self, to: str, message: str):
        """Send SMS via Twilio (placeholder)"""
        from twilio.rest import Client
        
        client = Client(self.config['account_sid'], self.config['auth_token'])
        client.messages.create(
            body=message,
            from_=self.config['from_number'],
            to=to
        )

class WebhookNotifier:
    """Webhook notification handler"""
    
    def __init__(self, config: Dict):
        self.config = config
    
    def send_alert(self, alert_data: Dict) -> bool:
        """Send webhook alert"""
        try:
            payload = {
                'alert_id': alert_data['id'],
                'meter_id': alert_data['meter_id'],
                'title': alert_data['title'],
                'message': alert_data['message'],
                'severity': alert_data['severity'],
                'location': alert_data.get('location'),
                'zone': alert_data.get('zone_name'),
                'timestamp': alert_data['created_at'],
                'source': 'thiwasco-leak-detection'
            }
            
            response = requests.post(
                self.config['url'],
                json=payload,
                timeout=self.config.get('timeout', 10),
                headers={'Content-Type': 'application/json'}
            )
            
            response.raise_for_status()
            logger.info(f"Webhook alert sent for {alert_data['meter_id']}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to send webhook: {e}")
            return False

# Global alert manager instance
alert_manager = AlertManager()
