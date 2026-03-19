# REPORTS P0 — Baseline Técnico (2026-03-19)

## Estado validado (cierre de estabilización)
- Rama: `release/f6-f12-staging-pass-20260310`.
- Módulo activo: `backend/src/apps/modulos/reports`.
- Namespace canónico interno: `apps.modulos.reports`.
- API pública activa: `/api/backend/reports/*`.
- API legacy retirada: `/api/reports/*` (404 esperado).

## Snapshot de contratos
- Endpoints canónicos:
  - `GET /api/backend/reports/health/`
  - `GET|POST /api/backend/reports/definitions/`
  - `GET|POST /api/backend/reports/runs/`
  - `GET /api/backend/reports/runs/{run_id}/`
  - `POST /api/backend/reports/exports/`
  - `GET /api/backend/reports/exports/{export_id}/`
  - `GET /api/backend/reports/read-audit/`
  - `GET /api/backend/reports/sources/`
- Envelopes de error `REPORT_*` y contratos de export/reproducibilidad mantenidos sin breaking changes.

## Verificación operativa ejecutada
- `make qa-ci-gate1` -> PASS
- `make qa-ci-gate2` -> PASS
- `make qa-ci-gate3` -> PASS
- `manage.py reports_check_contracts` -> PASS
- `manage.py reports_verify_reproducibility` -> PASS

## Riesgos residuales
- Reorganización física grande de árbol (`apps/*` -> `apps/modulos/*`) pendiente de consolidación final en commit/publicación.
- No se mantiene compat de imports `apps.reports.*` en esta ola (hard cut interno).
