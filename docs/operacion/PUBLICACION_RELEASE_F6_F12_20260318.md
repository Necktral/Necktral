# Publicación Release F6-F12 (GitHub)

Versión: v1.0  
Fecha: 2026-03-18  
Estado: **Publicado en rama release**

## Resumen

Se publica el estado integral de la rama `release/f6-f12-staging-pass-20260310` con:

- backend canónico en `backend/` y alias legacy transicional `login_module`;
- rutas públicas canónicas bajo `/api/backend/*` para Auth/IAM/ORG;
- perfiles de simulación dual (`AUTH_FLOW_MODE`, `SIM_PROFILE`) y suite operacional contractual `header-only`.

## Verificaciones previas ejecutadas

- `python3 qa/repo_hygiene_guard.py` → PASS
- `python3 qa/architecture_boundaries_guard.py` → PASS
- `python3 qa/simulation_contract_guard.py` → PASS
- `bash -n simulacion/precheck_loadtest_auth.sh && bash -n simulacion/run_advanced_integral.sh` → PASS
- `make qa-ci-gate1` → FAIL (mypy en `apps.reports` y tests tipados, baseline detecta deuda nueva)

## Riesgo residual conocido

- Existen errores de tipado en el módulo `apps.reports` que bloquean Gate 1 por baseline mypy.
- La publicación se realiza con ese riesgo explícito para no bloquear el corte de reorganización y contratos.

## Rollback de publicación

1. Identificar SHA de publicación en la rama release.
2. Ejecutar `git revert <sha_publicado>` en la misma rama.
3. `git push origin release/f6-f12-staging-pass-20260310`.
4. Registrar incidente y resultado del revert en la bitácora operativa.
