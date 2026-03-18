# ADR — Auth Kernel Extraction v2.0

Version: v2.0  
Fecha: 2026-03-18  
Estado: Aprobado

## Decisión

Se extrae la lógica de autenticación/sesión desde `apps.accounts` hacia `modulos.auth_kernel`.

- `modulos.auth_kernel` pasa a ser la capa canónica de casos de uso auth:
  `login`, `refresh`, `logout`, `me`, `password`, `2FA`.
- `apps.accounts` queda como almacenamiento de identidad y compatibilidad técnica:
  `User`, `RefreshTokenSession`, `TwoFactorChallenge`, migraciones y señales.
- Bootstrap se divide por ownership:
  - `apps.iam`: `GET /api/iam/bootstrap/status/`, `POST /api/iam/bootstrap/init-admin/`
  - `apps.org`: `POST /api/org/bootstrap/organization/`

## Compatibilidad

- `/api/auth/*` se mantiene operativo.
- `/api/auth/bootstrap/*` se mantiene como wrapper legacy sin lógica de dominio.
- Wrappers legacy de bootstrap agregan:
  - `Deprecation: true`
  - `Sunset: Sun, 17 May 2026 00:00:00 GMT`
  - `Link: <endpoint_canónico>; rel="successor-version"`

## Alcance de esta etapa (Stage 1)

- No se migra `AUTH_USER_MODEL`; se mantiene `AUTH_USER_MODEL=accounts.User`.
- No se cambia modelo físico de tablas de usuario.
- Se refuerzan fronteras con guardas CI (`qa/architecture_boundaries_guard.py`).

## Riesgos controlados

- Riesgo de ruptura en onboarding: mitigado con wrappers legacy y pruebas E2E.
- Riesgo de regresión de ownership: mitigado con guardas de rutas/imports.

## Criterio de cierre

- `apps.accounts.views` sin orquestación de bootstrap.
- Bootstrap canónico servido por IAM/ORG.
- `/api/auth/bootstrap/*` funcionando como compatibilidad temporal con headers deprecados.
