# Guía Transversal de Kernels, Uso Móvil y Enrolamiento

Versión: v1.0  
Fecha: 2026-03-20  
Estado: Activo

## 1) Objetivo

Estandarizar el uso operativo de `apps.modulos` y `kernels`, con foco en el flujo móvil canónico (`/api/backend/sync/*`) para enrolamiento y sincronización segura.

## 2) Mapa de ownership (resumen operativo)

| Bloque | Ownership principal | No debe hacer |
|---|---|---|
| `kernels.auth_kernel` | Login, refresh, logout, me/acl, password, 2FA | Bootstrap organizacional |
| `apps.modulos.iam` + `apps.modulos.rbac` + `apps.modulos.org` | Contexto `company/branch`, membresías, permisos/grants | Lógica de stock, facturación, contabilidad |
| `apps.modulos.sync_engine` | Enrolamiento device, batch sync, revocación, policy/validación firma | Mutación directa de dominio fuera de handlers |
| `kernels.facturacion` | Documentos, numeración, emisión/anulación | Ownership de inventario/costo y journal final |
| `kernels.inventarios` | Movimientos, balances/costo, transferencias | Numeración fiscal |
| `apps.modulos.accounting` | Asientos, periodos, cierres, reportes financieros | Hecho operativo primario de kernels |
| `apps.modulos.reports` | Salidas reproducibles/exportes | Verdad primaria de negocio |
| `apps.modulos.dashboard` | Composición visual y consultas derivadas | Reglas de dominio |
| `kernels.compras` + `apps.modulos.payments` + `kernels.estacion_servicios` | Procurement, pagos/caja, fuel POS | Romper fronteras de ownership de otros kernels |

Fuente contractual: `docs/ADR_KERNEL_OWNERSHIP_BOUNDARIES_v1.0.md`.

## 3) Matriz de rutas canónicas backend

Prefijo recomendado: `/api/backend/*`.

| Dominio | Ruta canónica |
|---|---|
| Auth | `/api/backend/auth/` |
| IAM | `/api/backend/iam/` |
| ORG | `/api/backend/org/` |
| RBAC | `/api/backend/rbac/` |
| Sync engine | `/api/backend/sync/` |
| Sync legacy wrapper | `/api/backend/sync-hmac/` |
| Audit | `/api/backend/audit/` |
| HR | `/api/backend/hr/` |
| Accounting | `/api/backend/accounting/` |
| Dashboard | `/api/backend/dashboard/` |
| Reports | `/api/backend/reports/` |
| Billing | `/api/backend/billing/` |
| Inventory | `/api/backend/inventory/` |
| Fuel | `/api/backend/fuel/` |
| Procurement | `/api/backend/procurement/` |
| Payments | `/api/backend/payments/` |
| CEC | `/api/backend/cec/` |

Nota: `/api/backend/sync-hmac/` y aliases legacy `/api/*` se mantienen solo por compatibilidad.

## 4) Precondiciones DEV para frontend móvil/web

- Frontend local: `http://localhost:3000` (fallback habitual: `3001`, también soportado `3100`).
- CORS/CSRF confiables en `.env`:
  - `DJANGO_CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001,http://localhost:3100,http://127.0.0.1:3100`
  - `DJANGO_CSRF_TRUSTED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:3001,http://127.0.0.1:3001,http://localhost:3100,http://127.0.0.1:3100`
- Transporte auth DEV: `AUTH_TOKEN_TRANSPORT=cookie`.
- Firma JWT obligatoria dedicada: `DJANGO_JWT_SIGNING_KEY` con minimo `32 bytes` (fail-fast al iniciar backend).
- Para requests autenticados `POST/PUT/PATCH/DELETE` desde browser: enviar `X-CSRFToken` con cookie `nt_csrf`.

Header canónico recomendado para clientes: `X-CSRF-Token` (se acepta compatibilidad con `X-CSRFToken`).

## 5) Flujo móvil end-to-end (canónico)

1. `POST /api/backend/auth/login/`  
   Resultado: cookies `nt_access`, `nt_refresh`, `nt_csrf`.
2. Requests autenticados de app web envían `X-Company-Id` (obligatorio en rutas operativas), `X-Branch-Id` opcional.
3. `POST /api/backend/sync/enrollment/challenges/` (requiere JWT + RBAC `sync.device.enroll` + CSRF).  
   Devuelve `enrollment_code` de un solo uso.
4. `POST /api/backend/sync/enroll/` (sin JWT).  
   Intercambia `enrollment_code` + `public_key_b64` por `device_id` activo.
5. `POST /api/backend/sync/batch/` con `X-Device-Id` + firma Ed25519 por comando.
6. `GET /api/backend/sync/devices/` para inventario de dispositivos.
7. `POST /api/backend/sync/devices/{device_id}/revoke/` para invalidación inmediata.

## 6) Contrato operativo por carril

- Autenticación/cookies: ownership `auth_kernel`.
- Contexto org/scope: ownership `iam` + `rbac`.
- Enrolamiento/sync y seguridad de dispositivo: ownership `sync_engine`.
- Mutación de negocio: handlers del kernel dueño (`facturacion`, `inventarios`, etc.).
- Auditoría contractual: `apps.modulos.audit`.

## 6.1) Linking contable operacional (latencia controlada)

- Variable de operación: `ACCOUNTING_OPERATIONAL_LINK_MODE`.
- `sync` (default): `facturacion`/`inventarios` ejecutan linking contable inline.
- `async`: los kernels dejan estado inicial `PENDING_RULESET` y el linking se procesa fuera de request.

Comando de drenaje para modo `async`:

```bash
make qa-operational-projector-drain COMPANY_ID=<COMPANY_ID>
```

## 7) Anti-patrones prohibidos

- Consumir aliases legacy (`/api/*`) en nuevas integraciones.
- Bypass de `X-Company-Id` o uso de scopes cruzados sin grants.
- Enrolar dispositivo por fuera de `enrollment_code` one-time.
- Escribir lógica de dominio en dashboard/reportes/sync wrappers.

## 8) Evidencia de validación local (2026-03-20)

- Reset DB total con volúmenes: OK.
- Bootstrap org mínimo (`company=2`, `branch=3`): OK.
- CORS con credenciales en `localhost:3000/3001/3100`: OK.
- Flujo canónico `challenge -> enroll -> batch(APPLIED) -> revoke`: OK.

## 9) Gate recomendado de verificación

- Preparación reproducible (DB limpia + seed + bootstrap): `make qa-auth-sync-reset-run`
- Smoke puntual (sin reset): `make qa-auth-sync-smoke`
- Artefactos esperados:
  - `qa/reports/auth_sync_smoke_report.json`
  - `qa/reports/auth_sync_smoke_report.md`
