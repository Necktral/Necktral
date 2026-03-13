# Simulación – Pruebas de Carga y Bug Bounty

Este paquete contiene las herramientas avanzadas de simulación para validar el
rendimiento, la estabilidad y la seguridad de la plataforma Necktral.

## Funciones principales

### 1. Simulación de carga y estrés

Pruebas realistas que ejercitan todos los subsistemas del proyecto bajo carga
elevada, incluyendo creación de usuarios, flujos de RBAC, 2FA, y operaciones
del módulo completo.

### 2. Bug Bounty (seguridad)

Suite de pruebas de seguridad alineada con OWASP Top-10 que detecta
vulnerabilidades de inyección, control de acceso, criptografía, CSRF, IDOR,
escalamiento de privilegios, y más.

---

## Contenido

| Archivo | Tipo | Descripción |
|---------|------|-------------|
| `auth_load_simulation.js` | K6 | Carga base: ciclo 2FA + básico con cookies |
| `auth_load_simulation_extended.js` | K6 | Carga extendida: 6 escenarios de seguridad y rendimiento |
| `user_lifecycle_simulation.js` | K6 | Ciclo de vida completo: bootstrap → org → HR → provisión de usuarios → auth multi-usuario → RBAC → cambio de contraseña → 2FA toggle |
| `full_platform_stress.js` | K6 | Estrés de plataforma completa: spike / soak / breakpoint sobre auth + RBAC + org + HR + contabilidad + pagos + auditoría |
| `bug_bounty_security.js` | K6 | Bug bounty OWASP: inyección SQL/NoSQL/XSS, IDOR, bypass de auth, tokens forjados, CSRF bypass, header injection, info leakage |
| `run_simulation.sh` | Shell | Runner automatizado con monitoreo Grafana |
| `run_bug_bounty.sh` | Shell | Runner de bug bounty con reportes JSON + Markdown |
| `docker-compose.monitoring.yaml` | Docker | Stack Grafana + InfluxDB |
| `auth-load-simulation.yml` | Workflow | Referencia CI para simulación de carga |
| `dashboards/` | Grafana | Dashboard preconfigurado |

---

## Requisitos

- Docker y Docker Compose
- Backend Django levantado
- Base de datos disponible
- k6 (local o vía contenedor `grafana/k6`)

---

## Scripts de carga

### auth_load_simulation.js (base)

Ciclo cookie con 2FA TOTP y ciclo básico sin 2FA.

```bash
BASE_URL=http://localhost:8000/api \
ADMIN_USERNAME=k6_admin ADMIN_PASSWORD=<pw> \
ADMIN_TOTP_SECRET=JBSWY3DPEHPK3PXP \
USER_USERNAME=k6_user USER_PASSWORD=<pw> \
k6 run simulacion/auth_load_simulation.js
```

### auth_load_simulation_extended.js (recomendado)

6 escenarios: cookie_flow, admin_2fa, refresh_rotation, logout_idempotent,
cookie_logout_idempotent, attacks.

```bash
BASE_URL=http://localhost:8000/api \
VUS=12 DURATION=60s \
ADMIN_USERNAME=k6_admin ADMIN_PASSWORD=<pw> \
ADMIN_TOTP_SECRET=JBSWY3DPEHPK3PXP \
USER_USERNAME=k6_user USER_PASSWORD=<pw> \
k6 run simulacion/auth_load_simulation_extended.js
```

#### Escenarios del script extendido

1. **cookie_flow** – Login en modo cookie, refresh/logout sin CSRF (espera 403), refresh/logout con CSRF (espera 200/204), verificación estricta de limpieza de cookies
2. **admin_2fa** – Login admin (202 con challenge), verify TOTP (200), replay del challenge (400 esperado), logout
3. **refresh_rotation** – Login header, refresh con rotación, reuso de refresh viejo (401 esperado)
4. **logout_idempotent** – Logout válido (204), logout repetido (204 esperado)
5. **cookie_logout_idempotent** – Logout con cookie corrupta/expirada, verifica 204 idempotente y limpieza forzada
6. **attacks** – Refresh corrupto (401 esperado)

### user_lifecycle_simulation.js (ciclo de vida completo)

Prueba avanzada que ejecuta el ciclo de vida completo de usuarios:

1. **Bootstrap** – Crea admin root y jerarquía organizacional
2. **HR provisioning** – Crea posiciones, empleados y provisiona cuentas de usuario
3. **Auth churn** – Login/me/acl/refresh/logout concurrente con múltiples usuarios
4. **RBAC gate** – Valida permisos (roles, permissions, demo endpoint) bajo carga
5. **Password change** – Ciclo de cambio de contraseña obligatorio
6. **2FA toggle** – Ciclo enable → confirm → disable de TOTP

```bash
BASE_URL=http://localhost:8000/api \
ADMIN_PASSWORD=<pw> \
VUS=10 DURATION=60s \
EMPLOYEE_COUNT=5 \
k6 run simulacion/user_lifecycle_simulation.js
```

