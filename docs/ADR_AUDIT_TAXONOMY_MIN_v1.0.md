# ADR — Audit Taxonomy Min v1.0

Version: v1.0  
Fecha: 2026-03-17  
Estado: Aprobado

## Decisión

Se congela una taxonomía mínima de auditoría contractual por kernel para operaciones write críticas. La referencia viva del catálogo sigue siendo `apps.audit.contracts`, pero este ADR fija el mínimo que no puede omitirse.

## Catálogo mínimo

- IAM / AUTH:
  - `AUTH_ACCESS_DENIED`
- Billing:
  - `BILLING_DOC_CREATED`
  - `BILLING_DOC_ISSUED`
  - `BILLING_DOC_VOIDED`
- Inventory:
  - `INVENTORY_ITEM_CREATED`
  - `INVENTORY_MOVEMENT_POSTED`
- Payments & Cash:
  - `PAYMENT_INTENT_CREATED`
  - `CASH_SESSION_OPENED`
  - `CASH_MOVEMENT_POSTED`
  - `CASH_SESSION_CLOSED`
- Accounting:
  - `JournalDraftGenerated`
  - `JournalDraftApproved`
  - `JournalPosted`
- CEC:
  - apertura y resolución de excepción
  - ejecución/cierre de run con `manifest_hash` y gate result

## Metadata mínima esperada

- `request_id`
- scope efectivo: `company_id` y `branch_id` cuando aplique
- `required_permission` o `required_scope` en denegaciones
- subject/causalidad suficiente para trazabilidad contractual

## Regla de cierre

- Ningún write crítico se considera endurecido si no deja rastro auditable verificable.
- Las pruebas deben validar emisión y metadatos mínimos, no solo status HTTP.
