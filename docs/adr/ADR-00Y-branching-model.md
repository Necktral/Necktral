# ADR-00Y: Modelo de Ramas y Gobernanza GitHub

- Fecha: 2026-03-19
- Estado: Aceptado
- Troncal: `master`

## Contexto

El repositorio operaba con mezcla de ramas persistentes y sin una politica uniforme de proteccion.

## Decision

1. `master` queda como unica troncal protegida.
2. Ramas de trabajo: `release/*`, `feat/*`, `fix/*`, `hotfix/*`, `docs/*`, `chore/*`, `spike/*`.
3. Ramas `codex/*` y `copilot/*` se consideran efimeras y no permanentes.
4. Workflows principales disparan en `master` y `release/**`.
5. Plantillas y ownership obligatorios en repo:
   - `.github/CODEOWNERS`
   - `.github/PULL_REQUEST_TEMPLATE.md`
   - `.github/ISSUE_TEMPLATE/*`
6. Branch protection se aplica desde GitHub UI segun checklist versionado.

## Consecuencias

- Trazabilidad consistente por release.
- Menor riesgo de cambios directos no revisados en troncal.
- CI pasa a ser gate operativo real.

## Controles

- `docs/engineering/branching_strategy.md`
- `docs/engineering/github_branch_protection_checklist.md`

