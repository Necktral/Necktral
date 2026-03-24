# RETAIL v1 Avanzado — POS vertical robusto sobre kernels

## Summary
- Implementar `RETAIL` como vertical de negocio completo en `backend/src/apps/modulos/ventas_retail` (vertical semántico en layout transicional), no como wrapper delgado ni como mini-kernel.
- El alcance v1 queda congelado como `online-first`, `cash-first`, pero con arquitectura preparada para multi-tender, devoluciones parciales, recovery formal y evolución a sync sin refactor semántico.
- `Retail` consumirá `Billing`, `Inventory` y `Payments/Cash`; además incluye el hardening necesario en esos kernels para que el POS no dependa de huecos contractuales actuales.
- El path público canónico será `/api/backend/retail/`; `/api/retail/` se expondrá como alias legacy temporal con headers de deprecación, igual que `fuel` e `inventory`.

## Public APIs, Types and Contracts
- Nuevo vertical `apps.modulos.ventas_retail` con `health`, `bootstrap`, `catalog/search`, `tickets`, `holds`, `checkout`, `void`, `returns`, `sales` y `compensation/retry`.
- Nuevo bootstrap POS: `GET /api/backend/retail/bootstrap/` devolverá `branch_config`, `active_cash_session`, `terminals`, `fiscal_mode`, `default_series`, `default_warehouse`, `shortcuts_enabled`.
- `checkout/preview` devolverá validación estructurada: `ok`, `blocking_errors`, `warnings`, `totals`, `line_checks`, `cash_session_status`, `fiscal_requirements`.
- `checkout/commit` devolverá contrato fuerte: `ticket_id`, `sale_id`, `status`, `correlation_id`, `billing`, `payment`, `inventory`, `accounting`.
- `billing` será objeto, no scalar: `doc_id`, `number`, `status`, `fiscal_status`, `fiscal_reference`, `evidence_id`, `accounting_status`.
- `payment` será objeto: `payment_id`, `intent_status`, `cash_movement_id`, `cash_received`, `change_due`, `refund_payment_id`.
- `inventory` será objeto: `movement_ids`, `fulfillment_status`, `reversal_movement_ids`.
- `accounting` será objeto agregado: `aggregate_status`, `billing_status`, `inventory_statuses`; `Retail` no publicará journal final propio.
- Extender `InventoryTaxProfile` con `rate` decimal y exponerlo en serializers/lookups; `Retail` no inventará tasas por fuera del kernel.
- Extender `Payments/Cash` con servicios y endpoints de `capture` y `refund` para `PaymentIntent`, más eventos `PaymentCaptured` y `RefundProcessed`.
- Agregar permisos `payments.intent.capture` y `payments.intent.refund` para recovery/manual ops; POS normal seguirá entrando por `retail.*`.

## Implementation Changes
### Dominio Retail
- Modelos nuevos: `RetailBranchConfig`, `RetailTerminal`, `RetailTicket`, `RetailTicketLine`, `RetailPaymentRecord`, `RetailSale`, `RetailHold`, `RetailReturn`.
- `RetailBranchConfig` poseerá `series`, `default_warehouse_id`, `price_includes_tax`, `hold_expiry_minutes`, `print_after_issue`, `require_customer_for_fiscal`, `allow_manual_reprice`, `active`.
- `RetailTerminal` será entidad explícita por sucursal; `terminal_code` no quedará como string suelto.
- `RetailTicket` será el agregado mutable; tendrá `ticket_kind`, `status`, `payment_status`, `fulfillment_status`, `version`, `active_hold_id`, `flow_correlation_id`, `checkout_lock_token`, `last_error`, `compensation_status`, `compensation_attempts`.
- `RetailTicketLine` guardará snapshots duros: `sku_snapshot`, `name_snapshot`, `invoice_name_snapshot`, `uom_snapshot`, `tax_profile_snapshot`, `tax_rate_snapshot`, `unit_price_snapshot`, `discount_snapshot`.
- `RetailPaymentRecord` permitirá múltiples intentos desde v1, aunque el flujo operativo solo habilite un capture exitoso; esto evita rediseño al introducir split tender después.
- `RetailSale` y `RetailReturn` serán inmutables y servirán como registro de cierre/post-mortem, no como carrito editable.

### Políticas funcionales congeladas
- Serie retail por sucursal: `RTL`.
- Fuente de precio: `InventoryItem.suggested_price`; piso de venta: `InventoryItem.min_sale_price`; override solo con permiso `retail.ticket.reprice`.
- Fuente de impuesto: `InventoryTaxProfile.rate`; `EXENTO/EXONERADO` fuerzan `0.0000`.
- Política de precios v1: `price_includes_tax = false` por defecto y redondeo por línea, alineado con `Billing`.
- Política de stock v1: `allow_negative = false`; no hay reserva blanda de stock ni stock shadow en `Retail`.
- Ítems `SERVICIO` o `controls_stock = false` facturan pero no generan `post_issue/post_receive`.
- `CashSession OPEN` por sucursal será requisito duro de checkout; `Retail` no abrirá caja implícitamente.

