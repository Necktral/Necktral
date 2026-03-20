# Arquitectura Reporting vs Dashboard (Contabilidad)

## Objetivo

Separar contrato formal de reportes contables del contrato ejecutivo de dashboard para evitar acoplamiento semantico y tecnico.

## Capas backend

### Reporting formal

- Namespace: `apps.modulos.accounting.reports`
- Rutas: `/api/backend/accounting/reports/*`
- Responsabilidad: detalle formal, reconciliacion operacional formal, payload estable para export/auditoria.

### Dashboard ejecutivo

- Namespace: `apps.modulos.accounting.dashboard`
- Rutas: `/api/backend/accounting/dashboard/*`
- Responsabilidad: agregados KPI, tendencias y salud operacional para consumo UI.
- Cache KPI: key por `metric + company + branch + filtros`.

### Capa HTTP

- `apps.modulos.accounting.api.views_reports`
- `apps.modulos.accounting.api.views_dashboard`
- Solo auth/permisos, parseo, invocacion de servicios y envelope.

## Contrato API (v2 canonico)

```json
{
  "meta": {
    "contract_version": "2.0.0",
    "report_code": "TRIAL_BALANCE"
  },
  "summary": {},
  "results": [],
  "pagination": {}
}
```

## Frontend

- Modulo dashboard contable:
  - `frontend/src/modules/accounting/dashboard/pages`
  - `frontend/src/modules/accounting/dashboard/components`
  - `frontend/src/modules/accounting/dashboard/services`
  - `frontend/src/modules/accounting/dashboard/stores`
  - `frontend/src/modules/accounting/dashboard/types`
- Ruta UI:
  - `/contabilidad/tablero`
- ACL:
  - `accounting.dashboard.read`

## Compatibilidad legacy

- Alias temporal: `/api/accounting/*`
- Headers de deprecacion activos hasta `2026-05-18`.

