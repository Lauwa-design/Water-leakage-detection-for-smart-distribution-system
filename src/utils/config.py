"""
config.py — THIWASCO Leak Detection
Single source of truth for ALL paths, parameters and schema.
Every other file imports from here. Never hardcode anything elsewhere.

Location : src/utils/config.py
"""

from pathlib import Path

# PROJECT ROOT
# src/utils/config.py
# .parent        → src/utils/
# .parent.parent → src/
# .parent.parent.parent → project root  ✓
BASE_DIR = Path(__file__).resolve().parent.parent.parent

# DIRECTORY PATHS
DATA_DIR          = BASE_DIR / 'data'
RAW_SCENARIOS_DIR = DATA_DIR / 'raw'  / 'scenarios'
PROCESSED_DIR     = DATA_DIR / 'processed'
EXTERNAL_DIR      = DATA_DIR / 'external'

OUTPUTS_DIR       = BASE_DIR / 'outputs'
MODELS_DIR        = OUTPUTS_DIR / 'models'
FIGURES_DIR       = OUTPUTS_DIR / 'figures'
METRICS_DIR       = OUTPUTS_DIR / 'metrics'


# KEY FILES

NETWORK_FILE       = EXTERNAL_DIR  / 'hanoi_network.inp'
MERGED_DATASET     = PROCESSED_DIR / 'merged_dataset.csv'
ENGINEERED_DATASET = PROCESSED_DIR / 'engineered_features.csv'

# Saved by train_model.py — loaded by Streamlit app
BINARY_MODEL_FILE  = MODELS_DIR / 'random_forest_binary.pkl'
MULTI_MODEL_FILE   = MODELS_DIR / 'random_forest_multi.pkl'
SCALER_FILE        = MODELS_DIR / 'scaler.pkl'
LABEL_ENCODER_FILE = MODELS_DIR / 'label_encoder.pkl'
FEATURE_LIST_FILE  = MODELS_DIR / 'feature_list.json'
BASELINE_FILE      = MODELS_DIR / 'baseline_stats.json'
METRICS_FILE       = METRICS_DIR / 'evaluation_metrics.json'

# SIMULATION PARAMETERS
SIM_DURATION_HOURS = 24
TIMESTEP_HOURS     = 1
TIMESTEPS_PER_DAY  = 24


# SCENARIO GENERATION
NUM_SCENARIOS    = 1000
LEAK_PROBABILITY = 0.5

LEAK_MAG_MIN = 0.005   # m³/s
LEAK_MAG_MAX = 0.020   # m³/s

LEAK_START_MIN    = 0
LEAK_START_MAX    = 20
LEAK_DURATION_MIN = 2
LEAK_DURATION_MAX = 12

# Must sum to 1.0
LEAK_TYPES = {
    'continuous':   0.60,
    'pressure':     0.25,
    'demand':       0.10,
    'intermittent': 0.05,
}


# NIGHT / DAY WINDOWS
NIGHT_HOURS = list(range(0, 6))    # 00:00–05:00
DAY_HOURS   = list(range(6, 22))   # 06:00–21:00

# DATASET SCHEMA
# Contract between all pipeline stages:
#   generate_scenarios → raw CSVs per scenario folder
#   data_builder       → ID + TARGET + RAW_FEATURE columns
#   feature_extractor  → ENGINEERED columns
#   train_model        → validates ENGINEERED columns before training
#   app                → loads FEATURE_LIST_FILE saved by train_model

ID_COLUMNS = ['scenario', 'time_index']

TARGET_COLUMNS = [
    'scenario_has_leak',        # int  0|1  — scenario level
    'leak_type',                # str       — leak type or no_leak
    'leak_score',               # float 0–1 — normalised severity
    'leak_active_at_timestep',  # int  0|1  — timestep level (PRIMARY label)
]

RAW_FEATURE_COLUMNS = [
    'mean_demand', 'max_demand', 'min_demand', 'std_demand',
    'demand_range', 'total_demand',
    'mean_pressure', 'max_pressure', 'min_pressure', 'std_pressure',
    'pressure_range',
    'mean_flow', 'max_flow', 'min_flow', 'std_flow',
    'flow_range', 'total_flow',
    'flow_demand_ratio',
    'night_flow_min', 'night_flow_mean', 'night_flow_std',
    'day_flow_mean', 'night_to_day_ratio',
    'flow_trend_slope', 'flow_rolling_mean_avg',
    'flow_rolling_std_avg', 'flow_cv',
]

