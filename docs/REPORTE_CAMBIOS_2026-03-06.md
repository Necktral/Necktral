# Reporte de Cambios - 2026-03-06

## 1) Estado de publicación

- Rama local: `feat/sync-inv-cp2-tests-clean`
- Commits generados:
  - `0a3e792` - `chore(recovery): snapshot local seguro y continuidad fase A en backend`
  - `8a72b3c` - `chore(repo): sincronizacion total de cambios locales (backend/docs/frontend/infra)`
- Estado del árbol local: limpio (`git status` sin cambios pendientes).

## 2) Estado del push a GitHub

Intento de push realizado contra `origin`:

```bash
git push -u origin feat/sync-inv-cp2-tests-clean
```

Resultado:

- Error de autenticación HTTPS: `Invalid username or token`
- Causa: el remoto requiere token válido (PAT) o sesión autenticada de GitHub CLI.

## 3) Resumen técnico del commit principal (`8a72b3c`)

- Total: `313 files changed`
- Líneas: `171496 insertions(+), 25694 deletions(-)`

Impacto por carpetas (nivel superior):

- `login_module/`: 218 archivos (eliminación por consolidación de estructura)
- `modulos/`: 36 archivos (eliminación de raíz tras migración)
- `simulacion/`: 22 archivos (actualizaciones de soporte y docs)
- `frontend/`: 11 archivos (ajustes de UI/store/dependencias)
- `backend/`: 4 archivos (documentación/estructura asociada en este commit)
- `.github/`: 4 archivos (workflows e instrucciones)
- `qa/`: 3 archivos (documentación/flujo)
- `docker/`: 3 archivos (entrypoints/nginx)

## 4) Cambios de código y configuración por dominio

### 4.1 Infraestructura y CI/CD

- `.github/workflows/security-ci.yml`
- `.github/workflows/pm-snapshot.yml`
- `.github/workflows/ai-review.yml`
- `Makefile`
- `compose.yaml`
- `compose.prod.yaml`
- `docker/entrypoint.sh`
- `docker/entrypoint.prod.sh`
- `docker/nginx/default.conf`

Objetivo: consolidar ejecución de gates QA, endurecer flujo de seguridad y alinear contenedores al backend actual.

### 4.2 Backend (consolidación de estructura)

- Eliminación de árbol legacy completo en `login_module/**`.
- Eliminación de `modulos/**` en raíz (ya integrados bajo estructura backend vigente).
- Referencias operativas/documentales alineadas al backend activo.

### 4.3 Frontend

- `frontend/package.json`
- `frontend/package-lock.json`
- `frontend/src/stores/auth.store.ts`
- `frontend/src/stores/__tests__/auth.store.spec.ts`
- `frontend/src/pages/BootstrapWizardPage.vue`
- `frontend/src/pages/HrEmployeesPage.vue`
- `frontend/src/pages/HrPositionsPage.vue`
- `frontend/src/pages/OrgBranchesPage.vue`
- `frontend/src/pages/OrgCompaniesPage.vue`

Objetivo: alinear UI y estado de autenticación con cambios de backend/flujo operativo.

### 4.4 Seguridad y entorno

- `.env.example`
- `.env.prod.example`
- `docker/nginx/default.conf`

Objetivo: actualización de parámetros y referencias de seguridad/entorno para despliegue consistente.

## 5) Actualización documental realizada

Se normalizaron rutas y comandos en documentación para reflejar estructura y ejecución vigentes:

- Comandos actualizados de `python src/manage.py ...` a `python manage.py ...`
- Comandos Docker actualizados de `docker compose exec backend python src/manage.py ...` a `docker compose exec backend python manage.py ...`
- Referencias de `login_module/src/...` migradas a `backend/src/...` en documentación activa

Archivos destacados actualizados:

- `README.md`
- `BITACORA.md`
- `backend/README.md`
- `backend/src/README.md`
- `backend/src/BITACORA.md`
- `backend/src/apps/hr/README.md`
- `frontend/README.md`
- `frontend/src/pages/README.md`
- `qa/README.md`
- `qa/k6/README.md`
- `simulacion/README.md`
- `simulacion/dashboards/README.md`

## 6) Validación ejecutada

Pipeline completo del sistema ejecutado previamente con `make qa-ci`:

- Gate 1: static scan + ruff + mypy + frontend lint/typecheck: OK
- Gate 2: tests backend + cobertura + rbac doctor: OK
- Gate 3: verificación de cadena de auditoría: OK

Resultados reportados:

- `154 passed`
- Cobertura: `100%`

Artefactos:

- `qa/reports/pytest.xml`
- `qa/reports/coverage.txt`
- `qa/reports/mypy.txt`
- `qa/reports/ruff.txt`
- `qa/reports/audit_integrity.json`

## 7) Comandos para auditoría completa de cambios

```bash
# Resumen breve de commits
git log --oneline -n 10

# Resumen del commit principal
git show --stat 8a72b3c

# Lista completa de archivos tocados
git diff-tree --no-commit-id --name-status -r 8a72b3c

# Diff completo del commit principal
git show 8a72b3c

# Diff del commit de recuperación
git show 0a3e792
```

## 8) Paso pendiente para publicación remota

Configurar autenticación GitHub y repetir:

```bash
git push -u origin feat/sync-inv-cp2-tests-clean
```

Opciones recomendadas:

- GitHub CLI autenticado (`gh auth login`) y/o
- PAT con alcance `repo` para remoto HTTPS.
