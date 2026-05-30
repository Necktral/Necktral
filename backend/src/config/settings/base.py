# RBAC (modo transición): incluye roles globales legacy (UserRole) además de RoleAssignment scoped
RBAC_INCLUDE_GLOBAL_USERROLES = True
AXES_RESET_ON_SUCCESS = True
"""
NOTA:
- REST_FRAMEWORK se define UNA sola vez más abajo para evitar shadowing.
- AXES_* se define UNA sola vez en base (prod-safe) y se sobreescribe en dev.py.
"""


# (AXES_* se define abajo en formato correcto con timedelta)

from datetime import timedelta
from typing import cast
from pathlib import Path

import environ

# base.py está en: backend/src/config/settings/base.py
# BASE_DIR = backend/src
BASE_DIR = Path(__file__).resolve().parents[2]  # -> backend/src
ENV_FILE = BASE_DIR.parent.parent / ".env"  # -> ERP_CRM/.env

env = environ.Env(
    DJANGO_DEBUG=(bool, False),
    DJANGO_SECRET_KEY=(str, "unsafe-dev-secret"),
    DJANGO_ALLOWED_HOSTS=(list, ["localhost", "127.0.0.1"]),
    DJANGO_CORS_ALLOWED_ORIGINS=(list, ["http://localhost:3000"]),
    DJANGO_CSRF_TRUSTED_ORIGINS=(list, ["http://localhost:3000"]),
    AUTH_TOKEN_TRANSPORT=(str, "cookie"),
    AUTH_ALLOW_TRANSPORT_OVERRIDE=(bool, False),
    AUTH_COOKIE_ACCESS_NAME=(str, "nt_access"),
    AUTH_COOKIE_REFRESH_NAME=(str, "nt_refresh"),
    AUTH_COOKIE_CSRF_NAME=(str, "nt_csrf"),
    AUTH_COOKIE_SECURE=(bool, False),
    AUTH_COOKIE_SAMESITE=(str, "Lax"),
    AUTH_COOKIE_REQUIRE_HTTPS=(bool, False),
    AUTH_COOKIE_DOMAIN=(str, ""),
    AUTH_COOKIE_PATH=(str, "/"),
    DRF_THROTTLE_ANON=(str, "60/min"),
    DRF_THROTTLE_USER=(str, "600/min"),
    DRF_THROTTLE_AUTH_LOGIN=(str, "20/min"),
    DRF_THROTTLE_AUTH_REFRESH=(str, "60/min"),
    DRF_THROTTLE_AUTH_LOGOUT=(str, "60/min"),
    DRF_THROTTLE_ME_READ=(str, "60/min"),
    DRF_THROTTLE_ME_ACL_READ=(str, "30/min"),
    AXES_FAILURE_LIMIT=(int, 5),
    AXES_COOLOFF_SECONDS=(int, 900),
    DJANGO_CSP_CONNECT_SRC=(list, ["http://localhost:8000", "http://127.0.0.1:8000"]),
    AUDIT_HMAC_KEYS=(str, ""),
    SENTRY_DSN=(str, ""),
    SENTRY_ENVIRONMENT=(str, "dev"),
    SENTRY_TRACES_SAMPLE_RATE=(float, 0.0),
    SENTRY_PROFILES_SAMPLE_RATE=(float, 0.0),
    SENTRY_RELEASE=(str, ""),
    TOTP_ISSUER=(str, "Necktral"),
    TOTP_CHALLENGE_TTL=(int, 300),
    TOTP_VALID_WINDOW=(int, 1),
    FISCAL_ADAPTER_MODE=(str, "NOOP"),
    FISCAL_ADAPTER_B_PROVIDER=(str, "EMULATED"),
    FISCAL_ADAPTER_B_HTTP_BASE_URL=(str, ""),
    FISCAL_ADAPTER_B_HTTP_API_KEY=(str, ""),
    FISCAL_ADAPTER_B_HTTP_TIMEOUT_SECONDS=(int, 15),
    FISCAL_ADAPTER_B_HTTP_VERIFY_TLS=(bool, True),
    ACCOUNTING_POSTING_MODE=(str, "HYBRID"),
    ACCOUNTING_POSTING_ENABLE_BILLING=(bool, True),
    ACCOUNTING_POSTING_ENABLE_INVENTORY=(bool, True),
    ACCOUNTING_POSTING_AUTO_POST_ON_WRITE=(bool, False),
    ACCOUNTING_SHADOW_PREFIX_FALLBACK_ENABLED=(bool, False),
    ACCOUNTING_SHADOW_PREFIX_FALLBACK_STRICT=(bool, False),
    REPORTING_LEGACY_ACCOUNTING_REPORTS_SUNSET=(str, "Mon, 22 Jun 2026 00:00:00 GMT"),
    REPORTING_R8_GATE_WARN_UNTIL=(str, "2026-04-07"),
    REPORTING_R8_GATE_HARD_FAIL_FROM=(str, "2026-04-08"),
    REPORTING_R8_GATE_WINDOW_HOURS=(int, 24),
    REPORTING_OBSERVABILITY_WINDOW_HOURS=(int, 24),
    SYNC_V2_ACCEPT_ENABLED=(bool, True),
    SYNC_V2_REQUEST_AUTH_ENFORCED=(bool, True),
    SYNC_V2_MAX_SKEW_SECONDS=(int, 300),
    SYNC_MAX_COMMANDS_PER_BATCH=(int, 100),
    SYNC_MAX_PAYLOAD_BYTES=(int, 64_000),
    SYNC_MAX_DEVICE_CLOCK_SKEW_SECONDS=(int, 6 * 3600),
    SYNC_SEQ_TOLERANT=(bool, True),
    SYNC_ENROLL_WEB_BASE_URL=(str, "http://localhost:3000"),
    SYNC_LEGACY_HMAC_ENABLED=(bool, False),
    SYNC_HMAC_WRAPPER_ENABLED=(bool, False),
    SYNC_LEGACY_HMAC_SUNSET=(str, "2026-03-31T00:00:00Z"),
    POS_EDGE_CONNECTOR_SHARED_SECRET=(str, ""),
    POS_EDGE_CHALLENGE_TTL_SEC=(int, 120),
    POS_EDGE_SESSION_TTL_SEC=(int, 3600),
    POS_COMPENSATION_MAX_ATTEMPTS=(int, 8),
    POS_COMPENSATION_BACKOFF_CAP_MIN=(int, 60),
)

