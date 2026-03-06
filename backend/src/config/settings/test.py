from .base import *  # noqa

from rest_framework.settings import api_settings

# Tests: deterministas y rápidos
DEBUG = False

# Tests: usar clave robusta para evitar InsecureKeyLengthWarning de PyJWT/SimpleJWT.
SECRET_KEY = "test-only-secret-key-with-at-least-32-bytes-2026"
SIMPLE_JWT = {
    **SIMPLE_JWT,
    "SIGNING_KEY": SECRET_KEY,
}

# Tests: preservar compatibilidad transicional para no romper baseline actual.
RBAC_INCLUDE_GLOBAL_USERROLES = True

# Tests: mantener header para facilitar clientes no-browser
AUTH_TOKEN_TRANSPORT = "header"

# Tests: permitir host por defecto de APIClient
ALLOWED_HOSTS = list(ALLOWED_HOSTS) + ["testserver"]

# Tests: bootstrap sin token para no romper fixtures actuales
INITIAL_SETUP_REQUIRE_TOKEN = False

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
        "bootstrap": "10000/min",
        "context_read": "10000/min",
        "sync_batch": "10000/min",
        "admin_writes": "10000/min",
        "heavy_reads": "10000/min",
    },
}

api_settings.reload()