ENGINEERED_FEATURE_COLUMNS = [
    'night_flow_deviation', 'night_flow_anomaly', 'night_to_day_ratio',
    'pressure_deviation', 'pressure_drop_alert',
    'pressure_drop_deviation', 'pressure_cv',
    'flow_deviation', 'high_flow_alert', 'flow_cv', 'flow_stability',
    'demand_deviation', 'peak_demand_ratio',
    'flow_demand_ratio', 'hydraulic_imbalance', 'mass_balance_error',
    'flow_pressure_ratio', 'demand_pressure_ratio',
    'pressure_drop', 'flow_anomaly_score',
]

# MODEL PARAMETERS

RANDOM_STATE = 42

# Split BY SCENARIO ID — prevents data leakage
TEST_SIZE  = 0.15
VAL_SIZE   = 0.15
TRAIN_SIZE = 0.70

RF_N_ESTIMATORS      = 200
RF_MAX_DEPTH         = 15
RF_MIN_SAMPLES_SPLIT = 5
RF_MIN_SAMPLES_LEAF  = 2
RF_CLASS_WEIGHT      = 'balanced'
RF_N_JOBS            = -1

CV_FOLDS = 5

# ================================================================
# DETECTION THRESHOLDS (used by Streamlit app)
# ================================================================
LEAK_THRESHOLD_HIGH   = 0.7   # trigger alert
LEAK_THRESHOLD_MEDIUM = 0.4   # monitor
LEAK_THRESHOLD_LOW    = 0.0   # normal

# ================================================================
# EMAIL NOTIFICATION (used by app/components/notifier.py)
# ================================================================
ALERT_EMAIL_SUBJECT = 'THIWASCO ALERT: Leak Detected in Water Network'
ALERT_SMTP_PORT     = 587

# ================================================================
# VISUALISATION
# ================================================================
FIGURE_DPI     = 150
FIGURE_SIZE    = (10, 6)
COLOR_NO_LEAK  = '#2ecc71'
COLOR_LEAK     = '#e74c3c'
COLOR_DETECTED = '#3498db'
COLOR_MONITOR  = '#f39c12'

# ================================================================
# UTILITY FUNCTIONS
# ================================================================

def create_directories():
    """Create all project directories. Call once at pipeline start."""
    dirs = [
        RAW_SCENARIOS_DIR, PROCESSED_DIR, EXTERNAL_DIR,
        MODELS_DIR, FIGURES_DIR, METRICS_DIR,
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    print("✓ All directories verified/created")


def verify_network_file() -> bool:
    """Check EPANET network file exists before simulation."""
    if NETWORK_FILE.exists():
        print(f"✓ Network file found: {NETWORK_FILE}")
        return True
    print(f"✗ Network file NOT found: {NETWORK_FILE}")
    print("  → Place hanoi_network.inp in data/external/")
    return False


def print_config():
    """Print active configuration summary."""
    print("\n" + "=" * 55)
    print("THIWASCO LEAK DETECTION — CONFIGURATION")
    print("=" * 55)
    print(f"  Base dir         : {BASE_DIR}")
    print(f"  Network file     : {NETWORK_FILE}")
    print(f"  Raw scenarios    : {RAW_SCENARIOS_DIR}")
    print(f"  Processed data   : {PROCESSED_DIR}")
    print(f"  Models           : {MODELS_DIR}")
    print(f"  Scenarios        : {NUM_SCENARIOS}")
    print(f"  Leak probability : {LEAK_PROBABILITY * 100:.0f}%")
    print(f"  Timesteps/day    : {TIMESTEPS_PER_DAY}")
    print(f"  RF estimators    : {RF_N_ESTIMATORS}")
    print(f"  Random seed      : {RANDOM_STATE}")
    print(f"  Alert threshold  : {LEAK_THRESHOLD_HIGH}")
    print("=" * 55 + "\n")


if __name__ == '__main__':
    print_config()
    create_directories()
    verify_network_file()