import os
from pathlib import Path

import dj_database_url
import sentry_sdk
from sentry_sdk.integrations.django import DjangoIntegration

# =========================
# BASE
# =========================

BASE_DIR = Path(__file__).resolve().parent.parent


# =========================
# SEGURIDAD / ENTORNO
# =========================


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "y", "on", "si", "sí"}


def _env_csv(name: str) -> list[str]:
    raw = os.environ.get(name)
    if not raw:
        return []
    return [x.strip() for x in str(raw).split(",") if x.strip()]


SECRET_KEY = (
    os.environ.get("DJANGO_SECRET_KEY") or os.environ.get("SECRET_KEY") or "django-insecure-cambia-esto-en-produccion"
)

_IS_RENDER = str(os.environ.get("RENDER") or "").strip().lower() in {"1", "true", "yes", "y"}
DEBUG = _env_bool("DJANGO_DEBUG", _env_bool("DEBUG", not _IS_RENDER))

PDF_MESSAGE_SANITIZE = _env_bool("PDF_MESSAGE_SANITIZE", _IS_RENDER)
DEBUG_TOOLBAR_ENABLED = DEBUG and _env_bool("DJANGO_DEBUG_TOOLBAR", False)
DEV_APPS_ENABLED = DEBUG and _env_bool("DJANGO_DEV_APPS", False)

SENTRY_DSN = os.environ.get("SENTRY_DSN", "")
if SENTRY_DSN:
    send_default_pii = str(os.environ.get("SENTRY_SEND_DEFAULT_PII") or "0").strip() == "1"
    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration()],
        send_default_pii=send_default_pii,
    )

_DEFAULT_ALLOWED_HOSTS = [
    "web-inversure-1.onrender.com",
    "inversurehomes.es",
    "www.inversurehomes.es",
    "app.inversurehomes.es",
]
if DEBUG:
    _DEFAULT_ALLOWED_HOSTS.extend(["localhost", "127.0.0.1", "[::1]"])
_ENV_ALLOWED_HOSTS = _env_csv("DJANGO_ALLOWED_HOSTS") + _env_csv("ALLOWED_HOSTS")
if _env_bool("DJANGO_ALLOWED_HOSTS_STRICT", False):
    ALLOWED_HOSTS = _ENV_ALLOWED_HOSTS or list(_DEFAULT_ALLOWED_HOSTS)
else:
    ALLOWED_HOSTS = list(dict.fromkeys(list(_DEFAULT_ALLOWED_HOSTS) + _ENV_ALLOWED_HOSTS))

# =========================
# CSRF (Render / Producción)
# =========================

_DEFAULT_CSRF_TRUSTED_ORIGINS = [
    "https://web-inversure-1.onrender.com",
    "https://inversurehomes.es",
    "https://www.inversurehomes.es",
    "https://app.inversurehomes.es",
]
if DEBUG:
    _DEFAULT_CSRF_TRUSTED_ORIGINS.extend(
        [
            "http://localhost:8000",
            "http://127.0.0.1:8000",
            "http://[::1]:8000",
        ]
    )
_ENV_CSRF_TRUSTED_ORIGINS = _env_csv("DJANGO_CSRF_TRUSTED_ORIGINS") + _env_csv("CSRF_TRUSTED_ORIGINS")
if _env_bool("DJANGO_CSRF_TRUSTED_ORIGINS_STRICT", False):
    CSRF_TRUSTED_ORIGINS = _ENV_CSRF_TRUSTED_ORIGINS or list(_DEFAULT_CSRF_TRUSTED_ORIGINS)
else:
    CSRF_TRUSTED_ORIGINS = list(dict.fromkeys(list(_DEFAULT_CSRF_TRUSTED_ORIGINS) + _ENV_CSRF_TRUSTED_ORIGINS))


# =========================
# APLICACIONES
# =========================

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django.contrib.humanize",
    "axes",
    "django_otp",
    "django_otp.plugins.otp_totp",
    "django_otp.plugins.otp_static",
    "django_otp.plugins.otp_email",
    "auditlog",
    "accounts.apps.AccountsConfig",
    "two_factor",
    "two_factor.plugins.phonenumber",
    "two_factor.plugins.email",
    "wagtail.contrib.forms",
    "wagtail.contrib.redirects",
    "wagtail.embeds",
    "wagtail.sites",
    "wagtail.users",
    "wagtail.snippets",
    "wagtail.documents",
    "wagtail.images",
    "wagtail.search",
    "wagtail.admin",
    "wagtail",
    "modelcluster",
    "taggit",
    "cms",
    "core.apps.CoreConfig",
    "landing",
    "storages",
]
if DEBUG_TOOLBAR_ENABLED:
    INSTALLED_APPS.insert(6, "debug_toolbar")
if DEV_APPS_ENABLED:
    INSTALLED_APPS.append("django_extensions")


