# Backend (backend) — Django/DRF

Backend del ERP/CRM basado en Django + DRF, con RBAC, auditoría contractual y módulos ORG/HR/IAM.

## Estructura relevante

- Código: `backend/src/`
- Apps: `backend/src/apps/` (audit, auth, hr, org, rbac, sync, etc.)
- Settings: `backend/src/config/settings/` (dev/test/prod)
- Tests: `backend/src/tests/` y `tests/` (en la raíz)

## Ejecutar en DEV (Docker)

Desde la raíz del repo:

```bash
cp .env.example .env
docker compose up -d --build
```

El contenedor `backend` corre migraciones al iniciar. Para tests dentro de Docker:

```bash
docker compose exec backend pytest -q
```

## Ejecutar en DEV (venv)

```bash
source system_wis/bin/activate
pip install -r requirements/dev.txt

cd backend
python src/manage.py migrate --noinput
python src/manage.py runserver
```

## Ejecutar en PROD (Docker)

```bash
cp .env.prod.example .env
docker compose -f compose.prod.yaml up -d --build
```

En PROD, Nginx sirve la SPA y proxyea `/api/` hacia el backend.

## Endpoints clave

### Bootstrap / Fresh install

- `GET /api/backend/iam/bootstrap/status/` — Indica si la instalación está “fresh” (DB vacía) y permite al frontend evitar llamadas protegidas hasta completar bootstrap.

### HR (IAM desde empleados)

- `POST /api/hr/employees/<id>/provision-user/` — Crea usuario vinculado al empleado (requiere asignación activa).
- `POST /api/hr/employees/<id>/reset-temp-password/` — Resetea la contraseña provisional sin auditar/exponer el secreto.
- `POST /api/hr/employees/<id>/revoke-access/` — Revoca accesos del usuario vinculado al empleado en scope de company+branches.

## Auditoría contractual

- Todos los endpoints de escritura emiten eventos de auditoría con `reason_code` y `event_type` permitido por contrato.
- Integridad: encadenado por hash y firmado con HMAC (keyring `AUDIT_HMAC_KEYS` o fallback `AUDIT_HMAC_KEY`).
- Los eventos nuevos guardan `signature_key_id` para rotación segura.

## Observabilidad (Sentry + métricas)

- Sentry es opcional. Se activa configurando `SENTRY_DSN` en `.env`.
- Variables útiles: `SENTRY_ENVIRONMENT`, `SENTRY_TRACES_SAMPLE_RATE`, `SENTRY_PROFILES_SAMPLE_RATE`, `SENTRY_RELEASE`.
- Métricas básicas: `GET /api/metrics/` (solo staff/superuser). Requiere auth y contexto (`X-Company-Id`).
- En desarrollo, `testserver` debe estar en `DJANGO_ALLOWED_HOSTS` para pruebas con `APIClient`.
- Todas las respuestas incluyen `X-Request-Id` para trazabilidad.

Guías de organización:

- Contract Pack v1.0: [../docs/CONTRACT_PACK_v1.0.md](../docs/CONTRACT_PACK_v1.0.md)
- Addendum Offline-first v1.0: [../docs/ADDENDUM_OFFLINE_FIRST_v1.0.md](../docs/ADDENDUM_OFFLINE_FIRST_v1.0.md)
- Índice de docs: [../docs/README.md](../docs/README.md)

### Verificar integridad (Gate 3)

El comando valida:

- `signature` (HMAC-SHA256 sobre `event_hash`)
- consistencia del encadenamiento por partición (`prev_event_hash` + `AuditChainHeadV2`)

## Paginación en listados

- Listados ORG/HR/RBAC soportan `limit` y `offset`.
- Respuesta estándar: `{ count, limit, offset, results }`.

## FUEL (Estación de Servicios)

- Base path canónico: `/api/backend/fuel/`
- Alias legacy temporal: `/api/fuel/` (con headers `Deprecation/Sunset/Link`)
- `GET /api/backend/fuel/health/` — Healthcheck del módulo (público)

Endpoints (MVP):

