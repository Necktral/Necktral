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

## Offline (companion): outbox de inventario y Sync Engine

### Robustez UI Sync Offline

- Todas las rutas de API usan paths relativos a baseURL `/api` (ver `src/boot/axios.ts`).
- El campo Branch ID en enrollment challenge solo acepta números enteros positivos.
- Si el device está enrolado en otro company/branch, se bloquean acciones peligrosas (flush/enroll) y se muestra advertencia.
- El panel de enrollment solo aparece si el usuario tiene permiso `sync.device.enroll` en el company activo.
- El tipo de respuesta de enrollment challenge está alineado al backend (IDs como string).
- Tras enrolar, se limpia el campo y se refresca el outbox; se muestra confirmación.
- Si el usuario cambia de contexto (company/branch), la UI recarga métricas y estado.
- El banner de flush muestra resumen de errores si hay fallos (top 3 motivos, si están disponibles).

El frontend incluye una base **offline-first** para operaciones de inventario (store-and-forward):

- Persistencia local en IndexedDB (dependencia `idb`).
- Cola `outbox` con reintentos/backoff.
- Flush automático al arrancar si hay internet y al evento `online`.
- Robustez: cada request encolado lleva `X-Request-Id` y queda ligado al `company/branch/user` activo al encolar.

Estado actual:

- Se encolan operaciones de inventario y se sincronizan vía **Sync Engine** usando `POST /api/sync/batch/`.
- Cada comando se firma (Ed25519) y el batch se autentica con `X-Device-Id`.
- El flush valida binding estricto a `company/branch/user` (si cambió el scope/actor, el item se rechaza localmente para evitar aplicar con otro contexto).

### Enrollment (requisito para flush)

Antes de poder enviar batches, el cliente debe **enrolar el dispositivo** para obtener `device_id` y generar/guardar su keypair Ed25519.

Flujo recomendado (DEV):

1. Crear un enrollment_code (requiere JWT + permiso `sync.device.enroll` + `X-Company-Id`):

```bash
curl -sS -X POST http://localhost:8000/api/sync/enrollment/challenges/ \
  -H 'Authorization: Bearer <ACCESS_TOKEN>' \
  -H 'Content-Type: application/json' \
  -H 'X-Company-Id: <COMPANY_ID>' \
  -d '{"branch_id": <BRANCH_ID>, "label_hint": "Companion Inventario", "expires_in_minutes": 15}'
```

2. Enrolar el dispositivo con `enrollment_code` (no requiere JWT):

```bash
curl -sS -X POST http://localhost:8000/api/sync/enroll/ \
  -H 'Content-Type: application/json' \
  -d '{"enrollment_code": "<ENROLLMENT_CODE>", "public_key_b64": "<PUBLIC_KEY_B64>", "label": "Companion Inventario"}'
```

Nota: el frontend ya incluye helper `enrollSyncDevice()` que genera keypair y persiste `device_id`+keys. Aún falta exponer este flujo en UI (por ahora es para integración/DEV).

Archivos clave:

- `src/core/offline/db.ts`
- `src/core/offline/outbox.ts`
- `src/core/offline/processor.ts`
- `src/core/sync/device.ts`
- `src/core/sync/signing.ts`
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
