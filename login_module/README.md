# Backend (login_module) — Django/DRF

Backend del ERP/CRM basado en Django + DRF, con RBAC, auditoría contractual y módulos ORG/HR/IAM.

## Estructura relevante

- Código: `login_module/src/`
- Apps: `login_module/src/apps/` (audit, auth, hr, org, rbac, sync, etc.)
- Settings: `login_module/src/config/settings/` (dev/test/prod)
- Tests: `login_module/src/tests/` y `tests/` (en la raíz)

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

cd login_module
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

- `GET /api/auth/bootstrap/status/` — Indica si la instalación está “fresh” (DB vacía) y permite al frontend evitar llamadas protegidas hasta completar bootstrap.

### HR (IAM desde empleados)

- `POST /api/hr/employees/<id>/provision-user/` — Crea usuario vinculado al empleado (requiere asignación activa).
- `POST /api/hr/employees/<id>/reset-temp-password/` — Resetea la contraseña provisional sin auditar/exponer el secreto.
- `POST /api/hr/employees/<id>/revoke-access/` — Revoca accesos del usuario vinculado al empleado en scope de company+branches.

## Auditoría contractual

- Todos los endpoints de escritura emiten eventos de auditoría con `reason_code` y `event_type` permitido por contrato.
- Integridad: encadenado por hash y firmado con HMAC (`AUDIT_HMAC_KEY` en PROD).

Guías de organización:

- Contract Pack v1.0: [../docs/CONTRACT_PACK_v1.0.md](../docs/CONTRACT_PACK_v1.0.md)
- Addendum Offline-first v1.0: [../docs/ADDENDUM_OFFLINE_FIRST_v1.0.md](../docs/ADDENDUM_OFFLINE_FIRST_v1.0.md)
- Índice de docs: [../docs/README.md](../docs/README.md)

---

## Contrato de errores API (JSON envelope)

Para clientes web/móvil, el backend aplica un contrato de errores consistente en `/api/*`:

- Respuestas `>= 400` se normalizan a un envelope JSON con campo raíz `error`.
- Se preserva/expone `X-Request-Id` y se replica en `error.request_id`.
- 404/500 fuera de DRF también devuelven JSON contractual bajo `/api/*`.

Tests contractuales:

- `tests/test_contract_404_envelope.py`
- `tests/test_contract_error_envelope_middleware.py`

### Verificar integridad (Gate 3)

El comando valida:

- `signature` (HMAC-SHA256 sobre `event_hash`)
- consistencia del encadenamiento por partición (`prev_event_hash` + `AuditChainHeadV2`)

## FUEL (Estación de Servicios)

- Base path: `/api/fuel/`
- `GET /api/fuel/health/` — Healthcheck del módulo (público)

Endpoints (MVP):

- `POST /api/fuel/shifts/open/` — Abrir turno (permiso: `fuel.shift.open`)
- `POST /api/fuel/shifts/<shift_id>/close/` — Cerrar turno (permiso: `fuel.shift.close`)
- `POST /api/fuel/dispenses/` — Registrar despacho (permiso: `fuel.dispense.create`)
- `POST /api/fuel/sales/` — Crear venta (permiso: `fuel.sale.create`)
- `POST /api/fuel/sales/<sale_id>/cancel/` — Cancelar venta (permiso: `fuel.sale.void`)

Roles/permisos del módulo se agregan vía `python src/manage.py seed_rbac_v01` (roles `fuel_*`, permisos `fuel.*`).

```bash
docker compose exec -T backend python manage.py audit_verify_chain
```

- En DB vacía (CI determinista):

  ```bash
  docker compose exec -T backend python manage.py audit_verify_chain --seed-minimal
  ```

## Endpoints principales

### Documentación y esquema

- `GET /api/schema/` — Esquema OpenAPI
- `GET /api/schema/swagger-ui/` — Swagger UI
- `GET /api/schema/redoc/` — Redoc

### Autenticación

- `/api/auth/` — Endpoints de login, logout, registro, etc.

### IAM (Identidad y membresías)

- `/api/iam/` — Gestión de usuarios, membresías, etc.

### RBAC (Roles y permisos)

- `/api/rbac/` — Roles, permisos, asignaciones

### Sincronización de dispositivos

- `POST /api/sync/enrollment/challenges/` — Crear `enrollment_code` (requiere JWT + permiso: `sync.device.enroll` + header `X-Company-Id`)
- `POST /api/sync/enroll/` — Enrolar dispositivo (no requiere JWT; el secreto es `enrollment_code` one-time)
- `POST /api/sync/batch/` — Enviar batch offline (auth por `X-Device-Id` + firma Ed25519 por comando)
- `GET /api/sync/devices/` — Listar dispositivos registrados (requiere permiso: `sync.device.revoke`)
- `POST /api/sync/devices/<device_id>/revoke/` — Revocar dispositivo (requiere permiso: `sync.device.revoke`)

Documentación base (contrato offline-first):

- [../docs/ADDENDUM_OFFLINE_FIRST_v1.0.md](../docs/ADDENDUM_OFFLINE_FIRST_v1.0.md)

### Auditoría

- `GET /api/audit/bitacora/` — Listar eventos de auditoría
- `GET /api/audit/events/<uuid:event_id>/` — Detalle de evento de auditoría

### ORG (Organización)

- `GET /api/org/company/profile/` — Ver perfil de la empresa
- `PUT /api/org/company/profile/` — Actualizar perfil de la empresa
- `GET /api/org/companies/` — Listar compañías accesibles por membresía
- `POST /api/org/companies/` — Crear compañía bajo el holding (clona accesos del creador)
- `GET /api/org/branches/` — Listar sucursales (requiere permiso: org.branch.read)
- `POST /api/org/branches/` — Crear sucursal (requiere permiso: org.branch.create)
- `PATCH /api/org/branches/{branch_id}/` — Actualizar sucursal (requiere permiso: org.branch.update)

### HR (Recursos Humanos)

- `GET /api/hr/positions/` — Listar puestos
- `POST /api/hr/positions/` — Crear puesto
- `PATCH /api/hr/positions/<int:position_id>/` — Actualizar puesto
- `PUT /api/hr/positions/<int:position_id>/roles/` — Mapear puesto a roles
- `GET /api/hr/employees/` — Listar empleados
- `POST /api/hr/employees/` — Crear empleado
- `PATCH /api/hr/employees/<int:employee_id>/` — Actualizar empleado
- `POST /api/hr/employees/<int:employee_id>/assignments/` — Asignar puesto/sucursal
- `GET /api/hr/employees/<int:employee_id>/assignments/` — Listar asignaciones del empleado (requiere permiso: hr.assignment.read)
- `POST /api/hr/employees/<int:employee_id>/assignments/` — Asignar puesto/sucursal
- `POST /api/hr/employees/<int:employee_id>/assignments/<int:assignment_id>/end/` — Finalizar asignación
- Nuevo endpoint: `POST /api/hr/employees/<id>/provision-user/`
  - Permite crear usuarios vinculados a empleados con contraseña provisional.
  - Valida asignaciones activas y fuerza cambio de contraseña en primer login.
  - Requiere permisos `iam.users.create` y `hr.employee.update`.

- `POST /api/hr/employees/<id>/reset-temp-password/`
  - Resetea contraseña provisional del usuario vinculado.
  - Auditoría: `HR_EMPLOYEE_TEMP_PASSWORD_RESET` (sin exponer la contraseña).

- `POST /api/hr/employees/<id>/revoke-access/`
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

Actualizado: 2026-01-23.
