"""
THIWASCO Leak Detection Backend
Clean separation of concerns - no UI logic
"""

from .leak_detector import LeakDetector, predict_leak, batch_predict, LeakPrediction, LeakSeverity

# Import MySQL data manager by default
try:
    from .data_manager_mysql import data_manager
    print("Using MySQL database")
except ImportError as e:
    print(f"MySQL not available, falling back to SQLite: {e}")
    from .data_manager import data_manager

from .prediction_service import PredictionService, prediction_service
from .realtime_simulator import RealTimeSimulator, realtime_simulator
from .alert_manager import AlertManager, alert_manager

__all__ = [
    'LeakDetector',
    'predict_leak', 
    'batch_predict',
    'LeakPrediction',
    'LeakSeverity',
    'data_manager',
    'PredictionService',
    'prediction_service',
    'RealTimeSimulator',
    'realtime_simulator',
    'AlertManager',
    'alert_manager'
]
