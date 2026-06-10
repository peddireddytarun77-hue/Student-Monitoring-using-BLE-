import os, logging
from datetime import datetime, date, timedelta

# ── LOGGING ──────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    handlers=[
        logging.FileHandler("backend.log"),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger("NEXUS-Backend")

# ── SUPABASE CONFIG ──────────────────────────────
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    logger.critical("❌ SUPABASE_URL or SUPABASE_KEY not found in environment variables!")
    raise EnvironmentError("Missing Supabase configuration. Copy .env.example to .env and fill in your credentials.")

# ── JWT & SECURITY CONFIG ────────────────────────
SECRET_KEY = os.environ.get("SECRET_KEY")
if not SECRET_KEY:
    logger.critical("❌ SECRET_KEY not found! Generate one with: python -c \"import secrets; print(secrets.token_urlsafe(32))\"")
    raise EnvironmentError("Missing SECRET_KEY in .env file.")

JWT_SECRET = os.environ.get("JWT_SECRET", SECRET_KEY)
JWT_ALGORITHM = "HS256"
JWT_EXPIRATION_HOURS = 24

# ── ADMIN PASSWORD (hashed, should be set via .env) ────────────────────────
ADMIN_PASSWORD_HASH = os.environ.get("ADMIN_PASSWORD_HASH")
if not ADMIN_PASSWORD_HASH:
    logger.warning("⚠️  ADMIN_PASSWORD_HASH not set. Generate with: python -c \"from werkzeug.security import generate_password_hash; print(generate_password_hash('your_password'))\"")

# ── FILE STORAGE ────────────────────────────────
FACES_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'faces')
os.makedirs(FACES_DIR, exist_ok=True)

# ── CAMERA & RECOGNITION CONFIG ─────────────────────────
CAMERA_INDEX = int(os.environ.get("CAMERA_INDEX", 0))
FACE_THRESHOLD = float(os.environ.get("FACE_THRESHOLD", 0.50))
BLE_SCAN_TIMEOUT = float(os.environ.get("BLE_SCAN_TIMEOUT", 5.0))

# ── ATTENDANCE WINDOW & BREAKS ──────────────────
ATT_START_H, ATT_START_M = 9, 0
ATT_END_H, ATT_END_M = 16, 50
BREAKS = [
    (10, 40, 10, 50),
    (12, 30, 13, 20),
    (15, 0, 15, 10)
]

TIMELAPSE_SECONDS = 60

# ── SECURITY SETTINGS ────────────────────────────
CORS_ORIGINS = os.environ.get("CORS_ORIGINS", "http://localhost:5000").split(",")
SESSION_COOKIE_SECURE = os.environ.get("FLASK_ENV", "development") == "production"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
PERMANENT_SESSION_LIFETIME = timedelta(hours=24)

# ── RATE LIMITING CONFIG ────────────────────────
RATE_LIMIT_STORAGE_URL = os.environ.get("RATE_LIMIT_STORAGE_URL", "memory://")

logger.info("✅ Configuration loaded successfully")
