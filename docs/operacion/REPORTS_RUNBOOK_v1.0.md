# Runbook Operativo — `apps.modulos.reports` v1.2

## Endpoints canónicos
- `GET /api/backend/reports/health/`
- `GET|POST /api/backend/reports/definitions/`
- `GET|POST /api/backend/reports/runs/`
- `GET /api/backend/reports/runs/{run_id}/`
- `POST /api/backend/reports/runs/{run_id}/cancel/`
- `POST /api/backend/reports/runs/{run_id}/retry/`
- `POST /api/backend/reports/exports/`
- `GET /api/backend/reports/exports/{export_id}/`
- `GET /api/backend/reports/read-audit/`
- `GET /api/backend/reports/sources/`

## Compatibilidad actual
- Alias API legacy removido: `/api/reports/*` no se expone.
- Namespace canónico interno: `apps.modulos.reports` (hard cut, sin shim `apps.reports`).

## Operación diaria
- Procesar cola de corridas:
  - `python manage.py process_report_queue --limit 20`
- Limpieza de vencidos:
  - `python manage.py reports_cleanup_expired`
- Verificación contractual:
  - `python manage.py reports_check_contracts`
- Verificación de reproducibilidad:
  - `python manage.py reports_verify_reproducibility`
- Invalidación de cache:
  - `python manage.py reports_invalidate_cache --company-id <id> --dataset-code <code> [--dataset-version v] [--source-manifest-hash h]`

## Reglas contractuales activas
- Códigos de error estables:
  - `REPORT_NOT_FOUND`
  - `REPORT_FORBIDDEN`
  - `REPORT_INVALID_SCOPE`
  - `REPORT_INVALID_PARAMS`
  - `REPORT_UNSUPPORTED_SOURCE`
  - `REPORT_EXPORT_FORBIDDEN`
  - `REPORT_DATA_CLASSIFICATION_CONFLICT`
  - `REPORT_REPRODUCIBILITY_VIOLATION`
- Policy por sensibilidad para exports:
  - `low|medium`: `json|jsonl|csv|xlsx`
  - `high`: `json|xlsx|pdf` (reason obligatorio)
  - `restricted`: `pdf` y aprobación dual obligatoria

## Troubleshooting rápido
- Si un export falla con `REPORT_DATA_CLASSIFICATION_CONFLICT`:
  - validar formato vs sensibilidad efectiva del run.
- Si un export/run detail falla con `REPORT_REPRODUCIBILITY_VIOLATION`:
  - revisar hashes `source_manifest_hash` y `output_manifest_hash`.
- Si falla `REPORT_INVALID_SCOPE`:
  - validar `X-Company-Id`/`X-Branch-Id` efectivos contra alcance del recurso.
