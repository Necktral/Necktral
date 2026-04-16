# HANDOFF - Slice 4 Inventarios Workbench/Taskflow (2026-04-15)

Version: v1.0  
Fecha: 2026-04-15  
Tipo de cambio: `cross_domain`  
Modo de ejecucion: auto edit

## A) Diagnóstico del área

Estado inicial sobre Slice 3:

1. Inventarios ya tenia mutaciones (`receive/issue/adjust/transfer`) y `GET /balances/`.
2. Faltaba superficie minima de lectura para UX operativa (`warehouses`, `items`, `movements` corto).
3. Frontend no tenia ruta canonica `/inventarios` ni entrada de menu para este dominio.
4. La separacion de shell estaba disponible, pero sin un modulo funcional de inventarios que ejecutara `read/capture/commit`.

## B) Alcance exacto

Incluido:

1. Backend inventarios: endpoints GET aditivos `warehouses`, `items`, `movements` con permisos existentes y scoping de contexto activo.
2. Frontend: ruta privada canonica `/inventarios`, guard por `allowed_modules + ACL`, entrada de menu y pagina contenedora unica con variantes `Workbench` y `Taskflow`.
3. Flujo funcional Slice 4: `read`, `capture`, `commit` para `receive/issue` con `idempotency_key` del cliente.
4. Documentacion de arquitectura SPA y este handoff de gobernanza.

Excluido:

1. `adjust` y `transfer` en UX frontend.
2. Cambios en auth/enroll/sync publico.
3. Cambios en reporting, fuel, facturacion o dashboard.
4. Migraciones o cambios de modelo.

## C) Contratos impactados

Aditivos no-breaking en `/api/inventory/*`:

1. `GET /api/inventory/warehouses/` (permiso `inventory.balance.read`).
2. `GET /api/inventory/items/?q=&limit=` (permiso `inventory.item.read`, `limit` maximo 50).
3. `GET /api/inventory/movements/?warehouse_id=&item_id=&limit=` (permiso `inventory.balance.read`, default 20, max 50).

Sin cambios en:

1. `POST /api/inventory/movements/receive|issue|adjust/`.
2. `POST /api/inventory/transfers/`.
3. `/api/auth/bootstrap/session/`, `/device/enroll`, `/api/sync/enroll/`, `/api/sync/batch/`.

## D) Implementación realizada

Backend:

1. `apps.kernels.inventarios.views` extendido con GET method-level permissions para `warehouses` e `items`.
2. Nuevo `MovementsHistoryView` con filtro obligatorio por `warehouse_id + item_id`, orden descendente por fecha/id y limite acotado.
3. Nuevos serializers de query y salida de movimientos para validar limites y shape estable.

Frontend:

1. Servicio `inventory.service.ts` con operaciones `balances`, `warehouses`, `items`, `movements`, `receive`, `issue`.
2. Ruta canonica `/inventarios` con `requiresAuth`, `requiresContext`, `requiredPermissions=['inventory.balance.read']` y `requiredModules=['inventory']`.
3. Guard router actualizado para validar `requiredModules` desde bootstrap.
4. Menu privado actualizado con entrada Inventarios visible por interseccion `allowed_modules + ACL`.
5. `InventoryPage.vue` como contenedor unico que decide variante por `sessionBootstrap.shell_mode`:
   - `Workbench`: filtros, balance, historial tabular, captura y commit.
   - `Taskflow`: pasos guiados seleccion -> captura -> confirmacion.
6. `idempotency_key` generado en cliente para cada `commit` (`receive/issue`).

## E) Pruebas / validación

Cobertura agregada:

1. Backend inventarios (`backend/src/tests/test_inventory_kernel.py`):
   - `401` sin sesion en endpoints GET nuevos.
   - `403` sin permisos.
   - scope por sucursal en `warehouses`.
   - filtro `q` y limite en `items`.
   - historial corto con orden descendente y `limit`.
2. Frontend:
   - `router/routes.spec.ts` valida ruta canonica `/inventarios` y metas (`ACL + module gate`).
   - `features/inventory/__tests__/inventory-shell.spec.ts` valida gate `allowed_modules + ACL`, decision shell y formato de idempotency key.

Comandos de validacion ejecutados en este slice: ver seccion final de entrega tecnica (estado PASS/FAIL por comando).

## F) Riesgos remanentes y siguiente paso

Riesgos remanentes:

1. Gate operativo externo permanece: rollout funcional bloqueado hasta acta movil HTTPS 7/7 PASS.
2. `Taskflow` actual cubre recepcion/salida base; optimizaciones de UX movil avanzada quedan para slices siguientes.
3. Historial corto no reemplaza reporteria analitica (se mantiene alcance operativo rapido).

Siguiente paso recomendado:

1. Slice 5: habilitar `adjust/transfer` en UX con validaciones y confirmaciones reforzadas.
2. Preparar pruebas E2E cruzadas `desktop/mobile` para secuencias de inventario con cambio de contexto en caliente.
