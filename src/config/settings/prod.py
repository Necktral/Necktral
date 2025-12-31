
from .base import *  # noqa

DEBUG = False

# Fail-fast si llaves inseguras o faltan
import sys
if SECRET_KEY in (None, "", "unsafe-dev-secret", "change-me-please"):
	print("ERROR: SECRET_KEY insegura o faltante en producción.", file=sys.stderr)
	sys.exit(1)
if AUDIT_HMAC_KEY in (None, "", "dev-audit-key-change-me", "pon-tu-clave-segura-aqui"):
	print("ERROR: AUDIT_HMAC_KEY insegura o faltante en producción.", file=sys.stderr)
	sys.exit(1)
