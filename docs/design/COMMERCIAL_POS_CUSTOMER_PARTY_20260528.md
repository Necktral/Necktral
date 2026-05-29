# Commercial POS Customer Party Link

## Control

Documento: `COMMERCIAL_POS_CUSTOMER_PARTY_20260528.md`
Fecha: 2026-05-28
Estado: Design note para guard de blast radius
Corte: Commercial 6.3B - PosTicket.customer_party -> FuelSale.customer_party

## Decision

`PosTicket` puede vincularse a `Party` mediante `customer_party` nullable y protegida. `customer_name` y `customer_ref` permanecen como snapshots legacy, pero el ticket POS conserva una identidad fuerte opcional para retry, compensacion e inspeccion operacional.

Durante checkout, POS propaga `ticket.customer_party_id` hacia Fuel `create_sale`. Fuel ya estaba preparado para persistir `FuelSale.customer_party` y propagarlo hacia Billing `create_draft`, donde se asegura `PartyRole.CUSTOMER` de forma transaccional e idempotente.

## Rationale

POS es el origen operativo del checkout retail. Pasar `customer_party_id` solo como parametro de checkout seria fragil: si el checkout falla, queda en compensacion o se reintenta, el sistema necesita recuperar la identidad del cliente desde el ticket persistido, no desde un payload transient.

Persistir `PosTicket.customer_party` conserva compatibilidad con tickets legacy sin Party y permite que retries y compensaciones usen el mismo cliente sin tocar Payments, Cash, Accounting, CEC, frontend, Sync ni settlement TRANSFER.

## Scope

Incluido:

- FK nullable `PosTicket.customer_party`.
- Validacion de misma company.
- API POS open con `customer_party_id` opcional.
- Output POS con `customer_party_id` y `customer_party_display_name` seguro.
- Propagacion POS checkout -> Fuel `create_sale(customer_party_id=...)`.
- Payload Outbox POS aditivo con `customer_party_id` en eventos existentes.
- Tests de compatibilidad legacy cercana, cross-company, checkout cash, checkout transfer, retry de compensacion y cadena Fuel -> Billing.

Fuera de alcance:

- Cambios a Payments/Cash.
- CxC, CxP y creditos.
- EconomicEvent y JournalDraft nuevos.
- Cambios nuevos en Accounting, Shadow Ledger o CEC.
- Backfill de tickets historicos.
- Frontend y Sync.
- settlement TRANSFER.
- Redisenio de eventos POS.

## QA Gates

Este corte requiere PostgreSQL real, `makemigrations --check`, tests POS/Fuel/Billing/Parties/compensacion, `migration_safety_guard`, `architecture_dependency_guard`, `pr_blast_radius_guard` y `qa-retail-pos-backend-contract-guard`.
