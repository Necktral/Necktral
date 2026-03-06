# Settings del backend (backend)

Esta carpeta contiene la configuración del backend Django/DRF.

## Archivos clave

- `base.py`: defaults seguros y configuración común.
- `dev.py`: overrides de desarrollo.
- `prod.py`: hardening y checks de producción.
- `test.py`: overrides para tests (throttles altos y host `testserver`).

## Variables de entorno relevantes

- Auth/Cookies: `AUTH_TOKEN_TRANSPORT`, `AUTH_COOKIE_*`
- JWT: `DJANGO_SECRET_KEY` y `DJANGO_JWT_SIGNING_KEY` (recomendado dedicado, minimo 32 bytes para HS256)
- Throttling: `DRF_THROTTLE_*` y scopes (`auth_login`, `auth_refresh`, `auth_logout`, `auth_sensitive`, `me_read`, `me_acl_read`, `admin_writes`, `heavy_reads`)
- Auditoría: `AUDIT_HMAC_KEYS` (keyring) y fallback `AUDIT_HMAC_KEY`
- Observabilidad: `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_TRACES_SAMPLE_RATE`, `SENTRY_PROFILES_SAMPLE_RATE`, `SENTRY_RELEASE`
- 2FA: `TOTP_ISSUER`, `TOTP_CHALLENGE_TTL`, `TOTP_VALID_WINDOW`

## Notas

- En `base.py`, `SIMPLE_JWT` usa `ALGORITHM=HS256` y firma con `DJANGO_JWT_SIGNING_KEY` (fallback a `DJANGO_SECRET_KEY` si no se define).
- En `prod.py` hay fail-fast si `DJANGO_SECRET_KEY`, `DJANGO_JWT_SIGNING_KEY` o claves de auditoria (`AUDIT_HMAC_KEYS`/`AUDIT_HMAC_KEY`) son debiles o placeholders inseguros.
- El middleware agrega `X-Request-Id` en todas las respuestas.

---

Actualizado: 2026-02-09.
