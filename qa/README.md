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

### Guard de contrato Analytics (puerto/prefix/proxy)

Se valida en Gate 1 que el contrato operativo de Analytics no derive:

- Prefix canónico: `/analytics`
- Puerto interno Dash: `8050`
- Dev con `8050:8050` publicado (debug)
- Prod sin publicación host de Dash (solo same-origin vía Nginx)

Ejecución manual:

```bash
make qa-analytics-contract-guard
```

### Verificación estática veraz (ruff + mypy)

Gate 1 ahora valida estáticos en dos capas:

- `ruff` y `mypy` corren con `pipefail` (fallan si el comando falla aunque use `tee`).
- `qa-verify-static-gate` parsea `qa/reports/ruff.txt` y `qa/reports/mypy.txt` para bloquear falsos verdes.

Ejecución manual:

```bash
make qa-backend-ruff QA_REPORTS_DIR=qa/reports
make qa-backend-mypy QA_REPORTS_DIR=qa/reports
make qa-verify-static-gate QA_REPORTS_DIR=qa/reports
```

Artefacto:

- `qa/reports/static_gate_summary.json`

### Guard de drift de migraciones

Gate 1 bloquea drift de modelos/migraciones con:

```bash
make qa-makemigrations-check QA_REPORTS_DIR=qa/reports
```

Artefacto:

- `qa/reports/makemigrations_check.txt`

### Guard de bootstrap de `PYTHONPATH` en runtime

Gate 1 bloquea reintroducir hacks de `sys.path.insert(...)` dentro de `backend/src`:

```bash
make qa-pythonpath-bootstrap-guard
```

### Guard de contrato de registry (`reporting`)

Gate 1 también bloquea drift en datasets de reporting:

- metadata mínima obligatoria por dataset (`render_hints`, `drill_metadata`, `quality_policy`, `export_capabilities`),
- `dataset_key` únicos,
- handlers de adapters (`accounting`/`fuel`) alineados con datasets habilitados en `registry`.

Ejecución manual:

```bash
make qa-reporting-registry-guard
```

### Guard de compatibilidad contractual versionada (`reporting` U2)

Gate 1 bloquea cambios contractuales silenciosos en datasets de reporting usando baseline versionado:

- baseline: `qa/contracts/reporting_dataset_contract_baseline.json`
- verifica bumps obligatorios:
  - cambios estructurales (`filters_schema`, `dimensions`, `measures`, `export_capabilities`) requieren `schema_version` mayor.
  - cambios semánticos (`quality_policy`) requieren `semantic_version` mayor.
- datasets nuevos solo pasan si cumplen metadata contractual mínima.

Ejecución manual:

```bash
make qa-reporting-contract-version-guard
```

Artefacto:

- `qa/reports/reporting_contract_guard.json`

Nota: el “Gate 3” del runner de CI es **integridad de auditoría** (comando `audit_verify_chain`). El target `make qa-gate3` de este README es un **Gate 3 de carga** (k6 smoke+stress).

### Gate R8 (reporting calidad + SLO)

Gate adicional de R8 (incluido en `qa-ci-gate3`) para `reporting/dashboard`:

```bash
make qa-reporting-r8-gate
make qa-verify-reporting-r8-gate-artifact
```

Artefacto generado:

- `qa/reports/reporting_r8_gate.json`
- `qa/reports/reporting_r8_gate_guard.json`

Política de enforcement:

- hasta `2026-04-07`: resultado con brechas = `WARN` (no bloquea CI).
- desde `2026-04-08`: brechas = `FAIL` (bloquea CI).

Thresholds por defecto:

- `snapshot p95 <= 800ms`
- `near-realtime/cache p95 <= 1500ms`
- `error_rate < 0.5%`

Taxonomía normalizada de `failure_class`:

- `none`
- `quality_breach`
- `latency_regression`
- `app_error`
- `infra_error`

Prioridad de clasificación cuando coexisten brechas:

