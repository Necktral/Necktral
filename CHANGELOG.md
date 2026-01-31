## [2026-01-31] - Endurecimiento Sync HMAC

### Changed

- **Sync Engine (Backend):** El endpoint `/api/sync-hmac/batch/` ahora solo persiste el nonce tras validar la firma HMAC. Esto previene ataques de denegación y asegura que nonces inválidos no se almacenan. El manejo de replays es atómico y seguro usando `IntegrityError`.
- **Tests:** Se extiende el test de firma inválida para verificar que no se crea nonce en ese caso. Se mantiene la cobertura de replay.

# Changelog

## [Unreleased]

### Added

- **Docs (Operación):** pack operativo Import/Export & Sourcing (empresa + plantillas: RFQ, landed cost, checklist, términos).
- **HR (Backend/Frontend):** endpoint `POST /api/hr/employees/<id>/reset-temp-password/` + evento de auditoría `HR_EMPLOYEE_TEMP_PASSWORD_RESET` + acción UI en empleados.
- **HR (Backend/Frontend):** endpoint `POST /api/hr/employees/<id>/revoke-access/` + evento de auditoría `HR_EMPLOYEE_ACCESS_REVOKED` + acción UI en empleados.
- **Infra PROD:** `compose.prod.yaml` (backend+db+web), Nginx SPA + proxy `/api/`, `.env.prod.example` y Dockerfiles PROD (backend y web).
- **FUEL (Backend):** base del módulo Estación de Servicios bajo `/api/fuel/` + endpoint `GET /api/fuel/health/`.
- **FUEL (Backend):** endpoints operativos MVP:
  - `POST /api/fuel/shifts/open/`
  - `POST /api/fuel/shifts/<shift_id>/close/`
  - `POST /api/fuel/dispenses/`
  - `POST /api/fuel/sales/`
  - `POST /api/fuel/sales/<sale_id>/cancel/`
- **FUEL (Tests):** test de flujo (turno → despacho → venta → cierre) + constraint de turno único.
- **RBAC:** roles `fuel_*` y permisos `fuel.*` en `seed_rbac_v01`.
- **Auditoría (contrato):** extensión del contrato con `event_type`, `reason_code` y `subject_type` para FUEL.
- **API (Contrato):** handlers 404/500 para `/api/*` que devuelven JSON contractual con `error.request_id` + header `X-Request-Id`.
- **API (Contrato):** middleware que normaliza cualquier respuesta `>=400` en `/api/*` a envelope JSON (incluye respuestas no-JSON).
- **Frontend (Offline):** outbox en IndexedDB (dependencia `idb`) para encolar operaciones de inventario y hacer flush al recuperar conectividad.
- **Frontend (Offline Sync):** flush real vía `POST /api/sync/batch/` con autenticación por `X-Device-Id` y firma Ed25519 por comando (dependencia `tweetnacl`).
- **Frontend (Sync):** helper de enrollment de dispositivo (`POST /api/sync/enroll/`) que genera keypair Ed25519 y persiste `device_id`+keys.
- **Sync Engine (Backend):** handlers de inventario para aplicar comandos offline (receive/issue/adjust/transfer) con idempotencia por `command_id`.
- **Sync Engine (Tests):** test E2E que enrola → envía batch → verifica efectos e integridad/auditoría.

### Changed

- **Docs (Operación):** índice de templates del pack Import/Export + corrección de placeholders en contrato proveedor.
- **FUEL (Backend):** `GET /api/fuel/health/` queda público (sin auth) para monitoreo.

## [2026-01-13] - Release

### Added

- **Módulo HR (Frontend):**
  - Implementación de `HrPositionsPage.vue` para gestión de cargos/posiciones.
  - Implementación de `HrEmployeesPage.vue` para gestión de empleados y asignaciones.
  - Servicio `hr.service.ts` con métodos para interactuar con la API de HR (Positions, Employees, Assignments).
  - Rutas `/hr/positions` y `/hr/employees` protegidas por permisos RBAC (`hr.position.read`, `hr.employee.read`).
  - Integración de `RoleMap` en la creación de asignaciones.
  - Columna "Asignación" (badge) y acciones PC-first (asignar, terminar, provisionar).
