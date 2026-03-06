## 2026-02-09 — WS5 paginación/indexes + WS6 CD + hardening 2FA/cookies

### Contexto

Se completa WS5 (paginación + índices) y WS6 (pipeline CD), y se endurece 2FA con challenge one-time y limpieza robusta de cookies en auth.

### Cambios principales

- **Paginación (Backend):** helper limit/offset + respuesta estándar en listados ORG/HR/RBAC/SYNC.
- **Índices (DB):** índices en OrgUnit, EmploymentAssignment y Role/Permission con migraciones.
- **Frontend:** paginación server-side en páginas ORG/HR, servicios con `limit/offset`, `AppDataTable` con eventos/attrs.
- **CD (CI/CD):** workflow de despliegue a GHCR + SSH, tags en `compose.prod.yaml` y docs operativas.
- **Auth (Backend):** challenge 2FA one-time (DB-backed) + consumo atómico + binding suave.
- **Auth (Backend):** logout/refresh en cookie-mode limpian cookies en rutas idempotentes de error.
- **Tests (Backend):** nuevos tests de listados paginados y anti-replay 2FA.
- **QA:** `test_axes_lockout` vuelve a ejecutarse (sin skip).

### QA / Gates

- Último pytest completo (antes del hardening 2FA): `143 passed` con `DJANGO_SETTINGS_MODULE=config.settings.test`.
- Cambios 2FA/cookies no se han revalidado aún con suite completa.
- CI en PR #2: **QA CI (Gates 1–3) = failure**, **Security CI (Blocking) = failure**.

### Archivos/Areas

- `backend/src/apps/common/pagination.py`
- `backend/src/apps/org/views.py`
- `backend/src/apps/hr/views.py`
- `backend/src/apps/rbac/views.py`
- `backend/src/apps/sync_engine/views.py`
- `backend/src/apps/iam/models.py`
- `backend/src/apps/hr/models.py`
- `backend/src/apps/rbac/models.py`
- `backend/src/apps/accounts/models.py`
- `backend/src/apps/accounts/views.py`
- `backend/src/apps/accounts/migrations/0006_two_factor_challenge.py`
- `frontend/src/pages/OrgCompaniesPage.vue`
- `frontend/src/pages/OrgBranchesPage.vue`
- `frontend/src/pages/HrEmployeesPage.vue`
- `frontend/src/pages/HrPositionsPage.vue`
- `frontend/src/services/hr.service.ts`
- `frontend/src/services/org.service.ts`
- `frontend/src/services/rbac.service.ts`
- `frontend/src/ui/AppDataTable.vue`
- `.github/workflows/cd.yml`
- `compose.prod.yaml`
- `docs/operacion/CD_DEPLOY_v1.0.md`
- `docs/operacion/README.md`
- `backend/tests/test_2fa_challenge.py`
- `backend/tests/test_pagination_list_endpoints.py`

## 2026-02-09 — Fixes QA 2FA & Linting

### Contexto

Se abordan los fallos de CI detectados en PR #2, especificamente en los tests de integracion de 2FA y verificaciones de tipado estatico.

### Cambios

- **Tests (Backend):** Actualizado `test_2fa_challenge.py` para manejar correctamente el formato de respuesta "Error Envelope" en fallos de validacion (400 Bad Request).
- **Calidad (Code):**
  - Correccion de imports no utilizados en `throttling.py` (Ruff).
  - Ajuste de tipos en `metrics.py` y `seed_auth_users.py` (Mypy).
- **QA:** Validacion exitosa local de `audit_verify_chain` (Integridad) y `test_axes_lockout` (Seguridad).

### Estado

- **Gate 2 (Tests):** `test_2fa_challenge` pasando.
- **Gate 3 (Audit):** Integro.
- **Linting:** Clean.

- `backend/tests/test_axes_lockout.py`

---

## 2026-02-08 — Etapa 2 (seguridad elite) + QA Gates

### Contexto

Cierre operativo de Etapa 2 con cambios de seguridad, auditoria y QA determinista.

### Cambios principales

- **Auth (Backend):** modo cookie opcional (AUTH_TOKEN_TRANSPORT) + refresh/logout con scopes `auth_refresh` y `auth_logout`.
- **CSRF (Backend):** middleware para cookies con override de error y reason_code.
- **Auditoria:** redaccion de metadata/snapshots + reason codes nuevos (`TOKEN_MISMATCH`, `INVALID_OLD_PASSWORD`, `CSRF_FAILED`).
- **Frontend:** soporte cookie transport + CSRF header desde cookie + `withCredentials`.
- **Nginx:** headers de seguridad y rate limits por ruta.

