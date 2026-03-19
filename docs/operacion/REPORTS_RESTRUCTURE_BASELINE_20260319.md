# REPORTS Reestructura Canónica — Baseline y Rollback (2026-03-19)

## Snapshot inicial (estado roto)
- Path del módulo quedó movido junto al backend modular, pero con referencias mezcladas.
- Namespace de código inconsistentes (`apps.*`, `apps.modulos.*`, y referencias antiguas de `reports`).
- Resultado inicial: fallos de import y gates inestables.

## Estado objetivo aplicado
- Path canónico productivo: `backend/src/apps/modulos/reports`.
- `INSTALLED_APPS`: `apps.modulos.reports.apps.ReportsConfig` (`label="reports"`).
- Router canónico: `include("apps.modulos.reports.urls")` en `/api/backend/reports/*`.
- Legacy `/api/reports/*` retirado.
- Sin shim de compatibilidad `apps.reports.*` (hard cut interno).

## Checklist de rollback técnico (si se necesita reversión rápida)
1. Restaurar `INSTALLED_APPS` al snapshot previo conocido.
2. Restaurar include de router previo de reports.
3. Reponer alias `/api/reports/*` y mapping en middleware de deprecación.
4. Ejecutar `python backend/src/manage.py check` y `showmigrations`.
5. Ejecutar `make qa-ci-gate1`, `make qa-ci-gate2`, `make qa-ci-gate3`.
