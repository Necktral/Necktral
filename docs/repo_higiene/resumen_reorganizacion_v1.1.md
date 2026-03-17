# Matriz de Inventario Ejecutable v1.1

Fecha: 2026-03-17

## Cobertura
- Rutas auditadas: `login_module/src`, `modulos`, `frontend/src`, `qa`, `docs`, `backend`.
- Exclusiones: terceros/artefactos masivos (`node_modules`, `system_wis`, evidencias operativas, outputs de build).

## Resumen cuantitativo
- Filas inventariadas: **571**.
- `KEEP`: **571**.
- `LEGACY`: **0**.
- `DELETE`: **0**.

## Distribución por tipo
- `codigo-fuente`: **511**
- `documentacion`: **50**
- `soporte`: **10**

## Distribución por owner
- `owner.accounting`: **79**
- `owner.architecture`: **52**
- `owner.audit`: **19**
- `owner.backend`: **57**
- `owner.billing`: **33**
- `owner.frontend`: **70**
- `owner.fuel`: **20**
- `owner.hr`: **12**
- `owner.iam`: **17**
- `owner.integration`: **13**
- `owner.inventory`: **11**
- `owner.org`: **11**
- `owner.payments`: **9**
- `owner.platform`: **22**
- `owner.procurement`: **17**
- `owner.qa`: **40**
- `owner.rbac`: **18**
- `owner.sync`: **14**
- `owner.unassigned`: **57**

## Duplicados por hash
- Grupos detectados: **4**.
- Filas en reporte de duplicados: **49**.

## Checklist por lotes
- Lote A (Documentación contractual): crear/normalizar `CONTRACT_PACK_v1.1` y referencias cruzadas.
- Lote B (Canónico backend): declarar `login_module/` como raíz oficial y `backend/` como legacy local.
- Lote C (Limpieza conservadora): eliminar residuos `DELETE` confirmados del árbol legacy y caches generados.
- Lote D (Guardas): activar chequeo de higiene en QA para evitar reintroducción de residuos/duplicados.

## Archivos generados
- `docs/repo_higiene/inventario_software_v1.1.csv`
- `docs/repo_higiene/duplicados_software_v1.1.csv`
- `docs/repo_higiene/resumen_reorganizacion_v1.1.md`