### QA / Gates

- `make qa-ci-fresh` OK (static scan, ruff, mypy, lint/typecheck, pytest, audit integrity).
- Gate 3 (k6) falla por rate limit en `/api/auth/me/` y `/api/auth/me/acl/`.
- Root cause: overrides de throttling pasados por shell no llegan al contenedor (compose usa `.env`).
- Ajuste QA via env: `DRF_THROTTLE_ME_READ`/`DRF_THROTTLE_ME_ACL_READ` y docs actualizados.

### Archivos/Areas

- `backend/src/apps/accounts/views.py`
- `backend/src/apps/audit/contracts.py`
- `backend/src/apps/audit/writer.py`
- `backend/src/config/settings/base.py`
- `frontend/src/boot/axios.ts`
- `docker/nginx/default.conf`

---

## 2026-01-28 — Ajustes documentación Import/Export (índice templates)

### Contexto

Se realizan ajustes menores para mejorar la navegación y consistencia del pack operativo Import/Export.

### Cambios principales

- Se agrega índice de templates en `docs/operacion/import_export/templates/README.md`.
- Se corrigen placeholders de firma en la plantilla de proveedor.

---

## 2026-01-28 — Pack operativo Import/Export (empresa + plantillas)

### Contexto

Se incorpora documentación operacional para aterrizar una empresa de **Import/Export & Sourcing B2B** con pipeline, riesgos y plan 0–90 días, junto con plantillas reutilizables.

### Cambios principales

- **Docs (Operación):** se crea la sección `docs/operacion/`.
- **Pack Import/Export:** documento maestro con definición operativa, modelos de ingresos, matriz de riesgos y plan 0–90.
- **Plantillas:** RFQ, cotización landed cost, checklist documental y términos (cliente/proveedor).

### Archivos

- `docs/operacion/README.md`
- `docs/operacion/import_export/EMPRESA_IMPORT_EXPORT_v1.0.md`
- `docs/operacion/import_export/templates/` (plantillas v1.0)

---

## 2026-01-23 — MVP módulo Estación de Servicios (FUEL): turnos + despachos + ventas + cancelación

### Contexto

Se completa el MVP operativo del módulo **Estación de Servicios** (FUEL) para soportar el flujo mínimo de operación diaria, integrado con **RBAC**, **scope multiempresa** y **auditoría contractual**.

### Cambios principales

- **Dominio/Modelos:** se agregan `FuelShift`, `FuelDispense`, `FuelSale` con estados y constraints (un turno abierto por sucursal).
- **Servicios:** lógica transaccional en `services.py` (open/close shift, record dispense, create sale, cancel sale) con validaciones DRF-friendly.
- **API:** endpoints operativos bajo `/api/fuel/`.
- **RBAC:** enforcement por endpoint (`fuel.shift.open`, `fuel.shift.close`, `fuel.dispense.create`, `fuel.sale.create`, `fuel.sale.void`).
- **Auditoría:** eventos mínimos emitidos por operación (module `FUEL`).
- **Migraciones:** se crea migración inicial manual para `estacion_servicios` para evitar bloqueo de `makemigrations` por cambios ajenos.
- **Tests:** se agrega/ajusta test de flujo Fuel usando el patrón de “client con permisos” ya existente en la suite.

### Archivos/Endpoints

- Endpoints:
  - `GET /api/fuel/health/` (público)
  - `POST /api/fuel/shifts/open/`
  - `POST /api/fuel/shifts/<shift_id>/close/`
  - `POST /api/fuel/dispenses/`
  - `POST /api/fuel/sales/`
  - `POST /api/fuel/sales/<sale_id>/cancel/`
- `modulos/estacion_servicios/models.py` (FuelShift/FuelDispense/FuelSale)
- `modulos/estacion_servicios/services.py` (operaciones + auditoría)
- `modulos/estacion_servicios/views.py`, `modulos/estacion_servicios/urls.py`
- `modulos/estacion_servicios/migrations/0001_initial.py`
- `backend/src/tests/test_fuel_shift_flow.py`

### Notas/Riesgos

- El endpoint de health fue dejado **público** por conveniencia operativa (monitoreo); el resto requiere auth + RBAC.
- Cancelación expone solo ruta `/cancel/` (sin alias `/void/`).

---

## 2026-01-20 — Base módulo Estación de Servicios (FUEL): RBAC + rutas + contrato auditoría

### Contexto

Se inicializa el módulo de dominio **Estación de Servicios** (FUEL) con una app Django mínima, ruta API y catálogo RBAC, dejando el esqueleto listo para implementar operación (turnos, despachos, ventas, tanques, conciliación e intercompany).

