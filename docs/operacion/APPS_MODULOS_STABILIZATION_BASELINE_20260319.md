# Baseline — Estabilización `apps.modulos.*` (2026-03-19)

## Estado inicial detectado
- Backend movido físicamente a `backend/src/apps/modulos/*`.
- Namespace de imports/config mezclado (`apps.*` + `apps.modulos.*`) con fallo de arranque:
  - `ModuleNotFoundError: apps.common`.
- `reports` degradado a wrappers no funcionales (sin implementación real/migraciones en ruta canónica).
- `.gitignore` ocultando `backend/src/apps/modulos/**`, generando borrados masivos visibles y árbol canónico no trackeado.

## Correcciones aplicadas
- Tracking Git corregido para exponer `backend/src/apps/modulos/**`.
- Hard cut interno completado a `apps.modulos.*` en:
  - imports runtime/tests/QA,
  - `INSTALLED_APPS`,
  - `config/urls.py`,
  - referencias string críticas (auth middleware/validators).
- `reports` restaurado desde último estado estable y reconectado en `backend/src/apps/modulos/reports`.
- Guardas actualizadas para bloquear regresión de namespace legacy.

## Validación técnica mínima
- `python backend/src/manage.py check` -> PASS
- `python backend/src/manage.py showmigrations` -> PASS
- `python3 qa/repo_hygiene_guard.py` -> PASS
- `python3 qa/architecture_boundaries_guard.py` -> PASS
- `python3 qa/simulation_contract_guard.py` -> PASS
- `make qa-ci-gate1` -> PASS
- `make qa-ci-gate2` -> PASS
- `make qa-ci-gate3` -> PASS
- Smoke de ruta reports:
  - `/api/backend/reports/health/` -> 200
  - `/api/reports/health/` -> 404

## Riesgos residuales
- Existe un diff estructural grande por movimiento físico (`apps/*` -> `apps/modulos/*`) que requiere revisión cuidadosa al publicar.
- El hard cut elimina compatibilidad de imports internos legacy (`apps.<kernel>`); cualquier script externo no migrado fallará hasta actualizarse.
