# Necktral ERP/CRM

Sistema ERP/CRM modular con backend Django + DRF y frontend Quasar. Incluye Roles y Permisos, auditoria, Recursos Humanos, Organizacion, Identidad y Acceso, sincronizacion y ciclo de arranque profesional con Docker Compose.

## 🚀 Guía de Inicio Rápido (Docker)

### 1. Clonar y Configurar

```bash
git clone https://github.com/Necktral/Necktral.git
cd ERP_CRM
cp .env.example .env  # Ajustar credenciales DB si es necesario
```

### 2. Levantar Servicios

```bash
docker compose up -d --build
```

Esto levantará:

- **Backend**: http://localhost:8000
- **Base de Datos**: Postgres 16
- **Frontend**: http://localhost:3000

> Para stack PROD (SPA servida por Nginx y proxy `/api/`), ver el README raíz y usar `compose.prod.yaml`.

### 3. Aplicar Migraciones

```bash
docker compose exec backend python src/manage.py migrate --noinput
```

### 4. Flujo de Onboarding (Inicialización)

El sistema cuenta con un asistente de instalación automático. **No es necesario crear superusuarios por consola.**

1. Levanta el frontend (ver abajo).
2. Accede a `http://localhost:3000`.
3. Si es una instalación fresca, el login mostrará un CTA fuerte para ir a `/bootstrap` (crear usuario inicial).
4. El asistente (`/bootstrap`) te guiará para:
   - Crear el **Administrador Inicial**.
   - Validar credenciales.
   - Configurar la estructura organizacional base (**Holding -> Empresa -> Sucursal**).

---

## 💻 Desarrollo Frontend (local)

El frontend está desarrollado en Vue 3 + Quasar.

```bash
cd frontend
npm install
npm run dev
# Accede a http://localhost:3000
```

### API base

- En Docker DEV, el contenedor `frontend` usa `VITE_API_BASE_URL=http://localhost:8000/api` (ver `compose.yaml`).
- En PROD (Nginx), el frontend usa `VITE_API_BASE_URL=/api` para pegarle al mismo origen.

> El frontend detectará automáticamente si el backend requiere configuración inicial.

---

## ✅ Calidad

- Lint:
  ```bash
  npm run lint
  ```
- Tests (Vitest):
  ```bash
  npm run test
  ```
- Build + budget de bundle `dashboard_v3`:
  ```bash
  npm run build
  npm run bundle:budget:dashboard-v3
  ```
  Presupuestos aplicados:
  - `dashboard-v3-route` <= `700KB`
  - `analytics-echarts` <= `500KB`
  - `analytics-aggrid` <= `500KB`

## 🧱 Arquitectura SPA Modular

El frontend mantiene Quasar/Vue, con migracion incremental a capas por dominio:
- `app`, `shared`, `entities`, `features`, `widgets`, `pages`
- Guia: `frontend/src/ARCHITECTURE_SPA_MODULAR.md`

---

## 🛠 Comandos Útiles

- **Logs Backend**: `docker compose logs -f backend`
- **Shell Backend**: `docker compose exec backend bash`
- **Shell DB**: `docker compose exec db psql -U $POSTGRES_USER -d $POSTGRES_DB`

## 🐳 Frontend 100% Docker (sin Node local)

El `compose.yaml` incluye un servicio `frontend` que corre `quasar dev` dentro del contenedor.

```bash
docker compose up -d frontend
```

Luego abre http://localhost:3000

---

## ✅ Estado del Proyecto

### Hitos Completados

- [x] **Arquitectura Base**: Docker Compose, Django DRF, Postgres.
- [x] **Autenticación y Seguridad**: JWT, `X-Company-Id` Context Middleware, Protección CSRF/CORS.
- [x] **Onboarding/Bootstrap**: Wizard de instalación inicial (Admin + Estructura Org).
- [x] **Modulo Organizacion**: Gestion de perfil de empresa y sucursales.
- [x] **Modulo Recursos Humanos**: Gestion de empleados y puestos.
- [x] **UI Kit**: Componentes base (`AppDataTable`, `AppPageHeader`, layouts).

## Próximos pasos

- Roles y Permisos avanzados: editor visual de roles y permisos (modulo separado de administracion).

Notas:

- Auditoría ya disponible en la ruta /audit/bitacora (requiere permiso audit.read).

---

## Provisionar usuario a empleado (Recursos Humanos)

- Desde la UI de empleados, puedes crear acceso para un empleado con un solo clic.
- El sistema valida que el empleado tenga al menos una asignación activa.
- Se genera usuario, contraseña provisional y se muestra para entrega segura.
- El usuario debe cambiar la contraseña en el primer login.
- Requiere permisos `iam.users.create` y `hr.employee.update`.
- Endpoint backend: `POST /api/hr/employees/<id>/provision-user/`

Nota: si envías email vacío, el backend lo normaliza a `NULL` para evitar conflictos con la unicidad.

## Seguridad de memberships en Recursos Humanos

- La reconciliación de memberships ya no fuerza acceso a la empresa por defecto.
- Solo se asignan memberships por asignaciones activas y roles mapeados.

---

Actualizado: 2026-02-09
