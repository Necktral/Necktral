# Necktral ERP/CRM

Sistema ERP/CRM modular con backend Django + DRF y frontend Quasar. Incluye RBAC, auditoría contractual, HR, ORG, IAM y sincronización.

## Estructura del repo

- `backend/`: backend Django/DRF (código en `backend/src/`)
- `frontend/`: consola web (Vue 3 + Quasar)
- `backend/src/apps/kernels/`: kernels canónicos (`accounting`, `facturacion`, `inventarios`, `payments`, `reporting`)
- `backend/src/apps/modulos/`: verticales y core apps (`estacion_servicios`, `iam`, `rbac`, `org`, `hr`, etc.)
- `compose.yaml`: entorno Docker (backend + Postgres)
- `system_wis/`: entorno virtual Python (dev)

## Documentación

- Estado ejecutivo: [docs/contexto_nucleos.md](docs/contexto_nucleos.md)
- Blueprint arquitectónico: [docs/ARQUITECTURA_DOMINIO_Y_CONTROL_v1.0.md](docs/ARQUITECTURA_DOMINIO_Y_CONTROL_v1.0.md)
- Runbooks y operación release: [docs/operacion/README.md](docs/operacion/README.md)
- Índice general: [docs/README.md](docs/README.md)

## Estado Release F1–F12 (2026-03-10)

- Fases **F1 a F12** implementadas y certificadas en **staging-first** (backend-only).
- Toolchain operativo y SRE activo para F8–F12 (`qa/run_phase8_go_live.sh` a `qa/run_phase12_go_live.sh`).
- Cierre maestro y seguridad con evidencia firmada (`bug_bounty_local` + `master_closure` en PASS).

### Qué está cerrado

- F6 Adapter B readiness (staging PASS).
- F7A GL core + FX (staging PASS).
- F7B Intercompany + consolidación (staging PASS).
- F8 Go-live controlado (burn-in 14/14 con sign-off contador PASS).
- F9/F10/F11/F12 cerradas en staging con gates estrictos.

### Qué falta para producción

- PR de release `release/f6-f12-staging-pass-20260310 -> master` aprobado y mergeado.
- Cutover productivo de piloto con burn-in operativo y rollback formal.
- Operación mensual continua F12 en producción con evidencia histórica.

## 🚀 Inicio rápido (Docker)

1. Configura variables

### Windows 11 (PowerShell)

```powershell
Copy-Item .env.example .env
```

### WSL (Ubuntu / bash)

```bash
cp .env.example .env
```

2. Levanta servicios

```bash
docker compose up -d --build
```

Si solo quieres backend + db (sin frontend):

```bash
docker compose up -d db backend
```

Esto levanta por defecto:

- Frontend (Quasar): http://localhost:3000
- Backend (Django/DRF): http://localhost:8000
- Analytics (Dash engine): http://localhost:3000/analytics
- DB (Postgres): localhost:5432

### Contrato de puertos Analytics (congelado)

- Prefix público canónico: `/analytics`
- Puerto interno Dash canónico: `8050`
- Dev:
  - host principal: `http://localhost:3000/analytics`
  - debug opcional directo: `http://localhost:8050/analytics`
- Prod:
  - acceso solo same-origin por Nginx: `http://localhost/analytics/`
  - sin publicación host de `8050`

Nota: el contenedor `backend` corre migraciones automáticamente al iniciar (ver `compose.yaml`).

## 🚀 Producción (Docker Compose)

El stack PROD sirve el frontend compilado con Nginx en `:80` y hace proxy de `/api/` hacia el backend.

1. Configura variables PROD

```bash
cp .env.prod.example .env
```

2. Levanta el stack PROD

```bash
docker compose -f compose.prod.yaml up -d --build
```

Endpoints:

- Web (SPA): http://localhost/
- API (proxy): http://localhost/api/
- Analytics (proxy same-origin): http://localhost/analytics/

