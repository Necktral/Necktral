# Simulacion de carga de autenticacion

Este paquete ejecuta una simulacion realista del flujo de autenticacion en modo cookies (HttpOnly + CSRF), incluyendo 2FA TOTP, refresh, logout idempotente y escenarios de ataque.

## Objetivo

- Validar latencia p95 por endpoint
- Verificar tolerancia a errores y casos negativos
- Probar rotacion de refresh y logout idempotente
- Confirmar robustez frente a tokens invalidos
- **Auditoría de Seguridad**: Detectar vulnerabilidades de Replay Attack (2FA) y persistencia de cookies.

## Contenido

### Archivos clave

- Script base k6: simulacion/auth_load_simulation.js
- Script extendido k6: simulacion/auth_load_simulation_extended.js
- Seed de usuarios: backend/src/apps/accounts/management/commands/seed_auth_users.py
- Workflow de referencia: simulacion/auth-load-simulation.yml
- Workflow oficial (GitHub Actions): .github/workflows/auth-load-simulation.yml

## Requisitos

- Docker y Docker Compose
- Backend Django arriba
- DB disponible (puede estar vacia)
- k6 local o contenedor grafana/k6

## Ejecución Automatizada con Monitorización en Tiempo Real

Para ejecutar la simulación con visualización en Grafana sin configuración manual:

```bash
./simulacion/run_simulation.sh
```

Esto:

1. Levantará Grafana (puerto 3000) e InfluxDB automáticamente.
2. Ejecutará el script de k6 conectado a la red de contenedores.
3. Enviará métricas en tiempo real al dashboard preconfigurado.

**Acceso al Dashboard:**

