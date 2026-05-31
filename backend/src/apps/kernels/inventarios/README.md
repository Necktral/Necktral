# Inventory Kernel (Inventarios)

Stock management with warehouse organization, movement tracking, and real-time balance maintenance. Integrates movements into accounting for COGS and inventory valuation.

**Base Path:** `/api/inventory/`

## API Endpoints

| HTTP | Endpoint | Description | Permission |
|------|----------|-------------|-----------|
| GET | `/health/` | Service health check | Public |
| POST | `/warehouses/` | Create warehouse | IsAuthenticated |
| POST | `/items/` | Create inventory item | IsAuthenticated |
| POST | `/movements/receive/` | Receive stock into warehouse | IsAuthenticated |
| POST | `/movements/issue/` | Issue stock from warehouse | IsAuthenticated |
| POST | `/movements/adjust/` | Adjust stock (inventory reconciliation) | IsAuthenticated |
| POST | `/transfers/` | Transfer stock between warehouses | IsAuthenticated |
| GET | `/balances/` | Get current stock balances | IsAuthenticated |

### Query Parameters

**Balances Filters:**
- `warehouse_id` - Filter by warehouse
- `item_id` - Filter by item
- `location_id` - Filter by storage location

## Models

**Warehouse**
- Physical storage location
- Fields: name, code, branch, location_description, manager
- Scope: Branch-level

**InventoryItem**
- Product/component tracked in inventory
- Fields: sku, name, unit, category, reorder_level, cost_value
- Master data shared across warehouses

**StockMovement**
- Individual inventory transaction
- Fields: item, warehouse, movement_type (receive/issue/adjust), quantity, unit_cost, reference, created_by, movement_date
- Types: receive (increase), issue (decrease), adjust (recount correction)
- Immutable audit trail

**StockBalance**
- Current quantity on hand per item per warehouse
- Fields: item, warehouse, quantity_on_hand, quantity_available, quantity_reserved, unit_cost
- Calculated from cumulative movements
- Used for availability checks

## Integration Points

- **Accounting:** Stock movements create economic events for COGS and inventory valuation
  - Receive: Increases inventory asset account
  - Issue: Decreases inventory asset, increases COGS expense
  - Adjust: Records gain/loss on recount
- **Billing:** Item prices from billing documents reconciled against inventory valuations
- **Reporting:** Stock balances and movement reports for financial statements

## Key Workflows

**Stock Receipt:** Receiving entry → balance increases → accounting event created

**Stock Issue:** Issue entry → balance decreases → COGS event created

**Transfer:** Source warehouse balance decreases → destination balance increases (single event)

**Adjustment:** Difference between counted and recorded → gain/loss event

## Scoping

Warehouse and branch-level access control; items are shared across company.