if ENV_FILE.exists():
    env.read_env(str(ENV_FILE))

SECRET_KEY = env("DJANGO_SECRET_KEY")
DEBUG = env("DJANGO_DEBUG")
ALLOWED_HOSTS = env("DJANGO_ALLOWED_HOSTS")

# --- Logging (request_id obligatorio) ---

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "request_id": {"()": "config.logging_utils.RequestIdFilter"},
    },
    "formatters": {
        "verbose": {
            "format": "[{levelname}] {asctime} {name}: {message} (request_id={request_id})",
            "style": "{",
        },
        "json": {"()": "config.logging_utils.JsonFormatter"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "filters": ["request_id"],
            "formatter": "json" if not DEBUG else "verbose",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "INFO",
    },
    "loggers": {
        "apps.observability": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "apps.modulos.audit": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
        "apps.modulos.accounts": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}

# CORS / CSRF para PWA
CORS_ALLOWED_ORIGINS = env("DJANGO_CORS_ALLOWED_ORIGINS")
CSRF_TRUSTED_ORIGINS = env("DJANGO_CSRF_TRUSTED_ORIGINS")
CSP_CONNECT_SRC_LIST = env("DJANGO_CSP_CONNECT_SRC")
TOTP_ISSUER = env("TOTP_ISSUER")
TOTP_CHALLENGE_TTL = env("TOTP_CHALLENGE_TTL")
TOTP_VALID_WINDOW = env("TOTP_VALID_WINDOW")

from corsheaders.defaults import default_headers

CORS_ALLOW_HEADERS = list(default_headers) + [
    "x-company-id",
    "x-branch-id",
    "x-data-company-id",
    "x-data-branch-id",
    "x-device-id",
    "x-device-ts",
    "x-device-nonce",
    "x-device-signature",
    "x-request-id",
    "x-csrf-token",
]

# Permite que el frontend lea el request id devuelto por el backend
CORS_EXPOSE_HEADERS = [
    "X-Request-Id",
]

CORS_ALLOW_CREDENTIALS = env("AUTH_TOKEN_TRANSPORT") == "cookie"

AUDIT_HMAC_KEY = env("AUDIT_HMAC_KEY")
AUDIT_HMAC_KEYS = env("AUDIT_HMAC_KEYS")
SENTRY_DSN = env("SENTRY_DSN")
SENTRY_ENVIRONMENT = env("SENTRY_ENVIRONMENT")
SENTRY_TRACES_SAMPLE_RATE = env("SENTRY_TRACES_SAMPLE_RATE")
SENTRY_PROFILES_SAMPLE_RATE = env("SENTRY_PROFILES_SAMPLE_RATE")
SENTRY_RELEASE = env("SENTRY_RELEASE")
# Nombre contractual del módulo que emite eventos de auditoría para este servicio.
AUDIT_MODULE_NAME = "AUTH"
AUDIT_SCHEMA_VERSION = 1

TIME_ZONE = "America/Managua"
USE_TZ = True

LANGUAGE_CODE = "es"

FISCAL_ADAPTER_MODE = env("FISCAL_ADAPTER_MODE")
FISCAL_ADAPTER_B_PROVIDER = env("FISCAL_ADAPTER_B_PROVIDER")
FISCAL_ADAPTER_B_HTTP_BASE_URL = env("FISCAL_ADAPTER_B_HTTP_BASE_URL")
FISCAL_ADAPTER_B_HTTP_API_KEY = env("FISCAL_ADAPTER_B_HTTP_API_KEY")
FISCAL_ADAPTER_B_HTTP_TIMEOUT_SECONDS = env("FISCAL_ADAPTER_B_HTTP_TIMEOUT_SECONDS")
FISCAL_ADAPTER_B_HTTP_VERIFY_TLS = env("FISCAL_ADAPTER_B_HTTP_VERIFY_TLS")
ACCOUNTING_POSTING_MODE = env("ACCOUNTING_POSTING_MODE")
ACCOUNTING_POSTING_ENABLE_BILLING = env("ACCOUNTING_POSTING_ENABLE_BILLING")
ACCOUNTING_POSTING_ENABLE_INVENTORY = env("ACCOUNTING_POSTING_ENABLE_INVENTORY")
ACCOUNTING_POSTING_AUTO_POST_ON_WRITE = env("ACCOUNTING_POSTING_AUTO_POST_ON_WRITE")
ACCOUNTING_SHADOW_PREFIX_FALLBACK_ENABLED = env("ACCOUNTING_SHADOW_PREFIX_FALLBACK_ENABLED")
ACCOUNTING_SHADOW_PREFIX_FALLBACK_STRICT = env("ACCOUNTING_SHADOW_PREFIX_FALLBACK_STRICT")
REPORTING_LEGACY_ACCOUNTING_REPORTS_SUNSET = env("REPORTING_LEGACY_ACCOUNTING_REPORTS_SUNSET")
REPORTING_R8_GATE_WARN_UNTIL = env("REPORTING_R8_GATE_WARN_UNTIL")
REPORTING_R8_GATE_HARD_FAIL_FROM = env("REPORTING_R8_GATE_HARD_FAIL_FROM")
REPORTING_R8_GATE_WINDOW_HOURS = env("REPORTING_R8_GATE_WINDOW_HOURS")
REPORTING_OBSERVABILITY_WINDOW_HOURS = env("REPORTING_OBSERVABILITY_WINDOW_HOURS")
SYNC_V2_ACCEPT_ENABLED = env("SYNC_V2_ACCEPT_ENABLED")
SYNC_V2_REQUEST_AUTH_ENFORCED = env("SYNC_V2_REQUEST_AUTH_ENFORCED")
SYNC_V2_MAX_SKEW_SECONDS = env("SYNC_V2_MAX_SKEW_SECONDS")
SYNC_MAX_COMMANDS_PER_BATCH = env("SYNC_MAX_COMMANDS_PER_BATCH")
SYNC_MAX_PAYLOAD_BYTES = env("SYNC_MAX_PAYLOAD_BYTES")
SYNC_MAX_DEVICE_CLOCK_SKEW_SECONDS = env("SYNC_MAX_DEVICE_CLOCK_SKEW_SECONDS")
SYNC_SEQ_TOLERANT = env("SYNC_SEQ_TOLERANT")
SYNC_ENROLL_WEB_BASE_URL = env("SYNC_ENROLL_WEB_BASE_URL")
SYNC_LEGACY_HMAC_ENABLED = env("SYNC_LEGACY_HMAC_ENABLED")
SYNC_HMAC_WRAPPER_ENABLED = env("SYNC_HMAC_WRAPPER_ENABLED")
SYNC_LEGACY_HMAC_SUNSET = env("SYNC_LEGACY_HMAC_SUNSET")
POS_EDGE_CONNECTOR_SHARED_SECRET = env("POS_EDGE_CONNECTOR_SHARED_SECRET")
POS_EDGE_CHALLENGE_TTL_SEC = env("POS_EDGE_CHALLENGE_TTL_SEC")
POS_EDGE_SESSION_TTL_SEC = env("POS_EDGE_SESSION_TTL_SEC")
POS_COMPENSATION_MAX_ATTEMPTS = env("POS_COMPENSATION_MAX_ATTEMPTS")
POS_COMPENSATION_BACKOFF_CAP_MIN = env("POS_COMPENSATION_BACKOFF_CAP_MIN")

INSTALLED_APPS = [
    # Django
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Terceros
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "django_filters",
    "axes",
    "csp",
    # Apps del proyecto
    "apps.modulos.common",
    "apps.modulos.audit",
    "apps.modulos.rbac",
    "apps.modulos.accounts.apps.AccountsConfig",
    "apps.modulos.iam.apps.IamConfig",
    "apps.modulos.org.apps.OrgConfig",  # <-- NUEVO
    "apps.modulos.parties.apps.PartiesConfig",
    "apps.modulos.hr.apps.HrConfig",  # <-- NUEVO
    "apps.kernels.accounting.apps.AccountingConfig",
    "apps.kernels.payments.apps.PaymentsConfig",
    "apps.kernels.portfolio.apps.PortfolioConfig",  # Financial Portfolio Kernel
    "apps.kernels.reporting.apps.ReportingConfig",
    "apps.modulos.cec.apps.CecConfig",
    "apps.modulos.integration.apps.IntegrationConfig",
    "apps.modulos.dashboard.apps.DashboardConfig",
    "apps.modulos.sync_engine",
    "apps.modulos.sync.apps.SyncConfig",
    # Módulos de dominio (raíz/modulos)
    # (Se agregan abajo con el patrón INSTALLED_APPS += [...])
]

INSTALLED_APPS += [
    "apps.modulos.estacion_servicios.apps.EstacionServiciosConfig",
    "apps.modulos.retail_pos.apps.RetailPosConfig",
    "apps.kernels.inventarios",
    "apps.kernels.facturacion",
    "apps.modulos.compras",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "csp.middleware.CSPMiddleware",
    "config.middleware.request_id.RequestIdMiddleware",
    "config.middleware.request_logging.RequestLoggingMiddleware",
    # CORS lo más arriba posible (antes de CommonMiddleware y WhiteNoise)
    "corsheaders.middleware.CorsMiddleware",
    # WhiteNoise sirve estáticos (útil incluso en dev si lo deseas)
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "config.middleware.cookie_csrf.CookieJwtCsrfMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Axes al final (recomendación oficial)
    "axes.middleware.AxesMiddleware",
    "apps.modulos.audit.middleware.AuditAccessDeniedMiddleware",
    "config.middleware.legacy_api_deprecation.LegacyApiDeprecationMiddleware",
    "config.middleware.api_error_envelope.ApiErrorEnvelopeMiddleware",
]

ROOT_URLCONF = "config.urls"

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
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"


# Configuración para PostgreSQL usando variables de entorno
DATABASES = {
    "default": {
        "ENGINE": env("DB_ENGINE", default="django.db.backends.postgresql"),
        "NAME": env("POSTGRES_DB", default=env("DB_NAME", default="loggin_db")),
        "USER": env("POSTGRES_USER", default=env("DB_USER", default="loggin_user")),
        "PASSWORD": env(
            "POSTGRES_PASSWORD",
            default=env("DB_PASSWORD", default=""),
        ),
        "HOST": env("POSTGRES_HOST", default=env("DB_HOST", default="127.0.0.1")),
        "PORT": env("POSTGRES_PORT", default=env("DB_PORT", default="5432")),
        "CONN_MAX_AGE": 60,
    }
}

AUTH_USER_MODEL = "accounts.User"

# Axes: backend primero (recomendación oficial)
AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

# Password hashing fuerte
PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.Argon2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2PasswordHasher",
    "django.contrib.auth.hashers.PBKDF2SHA1PasswordHasher",
    "django.contrib.auth.hashers.BCryptSHA256PasswordHasher",
]

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
    {
        "NAME": "apps.modulos.accounts.password_validators.PasswordComplexityValidator",
        "OPTIONS": {"min_length": 10, "min_classes": 3},
    },
]


