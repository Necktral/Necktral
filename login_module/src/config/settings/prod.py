from .base import *  # noqa

DEBUG = False

# Fail-fast si llaves inseguras o faltan
import sys

if SECRET_KEY in (None, "", "unsafe-dev-secret", "change-me-please"):
    print("ERROR: SECRET_KEY insegura o faltante en producción.", file=sys.stderr)
    sys.exit(1)
if not AUDIT_HMAC_KEYS and AUDIT_HMAC_KEY in (None, "", "dev-audit-key-change-me", "pon-tu-clave-segura-aqui"):
    print("ERROR: AUDIT_HMAC_KEY insegura o faltante en producción.", file=sys.stderr)
    sys.exit(1)
if not AUDIT_HMAC_KEYS and not AUDIT_HMAC_KEY:
    print("ERROR: Debes configurar AUDIT_HMAC_KEY o AUDIT_HMAC_KEYS en producción.", file=sys.stderr)
    sys.exit(1)


# Hardening (proxy / TLS / cookies)
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
USE_X_FORWARDED_HOST = True

SECURE_SSL_REDIRECT = env.bool("DJANGO_SECURE_SSL_REDIRECT", default=True)
SECURE_HSTS_SECONDS = env.int("DJANGO_SECURE_HSTS_SECONDS", default=15552000)
SECURE_HSTS_INCLUDE_SUBDOMAINS = env.bool("DJANGO_SECURE_HSTS_INCLUDE_SUBDOMAINS", default=True)
SECURE_HSTS_PRELOAD = env.bool("DJANGO_SECURE_HSTS_PRELOAD", default=True)

SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = False
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"

AUTH_COOKIE_SECURE = True
AUTH_COOKIE_SAMESITE = env("AUTH_COOKIE_SAMESITE", default="Lax")

SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# Logging: reducir verbosidad en prod
for name in ("apps.audit", "apps.accounts"):
    if name in LOGGING.get("loggers", {}):
        LOGGING["loggers"][name]["level"] = "INFO"
