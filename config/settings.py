from pathlib import Path
import os
import shutil
from dotenv import load_dotenv

# -----------------------------
# Base Directory
# -----------------------------
BASE_DIR = Path(__file__).resolve().parent.parent
PROJECT_ROOT = BASE_DIR.parent

# -----------------------------
# Load Environment Variables
# -----------------------------
_env_path = BASE_DIR / ".env"
if _env_path.exists():
    load_dotenv(dotenv_path=_env_path)
else:
    # Try project root (e.g. when running from repo root)
    load_dotenv(dotenv_path=BASE_DIR.parent / ".env")


def _env_list(key: str, default: str = "") -> list[str]:
    """Read comma-separated list from .env."""
    value = os.getenv(key, default).strip()
    return [v.strip() for v in value.split(",") if v.strip()]


# Dev fallback hosts so DisallowedHost is avoided even if .env is missing or ALLOWED_HOSTS empty
_DEFAULT_DEV_HOSTS = ["127.0.0.1", "localhost",
                      "127.0.0.1:8000", "localhost:8000"]

# -----------------------------
# Security Settings
# -----------------------------
_SECRET_KEY = os.getenv("SECRET_KEY")
if not _SECRET_KEY and os.getenv("DEBUG", "False").lower() in ("true", "1", "yes"):
    # Allow a dev-only default only when DEBUG is explicitly enabled
    _SECRET_KEY = "dev-secret-key-do-not-use-in-production"
if not _SECRET_KEY:
    raise RuntimeError(
        "SECRET_KEY environment variable is required. "
        "Set it in .env or export SECRET_KEY=your-secret-key (never use the dev default in production)."
    )
SECRET_KEY = _SECRET_KEY
DEBUG = os.getenv("DEBUG", "False") == "True"
ALLOWED_HOSTS = _env_list("ALLOWED_HOSTS") or []
# In debug/development, allow LAN/IP access without frequent ALLOWED_HOSTS edits.
if DEBUG:
    ALLOWED_HOSTS = ["*"]

# -----------------------------
# Installed Apps
# -----------------------------
INSTALLED_APPS = [
    # Django Default Apps
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    'django_filters',  # Add this line


    # Third-party
    "corsheaders",
    "rest_framework",
    "rest_framework.authtoken",

    # Local apps
    "users",
    "visitors",
    'logs',
    "detentions",
    "cameras",
    "warehouse",
    "ml.apps.MlConfig",
]

# -----------------------------
# Middleware
# -----------------------------
MIDDLEWARE = [
    "corsheaders.middleware.CorsMiddleware",  # Must be first
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # for Logs
    'logs.middleware.ActivityLogMiddleware',
]

# -----------------------------
# CORS Settings
# -----------------------------
CORS_ALLOW_ALL_ORIGINS = os.getenv("CORS_ALLOW_ALL_ORIGINS", "True") == "True"
if not CORS_ALLOW_ALL_ORIGINS:
    CORS_ALLOWED_ORIGINS = _env_list("CORS_ALLOWED_ORIGINS")
CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "origin",
    "user-agent",
    "x-requested-with",
]
CORS_EXPOSE_HEADERS = ["Content-Type", "Authorization"]

# -----------------------------
# URL & Templates
# -----------------------------
ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# -----------------------------
# Database
# -----------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME"),
        "USER": os.getenv("DB_USER"),
        "PASSWORD": os.getenv("DB_PASSWORD"),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
    }
}

# -----------------------------
# REST Framework
# -----------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
        "rest_framework.authentication.SessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
}

# -----------------------------
# Auth
# -----------------------------
AUTH_USER_MODEL = "users.User"

# Password validation
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# -----------------------------
# Internationalization
# -----------------------------
LANGUAGE_CODE = "en-us"
TIME_ZONE = 'Asia/Karachi'
USE_I18N = True
USE_TZ = True

