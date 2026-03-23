# Branch Protection + Release Gate (v1.0)

Fecha: 2026-03-22  
Estado: Activo

## Objetivo

Asegurar que ningun deploy de `master` o `release/**` ocurra sin certificacion previa de QA + Security.

## Configuracion requerida en GitHub

Aplicar reglas de branch protection para:
- `master`
- `release/**`

Reglas minimas obligatorias:
- Require a pull request before merging = ON
- Require status checks to pass before merging = ON
- Required check = `Release Gate / gate`
- Require branches to be up to date before merging = ON
- Restrict who can push to matching branches = ON (solo maintainers autorizados)
- Allow force pushes = OFF
- Allow deletions = OFF
- Do not allow bypassing the above settings = ON

## Contrato de CI/CD

- `Release Gate` ejecuta QA y Security como precondicion unica de release.
- `CD Deploy (VPS)` se dispara por `workflow_run` exitoso de `Release Gate` (event `push`).
- `workflow_dispatch` en CD se mantiene solo para emergencia controlada.

## Evidencia esperada

- En PR: check visible `Release Gate / gate` en estado `success`.
- En push a rama protegida: ejecucion de `Release Gate` seguida por `CD Deploy`.
- Sin `Release Gate` exitoso: `CD Deploy` no inicia.
