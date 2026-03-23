# Inventario P0 Local Multisucursal (Frontend + Kernel)

Versión: v1.0  
Fecha: 2026-03-22  
Estado: Activo (fase P0 local)

## Objetivo

Operar alta/edición de ítems en entorno local multisucursal (sucursal a sucursal) con UX productiva para PC (touch + teclado), sin import/export en esta fase.

## Alcance funcional

- Rutas UI:
  - `/inventario`
  - `/inventario/items`
  - `/inventario/items/nuevo`
  - `/inventario/items/:id/editar`
  - `/inventario/almacenes`
  - `/inventario/movimientos`
  - `/inventario/balances`
  - `/inventario/kardex`
- Wizard `ItemMasterWizard` de 6 pasos con guardado final (sin borrador).
- Cola offline local (IndexedDB), flush por lote y centro visual de estado/conflictos.
- Accesibilidad operativa:
  - targets touch mínimos,
  - navegación por foco,
  - atajos (`Ctrl/Cmd+K`, `Alt+1..6`, `/`, `Ctrl+Enter`, `Esc`).

## Contratos backend aditivos

- Inventario ítems:
  - payload extendido create/patch/get/list,
  - filtros `sku_exact` y `barcode_exact`,
  - unicidad de `barcode` por empresa.
- Lookups:
  - `GET /api/inventory/lookups/uoms/`
  - `GET/POST /api/inventory/lookups/brands/`
  - `GET/POST /api/inventory/lookups/categories/`
  - `GET/POST /api/inventory/lookups/tax-profiles/`
- Compatibilidad preservada:
  - payload mínimo heredado (`sku`, `name`, `uom`, `is_active`),
  - alias `/api/inventory/*` y `/api/backend/inventory/*`.

## Reglas clave

- Si `item_type=SERVICIO`:
  - `controls_stock=false` forzado,
  - `transfer_enabled=false` forzado.
- Si `controls_stock=false`:
  - no se exige configuración de sucursal/almacén/stock,
  - se ocultan secciones de costeo y trazabilidad operacional.
- `barcode` opcional; si existe, requiere `barcode_type` y unicidad por empresa.
- Método de costo fijo en P0: `MOVING_WEIGHTED_AVG`.

## Validación operativa mínima

1. Crear ítem inventariable completo desde `/inventario/items/nuevo`.
2. Editar ítem en `/inventario/items/:id/editar` y verificar persistencia.
3. Validar errores de duplicidad SKU/barcode en campo correcto.
4. Probar flujo de cola offline (enqueue/flush/reintento) desde dashboard/movimientos.
5. Verificar que `inventarios.0003_item_master_p0` esté aplicada antes de smoke UI.

## Comandos de verificación sugeridos

- Frontend:
  - `cd frontend && npm run -s typecheck`
  - `cd frontend && npm run -s test -- src/router/routes.spec.ts`
- Backend:
  - `pytest -q backend/src/tests/test_inventory_kernel_advanced.py`
  - `cd backend && python manage.py showmigrations inventarios`

## Notas de fase

- Android queda preparado por `ports/adapters` (`DirectInventoryAdapter` activo, `SyncEngineAdapter` en stub).
- Lotes/series/vencimiento transaccional completo queda fuera de P0 (fase siguiente).
