# Arquitectura Reporting Kernel vs Dashboard Engine (Enterprise v1)

## Objetivo

Separar fuente de verdad analítica (`reporting_kernel`) de la experiencia interactiva (`dashboard_engine`) para evitar acoplamiento semántico/técnico y habilitar escalamiento enterprise.

## Capas backend

### Reporting kernel

- Namespace: `apps.modulos.reports`
- Rutas: `/api/backend/reports/*`
- Responsabilidad: datasets certificados, contratos reproducibles, trazabilidad, export y gobierno semántico.

### Dashboard engine

- Namespace: `apps.modulos.dashboard`
- Rutas: `/api/backend/dashboard/*`
- Responsabilidad: workspaces/widgets, interacción (cross-filter, drill-down, drill-through), consumo del kernel.
- Cache: key por `workspace + company/branch + query`.
- Integración Dash: `POST /api/backend/dashboard/embed-token/` para sesión embebida con token efímero.

### Capa HTTP

- `apps.modulos.accounting.api.views_reports`
- `apps.modulos.accounting.api.views_dashboard`
- Solo auth/permisos, parseo, invocacion de servicios y envelope.

## Contrato API (dataset envelope v2)

```json
{
  "schema_version": 1,
  "rows": [],
  "warnings": [],
  "envelope_version": 2,
  "dataset_key": "accounting.overview",
  "semantic_version": "1.0.0",
  "metadata": {
    "scope": { "company_id": 1, "branch_id": 10 },
    "freshness_mode": "near_real_time",
    "materialization_policy": "cache_first",
    "certification_status": "CERTIFIED"
  },
  "dimensions": [],
  "measures": [],
  "totals": {},
  "lineage": {},
  "render_hints": {},
  "export_capabilities": {}
}
```

## Frontend

- Quasar = control-plane (ACL, contexto, navegación).
- Dashboard v3 = superficie interactiva certificada.
- Ruta embed engine:
  - `/analitica/elite`
- ACL transición:
  - nuevo: `report.dashboard.read`
  - legacy: `dashboard.workspace.read`

## Compatibilidad legacy

- API legacy se mantiene con deprecación controlada.
- RBAC dual `report.*` + `reports.* / dashboard.*` por 2 releases antes del retiro legacy.
