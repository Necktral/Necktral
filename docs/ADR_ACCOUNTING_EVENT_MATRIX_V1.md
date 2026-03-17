# ADR — Accounting Event Matrix v1

Version: v1.0  
Fecha: 2026-03-17  
Estado: Aprobado

## Decisión

Se congela la matriz oficial de eventos soportados por Accounting distinguiendo:

- eventos soportados por shadow/proyección,
- eventos con link operacional directo write-time.

## Matriz actual congelada

### Soportados por Accounting (`SUPPORTED_ECONOMIC_EVENTS`)

- Billing:
  - `DocumentIssued`
  - `DocumentVoided`
- Inventory:
  - `InventoryMovementPosted`
  - `InventoryAdjusted`
  - `InventoryTransferCompleted`
- Payments:
  - `CashMovementPosted`
  - `CashSessionClosed`
- Procurement:
  - `ProcurementDocumentPosted`
  - `ProcurementDocumentVoided`

### Soportados para link operacional directo (`OPERATIONAL_ACCOUNTING_EVENTS`)

- Billing:
  - `DocumentIssued`
  - `DocumentVoided`
- Inventory:
  - `InventoryMovementPosted`
  - `InventoryAdjusted`
  - `InventoryTransferCompleted`
- Procurement:
  - `ProcurementDocumentPosted`
  - `ProcurementDocumentVoided`

## Consecuencia

- Payments está soportado en el universo contable, pero no entra hoy por link operacional directo write-time.
- La frontera Payments/Accounting debe evolucionar por ADR y tests, no por cambios implícitos.
