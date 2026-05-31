# Payments Kernel

Payment processing with intent-based lifecycle, cash session management, and real-time settlement tracking.

**Base Path:** `/api/payments/`

## API Endpoints

| HTTP | Endpoint | Description | Permission |
|------|----------|-------------|-----------|
| GET | `/health/` | Service health check | Public |
| GET | `/intents/` | List payment intents | IsAuthenticated |
| POST | `/intents/` | Create payment intent | IsAuthenticated |
| POST | `/intents/{payment_id}/reverse-capture/` | Reverse captured payment | IsAuthenticated |
| GET | `/cash-sessions/` | List cash sessions | IsAuthenticated |
| POST | `/cash-sessions/open/` | Open new cash session | IsAuthenticated |
| POST | `/cash-sessions/{session_id}/close/` | Close cash session | IsAuthenticated |
| POST | `/cash-sessions/{session_id}/movements/` | Record cash movement | IsAuthenticated |

### Query Parameters

**Intents Filters:**
- `status` - Filter by intent status
- `date_from` - Start date (ISO 8601)
- `date_to` - End date (ISO 8601)
- `payment_method` - Filter by payment method

**Cash Sessions Filters:**
- `branch_id` - Filter by branch
- `operator_id` - Filter by cashier
- `status` - Filter by session status

## Models

**PaymentIntent**
- Payment instruction with custody and capture states
- Fields: amount, currency, payment_method, reference, status, created_by
- States: pending, captured, reversed, failed
- Immutable after capture; reversals create new reversing entries
- Integrates with Portfolio for payment allocation tracking

**CashSession**
- Represents a cashier's responsibility period
- Fields: operator, branch, opening_balance, closing_balance, opened_at, closed_at
- States: open, closed, archived
- Reconciled with physical cash count

**CashMovement**
- Individual cash transactions within a session
- Fields: session, amount, movement_type (receipt/payment/adjustment), description, reference
- Scope: Session-level

## Integration Points

- **Portfolio:** Payment intents allocate amounts across portfolio instruments and accounts
- **Audit:** All payment operations logged with operator identity and timestamp
- **Accounting:** Cash movements create economic events for journal entries

## Key Workflows

**Payment Intent:** pending → captured → [settled/reversed]
- Reversals allowed only on captured payments
- Capture is idempotent

**Cash Session:** open → closed → archived
- Requires opening/closing balances
- Locked after closure

## Scope

Branch-level for cash sessions; company-level for payment intents.
