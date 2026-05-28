# Commercial Fuel Customer Party Link

## Control

Documento: `COMMERCIAL_FUEL_CUSTOMER_PARTY_20260528.md`
Fecha: 2026-05-28
Estado: Design note para guard de blast radius
Corte: Commercial 6.3A - FuelSale.customer_party -> Billing.customer_party

## Decision

`FuelSale` puede vincularse a `Party` mediante `customer_party` nullable y protegida. `customer_name` y `customer_ref` permanecen como snapshots de compatibilidad, pero la identidad fuerte del cliente de Fuel queda representada por `Party`.

Fuel propaga `customer_party_id` hacia `Billing.create_draft` cuando existe. Billing sigue siendo responsable de asegurar `PartyRole.CUSTOMER` de forma transaccional e idempotente durante la creacion del documento comercial.

## Rationale

El Master Roadmap define Party/Counterparty como base para clientes, documentos, CxC futura, reportes por RUC/persona y paquetes del contador. Commercial 6.2 ya fortalecio Billing con `BillingDocument.customer_party`. Fuel es el siguiente puente operativo porque crea `FuelSale` y luego emite el documento Billing asociado.

El corte se limita a Fuel para evitar abrir POS checkout, caja, pagos y compensaciones en la misma entrega. POS seguira usando snapshots textuales hasta un corte posterior que pueda propagar `customer_party_id` hacia Fuel.

## Scope

Incluido:

- FK nullable `FuelSale.customer_party`.
- Validacion de misma company.
- API Fuel create/list/detail con `customer_party_id` y display name seguro.
- Idempotencia Fuel ampliada para comparar `customer_party_id`.
- Propagacion hacia `Billing.create_draft`.
- Payload Outbox Fuel con `customer_party_id`.
- Tests de compatibilidad legacy, cross-company, rol CUSTOMER, rollback, idempotencia, API y outbox.

Fuera de alcance:

- POS customer_party.
- CxC, CxP y creditos.
- EconomicEvent y JournalDraft nuevos de Fuel.
- Cambios nuevos en Accounting o Shadow Ledger.
- CEC gates nuevos.
- Backfill de clientes historicos.
- Frontend, Sync, Payments y settlement TRANSFER.

## QA Gates

Este corte requiere PostgreSQL real, `makemigrations --check`, tests de Fuel/Billing/Parties/POS cercano/audit chain, `migration_safety_guard`, `architecture_dependency_guard` y `pr_blast_radius_guard`.
