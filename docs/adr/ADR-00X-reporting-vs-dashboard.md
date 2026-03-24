# ADR-00X: Separacion Reporting Formal vs Dashboard Ejecutivo

- Fecha: 2026-03-19
- Estado: Aceptado
- Alcance: `backend/src/apps/modulos/accounting/*`, `frontend/src/modules/accounting/dashboard/*`
- Nota de evolución: extendido por `ADR-010-reporting-kernel-dashboard-engine-v1.md` para alcance transversal enterprise.

## Contexto

El modulo contable crecio con una capa HTTP sobrecargada y con logica de reportes y dashboard mezclada. Eso degradaba mantenibilidad, pruebas de contrato y evolucion frontend-first.

## Decision

1. `reports` se mantiene como nucleo formal de salida contable (detalle, export y reconciliacion formal).
2. `dashboard` se fija como capa KPI separada en `apps.modulos.accounting.dashboard` con `selectors/services/presenters/cache_keys`.
3. API canonicamente bajo `/api/backend/accounting/reports/*` y `/api/backend/accounting/dashboard/*`.
4. Alias legacy `/api/accounting/*` se mantiene temporalmente con `Deprecation/Sunset/Link` (Sunset 2026-05-18).
5. El frontend ejecutivo consume solo endpoints de dashboard; no reusa payload crudo de reportes como contrato principal.

## Consecuencias

- Menor acoplamiento entre HTTP y dominio.
- Contrato v2 uniforme (`meta`, `summary`, `results`, `pagination`, `contract_version`) para endpoints canonicos.
- Facilita pruebas de contrato y cache selectivo por KPI.

## Riesgos

- Doble mantenimiento temporal por alias legacy.
- Riesgo de regresion si reaparece logica de negocio en `api/views_*`.

## Controles

- Guardas CI (`qa/accounting_http_contract_guard.py`, `qa/architecture_boundaries_guard.py`).
- Tests de contrato y paridad canonic/legacy en `backend/src/tests/test_accounting_reporting_dashboard_contract_v2.py`.
