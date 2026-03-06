from .base import *  # noqa

from config.settings.security import find_weak_keys, is_hs256_key_strong, is_insecure_default, parse_keyring

DEBUG = False

# Prod: sólo RBAC scoped para evitar escalamiento por roles globales legacy.
RBAC_INCLUDE_GLOBAL_USERROLES = False

# Fail-fast si llaves inseguras o faltan
import sys

if is_insecure_default(SECRET_KEY) or not is_hs256_key_strong(SECRET_KEY, min_bytes=JWT_MIN_SIGNING_KEY_BYTES):
    print("ERROR: SECRET_KEY insegura o faltante en producción.", file=sys.stderr)
    sys.exit(1)

if is_insecure_default(JWT_SIGNING_KEY) or not is_hs256_key_strong(
    JWT_SIGNING_KEY,
    min_bytes=JWT_MIN_SIGNING_KEY_BYTES,
):
    print("ERROR: DJANGO_JWT_SIGNING_KEY insegura o faltante en producción.", file=sys.stderr)
    sys.exit(1)

keyring = parse_keyring(AUDIT_HMAC_KEYS)
if keyring:
    weak_key_ids = find_weak_keys(keyring, min_bytes=JWT_MIN_SIGNING_KEY_BYTES)
    if weak_key_ids:
        print(
            f"ERROR: AUDIT_HMAC_KEYS contiene claves débiles/inseguras: {', '.join(weak_key_ids)}",
            file=sys.stderr,
        )
        sys.exit(1)
elif is_insecure_default(AUDIT_HMAC_KEY) or not is_hs256_key_strong(
    AUDIT_HMAC_KEY,
    min_bytes=JWT_MIN_SIGNING_KEY_BYTES,
):
    print("ERROR: AUDIT_HMAC_KEY insegura o faltante en producción.", file=sys.stderr)
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
loggers = LOGGING.get("loggers")
if isinstance(loggers, dict):
    for name in ("apps.audit", "apps.accounts"):
        logger_cfg = loggers.get(name)
        if isinstance(logger_cfg, dict):
            logger_cfg["level"] = "INFO"