- **Módulo ORG (Frontend):**
  - Implementación de `OrgCompanyProfilePage.vue` y `OrgBranchesPage.vue`.
  - Servicio `org.service.ts`.
- **ORG Multi-company (Backend + Frontend):**
  - Endpoint `GET/POST /api/org/companies/` (listado por memberships + creación bajo holding).
  - Auditoría contractual: `ORG_COMPANY_CREATED` permitido y emitido en POST.
  - Clonado de accesos del creador (roles/grants) al crear una nueva company.
  - Permiso RBAC nuevo: `org.company.create` (asignado a `company_admin`).
  - UI: página `OrgCompaniesPage.vue` (ORG · Empresas) con tabla PC-first + dialog de creación.
- **UX Bootstrap/Login:**
  - En primer arranque, `/login` muestra CTA para crear usuario inicial en `/bootstrap`.
- **UI Density:**
  - Modo `compact` más perceptible (padding de páginas, gutters, densidad real de tablas).
- **Configuración:**
  - Plugin `Notify` habilitado en `quasar.config.ts`.
  - Configuración de auditoría (`AUDIT_MODULE_NAME`, `AUDIT_SCHEMA_VERSION`) en `base.py`.

### Fixed

- **Backend:**
  - Corrección de ruta de carga de `.env` en `base.py`.
  - Adición de headers CORS personalizados (`x-company-id`, `x-branch-id`, etc.) en `base.py`.
  - Corrección de error 500 en Login por falta de configuración de auditoría (`AUDIT_MODULE_NAME`, `AUDIT_SCHEMA_VERSION`).
  - Corrección de tipo de dato para `AUDIT_SCHEMA_VERSION` (int en lugar de str).
  - Auditoría contractual: `module` de eventos ajustado a `AUTH`.
  - Endpoint `GET /api/auth/me/`: `roles` incluye roles scoped (`RoleAssignment`) y legacy (`UserRole`).
- **Frontend:**
  - Solución a error `$q.notify is not a function` habilitando el plugin.
  - Tipado estricto en columnas de tablas Quasar (`QTableColumn`).
  - Lint: eliminación de imports/funciones no usados en `HrEmployeesPage.vue`.

- **HR (Backend/Frontend):**
  - Se corrige el endpoint documentado de provisión: `POST /api/hr/employees/<id>/provision-user/`.
  - Se agrega migración y campo `is_setup_complete` en `accounts.User` para evitar error 500 al crear usuarios en BD existentes.
  - Se normaliza `email` vacío a `NULL` en provisionamiento para evitar violación de unicidad en `accounts_user.email`.
- **ORG (Backend):**
  - Permisos por método en Company Profile: `GET` usa `org.company.read`, `PUT` usa `org.company.update`.
  - URLs ORG con nombres de ruta (`org-companies`, `org-company-profile`, etc.).

## [2026-01-08] - Release

### Added

- Endpoint backend: `POST /api/hr/employees/<id>/provision-user/` para provisionar usuario a empleado.
- Permiso IAM: `iam.users.create` para controlar el acceso a la provisión de usuarios.
- Diálogo y botón en frontend para provisionar acceso desde la UI de empleados.
- Documentación actualizada en todos los módulos sobre el nuevo flujo y seguridad HR.

### Changed

- Lógica de reconciliación HR: ya no se fuerza la membresía a la empresa (COMPANY) por defecto, solo por asignaciones activas y roles mapeados.
- Mejoras de robustez y seguridad en la asignación de memberships.

### Fixed

- Mensajes y validaciones en el flujo de provisionamiento de usuario (backend y frontend).
