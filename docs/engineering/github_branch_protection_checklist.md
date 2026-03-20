# Checklist de Branch Protection (GitHub UI)

## Objetivo
- Asegurar `master` como troncal protegida.
- Exigir calidad mínima antes de merge.

## Reglas obligatorias en `master`

1. Require a pull request before merging.
2. Require approvals: mínimo 1 review.
3. Dismiss stale approvals when new commits are pushed.
4. Require status checks to pass before merging:
   - `QA CI (Gates 1–3)`
   - `Security CI (Blocking)`
5. Require branches to be up to date before merging.
6. Restrict force pushes.
7. Restrict branch deletions.

## Reglas recomendadas para `release/*`

1. Require pull request before merging.
2. Require status checks:
   - `QA CI (Gates 1–3)`
3. Restrict force pushes.

## Gobernanza operativa

1. Labels mínimas en PR:
   - `type/*`
   - `risk/*`
   - `area/*`
2. CODEOWNERS activo para reviewers automáticos.
3. PR template obligatorio para evidencia y rollback.

## Evidencia de aplicación

- Captura de pantalla de branch protection en `master`.
- URL del rule set aplicado.
- Fecha/hora y responsable de la configuración.