# =========================
# MIDDLEWARE
# =========================

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",  # ← ESTA LÍNEA
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "axes.middleware.AxesMiddleware",
    "auditlog.middleware.AuditlogMiddleware",
    "django_otp.middleware.OTPMiddleware",
    "config.middleware.MaintenanceModeMiddleware",
    "accounts.middleware.UserSessionMiddleware",
    "accounts.middleware.RoleAccessMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "wagtail.contrib.redirects.middleware.RedirectMiddleware",
]
if DEBUG_TOOLBAR_ENABLED:
    MIDDLEWARE.insert(3, "debug_toolbar.middleware.DebugToolbarMiddleware")

# =========================
# URLS / WSGI
# =========================

ROOT_URLCONF = "config.urls"

WSGI_APPLICATION = "config.wsgi.application"

# =========================
# AUTH / AXES
# =========================

# Axes recomienda usar su backend para contabilizar intentos de login.
# Mantiene el comportamiento estándar de Django y añade protección anti fuerza bruta.
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]


# =========================
# TEMPLATES
# =========================

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "core.context_processors.pending_solicitudes",
            ],
        },
    },
]


LOGIN_URL = "/account/login/"
LOGOUT_REDIRECT_URL = "/account/login/"
LOGIN_REDIRECT_URL = "/app/"

# =========================
# BASE DE DATOS (ÚNICA FUENTE)
# =========================
DATABASE_URL = os.environ.get("DATABASE_URL")

SENSITIVE_DATA_KEY = os.environ.get("SENSITIVE_DATA_KEY", "")
SENSITIVE_DATA_HMAC_KEY = os.environ.get("SENSITIVE_DATA_HMAC_KEY", "")

if DATABASE_URL:
    DATABASES = {
        "default": dj_database_url.config(
            default=DATABASE_URL,
            conn_max_age=600,
            ssl_require=True,
        )
    }
else:
    # LOCAL (SQLite)
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }


# =========================
# PASSWORDS
# =========================

AUTH_PASSWORD_VALIDATORS = [
    {
        "NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.CommonPasswordValidator",
    },
    {
        "NAME": "django.contrib.auth.password_validation.NumericPasswordValidator",
    },
]


# =========================
# INTERNACIONALIZACIÓN
# =========================

LANGUAGE_CODE = "es-es"

TIME_ZONE = "Europe/Madrid"

USE_I18N = True
USE_TZ = True


# =========================
# STATIC FILES
# =========================

STATIC_URL = "/static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Media (subidas)
MEDIA_URL = "/media/"
MEDIA_ROOT = BASE_DIR / "media"

# =========================
# LÍMITES DE SUBIDA
# =========================

MAX_UPLOAD_MB = int(os.environ.get("MAX_UPLOAD_MB", "25"))
DATA_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_MB * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = MAX_UPLOAD_MB * 1024 * 1024
DATA_UPLOAD_MAX_NUMBER_FILES = int(os.environ.get("MAX_UPLOAD_FILES", "50"))

