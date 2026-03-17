# Checklist de Ejecución — Reorganización v1.1

Versión: v1.1  
Fecha: 2026-03-17  
Estado: Ejecutable

## Lote A — Contrato y referencias

- [x] Crear `docs/CONTRACT_PACK_v1.1.md`.
- [x] Declarar precedencia `v2.0 > v1.1 > v1.0` según ámbito.
- [x] Actualizar índice en `docs/README.md`.
- [x] Actualizar referencias en `README.md`.

## Lote B — Canónico vs legacy

- [x] Congelar `login_module/` como backend canónico en contrato y runbooks.
- [x] Declarar `backend/` como legacy local no canónico.
- [x] Normalizar `.gitignore` para bloquear `backend/` en git.
- [x] Publicar política única en `docs/repo_higiene/POLITICA_CANONICO_Y_LEGACY_v1.1.md`.

## Lote C — Inventario y limpieza controlada

- [x] Generar inventario ejecutable por archivo con decisión `KEEP/LEGACY/DELETE`.
- [x] Generar reporte de duplicados por hash.
- [x] Eliminar residuos generados confirmados en `backend/` (caches/pyc/coverage/staticfiles), incluyendo remanentes previamente root-owned.
- [x] Mantener limpieza conservadora: no borrar software canónico ni artefactos no confirmados.

## Lote D — Guardas de no regresión

- [x] Crear `qa/repo_hygiene_guard.py`.
- [x] Integrar guarda en `Makefile` (`qa-repo-hygiene`).
- [x] Ejecutar guarda dentro de Gate 1 (`qa/run_qa_ci.sh`).
- [x] Exponer generación de inventario (`qa-repo-hygiene-inventory`).

## Verificación mínima post-ejecución

- [x] `python3 qa/repo_hygiene_guard.py`
- [x] `python3 qa/repo_hygiene_inventory.py`
- [x] `git status --short` revisado sin cambios fuera del alcance de reorg v1.1
