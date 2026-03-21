import os

os.environ.setdefault("DJANGO_JWT_SIGNING_KEY", "test-jwt-signing-key-with-minimum-32-bytes-2026")

from .base import *  # noqa

from datetime import timedelta
from rest_framework.settings import api_settings

# Tests: deterministas y rápidos
DEBUG = False
SECRET_KEY = "test-signing-key-with-minimum-32-bytes-2026"
SIMPLE_JWT = {
    **SIMPLE_JWT,
    "SIGNING_KEY": os.environ["DJANGO_JWT_SIGNING_KEY"],
    "ACCESS_TOKEN_LIFETIME": timedelta(days=365),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=365),
}

# Tests: mantener header para facilitar clientes no-browser
AUTH_TOKEN_TRANSPORT = "header"
OPENAPI_ALLOW_ANON = True

# Tests: permitir host por defecto de APIClient
ALLOWED_HOSTS = list(ALLOWED_HOSTS) + ["testserver"]

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

# Tests: desactivar Axes para evitar lockouts en flujos masivos
AXES_ENABLED = False

MIDDLEWARE = [m for m in MIDDLEWARE if m != "axes.middleware.AxesMiddleware"]

AUTHENTICATION_BACKENDS = [
    "django.contrib.auth.backends.ModelBackend",
]

# Tests: relajar validadores de password para evitar friccion
AUTH_PASSWORD_VALIDATORS = []

# Throttling activo pero con límites altos para evitar 429 en tests
REST_FRAMEWORK = {
    **REST_FRAMEWORK,
    "DEFAULT_THROTTLE_RATES": {
        "anon": "10000/min",
        "user": "10000/min",
        "auth_login": "10000/min",
        "auth_refresh": "10000/min",
        "auth_logout": "10000/min",
        "auth_sensitive": "10000/min",
        "me_read": "10000/min",
        "me_acl_read": "10000/min",
        "context_read": "10000/min",
        "sync_batch": "10000/min",
        "admin_writes": "10000/min",
        "heavy_reads": "10000/min",
    },
}

api_settings.reload()