- `infra_error > app_error > latency_regression > quality_breach`

Contrato adicional del artefacto `reporting_r8_gate.json`:

- `trigger_metric` obligatorio cuando `failure_class != none`.
- `breaches` estructurado por dataset/policy/métrica cuando aplica.

### Aislamiento de base de datos de tests (anti-colisión)

Por defecto, los tests usan **DB de test aislada por proceso** para evitar colisiones cuando hay corridas concurrentes.

- Variables disponibles:
  - `PYTEST_DB_BASE_NAME` (default: `test_erp_db`)
  - `PYTEST_DB_SLOT` (opcional, para nombre estable al reutilizar DB)

Modos recomendados:

- Modo seguro default (aislado, sin configuración):

  ```bash
  pytest -q
  ```

- Modo rápido de desarrollo con reuse explícito:

  ```bash
  PYTEST_DB_SLOT=dev pytest --reuse-db -q
  ```

- Diagnóstico (ver conexiones activas a DB de test):

  ```bash
  python backend/manage.py shell -c "from django.db import connection; c=connection.cursor(); c.execute(\"select datname,pid,state,application_name from pg_stat_activity where datname like 'test_%' order by datname,pid\"); print(c.fetchall())"
  ```

### Gate 3 dual recomendado (security + performance)

Modelo operativo:

- `qa-gate3` => alias de `qa-gate3-security` (canónico para PR/CI estable).
- `qa-gate3-performance` => perfil extendido para capacidad (nightly/release o ejecución manual).

Preflight recomendado:

```bash
docker compose up -d --build db backend
docker compose exec -T backend python /app/qa/wait_backend_ready.py
PASSWORD='K6Tmp!2026' make qa-load-user
make qa-load-reset-axes
```

Ejecución:

```bash
PASSWORD='K6Tmp!2026' make qa-gate3-security
PASSWORD='K6Tmp!2026' make qa-gate3-performance
```

Artefactos por perfil:

- `qa/reports/gate3_<profile>.log`
- `qa/reports/backend_gate3_<profile>_tail.log`
- `qa/reports/db_gate3_<profile>_tail.log`
- `qa/reports/gate3_<profile>_summary.json`

Lectura rápida de resultado:

- `passed=true` => corrida aceptada.
- `failure_class=throttle_mismatch` => desalineación de carga/throttle (ajustar perfil).
- `failure_class=latency_regression` => regresión de p95.
- `failure_class=app_error` => error real backend (5xx/traceback), bloquear release.
- `failure_class=infra_error` => salida no-cero sin firma clara de app (diagnóstico de infraestructura).

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
docker compose exec -T backend python manage.py shell -c "from django.contrib.auth import get_user_model; User=get_user_model(); u, _=User.objects.get_or_create(username='k6'); u.email='k6@test.com'; u.is_staff=True; u.set_password('<SET_STRONG_PASSWORD>');
setattr(u, 'must_change_password', False); u.save()"
```

Luego corre k6 con:

- `-e USERNAME=k6`
- `-e PASSWORD=<SET_STRONG_PASSWORD>`

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
  -e PASSWORD=<SET_STRONG_PASSWORD> \
  -e LOGIN_RATE_TARGET=2 \
  -e VUS_WARMUP=5 -e WARMUP=15s \
  -e VUS_TARGET=20 -e SUSTAIN=30s \
  -e COOLDOWN=10s \
  grafana/k6 run - < qa/k6/auth_stress.js
```

### Gate operacional (Billing + Inventory + Accounting)

Para Fase 4 (perfil SLO balanceado) usa:

```bash
COMPANY_ID=<COMPANY_ID> \
BRANCH_ID=<BRANCH_ID> \
USERNAME=<OPER_USER> \
PASSWORD=<OPER_PASSWORD> \
BASE_URL=http://localhost:8000/api \
./qa/run_operational_performance_gate.sh
```

Evidencia generada:
- `snapshot_before.json`
- `k6_summary.json`
- `snapshot_after.json`
- `gate_report.json` + `gate_report.sha256`

