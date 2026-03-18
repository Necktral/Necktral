# Necktral ERP/CRM

Sistema ERP/CRM modular con backend Django + DRF y frontend Quasar. Incluye Roles y Permisos, auditoria, Recursos Humanos, Organizacion, Identidad y Acceso, sincronizacion y ciclo de arranque profesional con Docker Compose.

## Ciclo de arranque (Onboarding/Bootstrap)

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

### 3. Onboarding automático (Wizard)

Al acceder por primera vez al frontend (`http://localhost:3000`), si el sistema está vacío, se activa el **Wizard Bootstrap**:

1. **Crear Admin Inicial**: Ingresa usuario, email y contraseña.
2. **Login**: Accede con el admin recién creado.
3. **Configura Organización**: Define Holding, Empresa y Sucursal principal.
4. **Acceso al Dashboard**: El sistema queda listo para operar.

Este flujo es 100% automático y guiado desde el frontend. No requiere comandos manuales.

### 4. Acceso manual (avanzado)

Si necesitas crear el admin o la organización por comandos:

```bash
docker compose exec backend python src/manage.py migrate --noinput
# Crear superusuario manual
# docker compose exec backend python src/manage.py createsuperuser
```

### 5. Endpoints clave del backend

- `/api/backend/iam/bootstrap/status/` — Verifica si el sistema está vacío.
- `/api/backend/iam/bootstrap/init-admin/` — Crea el admin inicial.
- `/api/backend/org/bootstrap/organization/` — Crea la estructura Holding/Empresa/Sucursal.
- `/api/backend/auth/password/` — Forzado de cambio de contraseña.
- `/api/metrics/` — Métricas básicas (solo staff/superuser).

### 6. Variables de entorno principales (.env)

Revisa y ajusta:

- POSTGRES_DB, POSTGRES_USER, POSTGRES_PASSWORD: credenciales de Postgres
- VITE_API_BASE_URL: URL del backend para el frontend

### 7. Acceso al backend

El backend queda expuesto en http://localhost:8000

---

## Docker Compose

El ciclo de vida completo se gestiona con Docker Compose. No es necesario instalar dependencias manualmente.

---

## Documentación adicional

- [frontend/README.md](frontend/README.md): detalles de la consola Quasar
- [compose.yaml](compose.yaml): configuración de servicios

---

Actualizado: 2026-02-09