### Cambios principales

- **API:** se agrega prefijo `api/fuel/` con un healthcheck autenticado.
- **RBAC:** roles `fuel_admin`, `fuel_supervisor`, `fuel_cashier`, `fuel_auditor` + permisos `fuel.*` en `seed_rbac_v01`.
- **Auditoría contractual:** se extiende el contrato con `event_type`/`reason_code`/`subject_type` de FUEL (preparado para operación futura).
- **Infra backend:** se habilita import de `modulos.*` desde la raíz del repo agregando `REPO_ROOT` al `sys.path` en settings.

### Archivos/Endpoints

- Endpoint: `GET /api/fuel/health/`
- `modulos/estacion_servicios/` (apps/urls/views)
- `backend/src/config/settings/base.py` (REPO_ROOT en `sys.path` + INSTALLED_APPS)
- `backend/src/config/urls.py` (include `api/fuel/`)
- `backend/src/apps/rbac/seed_v01.py`
- `backend/src/apps/audit/contracts.py`

---

## 2026-01-18 — Cierre backend (antes login_module): revoke-access, Auditoría UI y PROD

### Contexto

Cierre funcional del módulo backend (en ese momento nombrado `login_module`) (ORG/HR/IAM/RBAC/AUDIT) tras implementar auditoría UI, revoke-access y despliegue PROD.

### Cambios principales

- **HR:** Implementado endpoint y lógica `revoke-access` (desactiva RoleAssignments origin=POSITION, memberships y opcional user.is_active). Test dedicado y documentado en README.
- **Auditoría UI:** Nueva pantalla en `/audit/bitacora` (gated por permiso `audit.read`), integrada en menú y router. Permite filtrar y ver eventos, incluyendo `HR_EMPLOYEE_ACCESS_REVOKED`.
- **Infraestructura PROD:** Agregado `compose.prod.yaml`, Nginx SPA + proxy `/api/`, `.env.prod.example`, Dockerfiles prod. Documentado en CHANGELOG y README.

### Archivos/Endpoints

- `frontend/src/pages/AuditBitacoraPage.vue`
- `frontend/src/router/routes.ts`
- `frontend/src/layouts/MainLayout.vue`
- `frontend/README.md`
- `backend/src/apps/hr/services.py` (revoke-access)
- `backend/src/apps/hr/tests/test_hr_method_permissions.py`
- `compose.prod.yaml`, `Dockerfile.frontend`, `Dockerfile.backend`, `.env.prod.example`

### Notas/Riesgos

- Auditoría UI requiere permiso `audit.read` y contexto activo.
- `revoke-access` afecta acceso inmediato y memberships; requiere validación en ambientes productivos.

---

# Bitácora de Cambios (desarrollo)

## ¿Qué es esto?

Este documento es un **registro cronológico, detallado y “append-only”** de las acciones realizadas durante el desarrollo del proyecto.

- **Objetivo:** dejar trazabilidad de _qué_ se cambió, _por qué_ se cambió, _dónde_ (archivos/endpoints) y _qué impacto_ tiene.
- **No reemplaza** a `CHANGELOG.md`:
  - `CHANGELOG.md` se mantiene como resumen de cambios “curados” por versión/fecha para releases.
  - Esta bitácora se usa como **diario técnico** (más granular), útil para debugging, auditoría de decisiones y handoff.
- **Regla:** no se reescribe historial; se agregan entradas nuevas (idealmente al final o creando secciones por fecha).

## Formato recomendado para nuevas entradas

Cada entrada debe ser lo suficientemente clara como para que otra persona pueda entender el cambio sin contexto adicional.

- **Fecha:** `YYYY-MM-DD`
- **Contexto:** ticket/PR (si aplica), módulo afectado, motivación
- **Cambios:** listado breve y verificable
- **Archivos/Endpoints:** rutas tocadas
- **Notas/Riesgos:** compatibilidad, permisos, migraciones

---

## 2026-01-10 — ORG multi-company + flujo bootstrap/login

### Contexto

Se habilita el flujo de “primer arranque” (sistema _fresh_) sin redirección automática al wizard, mostrando CTA en login. Además se implementa ORG multi-company (Holding → Companies) con endpoint y UI.

### Backend (Django)

- Nuevo serializer para crear compañías:
  - `CompanyCreateSerializer`.
- Nuevo endpoint:
  - `GET /api/org/companies/` → lista compañías del holding de la compañía actual.
  - `POST /api/org/companies/` → crea compañía en el holding + crea `CompanyProfile`.
  - Dedupe por `name` dentro del holding (retorna `409` si duplica).
  - Al crear: se otorga acceso inmediato al creador (membership) y se asigna `company_admin` en el nuevo scope si existe el rol.
  - Auditoría: `ORG_COMPANY_CREATED`.
