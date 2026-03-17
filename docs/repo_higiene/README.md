# Repo Higiene — Reorganización v1.1

Este directorio concentra la evidencia ejecutable de reorganización controlada del repositorio.

## Artefactos

- `inventario_software_v1.1.csv`: inventario por archivo con columnas `ruta,tipo,estado,accion,riesgo,justificacion,owner`.
- `duplicados_software_v1.1.csv`: duplicados por hash para detectar copias/redundancias.
- `resumen_reorganizacion_v1.1.md`: resumen cuantitativo + checklist por lotes.
- `CHECKLIST_EJECUCION_REORG_v1.1.md`: secuencia operativa de ejecución.
- `POLITICA_CANONICO_Y_LEGACY_v1.1.md`: norma única para resolver ambigüedad de rutas.

## Generación

```bash
python3 qa/repo_hygiene_inventory.py
python3 qa/repo_hygiene_guard.py
```