# Configuración robusta de archivos estáticos
STATIC_URL = "/static/"
STATIC_ROOT = str(BASE_DIR.parent / "staticfiles")
# Permite incluir directorios adicionales de estáticos en desarrollo
STATICFILES_DIRS = [
    str(BASE_DIR / "static"),
]
# WhiteNoise: storage comprimido y con manifest para producción
STORAGES = {
    "staticfiles": {"BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage"},
}

# Crear el directorio STATIC_ROOT si no existe (robustez en dev)
import os

os.makedirs(STATIC_ROOT, exist_ok=True)

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# DRF
REST_FRAMEWORK = {
    "EXCEPTION_HANDLER": "config.drf_exception_handler.custom_exception_handler",
    "DEFAULT_AUTHENTICATION_CLASSES": ("apps.modulos.iam.authentication.JWTAuthWithOrgContext",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_FILTER_BACKENDS": ("django_filters.rest_framework.DjangoFilterBackend",),
    "DEFAULT_THROTTLE_CLASSES": (
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
        "rest_framework.throttling.ScopedRateThrottle",
        "config.throttling.DeviceScopedRateThrottle",
    ),
    "DEFAULT_THROTTLE_RATES": {
        "anon": env("DRF_THROTTLE_ANON"),
        "user": env("DRF_THROTTLE_USER"),
        "auth_login": env("DRF_THROTTLE_AUTH_LOGIN"),
        "auth_sensitive": env("DRF_THROTTLE_AUTH_SENSITIVE", default="10/min"),
        "auth_refresh": env("DRF_THROTTLE_AUTH_REFRESH"),
        "auth_logout": env("DRF_THROTTLE_AUTH_LOGOUT"),
        "me_read": env("DRF_THROTTLE_ME_READ"),
        "me_acl_read": env("DRF_THROTTLE_ME_ACL_READ"),
        "context_read": "60/min",
        "sync_batch": "30/min",
        "admin_writes": "60/min",
        "heavy_reads": "60/min",
    },
}

# SimpleJWT
SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=10),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
}