- `POST /api/backend/fuel/shifts/open/` — Abrir turno (permiso: `fuel.shift.open`)
- `POST /api/backend/fuel/shifts/<shift_id>/close/` — Cerrar turno (permiso: `fuel.shift.close`)
- `POST /api/backend/fuel/dispenses/` — Registrar despacho (permiso: `fuel.dispense.create`)
- `POST /api/backend/fuel/sales/` — Crear venta (permiso: `fuel.sale.create`)
- `POST /api/backend/fuel/sales/<sale_id>/cancel/` — Cancelar venta (permiso: `fuel.sale.void`)

Roles/permisos del módulo se agregan vía `python src/manage.py seed_rbac_v01` (roles `fuel_*`, permisos `fuel.*`).

```bash
docker compose exec -T backend python manage.py audit_verify_chain
```

- En DB vacía (CI determinista):

  ```bash
  docker compose exec -T backend python manage.py audit_verify_chain --seed-minimal
  ```

## Endpoints principales

### Prefijos canónicos

- `/api/backend/auth/`
- `/api/backend/iam/`
- `/api/backend/org/`
- `/api/backend/reports/`
- `/api/backend/rbac/`
- `/api/backend/sync/`
- `/api/backend/sync-hmac/`
- `/api/backend/audit/`
- `/api/backend/metrics/`
- `/api/backend/hr/`
- `/api/backend/accounting/`
- `/api/backend/payments/`
- `/api/backend/cec/`
- `/api/backend/integration/`
- `/api/backend/billing/`
- `/api/backend/inventory/`
- `/api/backend/procurement/`
- `/api/backend/fuel/`

### Accounting (rutas canónicas + compat temporal)

- Canónico:
  - `/api/backend/accounting/reports/*`
  - `/api/backend/accounting/dashboard/*`
- Legacy temporal:
  - `/api/accounting/reports/*`
  - `/api/accounting/dashboard/*`
- Ventana legacy activa con headers `Deprecation/Sunset/Link` hasta **2026-05-18**.

### Documentación y esquema

- `GET /api/schema/` — Esquema OpenAPI
- `GET /api/schema/swagger-ui/` — Swagger UI
- `GET /api/schema/redoc/` — Redoc

### Autenticación

- `/api/backend/auth/` — Endpoints de login, logout, registro, etc.

### IAM (Identidad y membresías)

- `/api/backend/iam/` — Gestión de usuarios, membresías, etc.

### RBAC (Roles y permisos)

- `/api/backend/rbac/` — Roles, permisos, asignaciones

### Sincronización de dispositivos

- `GET /api/backend/sync/devices/` — Listar dispositivos registrados (requiere permiso: sync.device.revoke)
  - [Ver documentación detallada](../ops/docs/api/sync_devices_list.md)

### Auditoría

- `GET /api/backend/audit/bitacora/` — Listar eventos de auditoría
- `GET /api/backend/audit/events/<uuid:event_id>/` — Detalle de evento de auditoría

### ORG (Organización)

- `GET /api/backend/org/company/profile/` — Ver perfil de la empresa
- `PUT /api/backend/org/company/profile/` — Actualizar perfil de la empresa
- `GET /api/backend/org/companies/` — Listar compañías accesibles por membresía
- `POST /api/backend/org/companies/` — Crear compañía bajo el holding (clona accesos del creador)
- `GET /api/backend/org/branches/` — Listar sucursales (requiere permiso: org.branch.read)
- `POST /api/backend/org/branches/` — Crear sucursal (requiere permiso: org.branch.create)
- `PATCH /api/backend/org/branches/{branch_id}/` — Actualizar sucursal (requiere permiso: org.branch.update)

### HR (Recursos Humanos)

- `GET /api/backend/hr/positions/` — Listar puestos
- `POST /api/backend/hr/positions/` — Crear puesto
- `PATCH /api/backend/hr/positions/<int:position_id>/` — Actualizar puesto
- `PUT /api/backend/hr/positions/<int:position_id>/roles/` — Mapear puesto a roles
- `GET /api/backend/hr/employees/` — Listar empleados
- `POST /api/backend/hr/employees/` — Crear empleado
- `PATCH /api/backend/hr/employees/<int:employee_id>/` — Actualizar empleado
- `POST /api/backend/hr/employees/<int:employee_id>/assignments/` — Asignar puesto/sucursal
- `GET /api/backend/hr/employees/<int:employee_id>/assignments/` — Listar asignaciones del empleado (requiere permiso: hr.assignment.read)
- `POST /api/backend/hr/employees/<int:employee_id>/assignments/` — Asignar puesto/sucursal
- `POST /api/backend/hr/employees/<int:employee_id>/assignments/<int:assignment_id>/end/` — Finalizar asignación
- Nuevo endpoint: `POST /api/backend/hr/employees/<id>/provision-user/`
  - Permite crear usuarios vinculados a empleados con contraseña provisional.
  - Valida asignaciones activas y fuerza cambio de contraseña en primer login.
  - Requiere permisos `iam.users.create` y `hr.employee.update`.

