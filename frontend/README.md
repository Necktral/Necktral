# Necktral ERP/CRM

Sistema ERP/CRM modular con backend Django + DRF y frontend Quasar. Incluye RBAC, auditoría, HR, ORG, IAM, sincronización y ciclo de arranque profesional con Docker Compose.

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
- Tests: por ahora `npm run test` no ejecuta suite (placeholder).

---

## Offline (companion): outbox de inventario

El frontend incluye una base **offline-first** para operaciones de inventario (store-and-forward):

- Persistencia local en IndexedDB (dependencia `idb`).
- Cola `outbox` con reintentos/backoff.
- Flush automático al arrancar si hay internet y al evento `online`.
- Robustez: cada request encolado lleva `X-Request-Id` y queda ligado al `company/branch/user` activo al encolar.

Estado actual:

- Se encolan operaciones hacia endpoints de inventario y se envían luego usando el mismo contrato HTTP (JWT + headers de contexto).
- Integración con `/api/sync/batch/` (Ed25519 + `X-Device-Id`) está planificada como siguiente paso.

Archivos clave:

- `src/core/offline/db.ts`
- `src/core/offline/outbox.ts`
- `src/core/offline/processor.ts`
- `src/boot/offline.ts`
- `src/services/inventory.service.ts`

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
- [x] **Módulo ORG**: Gestión de Perfil de Empresa y Sucursales.
- [x] **Módulo HR**: Gestión de Empleados y Posiciones.
- [x] **UI Kit**: Componentes base (`AppDataTable`, `AppPageHeader`, layouts).

## Próximos pasos

- RBAC Avanzado: Editor visual de roles y permisos (módulo separado de administración).

Notas:

- Auditoría ya disponible en la ruta /audit/bitacora (requiere permiso audit.read).
- Frontend tests: npm run test sigue siendo placeholder.

---

## 🆕 Provisionar usuario a empleado (HR)

- Desde la UI de empleados, puedes crear acceso para un empleado con un solo clic.
- El sistema valida que el empleado tenga al menos una asignación activa.
- Se genera usuario, contraseña provisional y se muestra para entrega segura.
- El usuario debe cambiar la contraseña en el primer login.
- Requiere permisos `iam.users.create` y `hr.employee.update`.
- Endpoint backend: `POST /api/hr/employees/<id>/provision-user/`

Nota: si envías email vacío, el backend lo normaliza a `NULL` para evitar conflictos con la unicidad.

## Seguridad memberships HR

- La reconciliación de memberships ya no fuerza acceso a la empresa por defecto.
- Solo se asignan memberships por asignaciones activas y roles mapeados.

---

Actualizado: 2026-01-10