# Observabilidad (Sentry)
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        environment=SENTRY_ENVIRONMENT,
        release=SENTRY_RELEASE or None,
        traces_sample_rate=SENTRY_TRACES_SAMPLE_RATE,
        profiles_sample_rate=SENTRY_PROFILES_SAMPLE_RATE,
        send_default_pii=False,
        integrations=[DjangoIntegration()],
    )

# CORS / CSRF para PWA
CORS_ALLOWED_ORIGINS = env("DJANGO_CORS_ALLOWED_ORIGINS")
CSRF_TRUSTED_ORIGINS = env("DJANGO_CSRF_TRUSTED_ORIGINS")

# drf-spectacular + sidecar (UI embebida)
SPECTACULAR_SETTINGS = {
    "TITLE": "Login Module API",
    "DESCRIPTION": "Auth + RBAC + Audit",
    "VERSION": "0.1.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "SWAGGER_UI_DIST": "SIDECAR",
    "SWAGGER_UI_FAVICON_HREF": "SIDECAR",
    "REDOC_DIST": "SIDECAR",
}

# Axes (política inicial)
AXES_FAILURE_LIMIT = env("AXES_FAILURE_LIMIT")
AXES_COOLOFF_TIME = timedelta(seconds=env("AXES_COOLOFF_SECONDS"))
AXES_LOCKOUT_PARAMETERS = ["ip_address", ["username", "user_agent"]]