- `POST /api/backend/hr/employees/<id>/reset-temp-password/`
  - Resetea contraseña provisional del usuario vinculado.
  - Auditoría: `HR_EMPLOYEE_TEMP_PASSWORD_RESET` (sin exponer la contraseña).

- `POST /api/backend/hr/employees/<id>/revoke-access/`
  - Revoca roles por puesto (`origin=POSITION`) y memberships en scope.
  - Auditoría: `HR_EMPLOYEE_ACCESS_REVOKED`.

## Comandos de gestión

- `python manage.py seed_rbac_v01` — Siembra roles, permisos y mapeos estándar (idempotente, auditable)
- `python manage.py bootstrap_company --company-name ... --branch-name ... --admin-username ...` — Bootstrap de empresa, sucursal y admin
  - El comando es idempotente: si la empresa, sucursal o holding ya existen (por código o nombre), los reutiliza y reactiva si estaban desactivados.
  - Si usas `--no-input`, todos los parámetros son obligatorios y el comando falla si falta alguno.
  - AdminGrant siempre se crea con `org_unit=company` y se reactiva si estaba desactivado.
  - Membership y RoleAssignment también se reactivan si estaban off.
  - Validado por el test: `tests/test_bootstrap_company_command.py`.

## Simulación de carga (auth)

- Seed determinista de usuarios para k6:
  ```bash
  docker compose exec -T backend python src/manage.py seed_auth_users
  ```
- Guía completa: [../simulacion/README.md](../simulacion/README.md)

## Auditoría contractual

- Todos los endpoints de escritura generan eventos en apps.audit con reason_code y event_type según contrato.
- Ejemplo: `HR_POSITION_CREATED`, `ORG_BRANCH_CREATED`, `RBAC_SEEDED_V01`.
- El contrato de auditoría es estricto y validado por tests.

Guías de organización:

- Contract Pack v1.0: [../docs/CONTRACT_PACK_v1.0.md](../docs/CONTRACT_PACK_v1.0.md)
- Addendum Offline-first v1.0: [../docs/ADDENDUM_OFFLINE_FIRST_v1.0.md](../docs/ADDENDUM_OFFLINE_FIRST_v1.0.md)
- Índice de docs: [../docs/README.md](../docs/README.md)

## Tests automáticos

- `tests/test_hr_position_role_automation.py`: Valida automatización de roles por puesto y auditoría.
- `tests/test_seed_rbac_v01_command.py`: Valida comando seed_rbac_v01, creación de permisos y evento de auditoría.
- `tests/test_bootstrap_company_command.py`: Valida robustez, idempotencia y grants correctos del comando bootstrap_company.
- `tests/test_org_endpoints_audit.py`: Valida permisos RBAC por método en endpoints ORG y la trazabilidad/auditoría contractual de operaciones clave.

## Permisos y roles

- Catálogo estándar en apps/rbac/seed_v01.py
- Roles: company_admin, branch_manager, hr_manager, etc.
- Permisos: hr.position.create, org.branch.create, etc.

## Buenas prácticas

- Siempre ejecutar los comandos de seed y bootstrap en entornos nuevos.
- Validar con tests antes de desplegar.
- Consultar la auditoría para trazabilidad de cambios críticos.

## Seguridad y memberships HR

- La reconciliación de memberships ya no fuerza acceso a la empresa (COMPANY) por defecto.
- Solo se asignan memberships por asignaciones activas y roles mapeados.
- Mejora la robustez y evita accesos innecesarios.

## Permisos IAM

- Nuevo permiso: `iam.users.create` para controlar el provisionamiento de usuarios desde HR.

---

Actualizado: 2026-02-09.
