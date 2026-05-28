# Supply Chain Supplier Party Link

## Control

Documento: `SUPPLY_CHAIN_SUPPLIER_PARTY_20260527.md`
Fecha: 2026-05-27
Estado: Design note para guard de blast radius
Corte: Supply Chain 6.1 - Supplier -> Party / Compras proveedor fuerte

## Decision

`PurchaseDocument` puede vincularse a `Party` mediante `supplier_party` nullable y protegida. `supplier_name`, `supplier_ref` y `external_ref` permanecen como snapshots de compatibilidad, pero la identidad fuerte del proveedor queda representada por `Party`.

Al crear un documento con `supplier_party`, el servicio de compras asegura `PartyRole.SUPPLIER` de forma transaccional e idempotente. El rol de negocio no concede permisos RBAC y no crea saldos.

## Rationale

El Master Roadmap define Party/Counterparty como base para proveedores, cartera, reportes por RUC/persona/proveedor y futuros paquetes del contador. Compras no debe seguir dependiendo solo de texto para nuevos flujos que luego alimenten CxP, costo, CEC o reportes.

## Scope

Incluido:

- FK nullable `PurchaseDocument.supplier_party`.
- Validacion de misma company.
- Payload Outbox con `supplier_party_id` en draft/post/void.
- API create/detail con `supplier_party_id`.
- Tests de compatibilidad legacy, cross-company, rol SUPPLIER, rollback e idempotencia.

Fuera de alcance:

- CxP, CxC y creditos.
- EconomicEvent y JournalDraft nuevos.
- CEC gates nuevos.
- Backfill de proveedores historicos.
- Frontend, Sync, Payments, Accounting y Billing.

## QA Gates

Este corte requiere PostgreSQL real, `makemigrations --check`, tests de compras/parties/audit chain, `migration_safety_guard`, `architecture_dependency_guard` y `pr_blast_radius_guard`.