Herramientas opcionales (Adminer):

```bash
docker compose -f compose.prod.yaml --profile tools up -d adminer
```

Si cambias dependencias Python (`requirements/*.txt`), reconstruye la imagen del backend:

```bash
docker compose build backend
docker compose up -d backend
```

### Reset total de DB (prueba “instalación fresca”)

```bash
docker compose down -v
docker compose up -d
```

Para verificar el estado fresh:

```bash
curl http://localhost:8000/api/auth/bootstrap/status/
```

### Bootstrap inicial (después de reset DB)

En una instalación fresca normalmente quieres:

1. Sembrar RBAC

```bash
docker compose exec backend python manage.py seed_rbac_v01
```

2. Crear usuario admin (si no existe)

```bash
docker compose exec backend python manage.py createsuperuser
```

3. Crear empresa/sucursal y grants iniciales (requiere que el usuario exista)

```bash
docker compose exec backend python manage.py bootstrap_company \
  --company-name "Necktral" \
  --branch-name "Principal" \
  --admin-username "admin"
```

## 💻 Desarrollo local

### Backend (venv)

```bash
source system_wis/bin/activate
pip install -r requirements/dev.txt

cd backend
python manage.py migrate --noinput
python manage.py runserver
```

### Frontend

```bash
cd frontend
npm install
npm run dev
```

## 🐳 100% Docker (incluye frontend)

Si prefieres no instalar Node localmente, el `compose.yaml` incluye un servicio `frontend`.

```bash
docker compose up -d frontend
```

Logs útiles:

- `docker compose logs -f backend`
- `docker compose logs -f frontend`

## ✅ Tests y análisis

## ✅ QA Runner (Gates 1–3)

El repo incluye un runner determinista para CI/local (lint + typecheck + tests + verificación de integridad de auditoría) con reportes en `qa/reports/`.

- Runner recomendado (DB limpia, reproducible):

  ```bash
  make qa-ci-fresh
  ```

- En CI (GitHub Actions):

  ```bash
  make qa-ci-ci
  ```

- Runner “normal” (usa la DB/volúmenes actuales; Gate 3 puede fallar si hay datos viejos inconsistentes):

  ```bash
  make qa-ci
  ```

Artefactos generados:

- `qa/reports/static_scan.txt`
- `qa/reports/ruff.txt`
- `qa/reports/mypy.txt`
- `qa/reports/pytest.xml`
- `qa/reports/coverage.xml`
- `qa/reports/coverage.txt`
- `qa/reports/audit_integrity.json`
- `qa/reports/reporting_r8_gate.json`
- `qa/reports/reporting_r8_gate_guard.json`
- `qa/reports/reporting_contract_guard.json`

Guard contractual versionado de reporting (U2):

```bash
make qa-reporting-contract-version-guard
```

### Backend

- Tests:

  ```bash
  source system_wis/bin/activate
  cd backend
  pytest
  ```

- Tests (dentro de Docker):
  ```bash
  docker compose exec backend pytest -q
  ```
- Lint (ruff):
  ```bash
  source system_wis/bin/activate
  cd backend
  ruff check .
  ```

### Frontend

- Lint:
  ```bash
  cd frontend
  npm run lint
  ```
- Tests (Vitest):
  ```bash
  cd frontend
  npm run test
  ```

## Auditoría (contrato)

- Los eventos de auditoría se emiten con `module=AUTH` y `schema_version=1`.
- Trazabilidad: hashes encadenados + firma HMAC con keyring (`AUDIT_HMAC_KEYS`) y `signature_key_id`.

### FUEL (Estación de Servicios)

Base path: `/api/fuel/`

### Reporting / Analytics (R8)