**Variables de entorno:**

| Variable | Default | Descripción |
|----------|---------|-------------|
| `BASE_URL` | `http://localhost:8000/api` | URL base |
| `ADMIN_USERNAME` | `lifecycle_root` | Admin para setup |
| `ADMIN_PASSWORD` | (requerido) | Contraseña admin |
| `EMPLOYEE_COUNT` | `5` | Número de empleados a crear |
| `EMPLOYEE_PREFIX` | `k6emp` | Prefijo de usernames |
| `EMPLOYEE_TEMP_PW` | `Tmp!9_K6_Empl` | Contraseña temporal |
| `EMPLOYEE_NEW_PW` | `New!9_K6_Empl` | Nueva contraseña |
| `VUS` | `10` | Usuarios virtuales |
| `DURATION` | `60s` | Duración |

**Thresholds:**

| Métrica | Objetivo |
|---------|----------|
| `lifecycle_error_rate` | < 5% |
| `auth_cycle_ms p(95)` | < 900ms |
| `rbac_check_ms p(95)` | < 600ms |
| `password_change_ms p(95)` | < 800ms |
| `twofa_cycle_ms p(95)` | < 1200ms |
| `hr_provision_ms p(95)` | < 1500ms |
| `bootstrap_ms p(95)` | < 3000ms |

### full_platform_stress.js (estrés de plataforma)

Prueba de estrés que golpea todos los subsistemas simultáneamente con tres
perfiles de carga:

- **spike** – Surge repentino de 5 → 50 VUs por 20s, luego baja
- **soak** – Carga moderada (15 VUs) sostenida por 5 minutos
- **breakpoint** – Rampa gradual de 0 → 100 VUs para encontrar el techo

Cada VU ejecuta un ciclo completo:
login → me → acl → refresh → roles → permissions → companies → branches →
company profile → positions → employees → accounting health → periods →
chart of accounts → trial balance → payments health → cash sessions →
audit bitacora → logout

```bash
# Spike test (default)
BASE_URL=http://localhost:8000/api \
USERNAME=k6_user PASSWORD=<pw> \
PROFILE=spike \
k6 run simulacion/full_platform_stress.js

# Soak test
PROFILE=soak SOAK_VUS=20 SOAK_DURATION=10m \
k6 run simulacion/full_platform_stress.js

# Breakpoint test
PROFILE=breakpoint BP_MAX=100 BP_STEPS=10 \
k6 run simulacion/full_platform_stress.js
```

**Variables de entorno:**

| Variable | Default | Descripción |
|----------|---------|-------------|
| `PROFILE` | `spike` | Perfil: `spike`, `soak`, `breakpoint` |
| `USERNAME` / `PASSWORD` | `k6_user` | Credenciales |
| `COMPANY_ID` | (auto) | ID de compañía |
| `BRANCH_ID` | (auto) | ID de sucursal |
| `SPIKE_BASE` / `SPIKE_PEAK` | `5` / `50` | VUs para spike |
| `SOAK_VUS` / `SOAK_DURATION` | `15` / `5m` | Nivel soak |
| `BP_MAX` / `BP_STEPS` | `100` / `10` | Techo breakpoint |

**Thresholds:**

| Métrica | Objetivo |
|---------|----------|
| `stress_error_rate` | < 10% |
| `stress_auth_ms p(95)` | < 1200ms |
| `stress_rbac_ms p(95)` | < 800ms |
| `stress_org_ms p(95)` | < 800ms |
| `stress_hr_ms p(95)` | < 1000ms |
| `stress_accounting_ms p(95)` | < 1000ms |
| `stress_payments_ms p(95)` | < 800ms |
| `stress_audit_ms p(95)` | < 800ms |

---

## Bug Bounty (seguridad)

### bug_bounty_security.js

Suite de seguridad alineada con OWASP Top-10 2021 que prueba:

| Categoría OWASP | Pruebas |
|------------------|---------|
| **A01** Broken Access Control | Acceso no autenticado a endpoints protegidos, IDOR con IDs secuenciales, escalamiento horizontal/vertical de privilegios, re-ejecución de bootstrap |
| **A02** Cryptographic Failures | JWT forjado, algoritmo `none`, token vacío, refresh corrupto, re-uso post-rotación, mismatch de token owner |
| **A03** Injection | SQL injection en login y query params, NoSQL injection en JSON body, XSS reflection check, path traversal |
| **A04** Insecure Design | Mass assignment (`is_superuser`/`is_staff`), parameter pollution |
| **A05** Security Misconfiguration | CORS wildcard check, HTTP method probing (TRACE/PUT/DELETE), debug endpoints, admin panel exposure |
| **A07** Auth Failures | Brute force (5 intentos rápidos → lockout), 2FA replay attack, challenge fabricado, credential stuffing |
| **A08** Data Integrity | CSRF bypass (sin token, token incorrecto), CSRF en logout |
| **A09** Logging Failures | Stack trace en errores, enumeración de usuarios, headers de tecnología expuestos |

