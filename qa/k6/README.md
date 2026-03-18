# QA

Este directorio contiene artefactos de QA que complementan los tests unitarios/integración.

## Load / Stress (k6)

Requisitos:

- Docker (recomendado) o k6 instalado localmente.
- Backend arriba en `http://localhost:8000` (por ejemplo con `docker compose up`).

### Perfiles de ejecución (dual por perfil)

| Perfil | Objetivo | Variables clave |
|---|---|---|
| `auth-local` | Smoke/stress sobre runtime base (cookie o auto-detección) | `AUTH_FLOW_MODE=auto` (default), `BASE_URL=http://.../api` |
| `integral-loadtest` | Corrida integral con contrato operacional header-first | `AUTH_FLOW_MODE=header` para smoke/stress de validación, `AUTH_TRANSPORT=header` para operacional |

### Crear un usuario para k6 (determinista)

Si no tienes credenciales conocidas (o tu entorno no está "fresh"), crea un usuario dedicado para carga:

```bash
docker compose exec -T backend python src/manage.py seed_auth_users
```

O bien crea un usuario manual:

```bash
docker compose exec -T backend python manage.py shell -c "from django.contrib.auth import get_user_model; User=get_user_model(); u, _=User.objects.get_or_create(username='k6'); u.email='k6@test.com'; u.is_staff=True; u.set_password('<SET_STRONG_PASSWORD>');
setattr(u, 'must_change_password', False); u.save()"
```

Luego corre k6 con:

- `-e USERNAME=k6`
- `-e PASSWORD=<SET_STRONG_PASSWORD>`

### Smoke de autenticación + ACL

Ejecuta un smoke test que hace:

- `POST /api/backend/auth/login/`
- `GET /api/backend/auth/me/`
- `GET /api/backend/auth/me/acl/`
- opcional: `GET /api/backend/org/companies/` con `X-Company-Id` recomendado

Comando (Docker):

Linux (recomendado, para que el contenedor vea el `localhost` del host):

```bash
docker run --rm -i --network host \
  -e BASE_URL=http://localhost:8000/api \
  -e USERNAME=admin \
  -e PASSWORD=admin \
  -e AUTH_FLOW_MODE=auto \
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
  -e AUTH_FLOW_MODE=auto \
  -e VUS=5 \
  -e DURATION=30s \
  grafana/k6 run - < qa/k6/auth_smoke.js
```

Notas:

- Ajusta `USERNAME/PASSWORD` a credenciales reales.
- `AUTH_FLOW_MODE` soporta `auto|cookie|header` (default `auto`).
- Si el entorno está "fresh" (sin usuarios), puedes habilitar bootstrap automático con `-e BOOTSTRAP=1` para crear el primer admin y la org de ejemplo.
- Si ejecutas k6 con credenciales erróneas, `django-axes` puede bloquear por IP. Para desbloquear en dev: `docker compose exec -T backend python manage.py axes_reset`.
- Para CI, recomienda levantar `db` + `backend` y crear un usuario seed (bootstrap) antes del k6.

### Stress (Auth: login + me + acl)

Script: `qa/k6/auth_stress.js`

Ejemplo (Linux, Docker):

```bash
docker run --rm -i --network host \
  -e BASE_URL=http://localhost:8000/api \
  -e USERNAME=k6 \
  -e PASSWORD=<SET_STRONG_PASSWORD> \
  -e AUTH_FLOW_MODE=auto \
  -e VUS_WARMUP=5 -e WARMUP=15s \
  -e VUS_TARGET=20 -e SUSTAIN=30s \
  -e COOLDOWN=10s \
  grafana/k6 run - < qa/k6/auth_stress.js
```

### Carga operacional (Billing + Inventory + Accounting)

Script: `qa/k6/operational_posting_load.js`

Objetivo:
- flujo `billing_issue_void`
- flujo `inventory_receive_issue`
- ciclo `accounting_posting_cycle`

Gate balanceado (thresholds del script):
- `billing_write_ms p95 < 400ms`
- `inventory_write_ms p95 < 400ms`
- `posting_cycle_ms p95 < 400ms`
- `operational_error_rate < 1%`

Ejemplo:

```bash
k6 run qa/k6/operational_posting_load.js \
  -e BASE_URL=http://localhost:8000/api \
  -e USERNAME=<OPER_USER> \
  -e PASSWORD=<OPER_PASSWORD> \
  -e AUTH_TRANSPORT=header \
  -e COMPANY_ID=<COMPANY_ID> \
  -e BRANCH_ID=<BRANCH_ID> \
  -e DURATION=2m \
  -e BILLING_VUS=6 \
  -e INVENTORY_VUS=6 \
  -e POSTING_VUS=1
```

Notas:
- Si no defines `WAREHOUSE_ID`/`ITEM_ID`, el script intentará crearlos (requiere permisos `inventory.warehouse.create` e `inventory.item.create`).
- El usuario de carga debe tener 2FA deshabilitado para login automático en k6.
- `operational_posting_load.js` es contractual `header-only` y falla rápido si `AUTH_TRANSPORT=cookie`.
- El runner recomendado para evidencia completa es `qa/run_operational_performance_gate.sh`.

### Overrides QA (throttles)

Si ves 429 bajo k6, normalmente es el limite global de `UserRateThrottle` o los scopes
`me_read`/`me_acl_read`. Para QA:

Nota importante (Docker Compose): el backend carga `.env` via `env_file`. Si las variables
no estan en `.env`, el contenedor usa defaults y el override no aplica.

```bash
DRF_THROTTLE_USER=120000/min \
DRF_THROTTLE_AUTH_LOGIN=1200/min \
DRF_THROTTLE_AUTH_REFRESH=1200/min \
DRF_THROTTLE_AUTH_LOGOUT=1200/min \
DRF_THROTTLE_ME_READ=60000/min \
DRF_THROTTLE_ME_ACL_READ=60000/min \
make qa-load-stress
```

### Un solo comando (Makefile)

En Linux puedes usar:

```bash
make qa-load-user && make qa-load-reset-axes && make qa-load-smoke
```

Y para stress:

```bash
make qa-load-stress
```
