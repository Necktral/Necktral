# Commercial Billing Customer Party Link

## Control

Documento: `COMMERCIAL_BILLING_CUSTOMER_PARTY_20260528.md`
Fecha: 2026-05-28
Estado: Design note para guard de blast radius
Corte: Commercial 6.2 - Billing Customer -> Party / Facturacion con cliente fuerte

## Decision

`BillingDocument` puede vincularse a `Party` mediante `customer_party` nullable y protegida. `customer_name` y `customer_ref` permanecen como snapshots de compatibilidad, pero la identidad fuerte del cliente queda representada por `Party`.

Al crear un documento con `customer_party`, el servicio de facturacion asegura `PartyRole.CUSTOMER` de forma transaccional e idempotente. El rol de negocio no concede permisos RBAC y no crea saldos de cartera.

## Rationale

El Master Roadmap define Party/Counterparty como base para clientes, documentos, CxC futura, reportes por RUC/persona y paquetes del contador. Billing es el dueno del documento comercial, pero no debe poseer saldos de cartera. Antes de abrir CxC, los documentos comerciales deben poder apuntar a una identidad fuerte.

## Scope

Incluido:

- FK nullable `BillingDocument.customer_party`.
- Validacion de misma company.
- Payload Outbox Billing con `customer_party_id` en draft/issue/void y eventos fiscales relacionados.
- API create/list/detail con `customer_party_id` y display name seguro.
- Tests de compatibilidad legacy, cross-company, rol CUSTOMER, rollback, idempotencia, API y outbox.

Fuera de alcance:

- CxC, CxP y creditos.
- EconomicEvent y JournalDraft nuevos.
- Cambios nuevos en Accounting o Shadow Ledger.
- CEC gates nuevos.
- Backfill de clientes historicos.
- Fuel, POS, frontend, Sync, Payments y settlement TRANSFER.

## QA Gates

Este corte requiere PostgreSQL real, `makemigrations --check`, tests de facturacion/parties/fuel cercano/audit chain, `migration_safety_guard`, `architecture_dependency_guard` y `pr_blast_radius_guard`.