# CSP nueva sintaxis para django-csp >= 4.0
CONTENT_SECURITY_POLICY = {
    "DIRECTIVES": {
        "default-src": ("'self'",),
        "script-src": ("'self'",),
        "style-src": ("'self'",),
        "object-src": ("'none'",),
        "base-uri": ("'self'",),
        "frame-ancestors": ("'self'",),
        "form-action": ("'self'",),
    }
}

CONTENT_SECURITY_POLICY_REPORT_ONLY = {
    "DIRECTIVES": {
        "default-src": ("'self'",),
        "script-src": ("'self'",),
        "style-src": ("'self'",),
        "connect-src": tuple(["'self'"] + list(CSP_CONNECT_SRC_LIST)),
        "img-src": ("'self'", "data:"),
        "font-src": ("'self'", "data:"),
        "report-uri": ("/api/csp/report/",),
    }
}

AUTH_TOKEN_TRANSPORT = env("AUTH_TOKEN_TRANSPORT")
AUTH_ALLOW_TRANSPORT_OVERRIDE = env("AUTH_ALLOW_TRANSPORT_OVERRIDE")
AUTH_COOKIE_ACCESS_NAME = env("AUTH_COOKIE_ACCESS_NAME")
AUTH_COOKIE_REFRESH_NAME = env("AUTH_COOKIE_REFRESH_NAME")
AUTH_COOKIE_CSRF_NAME = env("AUTH_COOKIE_CSRF_NAME")
AUTH_COOKIE_SECURE = env.bool("AUTH_COOKIE_SECURE", default=not DEBUG)
AUTH_COOKIE_SAMESITE = env("AUTH_COOKIE_SAMESITE")
AUTH_COOKIE_REQUIRE_HTTPS = env.bool("AUTH_COOKIE_REQUIRE_HTTPS", default=not DEBUG)
AUTH_COOKIE_DOMAIN = env("AUTH_COOKIE_DOMAIN") or None
AUTH_COOKIE_PATH = env("AUTH_COOKIE_PATH")

_access_lifetime = cast(timedelta, SIMPLE_JWT["ACCESS_TOKEN_LIFETIME"])
_refresh_lifetime = cast(timedelta, SIMPLE_JWT["REFRESH_TOKEN_LIFETIME"])
AUTH_COOKIE_ACCESS_MAX_AGE = int(_access_lifetime.total_seconds())
AUTH_COOKIE_REFRESH_MAX_AGE = int(_refresh_lifetime.total_seconds())
AUTH_COOKIE_CSRF_MAX_AGE = AUTH_COOKIE_REFRESH_MAX_AGE
