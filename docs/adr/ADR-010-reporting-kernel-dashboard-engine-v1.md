# ADR-010: Reporting Kernel Enterprise + Dashboard Engine v1

- Fecha: 2026-03-23
- Estado: Aceptado
- Alcance: `apps/modulos/reports`, `apps/modulos/dashboard`, `frontend/modules/dashboard_v3`

## Contexto

El repositorio ya contaba con base funcional de reportes y dashboard v3, pero sin formalizar completamente:

1. contrato semántico enterprise por dataset (certificación/versionado/owner),
2. transición RBAC dual kernel+legacy,
3. integración explícita Quasar control-plane + Dash interaction-plane.

## Decisión

1. `apps/modulos/reports` se oficializa como **reporting kernel semántico** (no greenfield, hardening incremental).
2. `apps/modulos/dashboard` se mantiene como **dashboard engine** consumidor del kernel.
3. Se congela integración UI:
   - Quasar conserva ACL/navegación/contexto.
   - Dash se integra por embed seguro con token efímero (`/api/backend/dashboard/embed-token/`).
4. Se congela RBAC dual por 2 releases:
   - nuevo: `report.*`
   - legacy: `reports.*` / `dashboard.*`
   - ambos válidos durante transición.
5. Se congela materialización v1:
   - `Postgres + Redis staged` (live / near-real-time / snapshot), sin motor columnar en esta fase.

## Consecuencias

1. Cada `ReportDefinition` ahora expone metadatos de gobierno (dataset key, owner, scope, certificación, capacidades de exportación).
2. `ReportRun` incorpora `lineage` para trazabilidad de consumo (API/dashboard/cache-hit).
3. Se introduce capa explícita de métricas semánticas (`ReportMetricDefinition` + registry canónico en código).
4. El dashboard puede operar con permisos kernel (`report.dashboard.read`, `report.dataset.read`) sin romper contratos legacy.
5. Se agregan workspaces v1 de alto valor:
   - `executive_v1`
   - `operations_fuel_accounting_v1`

## Controles

1. Tests de contrato backend para reportes/dashboard actualizados con rutas/permissions/kernel envelope.
2. Validaciones de contrato as-code (`reports_check_contracts`) incluyen dataset_key/domain_owner/semantic_version.
3. Logging/auditoría mantiene evidencia de emisión de token embed y consumo de workspaces.
