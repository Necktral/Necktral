# REPORTS P0 — Baseline Técnico (2026-03-19)

## Estado validado
- Rama: `release/f6-f12-staging-pass-20260310`.
- Módulo activo: `backend/src/apps/reports`.
- Tests directos módulo: `backend/src/tests/test_reports_module.py` (verde en baseline).
- Hallazgo bloqueante inicial: `qa-ci-gate1` fallaba por deuda de tipado concentrada en `apps.reports` y tests tipados.

## Snapshot de interfaces (antes de continuidad)
- Ruta existente previa: `/api/reports/*`.
- Decisión de continuidad aplicada: ruta canónica nueva `/api/backend/reports/*` + alias legacy `/api/reports/*` con headers de deprecación.

## Matriz rápida R01–R10 vs estado previo
- `R01–R06`: base funcional existente (definiciones, runs, exports, read-audit, familias AUDIT/OBS/TRACE).
- `R07–R08`: parcial (paginación/índices y contract-check presentes, faltaban cierres de códigos contractuales).
- `R09`: parcial (cola async y dedupe presentes, faltaban acciones explícitas cancel/retry y comando de invalidación).
- `R10`: parcial (ledger/modelos presentes, faltaba enforcement explícito de conflicto de clasificación y violaciones reproducibles en API).

## Riesgos residuales de arranque
- Riesgo de regresión en clientes legacy mitigado con alias + `Deprecation/Sunset/Link`.
- Riesgo de divergencia contractual mitigado con check `reports_check_contracts` integrado en gates.