### Servicios y orquestación
- Servicios de aplicación: `open_ticket`, `add_line`, `update_line`, `remove_line`, `hold_ticket`, `resume_hold`, `preview_checkout`, `commit_checkout`, `void_sale`, `create_return`, `retry_compensation`.
- Todos los writes usarán `select_for_update()` sobre ticket y `expected_version` en request para control optimista desde UI.
- Mutaciones críticas exigirán `idempotency_key`; checkout, void y return la requerirán siempre.
- Flujo `commit_checkout`: lock ticket, validar caja/config, crear `RetailPaymentRecord(INTENDED)`, crear `PaymentIntent`, crear `BillingDraft`, ejecutar `Inventory.post_issue` por líneas stock-controlled, emitir documento, registrar `CashMovement(INCOME)` por neto cobrado, capturar intent, cerrar ticket, crear `RetailSale`, publicar `RetailSaleCompleted`.
- Compensación formal si falla cualquier paso posterior al primer write canónico: refund/fail intent, `CashMovement(REFUND)` si ya hubo ingreso, `void_doc` si ya se emitió, `post_receive` para reversar stock, marcar excepción recuperable y publicar evento de failure.
- `void_sale` será reversa total de venta cerrada y mantendrá trazabilidad con doc original, movimientos originales y refs de refund.
- `create_return` soportará devolución parcial o total, solo sobre ventas cerradas, con validación de qty acumulada retornada, `allow_returns`, `CREDIT_NOTE`, `post_receive` y refund cash.
- Incluir command `run_retail_compensation_cycle` y endpoint `POST /api/backend/retail/sales/{sale_id}/compensate/retry/` para recovery operativo, siguiendo el precedente robusto de `Fuel`.

### Catálogo, búsqueda y filtros
- `catalog/search` filtrará `is_active`, `status=ACTIVO`, `sales_enabled`, `visible_pos`, branch habilitada y devolverá `barcode`, `uom_sale`, `allow_fraction`, `rounding_increment`, `suggested_price`, `min_sale_price`, `allow_discount`, `tax_rate`, `tax_treatment`.
- La línea tomará `invoice_name` si existe; si no, `name`.
- El POS validará `allow_fraction`, `min_qty` y `rounding_increment` antes de persistir líneas.

### Frontend
- Ruta nueva `UI_ROUTE_PATHS.retailPos = '/ventas'` y label `BUSINESS_LABELS.retail = 'Ventas'`.
- Módulo `frontend/src/modules/retail/pos/` con `RetailPosPage.vue`, `RetailCatalogPanel.vue`, `RetailTicketPanel.vue`, `RetailCheckoutDrawer.vue`, `RetailHoldDialog.vue`, `RetailReturnDialog.vue`, `RetailRecentTicketsDrawer.vue`, `RetailNumericPad.vue`, `RetailCashSessionBadge.vue`, `RetailFiscalStatusChip.vue`.
- Stores `useRetailBootstrapStore`, `useRetailCatalogStore`, `useRetailTicketStore`, `useRetailCheckoutStore`.
- UX de una sola pantalla, touch-first y keyboard-first; shortcuts `F2/F4/F6/F8/Enter/Esc/+/-/Ctrl+Backspace` centralizados en un composable con tests.
- El frontend no calculará verdad de negocio final; solo reflejará preview del backend y estado local efímero del ticket.

## Delivery Plan
- PR-01: endurecer `Payments/Cash` con capture/refund, eventos, endpoints, permisos y tests.
- PR-02: endurecer `InventoryTaxProfile` con `rate`, lookup serializers, fixtures y tests de compatibilidad.
- PR-03: crear `Retail` base con modelos, admin, migrations, config, terminales, health, bootstrap, RBAC seed, URLs canónicas y alias legacy.
- PR-04: implementar dominio de ticket/lines, versionado, catálogo search, políticas de precio/impuesto/qty, hold/resume y recent tickets.
- PR-05: implementar `checkout_preview` y `checkout_commit` con saga, outbox, auditoría y structured response.
- PR-06: implementar `void_sale`, compensation retry y management command de recovery.
- PR-07: implementar `return` parcial/total con `CREDIT_NOTE`, refund y reingreso controlado.
- PR-08: construir POS frontend completo, stores, guards de permisos, bootstrap y shortcuts.
- PR-09: hardening final con docs operativas, contract tests, smoke suite y go-live checklist retail.

## Test Plan
- Tests de dominio: totales, price floor, tax mapping, qty fractional, state transitions, hold expiry, cumulative returns.
- Tests de concurrencia: doble checkout del mismo ticket, dos cajas intentando mutar el mismo ticket, low-stock race entre tickets distintos.
- Tests de integración: cash sale feliz, idempotent replay, stock insuficiente, cash session cerrada, missing branch config, billing issue failure, inventory failure, cash movement failure, compensation retry exitosa.
- Tests de contratos: route canonical/legacy, envelope outbox retail, payloads `PaymentCaptured/RefundProcessed`, bootstrap contract, preview contract y commit response contract.
- Tests frontend: stores, shortcuts, bootstrap gating, catalog search, line edit, checkout, hold/resume, void, return y manejo de errores recuperables.
- Smoke acceptance end-to-end: abrir caja, crear ticket, buscar por SKU/barcode, cobrar cash, emitir factura, descargar stock, registrar caja, anular, devolver parcial, reintentar compensación y verificar `correlation_id` consistente en `Retail/Billing/Inventory/Payments`.

## Assumptions and Defaults
- La ubicación física queda congelada en `backend/src/apps/modulos/ventas_retail` por regla transicional vigente.
- v1 sigue siendo `cash-first`; el diseño admite múltiples `RetailPaymentRecord`, pero solo un capture exitoso por ticket estará habilitado funcionalmente.
- `RetailBranchConfig` vive en `Retail`, no en `ORG`, para no mezclar preferencias POS con perfil organizacional.
- `Billing` sigue siendo dueño absoluto de fiscalidad, numeración, impresión y contingencia.
- `Accounting` no cambia su frontera actual: `Retail` no hace posting final y `Payments` sigue fuera del direct-link write-time contable.
- Esta iniciativa no migra físicamente `fuel`, `billing`, `inventory` ni `procurement`.
