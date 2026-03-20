# Estrategia de Ramas (Canónica)

## Troncal
- Rama troncal protegida: `master`.
- No se permite `force-push` en `master`.
- Todo cambio entra por Pull Request.

## Ramas permitidas
- `release/*`: estabilización y publicación incremental.
- `hotfix/*`: correcciones urgentes con back-merge inmediato a `master`.
- `feat/*`: trabajo temporal de corta vida; merge por PR hacia `master` o `release/*` según ventana.

## Política de merges
- Requerido: 1+ review aprobada.
- Requerido: checks bloqueantes en verde (`qa-ci`, `security-ci`).
- Requerido: aprobaciones obsoletas se invalidan al recibir commits nuevos.
- Recomendado: squash merge para cambios funcionales; merge commit para releases.

## Compatibilidad y deprecaciones
- Rutas canónicas: `/api/backend/*`.
- Aliases legacy sólo durante ventana formal con headers `Deprecation`, `Sunset`, `Link`.
- Sunset contable actual: `2026-05-18` para `/api/accounting/*`.

## Checklist de configuración en GitHub UI
1. Branch protection en `master` con required checks (`qa-ci`, `security-ci`).
2. Required conversation resolution y required review approvals.
3. Disable force-push y delete protection activo.
4. CODEOWNERS habilitado para requerir review automática por área.
5. Auto-delete branch habilitado tras merge (opcional).