- API canónica reporting: `/api/reporting/*`
- Dashboard gateway: `/api/backend/dashboard/*`
- Métricas operativas consolidadas: `/api/metrics/` (incluye `reporting.dataset_slo`, `reporting.failure_classes_last_window` y `dashboard.workspace_redeem_rate`)
- Endpoints legacy contables `/api/accounting/reports/*` emiten headers `Deprecation`, `Sunset` y `Link` hacia `/api/reporting/catalog/`

- `GET /api/fuel/health/` — Healthcheck del módulo (público)
- `POST /api/fuel/shifts/open/` — Abrir turno (permiso: `fuel.shift.open`)
- `POST /api/fuel/shifts/{shift_id}/close/` — Cerrar turno (permiso: `fuel.shift.close`)
- `POST /api/fuel/dispenses/` — Registrar despacho (permiso: `fuel.dispense.create`)
- `POST /api/fuel/sales/` — Crear venta (permiso: `fuel.sale.create`)
- `POST /api/fuel/sales/{sale_id}/cancel/` — Cancelar venta (permiso: `fuel.sale.void`)

### Reporting Kernel

Base path: `/api/reporting/`

- `GET /api/reporting/catalog/` — Catálogo de datasets certificados (`report.catalog.read`)
- `POST /api/reporting/datasets/{dataset_key}/run/` — Ejecutar dataset (`report.dataset.read` + permiso de dominio)
- `GET /api/reporting/runs/` y `GET /api/reporting/runs/{run_id}/` — Historial/detalle de runs (`report.run.read`)
- `POST /api/reporting/runs/{run_id}/export/` y `GET /api/reporting/exports/{export_id}/` — Export reproducible por `run_id` (`report.dataset.export`)
- `GET /api/reporting/snapshots/` y `POST /api/reporting/snapshots/generate/` — Snapshots (`report.run.read` / `report.snapshot.generate`)
- `GET /api/reporting/saved-views/`, `POST /api/reporting/saved-views/`, `GET /api/reporting/saved-views/{view_id}/` — Vistas guardadas (`report.dashboard.read` / `report.dashboard.compose`)

## Historial de cambios

Ver [CHANGELOG.md](CHANGELOG.md).

Bitácora de desarrollo (registro detallado y cronológico): ver [BITACORA.md](BITACORA.md).

## PM Snapshot (para seguimiento por ChatGPT/PM)

Para que un Product Manager (o un LLM) pueda ponerse al día sin leer todo el repo, se genera un snapshot en Markdown con:

- rama/commit actual,
- lista de ramas remotas (top 50),
- últimos commits,
- diff de PR cuando aplica.

### En GitHub

- Workflow: `PM Snapshot`
- Artefacto: `pm-snapshot` (archivo `pm_snapshot.md`)

### En local

```bash
bash scripts/pm_snapshot.sh
cat pm_snapshot.md
```

### ORG (Organización)

- Todos los listados soportan `limit/offset` y responden `count/limit/offset/results`.

- `GET /api/org/company/profile/` — Ver perfil de la empresa (requiere permiso: org.company.read)
- `PUT /api/org/company/profile/` — Actualizar perfil de la empresa (requiere permiso: org.company.update)
- `GET /api/org/companies/` — Listar compañías accesibles por membresía (requiere permiso: org.company.read)
- `POST /api/org/companies/` — Crear compañía bajo el holding y clonar accesos del creador (requiere permiso: org.company.create)
- `GET /api/org/branches/` — Listar sucursales (requiere permiso: org.branch.read)
- `POST /api/org/branches/` — Crear sucursal (requiere permiso: org.branch.create)
- `PATCH /api/org/branches/{branch_id}/` — Actualizar sucursal (requiere permiso: org.branch.update)

### HR (Recursos Humanos)

- Todos los listados soportan `limit/offset` y responden `count/limit/offset/results`.

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
- `POST /api/hr/employees/<id>/provision-user/`
  - Crea un usuario vinculado al empleado con contraseña provisional.
  - Valida asignación activa y fuerza cambio de contraseña en primer login.
  - Requiere permisos `iam.users.create` y `hr.employee.update`.
