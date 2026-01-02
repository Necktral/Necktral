# ERP/CRM Logging Module

## Descripción

Este módulo forma parte de un sistema ERP/CRM robusto, orientado a la trazabilidad, auditoría y control de acceso. Implementa un core de auditoría y sincronización seguro, con enfoque en integridad, consistencia y facilidad de mantenimiento.

## Características principales
- Auditoría de eventos con cadena hash (AuditChainHeadV2, particionada para alta concurrencia)
- Control de acceso basado en RBAC y JWT
- Configuración DRF y AXES unificada y segura
- Migraciones limpias y alineadas para producción
- Tests automáticos con Pytest y configuración dedicada
- Eliminación de riesgos por duplicidad de contexto y configuraciones
- Integración lista para despliegue en entornos productivos

## Estructura relevante
- `backend/src/apps/audit/`: Modelos, migraciones y lógica de auditoría
- `backend/src/config/settings/`: Configuración base, dev y test
- `backend/tests/`: Pruebas automáticas


## Instalación y ciclo de desarrollo seguro

### 1. Clona el repositorio y activa el entorno virtual
```bash
git clone <repo_url>
cd loggin_module
source system_wis/bin/activate
```

### 2. Instala dependencias
```bash
pip install -r backend/requirements/prod.txt
```

### 3. Configura la base de datos PostgreSQL y variables en `.env`

### 4. (Opcional) Uso con Docker
```bash
cd backend
docker compose up -d
# Para limpiar completamente la base de datos:
docker compose down -v && docker compose up -d
```

### 5. Migraciones limpias y robustas
**Estrategia recomendada para evitar problemas:**
1. Elimina todas las migraciones de apps propias (excepto `__init__.py` en cada `migrations/`).
2. Borra todas las tablas de la base de datos (puedes usar `DROP SCHEMA public CASCADE; CREATE SCHEMA public;`).
3. Ejecuta:
	```bash
	python manage.py makemigrations
	python manage.py migrate
	```
4. Ejecuta los tests:
	```bash
	export PYTHONPATH=backend/src
	pytest ../tests --maxfail=3 --disable-warnings
	```

### 6. Levanta el backend (si aplica)
```bash
cd backend/src
python manage.py runserver
```

### 7. Levanta el frontend (si aplica)
```bash
cd frontend
npm install
npm run dev
```


## Seguridad y buenas prácticas
- Solo una fuente de contexto (JWTAuthWithOrgContext)
- Sin middlewares de contexto obsoletos
- Migraciones limpias, sin dependencias de datos antiguos
- Tests obligatorios antes de cada despliegue
- Si usas Docker, limpia los volúmenes con `docker compose down -v` antes de migraciones críticas


## Contribución
1. Crea una rama para tu feature o fix
2. Asegúrate de que todos los tests pasen
3. Haz pull request a main
4. Sigue la estrategia de migraciones limpias para evitar conflictos

## Contacto
Para soporte o dudas, contacta a los administradores del repositorio.

# Módulo ORG/HR + RBAC + Auditoría

## Endpoints principales

### ORG (Organización)
- `GET /api/org/company/profile/` — Ver perfil de la empresa
- `PUT /api/org/company/profile/` — Actualizar perfil de la empresa
- `GET /api/org/branches/` — Listar sucursales
- `POST /api/org/branches/` — Crear sucursal
- `PATCH /api/org/branches/{branch_id}/` — Actualizar sucursal

### HR (Recursos Humanos)
- `GET /api/hr/positions/` — Listar puestos
- `POST /api/hr/positions/` — Crear puesto
- `PATCH /api/hr/positions/{id}/` — Actualizar puesto
- `PUT /api/hr/positions/{id}/roles/` — Mapear puesto a roles
- `GET /api/hr/employees/` — Listar empleados
- `POST /api/hr/employees/` — Crear empleado
- `PATCH /api/hr/employees/{id}/` — Actualizar empleado
- `POST /api/hr/employees/{id}/assignments/` — Asignar puesto/sucursal

## Comandos de gestión
- `python manage.py seed_rbac_v01` — Siembra roles, permisos y mapeos estándar (idempotente, auditable)
- `python manage.py bootstrap_company --company-name ... --branch-name ... --admin-username ...` — Bootstrap de empresa, sucursal y admin

## Auditoría contractual
- Todos los endpoints de escritura generan eventos en apps.audit con reason_code y event_type según contrato.
- Ejemplo: `HR_POSITION_CREATED`, `ORG_BRANCH_CREATED`, `RBAC_SEEDED_V01`.

## Tests automáticos
- `tests/test_hr_position_role_automation.py`: Valida automatización de roles por puesto y auditoría.
- `tests/test_seed_rbac_v01_command.py`: Valida comando seed_rbac_v01, creación de permisos y evento de auditoría.

## Permisos y roles
- Catálogo estándar en apps/rbac/seed_v01.py
- Roles: company_admin, branch_manager, hr_manager, etc.
- Permisos: hr.position.create, org.branch.create, etc.

## Buenas prácticas
- Siempre ejecutar los comandos de seed y bootstrap en entornos nuevos.
- Validar con tests antes de desplegar.
- Consultar la auditoría para trazabilidad de cambios críticos.

---
Actualizado al 2026-01-02.