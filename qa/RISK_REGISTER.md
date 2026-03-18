# Registro De Riesgos (Estado Actualizado)

Actualizado: 2026-03-13T04:13:40Z

## Resumen Ejecutivo

- `R-001` npm audit frontend: `MITIGADO_TEMPORAL`
- `R-002` JWT/HMAC key corta en test: `RESUELTO`
- `R-003` UI de sincronizacion/enrolamiento faltante: `RESUELTO`
- `R-004` arbol Git sin consolidar: `RESUELTO`
- `R-005` warnings config npm legacy: `PENDIENTE`

## Matriz De Riesgos

| ID | Severidad | Estado | Evidencia | Causa raiz | Mitigacion/Fix | Validacion |
|---|---|---|---|---|---|---|
| R-001 | BLOCKER | MITIGADO_TEMPORAL | `qa/reports/npm_audit_latest.json` (`high=2`, `fixAvailable=false`) | Dependencia transitiva `serialize-javascript` via `@quasar/app-vite` sin parche upstream disponible | Excepcion temporal controlada + revision semanal + congelar lockfile | `npm audit --json` ejecutado en corrida actual |
| R-002 | MAJOR | RESUELTO | `backend/src/config/settings/test.py`, `qa/reports/auth_canary_warnings.log`, `qa/reports/sync_canary_warnings.log` | Clave de signing de test corta (<32 bytes) | `SECRET_KEY` robusta y `SIMPLE_JWT.SIGNING_KEY` explicita en settings test | Canarios auth/sync con `-W default` sin `InsecureKeyLengthWarning` |
| R-003 | MAJOR | RESUELTO | rutas/menu/paginas sync en frontend | Brecha de UI sobre APIs backend existentes | Se agregan rutas canonicas, menu RBAC, vistas de challenge/enroll/list/revoke | `frontend` test/typecheck/build + `qa-ci-ci` verde |
| R-004 | MAJOR | RESUELTO | `git status` limpio + PR `#8` abierta | Acumulacion de cambios heterogeneos en working tree | Consolidacion en commits atomicos + push + PR a rama por defecto | Cerrado en esta ejecucion |
| R-005 | MINOR | PENDIENTE | warnings npm sobre config legacy | Configuracion historica de npm | Normalizacion de config en ola de higiene de toolchain | `npm install`/CI sin warnings legacy |

## Evidencia De Corrida

- `make qa-ci-ci`: `PASSED`
- `pytest` canario auth/sync (`--ds=config.settings.test -W default`): `PASSED`
- `npm audit --json`: vulnerabilidades HIGH persisten en upstream (`R-001`)
