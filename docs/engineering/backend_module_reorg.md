# Reorganizacion Backend Canonica (Estado Actual)

## Topologia vigente

- Backend Django interno: `backend/src/apps/modulos/*`
- Verticales de negocio: `kernels/*`
- API publica canonica: `/api/backend/*`
- Excepcion transicional vigente: `backend/src/apps/modulos/ventas_retail` hospeda `RETAIL` como vertical semantico.

## Ownership operativo

- `apps.modulos.accounting`: core contable (GL, cierres, intercompany, reportes formales, dashboard API).
- `apps.modulos.reports`: modulo transversal de reportes institucionales.
- `apps.modulos.ventas_retail`: vertical POS retail sobre `Billing`, `Inventory` y `Payments/Cash`.
- `kernels.facturacion|inventarios|compras|estacion_servicios`: verticales funcionales.

## Reglas duras

1. No introducir logica de negocio en capa HTTP (`api/views_*`).
2. No crear rutas nuevas fuera de `/api/backend/*` para contratos canonicos.
3. Legacy solo por compat temporal y con headers:
   - `Deprecation`
   - `Sunset`
   - `Link`
4. `RETAIL` no puede tomar ownership de numeracion fiscal, stock canónico, caja canónica ni journal final.

## Estado de transicion

- Alias contable legacy activo hasta `2026-05-18`.
- Rutas canonicas activas y testeadas:
  - `/api/backend/accounting/reports/*`
  - `/api/backend/accounting/dashboard/*`
  - `/api/backend/retail/*`

## Verificacion recomendada

1. `python3 qa/repo_hygiene_guard.py`
2. `python3 qa/architecture_boundaries_guard.py`
3. `python3 qa/accounting_http_contract_guard.py`
4. `make qa-ci-gate1 && make qa-ci-gate2 && make qa-ci-gate3`
