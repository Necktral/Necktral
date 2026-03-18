# Settings del backend (backend)

Esta carpeta contiene la configuración del backend Django/DRF.

## Archivos clave

- `base.py`: defaults seguros y configuración común.
- `dev.py`: overrides de desarrollo.
- `prod.py`: hardening y checks de producción.
- `test.py`: overrides para tests (throttles altos y host `testserver`).

## Variables de entorno relevantes

- Auth/Cookies: `AUTH_TOKEN_TRANSPORT`, `AUTH_COOKIE_*`
- Throttling: `DRF_THROTTLE_*` y scopes (`auth_login`, `auth_refresh`, `auth_logout`, `auth_sensitive`, `me_read`, `me_acl_read`, `admin_writes`, `heavy_reads`)
- Auditoría: `AUDIT_HMAC_KEYS` (keyring) y fallback `AUDIT_HMAC_KEY`
- Observabilidad: `SENTRY_DSN`, `SENTRY_ENVIRONMENT`, `SENTRY_TRACES_SAMPLE_RATE`, `SENTRY_PROFILES_SAMPLE_RATE`, `SENTRY_RELEASE`
- 2FA: `TOTP_ISSUER`, `TOTP_CHALLENGE_TTL`, `TOTP_VALID_WINDOW`

## Notas

- En `prod.py` se valida que haya `AUDIT_HMAC_KEYS` o `AUDIT_HMAC_KEY` seguro.
- El middleware agrega `X-Request-Id` en todas las respuestas.

---

Actualizado: 2026-02-09.