```bash
BASE_URL=http://localhost:8000/api \
ADMIN_USERNAME=k6_admin ADMIN_PASSWORD=<pw> \
ADMIN_TOTP_SECRET=JBSWY3DPEHPK3PXP \
USER_USERNAME=k6_user USER_PASSWORD=<pw> \
k6 run simulacion/bug_bounty_security.js
```

**Métrica clave:** `vuln_found` debe ser 0 para pasar.

### run_bug_bounty.sh (runner automatizado)

Runner que ejecuta la suite de bug bounty y genera reportes:

```bash
# Ejecución por defecto (3 VUs, 45s)
./simulacion/run_bug_bounty.sh

# Con más carga
./simulacion/run_bug_bounty.sh 5 60s

# Con dashboard Grafana
./simulacion/run_bug_bounty.sh 3 45s --monitor
```

**Salida:**
- `simulacion/reports/bug_bounty_<timestamp>.json` – Datos crudos k6
- `simulacion/reports/bug_bounty_summary_<timestamp>.json` – Resumen JSON
- `simulacion/reports/bug_bounty_findings_<timestamp>.md` – Reporte Markdown

---

## Ejecución automatizada con monitorización

```bash
# Carga con Grafana dashboard
./simulacion/run_simulation.sh

# Carga extendida con más VUs
./simulacion/run_simulation.sh auth_load_simulation_extended.js 20 60s

# Ciclo de vida completo
./simulacion/run_simulation.sh user_lifecycle_simulation.js 10 60s

# Estrés spike
./simulacion/run_simulation.sh full_platform_stress.js 50 90s

# Bug bounty con monitoreo
./simulacion/run_bug_bounty.sh 5 60s --monitor
```

**Acceso al Dashboard:**
- URL: [http://localhost:3000](http://localhost:3000)
- Dashboard: "K6 Load Testing Results" (Carpeta General)

---

## Preparación del entorno

### 1. Iniciar servicios

```bash
docker compose down -v --remove-orphans || true
USE_GUNICORN=1 GUNICORN_WORKERS=4 docker compose up -d db backend
```

### 2. Esperar healthcheck

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
```

### 3. Migraciones y seed

```bash
docker compose exec -T backend python src/manage.py migrate --noinput
docker compose exec -T backend python src/manage.py seed_auth_users
```

---

## Variables de entorno comunes

| Variable | Default | Descripción |
|----------|---------|-------------|
| `BASE_URL` | `http://localhost:8000/api` | URL base del API |
| `ADMIN_USERNAME` | `k6_admin` | Usuario admin |
| `ADMIN_PASSWORD` | (requerido) | Contraseña admin |
| `ADMIN_TOTP_SECRET` | (opcional) | Secreto TOTP para 2FA |
| `USER_USERNAME` | `k6_user` | Usuario normal |
| `USER_PASSWORD` | (requerido) | Contraseña usuario |
| `CSRF_COOKIE_NAME` | `nt_csrf` | Nombre cookie CSRF |
| `VUS` | varía | Usuarios virtuales |
| `DURATION` | varía | Duración de la prueba |
| `ADMIN_2FA_VUS` | `1` | VUs dedicados a 2FA |
| `ADMIN_2FA_SLEEP` | `15` | Sleep entre intentos 2FA |
| `AUTH_SIM_ADMIN_SUPERUSER` | `0` | Siembra admin como superuser (0/1) |
| `AUTH_SIM_SHOW_SECRETS` | `0` | Imprime secreto TOTP en consola (0/1) |

---

## Thresholds esperados (script extendido base)

- `http_req_failed` < 1%
- p(95):
  - login < 600ms
  - 2FA < 700ms
  - refresh < 400ms
  - logout < 400ms
  - ataques < 500ms

---

## Solución de problemas

### 429 / throttling

Ajusta throttles en `.env` y reinicia el backend:
```
DRF_THROTTLE_AUTH_LOGIN=1200/min
DRF_THROTTLE_AUTH_REFRESH=1200/min
DRF_THROTTLE_AUTH_SENSITIVE=600/min
```

### Axes bloquea usuarios

```bash
docker compose exec -T backend python src/manage.py axes_reset
```

### TOTP inválido

- Verifica que `ADMIN_TOTP_SECRET` coincida con el seed
- Si hay desfase de reloj, aumenta `TOTP_VALID_WINDOW` en settings

### Employees no se crean

- Verifica que el admin tenga permisos de HR (`hr.employee.create`)
- Revisa los logs del backend: `docker compose logs backend`

---

## Notas

- El workflow oficial vive en `.github/workflows/auth-load-simulation.yml`.
- El script extendido es el recomendado para validar el flujo completo.
- Seed de usuarios: `login_module/src/apps/accounts/management/commands/seed_auth_users.py`
- Bug Bounty local (qa): `qa/run_bug_bounty_local.sh`
- Risk Register: `qa/RISK_REGISTER.md`