- `POST /api/hr/employees/<id>/reset-temp-password/`
  - Resetea la contraseña provisional del usuario ya vinculado al empleado.
  - Payload opcional: `{ "temp_password": "..." }` (si se omite, se autogenera).
  - Responde `409` si no hay `linked_user` o si el empleado no tiene asignación activa.
  - Auditoría: `HR_EMPLOYEE_TEMP_PASSWORD_RESET` (sin exponer la contraseña).

- `POST /api/hr/employees/<id>/revoke-access/`
  - Revoca accesos del usuario vinculado al empleado en el scope de la company y sus sucursales.
  - Desactiva `RoleAssignment` con `origin=POSITION` y cierra memberships (`left_at`) en scope.
  - Payload: `{ "disable_user": true|false }` (opcional; si es `true`, desactiva el usuario solo si no quedan memberships activas).
  - Responde `409` si el empleado no tiene `linked_user`.
  - Auditoría: `HR_EMPLOYEE_ACCESS_REVOKED` (sin incluir secretos).

### Nota de compatibilidad (provisionamiento)

- Si tu base de datos ya tenía la columna `accounts_user.is_setup_complete` como NOT NULL, asegúrate de aplicar migraciones: `docker compose exec backend python manage.py migrate --noinput`.

## Comandos de gestión

- `python manage.py seed_rbac_v01` — Siembra roles, permisos y mapeos estándar (idempotente, auditable)
- `python manage.py bootstrap_company --company-name ... --branch-name ... --admin-username ...` — Bootstrap de empresa, sucursal y admin
  - El comando es idempotente: si la empresa, sucursal o holding ya existen (por código o nombre), los reutiliza y reactiva si estaban desactivados.
  - Si usas `--no-input`, todos los parámetros son obligatorios y el comando falla si falta alguno.
  - AdminGrant siempre se crea con `org_unit=company` y se reactiva si estaba desactivado.
  - Membership y RoleAssignment también se reactivan si estaban off.
  - Validado por el test: `tests/test_bootstrap_company_command.py`.

En Docker, ejecuta estos comandos así:

```bash
docker compose exec backend python manage.py seed_rbac_v01
docker compose exec backend python manage.py bootstrap_company --company-name ... --branch-name ... --admin-username ...
```

## Auditoría contractual

- Todos los endpoints de escritura generan eventos en apps.audit con reason_code y event_type según contrato.
- Ejemplo: `HR_POSITION_CREATED`, `ORG_BRANCH_CREATED`, `RBAC_SEEDED_V01`.
- El contrato de auditoría es estricto y validado por tests.

Guías de organización:

- Contract Pack v1.0: [docs/CONTRACT_PACK_v1.0.md](docs/CONTRACT_PACK_v1.0.md)
- Addendum Offline-first v1.0: [docs/ADDENDUM_OFFLINE_FIRST_v1.0.md](docs/ADDENDUM_OFFLINE_FIRST_v1.0.md)
- Índice de docs: [docs/README.md](docs/README.md)

## Tests automáticos

- `tests/test_hr_position_role_automation.py`: Valida automatización de roles por puesto y auditoría.
- `tests/test_seed_rbac_v01_command.py`: Valida comando seed_rbac_v01, creación de permisos y evento de auditoría.
- `tests/test_bootstrap_company_command.py`: Valida robustez, idempotencia y grants correctos del comando bootstrap_company.
- `tests/test_org_endpoints_audit.py`: Valida permisos RBAC por método en endpoints ORG y la trazabilidad/auditoría contractual de operaciones clave.
- `tests/test_2fa_challenge.py`: Valida challenge 2FA one-time y anti-replay.
- `tests/test_pagination_list_endpoints.py`: Valida paginación en listados ORG/HR/RBAC.

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

Actualizado: 2026-03-10.