# S3 (opcional si existen variables de entorno)
AWS_ACCESS_KEY_ID = os.environ.get("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.environ.get("AWS_SECRET_ACCESS_KEY")
AWS_STORAGE_BUCKET_NAME = os.environ.get("AWS_STORAGE_BUCKET_NAME")
AWS_S3_REGION_NAME = os.environ.get("AWS_S3_REGION_NAME")
AWS_S3_CUSTOM_DOMAIN = os.environ.get("AWS_S3_CUSTOM_DOMAIN")
AWS_QUERYSTRING_AUTH = False
AWS_DEFAULT_ACL = None

if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY and AWS_STORAGE_BUCKET_NAME:
    STORAGES = {
        "default": {
            "BACKEND": "storages.backends.s3boto3.S3Boto3Storage",
        },
        "staticfiles": {
            "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
        },
    }
    if AWS_S3_CUSTOM_DOMAIN:
        MEDIA_URL = f"https://{AWS_S3_CUSTOM_DOMAIN}/"
    elif AWS_S3_REGION_NAME:
        MEDIA_URL = f"https://{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com/"
    else:
        MEDIA_URL = f"https://{AWS_STORAGE_BUCKET_NAME}.s3.amazonaws.com/"
else:
    STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"


# =========================
# OTROS
# =========================

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"
WAGTAIL_SITE_NAME = "Inversure Homes"

# Base URL para Wagtail admin (links en notificaciones).
WAGTAILADMIN_BASE_URL = os.environ.get("WAGTAILADMIN_BASE_URL", "").strip()
if not WAGTAILADMIN_BASE_URL:
    # En local priorizamos localhost; en producción usamos un host conocido.
    if DEBUG:
        _host = "localhost:8000"
        _scheme = "http"
    else:
        _host = (ALLOWED_HOSTS[0] if ALLOWED_HOSTS else "localhost").strip()
        _scheme = "https"
    WAGTAILADMIN_BASE_URL = f"{_scheme}://{_host}"

if DEBUG_TOOLBAR_ENABLED:
    INTERNAL_IPS = ["127.0.0.1", "localhost", "::1"]

# =========================
# EMAIL
# =========================

EMAIL_BACKEND = os.environ.get(
    "EMAIL_BACKEND",
    "django.core.mail.backends.console.EmailBackend",
)
EMAIL_HOST = os.environ.get("EMAIL_HOST", "")
EMAIL_PORT = int(os.environ.get("EMAIL_PORT", "587"))
EMAIL_HOST_USER = os.environ.get("EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = os.environ.get("EMAIL_USE_TLS", "1") == "1"
EMAIL_USE_SSL = os.environ.get("EMAIL_USE_SSL", "0") == "1"
DEFAULT_FROM_EMAIL = os.environ.get("DEFAULT_FROM_EMAIL", "Inversure <no-reply@inversurehomes.es>")
LANDING_LEAD_NOTIFY_EMAILS = [
    email.strip()
    for email in os.environ.get("LANDING_LEAD_NOTIFY_EMAILS", "comunicaciones@inversurehomes.es").split(",")
    if email.strip()
]

# =========================
# SEGURIDAD (PRODUCCIÓN)
# =========================

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True
SECURE_SSL_REDIRECT = not DEBUG
SESSION_COOKIE_SECURE = not DEBUG
CSRF_COOKIE_SECURE = not DEBUG
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"

# =========================
# AXES (Protección anti fuerza bruta)
# =========================

AXES_ENABLED = True
AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = 1  # hours
AXES_LOCK_OUT_AT_FAILURE = True
AXES_RESET_ON_SUCCESS = True
AXES_USERNAME_FORM_FIELD = "username"
AXES_LOCKOUT_PARAMETERS = ["username", "ip_address"]

# =========================
# MFA (Admin)
# =========================

OTP_TOTP_ISSUER = "Inversure"
OTP_EMAIL_SENDER = DEFAULT_FROM_EMAIL
OTP_EMAIL_TOKEN_VALIDITY = 600

# =========================
# WEB PUSH (PWA)
# =========================

VAPID_PUBLIC_KEY = os.environ.get("VAPID_PUBLIC_KEY", "")
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "")
VAPID_SUBJECT = os.environ.get("VAPID_SUBJECT", "mailto:comunicacion@inversurehomes.es")

# =========================
# INVERSORES (Fiscalidad)
# =========================
# Retención por defecto (España): 19%. Se puede ajustar por entorno.
try:
    INVERSOR_RETENCION_PCT = float(os.environ.get("INVERSOR_RETENCION_PCT", "19"))
except Exception:
    INVERSOR_RETENCION_PCT = 19.0
if INVERSOR_RETENCION_PCT < 0:
    INVERSOR_RETENCION_PCT = 0.0
if INVERSOR_RETENCION_PCT > 100:
    INVERSOR_RETENCION_PCT = 100.0


# Retención por tipo de partícipe (F/J). Por defecto hereda la global.
def _pct_env(name: str, default: float) -> float:
    try:
        raw = os.environ.get(name, "")
        if raw in ("", None):
            return float(default)
        return float(raw)
    except Exception:
        return float(default)


INVERSOR_RETENCION_PCT_F = _pct_env("INVERSOR_RETENCION_PCT_F", INVERSOR_RETENCION_PCT)
INVERSOR_RETENCION_PCT_J = _pct_env("INVERSOR_RETENCION_PCT_J", INVERSOR_RETENCION_PCT)
INVERSOR_RETENCION_PCT_F = max(0.0, min(100.0, float(INVERSOR_RETENCION_PCT_F)))
INVERSOR_RETENCION_PCT_J = max(0.0, min(100.0, float(INVERSOR_RETENCION_PCT_J)))

# En cuentas en participación, por defecto se asume que el partícipe no responde más allá de su aportación.
# Si el resultado fuera muy negativo, el "total a percibir" se limita a 0€.
CUENTAS_PARTICIPACION_LIMIT_LOSS_TO_CAPITAL = (
    str(os.environ.get("CUENTAS_PARTICIPACION_LIMIT_LOSS_TO_CAPITAL", "1")).strip() == "1"
)

# Si se activa, el beneficio/ROI de `_resultado_desde_memoria` se recalcula como:
# beneficio_neto = valor_transmision_neto - valor_adquisicion
# Esto suele incluir gastos de venta (si existen) aunque estén estimados.
MEMORIA_BENEFICIO_NETO_DESDE_TRANSMISION = (
    str(os.environ.get("MEMORIA_BENEFICIO_NETO_DESDE_TRANSMISION", "0")).strip() == "1"
)