### Rollout piloto (Fase 5)

Runner por etapa:

```bash
COMPANY_ID=<COMPANY_ID> BRANCH_ID=<BRANCH_ID> ./qa/run_operational_pilot_rollout.sh stage1
COMPANY_ID=<COMPANY_ID> BRANCH_ID=<BRANCH_ID> ./qa/run_operational_pilot_rollout.sh stage2
COMPANY_ID=<COMPANY_ID> BRANCH_ID=<BRANCH_ID> ATTEMPT_CLOSE=1 ./qa/run_operational_pilot_rollout.sh stage3
COMPANY_ID=<COMPANY_ID> BRANCH_ID=<BRANCH_ID> ./qa/run_operational_pilot_rollout.sh rollback
```

### Higiene de cierre F0/F1

```bash
./qa/run_operational_hygiene_checks.sh
```

Targets equivalentes de `make`:

```bash
make qa-operational-hygiene
make qa-operational-gate COMPANY_ID=<ID> BRANCH_ID=<ID> USERNAME=<USER> PASSWORD=<PASS>
make qa-operational-pilot-stage1 COMPANY_ID=<ID> BRANCH_ID=<ID>
make qa-operational-pilot-stage2 COMPANY_ID=<ID> BRANCH_ID=<ID>
make qa-operational-pilot-stage3 COMPANY_ID=<ID> BRANCH_ID=<ID>
make qa-operational-pilot-rollback COMPANY_ID=<ID> BRANCH_ID=<ID>
make qa-operational-go-live COMPANY_ID=<ID> BRANCH_ID=<ID> USERNAME=<USER> PASSWORD=<PASS>
```

Gate final de go-live (7 días estables por defecto):

```bash
./qa/run_operational_go_live.sh verify
```

El gate exige aprobaciones de owner funcional/técnico y signoff final (`FINAL_APPROVED`).
Registro manual recomendado:

```bash
python backend/manage.py record_operational_go_live_review --evidence-dir <RUTA_EVIDENCIA> --reviewer <OWNER_FUNCIONAL> --role FUNCTIONAL --status APPROVED --summary "<resumen>"
python backend/manage.py record_operational_go_live_review --evidence-dir <RUTA_EVIDENCIA> --reviewer <OWNER_TECNICO> --role TECHNICAL --status APPROVED --summary "<resumen>"
python backend/manage.py record_operational_go_live_review --evidence-dir <RUTA_EVIDENCIA> --reviewer <OWNER_TECNICO> --role TECHNICAL --status FINAL_APPROVED --summary "<resumen>"
```

Excepción auditable por fuerza mayor (día excusado):

```bash
python backend/manage.py record_operational_go_live_exception \
  --evidence-dir <RUTA_EVIDENCIA> \
  --date <YYYY-MM-DD> \
  --exception-type FORCE_MAJEURE \
  --status APPROVED \
  --reported-by <RESPONSABLE_OPERATIVO> \
  --approved-by <OWNER_APROBADOR> \
  --summary "<motivo>"
```

Validación no lineal controlada (opcional):

```bash
ALLOW_EXCUSED_DAYS=1 MAX_EXCUSED_DAYS=2 MAX_CALENDAR_DAYS=9 \
./qa/run_operational_go_live.sh verify
```

Modo automático opcional (solo QA):

```bash
AUTO_SIGNOFF=1 FUNCTIONAL_REVIEWER=<OWNER_FUNCIONAL> TECHNICAL_REVIEWER=<OWNER_TECNICO> \
./qa/run_operational_go_live.sh verify
```

Overrides del gate final (mantener trazabilidad en evidencia):

```bash
REQUIRED_DAYS=1 \
MAX_RECONCILIATION_MISMATCH=10 \
MAX_PENDING_OPERATIONAL=500 \
./qa/run_operational_go_live.sh verify
```

