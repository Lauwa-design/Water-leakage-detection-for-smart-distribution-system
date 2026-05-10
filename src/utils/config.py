from pathlib import Path

# Paths
BASE_DIR = Path(__file__).resolve().parents[2]
RAW_DIR = BASE_DIR / "data" / "raw"
PROCESSED_DIR = BASE_DIR / "data" / "processed"
MODELS_DIR = BASE_DIR / "outputs" / "models"
NETWORK_FILE = BASE_DIR / "data" / "external" / "hanoi_network.inp"

for p in [RAW_DIR, PROCESSED_DIR, MODELS_DIR]:
    p.mkdir(parents=True, exist_ok=True)

# Simulation Settings
RANDOM_STATE = 42
NUM_SCENARIOS = 3000
LEAK_PROBABILITY = 0.5
# Honeywell Q4000 electromagnetic water meter reference profile.
# Official product page values used directly:
# - sizes: 50 mm to 200 mm
# - flow rate envelope: 0.16 m3/h to 1250 m3/h
# - internal sampling rate: 0.5 s
# - battery life: 10 years
# - ingress protection: IP68
METER_MODEL = "Honeywell Q4000 Electromagnetic Water Meter"
METER_SIZE_OPTIONS_MM = (50, 80, 100, 150, 200)
METER_MIN_FLOW_M3H = 0.16
METER_MAX_FLOW_M3H = 1250.0
METER_INTERNAL_SAMPLE_SECONDS = 0.5
METER_OUTPUT_INTERVAL_SECONDS = 300
METER_BATTERY_LIFE_YEARS = 10
METER_INGRESS_RATING = "IP68"

# Modeling assumptions used to keep hydraulic output realistic for DMA/bulk use.
METER_VELOCITY_RANGE_MS = (0.05, 3.0)
PRESSURE_RANGE = (0, 16)  # bar, hydraulic context variable
PRESSURE_NOISE_STD = 0.005  # Reduced from 0.008 for better signal-to-noise ratio
FLOW_RANGE = (
    METER_MIN_FLOW_M3H * (1000.0 / 60.0),
    METER_MAX_FLOW_M3H * (1000.0 / 60.0),
)  # L/min
FLOW_NOISE_STD = 0.01  # Reduced from 0.015 for better signal-to-noise ratio
TEMPERATURE_RANGE = (0, 50)  # contextual network temperature range
DEMAND_NOISE_STD = 0.005  # Reduced from 0.008

# Meter cadence
METER_READING_INTERVAL = METER_OUTPUT_INTERVAL_SECONDS
DAILY_READINGS = 288

# Baseline ranges for scenario generation
DMA_BASELINE_MIN = 180.0
DMA_BASELINE_MAX = 420.0
PRESSURE_BASELINE_MIN = 3.5
PRESSURE_BASELINE_MAX = 5.5

# Leak settings - Wider separation between types for better multiclass distinction
LEAK_MAG_MIN = 5.0
LEAK_MAG_MAX = 180.0
SLOW_LEAK_THRESHOLD = 20  # 20-59 L/min
MODERATE_LEAK_THRESHOLD = 80  # 80-139 L/min (20 L/min gap from slow)
EXTREME_LEAK_THRESHOLD = 140  # 140-180 L/min (20 L/min gap from moderate)

# Filenames
BINARY_MODEL_FILE = MODELS_DIR / "leak_binary.joblib"
MULTI_MODEL_FILE = MODELS_DIR / "leak_multi.joblib"

