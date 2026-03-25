# Runbook Reporting R8 — Gobierno, Observabilidad y Hardening

Versión: v1.0  
Fecha: 2026-03-24  
Estado: **Activo**

## Objetivo

Operar R8 de `reporting + dashboard` con gates de calidad/SLO, telemetría de adopción y deprecación legacy controlada.

## Comandos canónicos

```bash
make qa-reporting-r8-gate
python backend/manage.py export_reporting_observability_snapshot --output qa/reports/reporting_observability_snapshot.json
```

Artefactos:

- `qa/reports/reporting_r8_gate.json`
- `qa/reports/reporting_observability_snapshot.json`

## Política de enforcement

- Hasta **2026-04-07**: incumplimientos R8 se reportan como `WARN` (no bloqueante).
- Desde **2026-04-08**: incumplimientos R8 son `FAIL` (bloqueante).

Thresholds:

- `snapshot p95 <= 800ms`
- `near-realtime/cache p95 <= 1500ms`
- `error_rate < 0.5%`
- `quality_fail_runs == 0` en ventana evaluada.

## Deprecación legacy contable

Prefijo legacy:

- `/api/accounting/reports/*`

Headers esperados:

- `Deprecation: true`
- `Sunset: Mon, 22 Jun 2026 00:00:00 GMT` (o valor de setting)
- `Link: </api/reporting/catalog/>; rel="successor-version"`

Calendario:

- T0: deprecación visible.
- T+60: freeze funcional legacy.
- T+90: retiro condicionado a adopción y validación operativa.

## Triage rápido

1. Abrir `qa/reports/reporting_r8_gate.json`.
2. Revisar `failure_class`, `trigger_metric` y `breaches`.
3. Si hay `latency_regression`:
   - validar `ReportSnapshot` hit-rate,
   - revisar runs con `materialization=LIVE_EXECUTION` inesperado,
   - recalentar snapshots de datasets críticos.
4. Si hay `quality_breach`:
   - identificar `dataset_key` con `quality_status=FAIL`,
   - revisar `quality_checks_json` en `ReportRun`,
   - corregir adapter/contrato y repetir gate.
5. Si hay `app_error`:
   - revisar runs `FAILED` por `dataset_key`,
   - correlacionar con logs de backend y grants dashboard.
6. Si hay `infra_error`:
   - revisar stack de métricas/DB y reintentar generación del artefacto,
   - tratar como bloqueo de infraestructura en ventana hard-fail.

Taxonomía canónica de `failure_class`:

- `none`
- `quality_breach`
- `latency_regression`
- `app_error`
- `infra_error`

Prioridad de clasificación:

- `infra_error > app_error > latency_regression > quality_breach`

## Criterio de salida

- Gate R8 en `PASS` o `WARN` (según ventana).
- `/api/metrics/` expone bloques `reporting` y `dashboard`.
- Legacy accounting responde con headers de deprecación.

## Operación Dash Analytics (same-origin)

Contrato operativo congelado:

- Prefix público: `/analytics`
- Puerto interno Dash: `8050`
- Health endpoint: `/analytics/health`

Diagnóstico rápido si `dash_analytics` aparece `unhealthy`:

1. `docker compose ps` y revisar `STATUS` del servicio.
2. `docker compose logs --tail=200 dash_analytics`.
3. `docker inspect -f '{{json .State.Health}}' erpcrm_dash_analytics`.
4. Confirmar respuesta del health endpoint desde el contenedor:
   - `docker compose exec -T dash_analytics python -c "import urllib.request; urllib.request.urlopen('http://localhost:8050/analytics/health', timeout=2)"`
