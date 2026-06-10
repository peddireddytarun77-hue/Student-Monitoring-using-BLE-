import os, logging
from datetime import datetime, date

# ── LOGGING ──────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler("backend.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("NEXUS-Backend")

# ── CONFIG ───────────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    logger.critical("SUPABASE_URL or SUPABASE_KEY not found in environment variables!")
    raise EnvironmentError("Missing Supabase configuration. Check your .env file.")

FACES_DIR        = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'faces')
os.makedirs(FACES_DIR, exist_ok=True)

CAMERA_INDEX     = 0
FACE_THRESHOLD   = 0.50
BLE_SCAN_TIMEOUT = 5.0

# ── Attendance Window & Breaks ───────────────
ATT_START_H, ATT_START_M = 9,  0
ATT_END_H,   ATT_END_M   = 16, 50
BREAKS = [ (10, 40, 10, 50), (12, 30, 13, 20), (15, 0, 15, 10) ]

TIMELAPSE_SECONDS = 60
