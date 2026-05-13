"""Backend module for THIWASCO leak detection system."""

from backend.mysql_database_manager import MySQLDatabaseManager

# Create a global instance using MySQL
db_manager = MySQLDatabaseManager()

from .session_manager import SessionManager
session_manager = SessionManager(db_manager)

from .smart_meter_simulator import smart_meter_simulator, SmartMeterSimulator, LeakType, setup_sample_meters
from .realtime_feature_extractor import realtime_feature_extractor, RealtimeFeatureExtractor
from .ml_integration import ml_model, LeakDetectionModel

__all__ = [
    'db_manager', 'MySQLDatabaseManager',
    'session_manager', 'SessionManager',
    'smart_meter_simulator', 'SmartMeterSimulator', 'LeakType', 'setup_sample_meters',
    'realtime_feature_extractor', 'RealtimeFeatureExtractor',
    'ml_model', 'LeakDetectionModel',
]
