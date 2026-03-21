# Checklist de Validación: Kernels + Móvil + Enrolamiento

Versión: v1.0  
Fecha: 2026-03-20  
Estado: Activo

## 1) Datos de corrida

- Entorno: local Docker.
- Frontend esperado: `http://localhost:3100`.
- Backend esperado: `http://localhost:8000`.
- Política auth DEV: cookie transport.

## 2) Smoke técnico obligatorio

Marcar `OK` o `FAIL` y guardar evidencia (`request_id`, respuesta, timestamp).

| Check | Resultado esperado | Estado |
|---|---|---|
| `GET /api/backend/iam/bootstrap/status/` | HTTP 200 | `OK/FAIL` |
| `OPTIONS /api/backend/auth/login/` con Origin `3100` | `Access-Control-Allow-Origin` + `Access-Control-Allow-Credentials: true` | `OK/FAIL` |
| `POST /api/backend/auth/login/` | `{"ok":true}` + cookies auth | `OK/FAIL` |
| `DJANGO_JWT_SIGNING_KEY` | definida y longitud `>=32 bytes` | `OK/FAIL` |
| `GET /api/backend/auth/me/` autenticado | HTTP 200 con usuario | `OK/FAIL` |
| `POST /api/backend/sync/enrollment/challenges/` sin CSRF | `403` con `AUTH_CSRF_FAILED` | `OK/FAIL` |
| `POST /api/backend/sync/enrollment/challenges/` con CSRF | HTTP 201 + `enrollment_code` | `OK/FAIL` |
| `POST /api/backend/sync/enroll/` | HTTP 201 + `device_id` activo | `OK/FAIL` |
| `POST /api/backend/sync/batch/` | `summary` consistente y no 5xx | `OK/FAIL` |
| `GET /api/backend/sync/devices/` | Lista paginada sin error | `OK/FAIL` |
| `POST /api/backend/sync/devices/{id}/revoke/` | `status=REVOKED` | `OK/FAIL` |
| `make qa-auth-sync-smoke` | PASS + artefacto JSON/MD | `OK/FAIL` |
| `ACCOUNTING_OPERATIONAL_LINK_MODE=async` + `make qa-operational-projector-drain` | Eventos operacionales pendientes procesados sin `failed` | `OK/FAIL` |

## 3) Checklist UX manual mínima

| Ruta/acción | Resultado esperado | Estado |
|---|---|---|
| `/login` con `k6_admin` | Login sin errores CORS | `OK/FAIL` |
| `/select-context` | Selección de company/branch exitosa | `OK/FAIL` |
| `/dashboard` | Carga sin 5xx en backend | `OK/FAIL` |
| `/analitica/v3` | Consulta y render chart/grid | `OK/FAIL` |
| CRUD crítico (`empleados` o `sucursales`) | create/edit/list con confirmación visual | `OK/FAIL` |
| Usuario restringido (`k6_user`) en ruta protegida | Bloqueo 403/no acceso | `OK/FAIL` |

## 4) Criterio de semáforo

- `PASS`: todos los checks técnicos en `OK`, UX crítica en `OK`, sin 5xx.
- `PASS_WITH_RISK`: operación usable con fallos no bloqueantes documentados.
- `FAIL`: bloqueo de login/contexto/CORS o error funcional crítico.

## 5) Hallazgos y acciones

Registrar por cada hallazgo:

- severidad (`INFO|MINOR|MAJOR|CRITICAL`),
- hipótesis causal,
- recomendación,
- responsable y fecha compromiso.
