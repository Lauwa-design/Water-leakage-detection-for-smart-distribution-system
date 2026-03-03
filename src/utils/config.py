"""
Configuration settings for THIWASCO Leak Detection Project
Modify these settings to customize the project
"""

import os
from pathlib import Path

# ============================================
# PROJECT PATHS
# ============================================

# Base directory (where this file is located)
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Data directories
DATA_DIR = BASE_DIR / 'data'
RAW_DATA_DIR = DATA_DIR / 'raw' / 'scenarios'
PROCESSED_DATA_DIR = DATA_DIR / 'processed'
EXTERNAL_DATA_DIR = DATA_DIR / 'external'

# Model directories
MODELS_DIR = BASE_DIR / 'models'

# Reports directories
REPORTS_DIR = BASE_DIR / 'reports'
FIGURES_DIR = REPORTS_DIR / 'figures'
METRICS_DIR = REPORTS_DIR / 'metrics'

# Network file
NETWORK_FILE = EXTERNAL_DATA_DIR / 'hanoi_network.inp'

# ============================================
# SIMULATION PARAMETERS
# ============================================

# Simulation duration
SIM_DURATION_HOURS = 24  # 24 hours per scenario

# Time resolution
TIMESTEP_MINUTES = 30  # 30-minute intervals (48 timesteps per day)

# Simulation mode
# 'DD' = Demand Driven (faster, simpler)
# 'PDD' = Pressure Dependent Demand (more realistic)
SIMULATION_MODE = 'PDD'

# ============================================
# DATASET GENERATION PARAMETERS
# ============================================

# Number of scenarios to generate
NUM_SCENARIOS = 100  # Start with 100, can increase later

# Probability that a scenario includes a leak
LEAK_PROBABILITY = 0.7  # 70% of scenarios will have leaks

# Leak parameters (following LeakDB methodology)
LEAK_DIAMETER_MIN = 0.02  # Minimum leak diameter in meters (2 cm)
LEAK_DIAMETER_MAX = 0.20  # Maximum leak diameter in meters (20 cm)

LEAK_START_HOUR_MIN = 1   # Earliest leak can start (hour 1)
LEAK_START_HOUR_MAX = 18  # Latest leak can start (hour 18)

LEAK_DURATION_MIN = 2     # Minimum leak duration in hours
LEAK_DURATION_MAX = 8     # Maximum leak duration in hours

# ============================================
# FEATURE ENGINEERING PARAMETERS
# ============================================

# Time windows for features
NIGHT_START_HOUR = 22  # 22:00 (10 PM)
NIGHT_END_HOUR = 6     # 06:00 (6 AM)

DAY_START_HOUR = 6     # 06:00 (6 AM)
DAY_END_HOUR = 22      # 22:00 (10 PM)

# Feature list
FEATURE_COLUMNS = [
    'night_flow_ratio',      # Night flow / day flow
    'daily_variance',        # Standard deviation of flow
    'trend',                 # Linear trend over time
    'max_increase',          # Maximum hourly increase
    'coefficient_variation', # CV = std/mean
    'flow_p50',             # 50th percentile flow
    'flow_p95',             # 95th percentile flow
    'mean_pressure',        # Average pressure
    'pressure_variance'     # Pressure variability
]

# ============================================
# MODEL PARAMETERS
# ============================================

# Train/test split
TEST_SIZE = 0.2        # 20% for testing
RANDOM_STATE = 42      # For reproducibility

# Random Forest parameters (starting values)
RF_N_ESTIMATORS = 100  # Number of trees
RF_MAX_DEPTH = 15      # Maximum depth of trees
RF_MIN_SAMPLES_SPLIT = 10
RF_MIN_SAMPLES_LEAF = 5
RF_CLASS_WEIGHT = 'balanced'  # Handle imbalanced data

# Cross-validation
CV_FOLDS = 5  # 5-fold cross-validation

# SMOTE for handling class imbalance
USE_SMOTE = True
SMOTE_RATIO = 1.0  # 1:1 ratio after oversampling

# ============================================
# EVALUATION PARAMETERS
# ============================================

# Threshold for leak detection
ANOMALY_THRESHOLD_HIGH = 0.7   # High confidence leak
ANOMALY_THRESHOLD_MEDIUM = 0.3 # Monitor zone
ANOMALY_THRESHOLD_LOW = 0.0    # Normal operation

# Metrics to track
METRICS_TO_TRACK = [
    'recall',      # Sensitivity (most important for leaks)
    'precision',   # Positive predictive value
    'f1_score',    # Harmonic mean
    'auc_roc',     # Area under ROC curve
    'accuracy'     # Overall accuracy
]

# ============================================
# VISUALIZATION PARAMETERS
# ============================================

# Plot settings
FIGURE_DPI = 300       # High resolution for thesis
FIGURE_SIZE = (10, 6)  # Default figure size

# Color scheme
COLOR_NO_LEAK = '#2ecc71'  # Green
COLOR_LEAK = '#e74c3c'     # Red
COLOR_DETECTED = '#3498db' # Blue

# ============================================
# LOGGING
# ============================================

# Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
LOG_LEVEL = 'INFO'

# ============================================
# COMPUTATIONAL SETTINGS
# ============================================

# Number of CPU cores to use
# -1 = use all available cores
# 1 = use single core
N_JOBS = -1

# Memory management
MAX_MEMORY_GB = 8  # Maximum memory to use in GB


# ============================================
# UTILITY FUNCTIONS
# ============================================

def create_directories():
    """Create all necessary directories if they don't exist"""
    directories = [
        DATA_DIR,
        RAW_DATA_DIR,
        PROCESSED_DATA_DIR,
        EXTERNAL_DATA_DIR,
        MODELS_DIR,
        REPORTS_DIR,
        FIGURES_DIR,
        METRICS_DIR
    ]
    
    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)
    
    print("✓ All directories created/verified")


def verify_network_file():
    """Check if network file exists"""
    if NETWORK_FILE.exists():
        print(f"✓ Network file found: {NETWORK_FILE}")
        return True
    else:
        print(f"✗ Network file NOT found: {NETWORK_FILE}")
        print("  Please copy Hanoi_CMH.inp to data/external/")
        return False


def print_config():
    """Print current configuration"""
    print("\n" + "="*50)
    print("THIWASCO LEAK DETECTION - CONFIGURATION")
    print("="*50)
    print(f"\nSimulation:")
    print(f"  Duration: {SIM_DURATION_HOURS} hours")
    print(f"  Timestep: {TIMESTEP_MINUTES} minutes")
    print(f"  Mode: {SIMULATION_MODE}")
    print(f"\nDataset:")
    print(f"  Scenarios: {NUM_SCENARIOS}")
    print(f"  Leak probability: {LEAK_PROBABILITY*100:.0f}%")
    print(f"\nModel:")
    print(f"  Algorithm: Random Forest")
    print(f"  Trees: {RF_N_ESTIMATORS}")
    print(f"  Max depth: {RF_MAX_DEPTH}")
    print(f"  Use SMOTE: {USE_SMOTE}")
    print(f"\nPaths:")
    print(f"  Base dir: {BASE_DIR}")
    print(f"  Network: {NETWORK_FILE}")
    print(f"  Output: {RAW_DATA_DIR}")
    print("="*50 + "\n")


if __name__ == '__main__':
    # Test configuration
    print_config()
    create_directories()
    verify_network_file()