- Fix de permisos por método en Company Profile:
  - `GET` requiere `org.company.read`.
  - `PUT` requiere `org.company.update`.

**Archivos tocados**

- `backend/src/apps/org/serializers.py`
- `backend/src/apps/org/views.py`
- `backend/src/apps/org/urls.py`

### RBAC seed

- Se agrega el permiso `org.company.create`.
- Se otorga a `company_admin`.

**Archivo tocado**

- `backend/src/apps/rbac/seed_v01.py`

### Frontend (Quasar/Vue)

- Router: se elimina la redirección automática a `/bootstrap` desde `/login` en primer arranque (para que el login siempre muestre el CTA).
- Login: se muestra banner “Crear usuario inicial” cuando `bootstrapState.is_fresh` y se deshabilita el formulario de login en ese estado.
- Service ORG: se agregan `listCompanies()` y `createCompany()` contra `/org/companies/`.
- Página nueva “ORG · Compañías” (AppContainer + AppDataTable + dialog de creación).
- Rutas:
  - Se agrega `/org/companies` con permisos `org.company.read`.
  - Se ajusta `/org/company-profile` para requerir `org.company.read` (ya no `update` para GET).
- Menú: se agrega item “ORG Compañías” en el drawer.

**Archivos tocados**

- `frontend/src/router/index.ts`
- `frontend/src/pages/LoginPage.vue`
- `frontend/src/services/org.service.ts`
- `frontend/src/pages/OrgCompaniesPage.vue`
- `frontend/src/router/routes.ts`
- `frontend/src/layouts/MainLayout.vue`

### Notas

- La pantalla `/bootstrap` queda como el punto de creación del usuario inicial.
- La UI de compañías requiere contexto activo y respeta permisos RBAC (`org.company.read` / `org.company.create`).

---

## 2026-01-10 — UI Density (compact) + actualización de documentación

### Contexto

Se refuerza el modo de densidad `compact` para que el cambio sea perceptible y consistente (padding de página, gutters, densidad real de tablas). Además se actualiza documentación para reflejar el nuevo flujo de onboarding y el endpoint de compañías.

### Frontend (UI Kit + estilos)

- `AppContainer`: padding de página dinámico según densidad (`compact` → `q-pa-sm`, default → `q-pa-md`).
- `AppDataTable`: gutters/padding del wrapper y `dense` automático en `compact` (respetando `dense` explícito si se pasa en attrs).
- `AppPageHeader`: gutters y tamaño de título según densidad.
- `app.scss`: `density-compact` más visible (font-size y tamaños mínimos de controles comunes), además de los ajustes de tablas.

**Archivos tocados**

- `frontend/src/ui/AppContainer.vue`
- `frontend/src/ui/AppDataTable.vue`
- `frontend/src/ui/AppPageHeader.vue`
- `frontend/src/css/app.scss`

### Documentación

- Se documenta `GET/POST /api/org/companies/` + permisos (`org.company.read` / `org.company.create`).
- Se documenta Company Profile con permisos por método (`GET` read, `PUT` update).
- Se actualiza el onboarding: ya no se afirma redirección automática a `/bootstrap`; ahora `/login` muestra CTA hacia `/bootstrap`.
- Se agrega referencia a `BITACORA.md` en el README principal.

**Archivos tocados**

- `README.md`
- `backend/src/README.md`
- `frontend/README.md`
- `CHANGELOG.md`

---

## 2026-01-10 — Addendum: ORG Companies (B2–B6) + UX frontend (C3–C4)

### Contexto

Se endurece el endpoint de compañías y se aclara el flujo UX para que sea coherente con RBAC por método, auditoría contractual y selector por memberships.

### Backend (ORG)

- `GET /api/org/companies/` pasa a listar **compañías accesibles por membresía** (selector `get_accessible_companies`).
- `POST /api/org/companies/` ahora corre en transacción y:
  - crea company+profile,
  - asegura/reactiva membership del creador,
  - clona accesos del creador desde la company actual (RoleAssignment + AdminGrant),
  - emite auditoría `ORG_COMPANY_CREATED`.
- Contrato de auditoría: se permite `ORG_COMPANY_CREATED`.
- URLs ORG: se agrega/asegura la ruta `companies/` con `name="org-companies"`.

### Tests

- Se extiende `backend/tests/test_org_endpoints_audit.py` para cubrir:
  - `GET /api/org/company/profile/` con permiso `org.company.read` (sin requerir update).
  - Listado/creación de companies + auditoría `ORG_COMPANY_CREATED`.