Variables soportadas por `run_operational_go_live.sh` para `verify`:
- `MAX_FAILED_OUTBOX`
- `MAX_RECONCILIATION_MISMATCH`
- `MAX_DRAFT_EXCEPTION`
- `MAX_PENDING_OPERATIONAL`
- `MAX_FUEL_PENDING`
- `MAX_FUEL_FAILED`
- `ALLOW_EXCUSED_DAYS` (`1|0`)
- `MAX_EXCUSED_DAYS`
- `MAX_CALENDAR_DAYS` (`0` = sin límite de ventana calendario)
- `EXCUSED_DAY_PATTERN`
- `REQUIRE_PERFORMANCE_PASS` (`1|0`)
- `REQUIRE_OWNER_APPROVALS` (`1|0`)
- `REQUIRE_FINAL_SIGNOFF` (`1|0`)
- `REQUIRE_CLOSE_OK` (`1|0`)

Para ejecutar ciclo completo + verificación final:

```bash
COMPANY_ID=<ID> BRANCH_ID=<ID> USERNAME=<USER> PASSWORD=<PASS> \
./qa/run_operational_go_live.sh full
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

## F8 Burn-in Operativo

Scripts para sostener F8 (piloto 5/6) durante los 14 días:

- Tick operativo cada 5 minutos: `qa/run_phase8_live_tick.sh`
- Cierre diario formal + actualización de resumen/hash: `qa/run_phase8_burnin_daily.sh`
- Guardia calendario (09–22 marzo 2026): `qa/run_phase8_calendar_guard.sh`
- Reinicio de ventana por fallo diario: `qa/reset_phase8_window.sh`
- Plantilla cron: `qa/phase8_burnin.cron.example`
- Calendario flexible (días laborales elegidos): `qa/phase8_work_calendar.example.json`

Hardening SRE integrado en scripts F8:

- Resolución robusta de intérprete (`PYTHON_BIN` -> `python3` -> `python`).
- Lock anti-solapamiento con `flock` en `live-tick`, `burnin-daily` y `calendar-guard`.
- Soporte de simulación controlada por fecha con `TODAY_LOCAL` (solo QA/dev).

Ejemplo manual:

```bash
OUT_DIR=docs/operacion/evidencia/phase8_go_live_20260309_1040 \
COMPANY_ID=5 BRANCH_ID=6 \
./qa/run_phase8_live_tick.sh

OUT_DIR=docs/operacion/evidencia/phase8_go_live_20260309_1040 \
COMPANY_ID=5 BRANCH_ID=6 PARENT_COMPANY_ID=5 COMPANY_IDS=5 \
./qa/run_phase8_burnin_daily.sh

