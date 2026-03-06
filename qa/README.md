# QA

Este directorio contiene artefactos de QA que complementan los tests unitarios/integración.

## QA Runner (Gates 1–3)

El Makefile incluye un runner para CI/local que genera reportes en `qa/reports/`:

## Cobertura (Gate 2): alcance y criterio de éxito

**Alcance (scope):** el reporte de coverage usa `.coveragerc` y está filtrado a `src/apps/sync_engine`.
Eso significa que el **TOTAL** del reporte corresponde **solo** a ese módulo, no al backend completo.

**Criterio de éxito recomendado (verificable):**

- Cobertura del scope definido **≥ 98%** (o **≥ 99%** si el objetivo es más estricto).
- `make qa-ci-gate2` y `make qa-ci-gate3` pasan sin errores.
- Sin regresión: no bajar la cobertura del scope ni en archivos tocados.

Si el KPI es “backend completo”, hay que **ampliar o ajustar** el `source` en `.coveragerc` y recalcular el %.

- Recomendado (DB limpia, reproducible):

  ```bash
  make qa-ci-fresh
  ```

- En CI (alias explícito):

  ```bash
  make qa-ci-ci
  ```

Workflow sugerido en GitHub Actions: `.github/workflows/qa-ci.yml`.

- Normal (usa la DB actual; puede fallar si hay auditoría histórica inconsistente):

  ```bash
  make qa-ci
  ```

Nota: el “Gate 3” del runner de CI es **integridad de auditoría** (comando `audit_verify_chain`). El target `make qa-gate3` de este README es un **Gate 3 de carga** (k6 smoke+stress).

## Load / Stress (k6)

Requisitos:

- Docker (recomendado) o k6 instalado localmente.
- Backend arriba en `http://localhost:8000` (por ejemplo con `docker compose up`).

### Crear un usuario para k6 (determinista)

Si no tienes credenciales conocidas (o tu entorno no está "fresh"), crea un usuario dedicado para carga:

```bash
docker compose exec -T backend python manage.py seed_auth_users
```

O bien crea un usuario manual:

```bash
docker compose exec -T backend python manage.py shell -c "from django.contrib.auth import get_user_model; User=get_user_model(); u, _=User.objects.get_or_create(username='k6'); u.email='k6@test.com'; u.is_staff=True; u.set_password('Pass12345__Strong');
setattr(u, 'must_change_password', False); u.save()"
```

Luego corre k6 con:

- `-e USERNAME=k6`
- `-e PASSWORD=Pass12345__Strong`

### Smoke de autenticación + ACL

Ejecuta un smoke test que hace:

- `POST /api/auth/login/`
- `GET /api/auth/me/`
- `GET /api/auth/me/acl/`
- opcional: `GET /api/org/companies/` con `X-Company-Id` recomendado

Comando (Docker):

Linux (recomendado, para que el contenedor vea el `localhost` del host):

```bash
docker run --rm -i --network host \
  -e BASE_URL=http://localhost:8000/api \
  -e USERNAME=admin \
  -e PASSWORD=admin \
  -e VUS=5 \
  -e DURATION=30s \
  grafana/k6 run - < qa/k6/auth_smoke.js
```

Alternativa (Docker Desktop / o Docker en Linux con `host-gateway`):

```bash
docker run --rm -i \
  --add-host=host.docker.internal:host-gateway \
  -e BASE_URL=http://host.docker.internal:8000/api \
  -e USERNAME=admin \
  -e PASSWORD=admin \
  -e VUS=5 \
  -e DURATION=30s \
  grafana/k6 run - < qa/k6/auth_smoke.js
```

Notas:

- Ajusta `USERNAME/PASSWORD` a credenciales reales.
- Si el entorno está "fresh" (sin usuarios), puedes habilitar bootstrap automático con `-e BOOTSTRAP=1` para crear el primer admin y la org de ejemplo.
- Si ejecutas k6 con credenciales erróneas, `django-axes` puede bloquear por IP. Para desbloquear en dev: `docker compose exec -T backend python manage.py axes_reset`.
- Para CI, recomienda levantar `db` + `backend` y crear un usuario seed (bootstrap) antes del k6.

### Stress (Auth: login + me + acl)

Script: `qa/k6/auth_stress.js`

Este stress usa 2 escenarios (sin bajar calidad):

- `me_acl`: simula tráfico normal (reutiliza token) y aplica thresholds estrictos a `/me` y `/acl`.
- `login_churn`: simula churn de login con arrival-rate controlado y aplica threshold estricto a `/auth/login/`.

Recomendación: para que los thresholds sean exigentes pero justos bajo carga, corre el backend con Gunicorn durante el stress (el `runserver` de Django es single-process y distorsiona latencias).

Ejemplo (Linux, Docker):

```bash
docker run --rm -i --network host \
  -e BASE_URL=http://localhost:8000/api \
  -e USERNAME=k6 \
  -e PASSWORD=Pass12345__Strong \
  -e LOGIN_RATE_TARGET=2 \
  -e VUS_WARMUP=5 -e WARMUP=15s \
  -e VUS_TARGET=20 -e SUSTAIN=30s \
  -e COOLDOWN=10s \
  grafana/k6 run - < qa/k6/auth_stress.js
```

### Un solo comando (Makefile)

Gate 3 completo (recomendado):

```bash
make qa-gate3
```

Defaults del Gate 3 (overrideables en `make`):

- `STRESS_VUS_TARGET=50`
- `STRESS_LOGIN_RATE_TARGET=5` (logins/seg)
- `STRESS_SUSTAIN=60s`

### Overrides QA (throttles)

Si Gate 3 falla por 429 bajo k6 (un solo usuario con alto RPS), el cuello suele ser
`UserRateThrottle` o los scopes `me_read`/`me_acl_read`. Para QA puedes subirlos por env
sin tocar defaults de codigo.

Nota importante (Docker Compose): el backend lee variables desde `.env` por `env_file`.
Si exportas variables en el shell pero no las agregas a `.env`, **no** llegan al contenedor
y el throttle sigue en los valores por defecto.

Ejemplo (solo QA/local):

```bash
DRF_THROTTLE_USER=120000/min \
DRF_THROTTLE_AUTH_LOGIN=1200/min \
DRF_THROTTLE_AUTH_REFRESH=1200/min \
DRF_THROTTLE_AUTH_LOGOUT=1200/min \
DRF_THROTTLE_ME_READ=60000/min \
DRF_THROTTLE_ME_ACL_READ=60000/min \
make qa-gate3
```

Para que el override aplique en el backend, agrega esas variables a `.env` local antes
de correr `make qa-gate3`.

Ejemplo para subir exigencia:

```bash
make qa-gate3 STRESS_VUS_TARGET=75 STRESS_LOGIN_RATE_TARGET=8 STRESS_SUSTAIN=120s
```

## Simulación de carga (auth)

- Guía operativa: [simulacion/README.md](../simulacion/README.md)
- Workflow en GitHub Actions: `.github/workflows/auth-load-simulation.yml`
