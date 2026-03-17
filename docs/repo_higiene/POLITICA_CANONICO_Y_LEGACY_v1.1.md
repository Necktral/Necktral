# Política Canónico vs Legacy v1.1

Versión: v1.1  
Fecha: 2026-03-17  
Estado: Vigente

## Regla normativa única

- `login_module/` es la única raíz canónica de backend para desarrollo, QA y release.
- `backend/` es legacy local no canónico.

## Interpretación de “duplicado”

- **Duplicado dañino**: contenido operativo que compite por ser fuente de verdad y puede desviar desarrollo.
- **Legacy local**: restos locales/artefactos no versionados que no participan en CI ni release.

`backend/` en el estado actual entra en categoría **legacy local**.  
No debe usarse como fuente de código activo.

## Acciones permitidas

- `KEEP`: software/documentación canónica en rutas activas.
- `LEGACY`: ruta local conservada temporalmente por trazabilidad.
- `DELETE`: artefacto generado, cache, binario compilado o residuo verificable.
- `MOVE`: reubicación explícita cuando una ruta canónica cambia.

## Guardas obligatorias

- Bloquear rutas no canónicas en git (`backend/`, caches, builds, terceros).
- Ejecutar `qa/repo_hygiene_guard.py` en Gate 1.
- Regenerar inventario/duplicados al cerrar cada ola de reorganización.

## Trazabilidad

- Contrato vigente: `docs/CONTRACT_PACK_v1.1.md`
- Histórico base: `docs/CONTRACT_PACK_v1.0.md`
- Sync canónico: `docs/CONTRACT_PACK_v2.0.md`