# Guardia calendario (live tick laboral / cierre diario calendario)
OUT_DIR=docs/operacion/evidencia/phase8_go_live_20260309_1040 \
COMPANY_ID=5 BRANCH_ID=6 PARENT_COMPANY_ID=5 COMPANY_IDS=5 \
PHASE8_START_DATE=2026-03-09 PHASE8_END_DATE=2026-03-22 \
./qa/run_phase8_calendar_guard.sh daily-close
```

Smoke controlado por fecha (QA/dev):

```bash
OUT_DIR=docs/operacion/evidencia/phase8_go_live_20260309_1040 \
PHASE8_CALENDAR_FILE=docs/operacion/evidencia/phase8_go_live_20260309_1040/phase8_work_calendar.json \
TODAY_LOCAL=2026-03-16 \
./qa/run_phase8_calendar_guard.sh daily-close-full
```

Auto reset de ventana si falla un cierre diario:

```bash
OUT_DIR=docs/operacion/evidencia/phase8_go_live_20260309_1040 \
COMPANY_ID=5 BRANCH_ID=6 PARENT_COMPANY_ID=5 COMPANY_IDS=5 \
PHASE8_START_DATE=2026-03-09 PHASE8_END_DATE=2026-03-22 \
PHASE8_AUTO_RESET_ON_FAIL=1 \
./qa/run_phase8_calendar_guard.sh daily-close
```

## F9 Provider Go-Live

Runner canónico F9 (carril EMULATED/HTTP):

- `qa/run_phase9_go_live.sh`
- Modos: `precheck`, `certify`, `cycle`, `gate`, `summary`, `full`

Plantilla cron F9:

- `qa/phase9_cycle.cron.example`

Ejemplo de ejecución completa (EMULATED):

```bash
OUT_DIR=docs/operacion/evidencia/phase9_go_live_<TS> \
COMPANY_ID=5 BRANCH_ID=6 \
F9_PROVIDER_MODE=EMULATED \
./qa/run_phase9_go_live.sh full
```

Ejemplo de ejecución completa (HTTP):

```bash
OUT_DIR=docs/operacion/evidencia/phase9_go_live_http_<TS> \
COMPANY_ID=5 BRANCH_ID=6 \
F9_PROVIDER_MODE=HTTP \
F9_HTTP_BASE_URL=https://provider.example \
F9_HTTP_API_KEY=<TOKEN> \
F9_HTTP_TIMEOUT_SECONDS=15 \
F9_HTTP_VERIFY_TLS=1 \
./qa/run_phase9_go_live.sh full
```

## F10 Procurement Go-Live

Runner canónico F10:

- `qa/run_phase10_go_live.sh`
- Modos: `precheck`, `certify`, `cycle`, `gate`, `summary`, `full`

Plantilla cron F10:

- `qa/phase10_cycle.cron.example`

Ejemplo de ejecución completa:

```bash
OUT_DIR=docs/operacion/evidencia/phase10_go_live_<TS> \
COMPANY_ID=5 BRANCH_ID=6 \
./qa/run_phase10_go_live.sh full
```

## F11 Intercompany Avanzado Go-Live

Runner canónico F11:

- `qa/run_phase11_go_live.sh`
- Modos: `precheck`, `certify`, `cycle`, `gate`, `summary`, `full`

Plantilla cron F11:

- `qa/phase11_cycle.cron.example`

Ejemplo de ejecución completa:

```bash
OUT_DIR=docs/operacion/evidencia/phase11_go_live_<TS> \
COMPANY_ID=5 BRANCH_ID=6 \
OPEN_SLA_HOURS=24 DISPUTE_SLA_HOURS=24 \
./qa/run_phase11_go_live.sh full
```

## F12 Cierre Mensual Consolidado Continuo Go-Live

Runner canónico F12:

- `qa/run_phase12_go_live.sh`
- Modos: `precheck`, `certify`, `cycle`, `gate`, `summary`, `full`

Plantilla cron F12:

- `qa/phase12_cycle.cron.example`

Ejemplo de ejecución completa:

```bash
OUT_DIR=docs/operacion/evidencia/phase12_go_live_<TS> \
COMPANY_ID=5 BRANCH_ID=6 PARENT_COMPANY_ID=5 COMPANY_IDS=5 \
REQUIRED_PERIODS=3 FX_BLOCKED_POLICY=ALERT \
./qa/run_phase12_go_live.sh full
```

### Calendario flexible de días laborales

Puedes controlar exactamente qué días son laborales completos y qué días son mínimos
usando `PHASE8_CALENDAR_FILE` con JSON:

- `mode=HYBRID`: habilita selección manual + fallback semanal.
- `manual_days`: override por fecha (`FULL|MINIMAL|SKIP`).
- `default_week_profile`: fallback semanal (`monday..sunday`).
- `required_pass_days`: mínimo de días `PASS` para `verify_phase8_burn_in`.
- `allow_eventual_close`: habilita cierres eventuales.
- `accountant_policy`: `ON_DEMAND_FINAL_REQUIRED`.

Ejemplo:

```bash
OUT_DIR=docs/operacion/evidencia/phase8_go_live_20260309_1040
cp qa/phase8_work_calendar.example.json "$OUT_DIR/phase8_work_calendar.json"
```

Luego ejecuta guardia usando ese calendario:

```bash
OUT_DIR=docs/operacion/evidencia/phase8_go_live_20260309_1040 \
PHASE8_CALENDAR_FILE=docs/operacion/evidencia/phase8_go_live_20260309_1040/phase8_work_calendar.json \
./qa/run_phase8_calendar_guard.sh live-tick
```

Chequeo de modo del día (útil para la revisión 07:50):

```bash
OUT_DIR=docs/operacion/evidencia/phase8_go_live_20260309_1040 \
PHASE8_CALENDAR_FILE=docs/operacion/evidencia/phase8_go_live_20260309_1040/phase8_work_calendar.json \
./qa/run_phase8_calendar_guard.sh day-mode
```

Modos de cierre diario por calendario híbrido:

- `daily-close-full`: ejecuta cierre solo si el día resolvió `FULL`.
- `daily-close-minimal`: ejecuta cierre solo si el día resolvió `MINIMAL`.
- `daily-close`: ejecuta en ambos (`FULL` o `MINIMAL`) para uso manual.

Cierre eventual (aunque el día resuelva `SKIP`), con evidencia obligatoria:

```bash
OUT_DIR=docs/operacion/evidencia/phase8_go_live_20260309_1040 \
PHASE8_CALENDAR_FILE=docs/operacion/evidencia/phase8_go_live_20260309_1040/phase8_work_calendar.json \
EVENTUAL_REASON_CODE=FORCE_MAINTENANCE \
EVENTUAL_APPROVED_BY=ops.supervisor \
EVENTUAL_NOTE="Cierre eventual aprobado por mantenimiento crítico del sistema." \
./qa/run_phase8_calendar_guard.sh eventual-close
```

Registro de revisión del contador (on-demand) y sign-off final:

```bash
cd backend
python3 manage.py record_phase8_accountant_review \
  --evidence-dir ../docs/operacion/evidencia/phase8_go_live_20260309_1040 \
  --date 2026-03-09 \
  --reviewer contador.principal \
  --status OBSERVED \
  --summary "Pendiente ajuste por reclasificación de gasto operativo."

