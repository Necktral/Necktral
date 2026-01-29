# Necktral ERP/CRM

Sistema ERP/CRM modular con backend Django + DRF y frontend Quasar. Incluye RBAC, auditoría contractual, HR, ORG, IAM y sincronización.

## Contratos de API (clientes web/móvil)

- **Errores uniformes en `/api/*`:** cualquier error HTTP (`>= 400`) se entrega con un envelope JSON estable (campo raíz `error`).
- **Trazabilidad:** el backend preserva/expone `X-Request-Id` y lo replica en `error.request_id`.
- **404/500 fuera de DRF:** los handlers de Django devuelven JSON contractual para rutas `/api/*`.

## Estructura del repo

- `login_module/`: backend Django/DRF (código en `login_module/src/`)
- `frontend/`: consola web (Vue 3 + Quasar)
- `modulos/`: módulos de dominio en la raíz del repo (ej: `modulos.estacion_servicios`)
- `compose.yaml`: entorno Docker (backend + Postgres)
- `system_wis/`: entorno virtual Python (dev)

## Documentación

- Índice: [docs/README.md](docs/README.md)
- Operación (negocio): [docs/operacion/README.md](docs/operacion/README.md)

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
- DB (Postgres): localhost:5432

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
docker compose exec backend python src/manage.py seed_rbac_v01
```

2. Crear usuario admin (si no existe)

```bash
docker compose exec backend python src/manage.py createsuperuser
```

3. Crear empresa/sucursal y grants iniciales (requiere que el usuario exista)

```bash
docker compose exec backend python src/manage.py bootstrap_company \
  --company-name "Necktral" \
  --branch-name "Principal" \
  --admin-username "admin"
```

## 💻 Desarrollo local

### Backend (venv)

```bash
source system_wis/bin/activate
pip install -r requirements/dev.txt

cd login_module
python src/manage.py migrate --noinput
python src/manage.py runserver
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

### Backend

- Tests:

  ```bash
  source system_wis/bin/activate
  cd login_module
  pytest
  ```

  Nota: ejecutar `pytest` desde la raíz del repo puede fallar por settings de Django no inicializados; el runner recomendado es desde `login_module/`.

- Tests (dentro de Docker):
  ```bash
  docker compose exec backend pytest -q
  ```
- Lint (ruff):
  ```bash
  source system_wis/bin/activate
  cd login_module
  ruff check .
  ```

### Frontend

- Lint:
  ```bash
  cd frontend
  npm run lint
  ```
- Tests: actualmente `npm run test` es un placeholder.

## Auditoría (contrato)

- Los eventos de auditoría se emiten con `module=AUTH` y `schema_version=1`.
- Para trazabilidad: se encadenan hashes y se firma con HMAC.

### FUEL (Estación de Servicios)

Base path: `/api/fuel/`

- `GET /api/fuel/health/` — Healthcheck del módulo (público)
- `POST /api/fuel/shifts/open/` — Abrir turno (permiso: `fuel.shift.open`)
- `POST /api/fuel/shifts/{shift_id}/close/` — Cerrar turno (permiso: `fuel.shift.close`)
- `POST /api/fuel/dispenses/` — Registrar despacho (permiso: `fuel.dispense.create`)
- `POST /api/fuel/sales/` — Crear venta (permiso: `fuel.sale.create`)
- `POST /api/fuel/sales/{sale_id}/cancel/` — Cancelar venta (permiso: `fuel.sale.void`)

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

- `GET /api/org/company/profile/` — Ver perfil de la empresa (requiere permiso: org.company.read)
- `PUT /api/org/company/profile/` — Actualizar perfil de la empresa (requiere permiso: org.company.update)
- `GET /api/org/companies/` — Listar compañías accesibles por membresía (requiere permiso: org.company.read)
- `POST /api/org/companies/` — Crear compañía bajo el holding y clonar accesos del creador (requiere permiso: org.company.create)
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

### FUEL (Estación de Servicios)

- `GET /api/fuel/health/` — Healthcheck del módulo (requiere sesión/auth)

Nota: el módulo FUEL está inicializado como “base” (scaffolding). El catálogo RBAC incluye roles/permisos `fuel.*` en `seed_rbac_v01`.

### Nota de compatibilidad (provisionamiento)

- Si tu base de datos ya tenía la columna `accounts_user.is_setup_complete` como NOT NULL, asegúrate de aplicar migraciones: `docker compose exec backend python src/manage.py migrate --noinput`.

## Comandos de gestión

- `python src/manage.py seed_rbac_v01` — Siembra roles, permisos y mapeos estándar (idempotente, auditable)
- `python src/manage.py bootstrap_company --company-name ... --branch-name ... --admin-username ...` — Bootstrap de empresa, sucursal y admin
  - El comando es idempotente: si la empresa, sucursal o holding ya existen (por código o nombre), los reutiliza y reactiva si estaban desactivados.
  - Si usas `--no-input`, todos los parámetros son obligatorios y el comando falla si falta alguno.
  - AdminGrant siempre se crea con `org_unit=company` y se reactiva si estaba desactivado.
  - Membership y RoleAssignment también se reactivan si estaban off.
  - Validado por el test: `tests/test_bootstrap_company_command.py`.

En Docker, ejecuta estos comandos así:

```bash
docker compose exec backend python src/manage.py seed_rbac_v01
docker compose exec backend python src/manage.py bootstrap_company --company-name ... --branch-name ... --admin-username ...
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

## Permisos y roles

- Catálogo estándar en apps/rbac/seed_v01.py
- Roles: company_admin, branch_manager, hr_manager, etc.
- Permisos: hr.position.create, org.branch.create, etc.

## Buenas prácticas

- Siempre ejecutar los comandos de seed y bootstrap en entornos nuevos.
- Validar con tests antes de desplegar (recomendado: `make qa-ci-fresh`).
- Consultar la auditoría para trazabilidad de cambios críticos.

## 🛡️ Robustez y monitoreo Docker

Todos los servicios críticos (backend, frontend, db) están configurados con:

- `restart: unless-stopped` para reinicio automático ante fallos.
- `healthcheck` activo: si el proceso principal no responde, Docker reinicia el contenedor.
- Dependencias explícitas (`depends_on` con `condition: service_healthy`) para evitar arranques fuera de orden.

Puedes monitorear el estado de los servicios con:

```bash
docker compose ps
docker compose logs -f backend
docker compose logs -f frontend
docker compose logs -f db
```

Si un servicio se cae repetidamente, revisa los logs y el estado de salud:

```bash
docker inspect --format='{{json .State.Health}}' <nombre_contenedor>
```

Para entornos productivos, se recomienda además monitoreo externo (Prometheus, Grafana) y alertas.

## 🧪 CI/QA (robustez)

- Si en CI ves `exit code 137` (OOM kill) en el paso `qa-backend-wait`, el backend ahora fuerza `runserver` cuando detecta `CI=1`/`GITHUB_ACTIONS=1` para reducir consumo de memoria.
- Los timeouts de arranque (espera de Postgres + wait de backend ready) se aumentaron a 5 minutos para runners lentos.

## Seguridad y memberships HR

- Mejora la robustez y evita accesos innecesarios.

## Permisos IAM

- Nuevo permiso: `iam.users.create` para controlar el provisionamiento de usuarios desde HR.

---

Actualizado: 2026-01-20.
