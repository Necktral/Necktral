## Bitácora (fuente canónica)

La bitácora oficial del proyecto se mantiene en un solo lugar para evitar duplicados:

- ../../BITACORA.md

Este archivo queda como stub por compatibilidad con referencias antiguas.

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

- `login_module/src/apps/org/serializers.py`
- `login_module/src/apps/org/views.py`
- `login_module/src/apps/org/urls.py`

### RBAC seed

- Se agrega el permiso `org.company.create`.
- Se otorga a `company_admin`.

**Archivo tocado**

- `login_module/src/apps/rbac/seed_v01.py`

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
- `login_module/src/README.md`
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

- Se extiende `login_module/tests/test_org_endpoints_audit.py` para cubrir:
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
