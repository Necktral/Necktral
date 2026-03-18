# Simulacion de carga de autenticacion

Este paquete ejecuta una simulacion realista del flujo de autenticacion en modo cookies (HttpOnly + CSRF), incluyendo 2FA TOTP, refresh, logout idempotente y escenarios de ataque.

## Objetivo

- Validar latencia p95 por endpoint
- Verificar tolerancia a errores y casos negativos
- Probar rotacion de refresh y logout idempotente
- Confirmar robustez frente a tokens invalidos
- **Auditoría de Seguridad**: Detectar vulnerabilidades de Replay Attack (2FA) y persistencia de cookies.

## Perfiles de simulación (dual por perfil)

| Perfil | Uso | Variables clave |
|---|---|---|
| `auth-local` | Validación funcional y seguridad auth en runtime base | `AUTH_FLOW_MODE=auto` (o `cookie/header`), `BASE_URL=http://.../api` |
| `integral-loadtest` | Corrida integral auth + operacional + gates | `SIM_PROFILE=integral`, `AUTH_TOKEN_TRANSPORT=header`, `AUTH_ALLOW_TRANSPORT_OVERRIDE=1`, `AUTH_TRANSPORT=header` |

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

### Smoke run (recomendado para validar entorno)

Para validar rápidamente que backend, seed, k6 y Grafana están bien conectados:

```bash
./simulacion/run_smoke.sh
```

Este script:

1. Levanta `db` y `backend`.
2. Espera healthcheck del backend.
3. Ejecuta migraciones + `seed_auth_users` con credenciales explícitas.
4. Resetea Axes y lanza una corrida corta (1 VU, 10s) del script extendido.

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
docker compose exec -T backend python src/manage.py migrate --noinput
docker compose exec -T backend python src/manage.py seed_auth_users
```

## Ejecucion local

### Script base (rapido)

```bash
BASE_URL=http://localhost:8000/api \
ADMIN_USERNAME=k6_admin \
ADMIN_PASSWORD=<SET_STRONG_PASSWORD> \
ADMIN_TOTP_SECRET=JBSWY3DPEHPK3PXP \
USER_USERNAME=k6_user \
USER_PASSWORD=<SET_STRONG_PASSWORD> \
CSRF_COOKIE_NAME=nt_csrf \
k6 run simulacion/auth_load_simulation.js
```

### Script extendido (recomendado)

```bash
BASE_URL=http://localhost:8000/api \
ADMIN_USERNAME=k6_admin \
ADMIN_PASSWORD=<SET_STRONG_PASSWORD> \
ADMIN_TOTP_SECRET=JBSWY3DPEHPK3PXP \
USER_USERNAME=k6_user \
USER_PASSWORD=<SET_STRONG_PASSWORD> \
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
docker compose exec -T backend python src/manage.py axes_reset
```

### TOTP invalido

- Verifica que ADMIN_TOTP_SECRET coincida con el seed
- Si hay desfase de reloj, aumentar TOTP_VALID_WINDOW

## Notas

- El workflow oficial vive en .github/workflows/auth-load-simulation.yml.
- El script extendido es el recomendado para validar el flujo completo.

## Corrida avanzada integral (150k+ transacciones)

Para ejecutar una corrida agresiva local de 15 minutos con cobertura integral
(auth/seguridad + operacional/DB + gates QA + escaneo seguridad), usa el
orquestador avanzado.

1. Prepara perfil de carga (sin tocar `.env` base):

```bash
cp .env.loadtest.example .env.loadtest
# Edita .env.loadtest y completa:
# AUTH_SIM_ADMIN_PASSWORD, AUTH_SIM_USER_PASSWORD, AUTH_SIM_ADMIN_TOTP_SECRET
# COMPANY_ID, BRANCH_ID, USERNAME y PASSWORD
```

2. Ejecuta precheck de autenticación y transporte:

```bash
SIM_PROFILE=integral make loadtest-precheck-auth
# esperado: PRECHECK_STATUS=OK
```

Para validar únicamente contexto auth (sin enforcement estricto de transporte integral):

```bash
SIM_PROFILE=auth-only make loadtest-precheck-auth
```

3. Ejecuta la corrida integral:

```bash
make loadtest-150k
# o target genérico:
# make loadtest TARGET_HTTP_REQS=200000
# o con archivo personalizado:
# make loadtest-150k LOADTEST_ENV_FILE=.env.loadtest
# sigue disponible la invocación directa:
# ./simulacion/run_advanced_integral.sh
```

4. Revisa evidencia:

- Carpeta de salida: simulacion/reports/advanced_YYYYMMDD_HHMMSS/
- Resumen de volumen objetivo: run_summary.txt
- Dashboard tiempo real: http://localhost:3000
- Estado por fase en `run_summary.txt`:
  - `ok`: fase completada sin fallos
  - `soft-fail`: fallo de thresholds/k6 con summary disponible (la corrida continua)
  - `hard-fail`: fallo de infraestructura/ejecucion (la corrida aborta)

### Variables principales del orquestador

- TOTAL_DURATION: duracion de ambos bloques de carga (default 15m)
- TARGET_HTTP_REQS: objetivo total de `http_reqs` consolidado (default 150000)
- AUTH_VUS: VUs de auth extendido (default 120)
- AUTH_ADMIN_2FA_VUS: VUs dedicados a 2FA (default 6)
- OPER_BILLING_VUS / OPER_INVENTORY_VUS / OPER_POSTING_VUS: VUs operacionales
- LOADTEST_ENV_FILE: archivo opcional de override (default `.env.loadtest`)
- SIM_PROFILE: `integral` (default en precheck de loadtest) o `auth-only`
- AUTH_TOKEN_TRANSPORT/AUTH_ALLOW_TRANSPORT_OVERRIDE: en `integral` se exige `header`/`1`
- AUTH_TRANSPORT: transporte para `operational_posting_load.js`; en corrida integral se fuerza `header`
- Variables obligatorias del perfil: `AUTH_SIM_ADMIN_PASSWORD`,
  `AUTH_SIM_USER_PASSWORD`, `AUTH_SIM_ADMIN_TOTP_SECRET`, `COMPANY_ID`,
  `BRANCH_ID`, `USERNAME`, `PASSWORD`
- RUN_QA_GATES: 1 para ejecutar qa-ci-gate1/2/3 y frontend CI
- RUN_SECURITY_SCAN: 1 para ejecutar bug bounty local
- ADAPTIVE_RETRY_ON_FAILURE: 1 para habilitar reintento adaptativo (reduce `BILLING_VUS`) cuando hay degradación (`billing_doc_create` fail, `operational_error_rate>1%` o `billing_write_ms p95>400ms`).
- ADAPTIVE_BILLING_SCALE: factor de reducción de `BILLING_VUS` en reintento adaptativo (default `0.5`).
- ADAPTIVE_DURATION: duración del reintento adaptativo (default `5m`).
- BASELINE_RUN_DIR: carpeta `advanced_*` base para comparador inter-corridas.
- REGRESSION_BUDGET_PCT: budget máximo de degradación permitida para comparador inter-corridas.

### Criterio de volumen

El script consolida `http_reqs` de las dos corridas (auth + operacional) y falla
si el total es menor a `TARGET_HTTP_REQS` (default `150000`).

### Redacción de secretos en evidencia

Los summaries de k6 (`auth_summary.json` y `operational_summary.json`) se redactan automáticamente
antes de persistirse en disco para evitar exposición de `token/password/secret`.

### Comparador inter-corridas

Si defines `BASELINE_RUN_DIR`, el orquestador ejecuta un comparador de regresión (`compare_k6_regression.py`)
contra `operational_summary.json` y genera `operational_regression_report.json` en la corrida actual.

### Troubleshooting

Si ves `AUTH_SIM_ADMIN_PASSWORD faltante`, normalmente significa una de estas dos
cosas:

- `.env.loadtest` no existe en la ruta esperada
- `.env.loadtest` sigue con `CHANGE_ME` o una variable requerida vacia

Bootstrap minimo:

```bash
cp .env.loadtest.example .env.loadtest
```