### Frontend

- `OrgCompanyProfilePage.vue`: modo lectura vs edición.
  - Badge Read siempre; badge Update y botón Guardar solo si `org.company.update`.
  - Inputs deshabilitados si no hay permiso de update.
- `OrgCompaniesPage.vue` se ajusta a “ORG · Empresas” con tabla PC-first:
  - filtro en toolbar,
  - badge de estado,
  - acción para cambiar contexto,
  - diálogo de creación que recarga ACL + cambia contexto a la nueva empresa.

---

## 2026-01-13 — HR Empleados (PC-first) + fixes de provisionamiento

### Contexto

Se completa el flujo PC-first de HR (empleados/asignaciones/provisionamiento) y se corrigen fallos encontrados al probar el frontend contra una BD existente.

### Frontend (Quasar/Vue)

- Se reestructura `HrEmployeesPage.vue` (template + script) y se eliminan artefactos que rompían el build.
- Tabla densa con filtro, badges de estado (activo/asignación/acceso) y acciones rápidas:
  - Crear/editar empleado
  - Asignar puesto/sucursal
  - Terminar asignación
  - Provisionar acceso (username + password provisional)

**Archivos tocados**

- `frontend/src/pages/HrEmployeesPage.vue`
- `frontend/src/services/hr.service.ts`
- `frontend/src/ui/AppDataTable.vue`

### Backend (Django/DRF)

- HR:
  - Listado de empleados incluye resumen de asignaciones activas.
  - Endpoints de asignaciones del empleado (`GET/POST`) y endpoint idempotente para terminar asignación.
  - Provisionamiento de usuario: normaliza `email` vacío a `NULL` y valida unicidad.
- Cuentas:
  - Se agrega el campo `is_setup_complete` al modelo `accounts.User` y una migración compatible (agrega columna solo si falta) para evitar 500 por NOT NULL en BD existentes.

**Archivos tocados**

- `backend/src/apps/hr/views.py`
- `backend/src/apps/hr/services.py`
- `backend/src/apps/hr/serializers.py`
- `backend/src/apps/accounts/models.py`
- `backend/src/apps/accounts/migrations/0003_user_is_setup_complete.py`

### RBAC

- Se incorpora el permiso `hr.assignment.read` y se asigna a roles relevantes vía seed.

**Archivo tocado**

- `backend/src/apps/rbac/seed_v01.py`

### Validación

- Frontend: `npm run build` compila correctamente.
- Backend: migraciones aplicadas; el endpoint `/api/hr/employees/<id>/provision-user/` deja de responder 500 en BD existentes.

---

## 2026-01-14 — HR reset de contraseña provisional (A)

### Contexto

Se implementa el reset controlado de contraseña provisional para empleados (HR), alineado con el flujo de provisionamiento y con auditoría contractual (sin exponer secretos).

### Backend (Django/DRF)

- Nuevo endpoint: `POST /api/hr/employees/<id>/reset-temp-password/`
  - Permisos: `iam.users.create` + `hr.employee.update`.
  - Reglas:
    - `409` si el empleado no tiene `linked_user`.
    - `409` si el empleado no tiene asignación activa.
    - Fuerza `must_change_password=True`.
  - Payload opcional: `{ "temp_password": "..." }` (si se omite, se autogenera).
  - Respuesta: `{ user_id, username, temp_password }`.
- Auditoría:
  - Se habilita y emite el evento `HR_EMPLOYEE_TEMP_PASSWORD_RESET`.
  - La contraseña **no** se guarda en auditoría.

**Archivos tocados**

- `backend/src/apps/audit/contracts.py`
- `backend/src/apps/hr/serializers.py`
- `backend/src/apps/hr/services.py`
- `backend/src/apps/hr/views.py`
- `backend/src/apps/hr/urls.py`

### Tests

- Se agregan pruebas para éxito + auditoría y para `409` sin `linked_user`.

**Archivo tocado**

- `backend/src/tests/test_hr_end_assignment_endpoint.py`

### Frontend (Quasar/Vue)

- HR Empleados: acción `lock_reset` para resetear contraseña provisional.
- Diálogo para reset (auto o manual) + diálogo de resultado (mostrar una vez + copiar).
- Servicio: método `resetEmployeeTempPassword()`.
- Mensajes UX mejorados para errores típicos (`403/404/409`).

**Archivos tocados**

- `frontend/src/pages/HrEmployeesPage.vue`
- `frontend/src/services/hr.service.ts`

### Validación

- Backend: `pytest -q`.
- Frontend: `npm run build`.