# -----------------------------
# Static & Media
# -----------------------------
STATIC_URL = "/static/"
MEDIA_URL = "/media/"
MEDIA_ROOT = os.path.join(BASE_DIR, "media")

# File upload settings for detention memo uploads (photos, documents, videos).
# Note: These are for Django — nginx has a separate client_max_body_size limit.
# Default Django limits are 2.5MB for file and 2.5MB for form data.
# We increase both to 100MB to handle large image uploads that will be compressed.
FILE_UPLOAD_MAX_MEMORY_SIZE = int(
    os.getenv("FILE_UPLOAD_MAX_MEMORY_SIZE", str(100 * 1024 * 1024)))  # 100MB
DATA_UPLOAD_MAX_MEMORY_SIZE = int(
    os.getenv("DATA_UPLOAD_MAX_MEMORY_SIZE", str(100 * 1024 * 1024)))  # 100MB

# Images are automatically compressed on the backend before storage
# This reduces stored file sizes significantly (typically 70-85% reduction)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

def _resolve_ffmpeg_path() -> str:
    """Full path to ffmpeg.exe (bundled in repo, then .env, then PATH)."""
    bundled = PROJECT_ROOT / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"
    if bundled.is_file():
        return str(bundled)
    custom = os.getenv("FFMPEG_PATH", "").strip()
    if custom and os.path.isfile(custom):
        return custom
    on_path = shutil.which("ffmpeg")
    if on_path:
        return on_path
    return ""


FFMPEG_PATH = _resolve_ffmpeg_path()

# -----------------------------
# ML inference service (backend/ml_service/api_server.py)
# -----------------------------
ML_SERVICE_URL = os.getenv("ML_SERVICE_URL", "http://127.0.0.1:8100").strip()
ML_SERVICE_TIMEOUT = int(os.getenv("ML_SERVICE_TIMEOUT", "60"))


def _resolve_ml_root() -> str:
    """Prefer backend/ml_service; honor ML_ROOT_PATH when it lives under backend or repo root."""
    default = str((BASE_DIR / "ml_service").resolve())
    configured = os.getenv("ML_ROOT_PATH", "").strip()
    if not configured:
        return default
    try:
        resolved = Path(configured)
        if not resolved.is_absolute():
            resolved = (BASE_DIR / resolved).resolve()
        else:
            resolved = resolved.resolve()
        for root in (BASE_DIR.resolve(), PROJECT_ROOT.resolve()):
            if resolved.is_relative_to(root):
                return str(resolved)
    except (ValueError, OSError):
        pass
    legacy = (PROJECT_ROOT / "ml_service").resolve()
    if legacy.is_dir():
        return str(legacy)
    return default


ML_ROOT_PATH = _resolve_ml_root()
ML_KNOWN_FACES_DIR = os.getenv("ML_KNOWN_FACES_DIR", os.path.join(ML_ROOT_PATH, "known_faces"))
ML_AUTO_START = os.getenv("ML_AUTO_START", "True").lower() in ("true", "1", "yes")
FRONTEND_ORIGIN = os.getenv("FRONTEND_ORIGIN", "http://localhost:5173").rstrip("/")

# Background detection worker (saves ML readings without browser open)
DETECTION_WORKER_ENABLED = os.getenv("DETECTION_WORKER_ENABLED", "True").lower() in ("true", "1", "yes")
DETECTION_WORKER_AUTO_START = os.getenv("DETECTION_WORKER_AUTO_START", "True").lower() in ("true", "1", "yes")
DETECTION_WORKER_INTERVAL_SEC = float(os.getenv("DETECTION_WORKER_INTERVAL_SEC", "2"))
DETECTION_WORKER_CAMERA_REFRESH_SEC = int(os.getenv("DETECTION_WORKER_CAMERA_REFRESH_SEC", "60"))

# CCTV stream FPS for ffmpeg proxy (RTSP URLs are built dynamically from NVR DB records)
CAMERA_STREAM_FPS = int(os.getenv("ML_LIVE_STREAM_FPS", "25"))
