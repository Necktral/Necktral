# Necktral ERP/CRM

Sistema ERP/CRM modular con backend Django + DRF y frontend Quasar. Incluye RBAC, auditoría, HR, ORG, IAM, sincronización y ciclo de arranque profesional con Docker Compose.

## Backend: ciclo de arranque recomendado

### 1. Clona el repositorio y configura variables

```bash
git clone https://github.com/Necktral/Necktral.git
cd ERP_CRM
cp .env.example .env  # Edita los valores según tu entorno
```

### 2. Levanta los servicios con Docker Compose

```bash
docker compose up -d --force-recreate
```

### 3. Aplica migraciones y crea el superusuario admin

```bash
docker compose exec backend python manage.py migrate --noinput
```

> Nota: en instalaciones frescas, el flujo recomendado es usar el wizard `/bootstrap` desde el frontend para crear el usuario inicial.

### 4. Siembra RBAC y bootstrap de empresa/sucursal/admin

```bash
docker compose exec backend python manage.py seed_rbac_v01
docker compose exec backend python manage.py bootstrap_company \
	--no-input \
	--holding-name HOLDING \
	--company-name ACME \
	--company-code AC \
	--branch-name ACME-1 \
	--branch-code AC1 \
	--admin-username admin
```

### 5. Accede al backend

El backend queda expuesto en http://localhost:8000

### 6. Variables de entorno principales (.env)

Revisa y ajusta:

- POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD: credenciales de Postgres
- DJANGO_SECRET_KEY: clave secreta Django
- DJANGO_ALLOWED_HOSTS: hosts permitidos
- DJANGO_CORS_ALLOWED_ORIGINS: orígenes frontend permitidos

### 7. Flujo de desarrollo frontend

```bash
cd frontend
npm install
npm run dev
```

---

## Comandos útiles

- `docker compose logs backend --tail=60` — Ver logs del backend
- `docker compose exec backend python manage.py showmigrations` — Ver estado de migraciones
- `docker compose exec db psql -U <POSTGRES_USER> -d <POSTGRES_DB> -c "\\l"` — Ver bases de datos en Postgres

---

## Documentación extendida

Consulta el archivo backend/README.md para detalles de endpoints, comandos, ciclo de migraciones, auditoría y buenas prácticas.

---

## Estado del Proyecto

### Hitos Completados

- [x] **Hito 1: Autenticación y Contexto**: Login JWT, manejo de `X-Company-Id`, selección de contexto (Empresa/Sucursal).
- [x] **Hito 2: Módulo ORG**: Gestión de Perfil de Empresa y Listado de Sucursales con validación de permisos (`org.company.update`, `org.branch.read`).
- [x] **Hito 3: Módulo HR**: Gestión de Posiciones, Empleados y Asignaciones (CRUD completo + Role Maps).
- [x] **Estabilización**: Corrección de CORS, configuración de Auditoría en backend y plugins de Quasar (Notify).

### Próximos Pasos

- [ ] **Hito 4: Auditoría**: Visualización de logs de auditoría.

---

## Historial de Cambios

Ver [CHANGELOG.md](CHANGELOG.md) para detalles de versiones y correcciones.

---

## Provisionar usuario a empleado (HR)

Desde la versión 2026-01, el sistema permite provisionar acceso a empleados directamente desde la UI y API:

- **Endpoint nuevo:**
  - `POST /hr/employees/<id>/provision-user/`
  - Requiere permisos `iam.users.create` y `hr.employee.update`.
  - Valida que el empleado tenga al menos una asignación activa.
  - Genera usuario, contraseña provisional y vincula al empleado.
  - Fuerza cambio de contraseña en primer login.

- **Frontend:**
  - Nuevo botón y diálogo en la página de empleados para provisionar acceso.
  - Si el empleado no tiene asignación activa, la UI bloquea el provisionamiento y muestra un mensaje claro.
  - Muestra credenciales provisionales para entrega segura.

## Seguridad: reconciliación de memberships HR

- El sistema ya **no fuerza la membresía a la empresa (COMPANY)** por defecto.
- Las memberships se asignan solo por asignaciones activas y roles mapeados.
- Esto mejora la robustez y evita accesos innecesarios.

## Permisos IAM

- Nuevo permiso: `iam.users.create` para controlar quién puede provisionar usuarios desde HR.

## Paginación en listados

- Listados HR soportan `limit` y `offset`.
- Respuesta estándar: `{ count, limit, offset, results }`.

---

Actualizado al 2026-02-09.
