# QA

Este directorio contiene artefactos de QA que complementan los tests unitarios/integración.

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

Ejemplo (Linux, Docker):

```bash
docker run --rm -i --network host \
  -e BASE_URL=http://localhost:8000/api \
  -e USERNAME=k6 \
  -e PASSWORD=Pass12345__Strong \
  -e VUS_WARMUP=5 -e WARMUP=15s \
  -e VUS_TARGET=20 -e SUSTAIN=30s \
  -e COOLDOWN=10s \
  grafana/k6 run - < qa/k6/auth_stress.js
```

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