python3 manage.py record_phase8_accountant_review \
  --evidence-dir ../docs/operacion/evidencia/phase8_go_live_20260309_1040 \
  --date 2026-03-22 \
  --reviewer contador.principal \
  --status FINAL_APPROVED \
  --summary "Sign-off final para cierre F8."
```

Si un día falla y debes reiniciar ventana (max_failed_days=0):

```bash
OUT_DIR=docs/operacion/evidencia/phase8_go_live_20260309_1040 \
REASON=DAILY_GATE_FAILED \
./qa/reset_phase8_window.sh
```

## F9-F12 Backend-Only

Orquestador secuencial post-F8 (sin frontend):

- Script: `qa/run_post_f8_phases.sh`
- Modos: `phase9`, `phase10`, `phase11`, `phase12`, `all`
- Evidencia: `docs/operacion/evidencia/post_f8_<timestamp>/`

Para operación avanzada de F12 usa preferentemente el runner dedicado:

- `qa/run_phase12_go_live.sh`

Ejemplo:

```bash
COMPANY_ID=5 BRANCH_ID=6 PARENT_COMPANY_ID=5 COMPANY_IDS=5 \
YEAR=2026 MONTH=3 \
./qa/run_post_f8_phases.sh all
```

## Cierre Maestro F1-F12

Runner canónico para cerrar release + seguridad + recertificación staging:

- Script: `qa/run_master_f1_f12_closure.sh`
- Modos: `precheck`, `security`, `staging`, `summary`, `all`
- Evidencia: `docs/operacion/evidencia/master_closure_<timestamp>/`

Ejemplo:

```bash
COMPANY_ID=5 BRANCH_ID=6 PARENT_COMPANY_ID=5 COMPANY_IDS=5 \
YEAR=2026 MONTH=3 \
./qa/run_master_f1_f12_closure.sh all
```