- URL: [http://localhost:3000](http://localhost:3000)
- Dashboard: "K6 Load Testing Results" (Carpeta General)

### Personalización

```bash
# Ejecutar script extendido con mas carga
./simulacion/run_simulation.sh auth_load_simulation_extended.js 20 60s
```

## Preparacion del entorno (DB vacia)

1. Bajar todo y limpiar volumenes:

```bash
docker compose down -v --remove-orphans || true
```

2. Levantar DB + backend:

```bash
USE_GUNICORN=1 GUNICORN_WORKERS=4 docker compose up -d db backend
```

3. Esperar healthcheck del backend:

```bash
for i in {1..30}; do
  status=$(docker inspect -f '{{.State.Health.Status}}' erpcrm_backend || echo "error")
  if [ "$status" = "healthy" ]; then
    echo "Backend listo"
    break
  fi
  echo "Esperando backend... ($i/30)"
  sleep 2
done
if [ "$status" != "healthy" ]; then
  echo "Backend no listo a tiempo" && docker compose logs backend && exit 1
fi
```

4. Migraciones + seed:

```bash
docker compose exec -T backend python manage.py migrate --noinput
docker compose exec -T backend python manage.py seed_auth_users
```

## Ejecucion local

### Script base (rapido)

```bash
BASE_URL=http://localhost:8000/api \
ADMIN_USERNAME=k6_admin \
ADMIN_PASSWORD=Pass12345__Strong \
ADMIN_TOTP_SECRET=JBSWY3DPEHPK3PXP \
USER_USERNAME=k6_user \
USER_PASSWORD=Pass12345__Strong \
CSRF_COOKIE_NAME=nt_csrf \
k6 run simulacion/auth_load_simulation.js
```

### Script extendido (recomendado)

```bash
BASE_URL=http://localhost:8000/api \
ADMIN_USERNAME=k6_admin \
ADMIN_PASSWORD=Pass12345__Strong \
ADMIN_TOTP_SECRET=JBSWY3DPEHPK3PXP \
USER_USERNAME=k6_user \
USER_PASSWORD=Pass12345__Strong \
CSRF_COOKIE_NAME=nt_csrf \
VUS=12 \
DURATION=60s \
ADMIN_2FA_VUS=1 \
ADMIN_2FA_SLEEP=15 \
k6 run simulacion/auth_load_simulation_extended.js
```

## Variables de entorno

- BASE_URL: URL base del API
- ADMIN_USERNAME / ADMIN_PASSWORD: usuario admin con 2FA
- ADMIN_TOTP_SECRET: secreto TOTP del admin
- USER_USERNAME / USER_PASSWORD: usuario normal
- CSRF_COOKIE_NAME: nombre de cookie CSRF
- VUS: usuarios virtuales
- DURATION: duracion de la prueba
- ADMIN_2FA_VUS: VUs dedicados a 2FA
- ADMIN_2FA_SLEEP: sleep entre intentos 2FA
- AUTH_SIM_ADMIN_SUPERUSER: siembra admin como superuser (0/1)
- AUTH_SIM_SHOW_SECRETS: imprime secreto TOTP en consola (0/1)
- REQUIRE_ADMIN_TOTP: falla si no hay ADMIN_TOTP_SECRET (0/1)
- REQUIRE_CSRF_COOKIE: falla si no se emite cookie CSRF (0/1)
- CSRF_CLEAR_REQUIRED: exige limpiar cookie CSRF en logout (0/1)
- ENABLE_429_TEST: habilita escenarios de throttling 429 (0/1)
- ONLY_429_TEST: ejecuta solo escenarios 429 (0/1)
- THROTTLE_RATE: tasa por segundo para pruebas 429 (default: 20)
- THROTTLE_DURATION: duracion de pruebas 429 (default: 15s)
- THROTTLE_PREALLOC: VUs preasignados para 429 (default: 20)
- THROTTLE_MAX: VUs maximos para 429 (default: 50)

## Escenarios del script extendido

1. cookie_flow

- Login en modo cookie
- Refresh/logout sin CSRF (espera 403)
- Refresh/logout con CSRF (espera 200/204)
- Verificación estricta de limpieza de cookies en logout

2. admin_2fa

- Login admin (202 con challenge)
- Verify TOTP valido (200)
- Replay del challenge (400 esperado - Anti-Replay Check)
- Logout y limpieza de cookies

3. refresh_rotation

- Login header
- Refresh con rotacion
- Reuso de refresh viejo (401 esperado)

4. logout_idempotent

- Logout valido (204)
- Logout repetido (204 esperado)

5. cookie_logout_idempotent

- Simulacion de logout con cookie corrupta/expirada
- Verifica respuesta 204 (idempotente)
- Verifica limpieza forzada de cookies (Set-Cookie: Max-Age=0)

6. attacks

- Refresh corrupto (401 esperado)

7. throttle_login (opcional)

- Login con credenciales invalidas para provocar 429 (si ENABLE_429_TEST=1)

8. throttle_refresh (opcional)

- Refresh con token invalido para provocar 429 (si ENABLE_429_TEST=1)

9. throttle_logout (opcional)

- Logout repetido para provocar 429 (si ENABLE_429_TEST=1)

10. throttle_2fa (opcional)

- 2FA con challenge invalido para provocar 429 (si ENABLE_429_TEST=1)

## Thresholds esperados

- http_req_failed < 1%
- p(95):
  - login < 600ms
  - 2FA < 700ms
  - refresh < 400ms
  - logout < 400ms
  - ataques < 500ms

## Solucion de problemas

### 429 / throttling

- Ajusta throttles en .env y reinicia backend
- Si el 2FA da 429, aumenta DRF_THROTTLE_AUTH_SENSITIVE

### Axes bloquea usuarios

```bash
docker compose exec -T backend python manage.py axes_reset
```

### TOTP invalido

- Verifica que ADMIN_TOTP_SECRET coincida con el seed
- Si hay desfase de reloj, aumentar TOTP_VALID_WINDOW

## Notas

- El workflow oficial vive en .github/workflows/auth-load-simulation.yml.
- El script extendido es el recomendado para validar el flujo completo.
