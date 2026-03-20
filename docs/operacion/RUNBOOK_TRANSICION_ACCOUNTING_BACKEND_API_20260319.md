# Runbook de Transición Contable a `/api/backend/accounting/*`

Versión: v1.0  
Fecha: 2026-03-19  
Estado: Activo (ventana de compatibilidad)

## Objetivo

Migrar consumidores de rutas legacy `/api/accounting/*` a rutas canónicas `/api/backend/accounting/*` sin ruptura.

## Rutas canónicas

- Reportes:
  - `/api/backend/accounting/reports/trial-balance/`
  - `/api/backend/accounting/reports/general-ledger/`
  - `/api/backend/accounting/reports/pnl/`
  - `/api/backend/accounting/reports/balance-sheet/`
  - `/api/backend/accounting/reports/operational-reconciliation/`
- Dashboard:
  - `/api/backend/accounting/dashboard/executive-summary/`
  - `/api/backend/accounting/dashboard/revenue-vs-expense/`
  - `/api/backend/accounting/dashboard/cash-position/`
  - `/api/backend/accounting/dashboard/reconciliation-health/`
  - `/api/backend/accounting/dashboard/branch-performance/`
  - `/api/backend/accounting/dashboard/monthly-trends/`

## Compatibilidad temporal

- Alias temporal activo: `/api/accounting/*`.
- Todo alias legacy responde headers:
  - `Deprecation: true`
  - `Sunset: Mon, 18 May 2026 00:00:00 GMT`
  - `Link: </api/backend/accounting/>; rel="successor-version"`

## Plan operativo

1. Actualizar clientes internos a prefijo `/api/backend/accounting/*`.
2. Monitorear uso de legacy por logs/proxy/API gateway.
3. Emitir reporte semanal de tráfico legacy.
4. Mantener alias hasta 2 ciclos limpios con uso legacy = 0.
5. Retirar alias en release posterior controlada.

## Rollback

- Si un consumidor crítico falla en canónico:
  1. Revertir cliente a alias legacy (`/api/accounting/*`) de forma temporal.
  2. Registrar incidente y endpoint afectado.
  3. Corregir contrato/cliente y reintentar canónico.

