# Accounting Kernel

Double-entry bookkeeping with real-time journal drafting, fiscal period management, multi-entity consolidation, and FX revaluation. Integrates with Shadow Ledger for economic event processing.

**Base Path:** `/api/accounting/`

## API Endpoints

| HTTP | Endpoint | Description | Permission |
|------|----------|-------------|-----------|
| GET | `/health/` | Service health check | Public |
| GET | `/journal-drafts/` | List journal drafts | IsAuthenticated |
| POST | `/journal-drafts/approve/` | Approve pending drafts | IsAuthenticated |
| POST | `/journal-drafts/post/` | Post approved drafts to ledger | IsAuthenticated |
| GET | `/journal-entries/` | List posted journal entries | IsAuthenticated |
| POST | `/journal-entries/reverse-batch/` | Reverse multiple entries | IsAuthenticated |
| POST | `/journal-entries/{entry_id}/reverse/` | Reverse single entry | IsAuthenticated |
| GET | `/periods/` | List fiscal periods | IsAuthenticated |
| POST | `/periods/close/` | Close fiscal period | IsAuthenticated |
| GET | `/chart-of-accounts/` | Chart of accounts | IsAuthenticated |
| GET | `/reports/trial-balance/` | Trial balance report | IsAuthenticated |
| GET | `/reports/general-ledger/` | General ledger detail report | IsAuthenticated |
| GET | `/reports/pnl/` | Profit & loss statement | IsAuthenticated |
| GET | `/reports/balance-sheet/` | Balance sheet | IsAuthenticated |
| GET | `/reports/operational-reconciliation/` | Reconciliation of operational vs accounting | IsAuthenticated |
| POST | `/fx-rates/` | Upsert FX rates | IsAuthenticated |
| POST | `/revaluation/run/` | Execute FX revaluation | IsAuthenticated |
| GET | `/intercompany/transactions/` | List intercompany transactions | IsAuthenticated |
| POST | `/intercompany/transactions/` | Create intercompany transaction | IsAuthenticated |
| POST | `/intercompany/transactions/{tx_id}/confirm/` | Confirm pending transaction | IsAuthenticated |
| POST | `/intercompany/transactions/{tx_id}/reconcile/` | Reconcile matched transactions | IsAuthenticated |
| POST | `/intercompany/transactions/{tx_id}/dispute/` | Raise dispute on transaction | IsAuthenticated |
| POST | `/intercompany/transactions/{tx_id}/settle/` | Settle reconciled transaction | IsAuthenticated |
| POST | `/intercompany/transactions/{tx_id}/close/` | Close settled transaction | IsAuthenticated |
| GET | `/intercompany/dispute-reasons/` | List available dispute reasons | IsAuthenticated |
| GET | `/intercompany/disputes/` | List open disputes | IsAuthenticated |
| POST | `/intercompany/disputes/{case_id}/review/` | Review and resolve dispute | IsAuthenticated |
| POST | `/consolidation/run/` | Execute consolidation process | IsAuthenticated |
| GET | `/consolidation/runs/{run_id}/summary/` | Consolidation run summary | IsAuthenticated |
| GET | `/consolidation/reports/trial-balance/` | Consolidated trial balance | IsAuthenticated |
| GET | `/consolidation/reports/pnl/` | Consolidated P&L statement | IsAuthenticated |
| GET | `/consolidation/reports/balance-sheet/` | Consolidated balance sheet | IsAuthenticated |

## Models

**EconomicEvent**
- Base entity representing real-world business transactions
- Fields: event_type, event_date, entity_id, context_data
- Scope: Company-level

**JournalDraft**
- Pending entries awaiting approval
- Fields: debit_account, credit_account, amount, description, reference, preparer
- States: draft, submitted, approved
- Reversal-safe with audit trail

**JournalEntry**
- Posted double-entry transactions
- Fields: debit_account, credit_account, amount, period, description, reference
- Locked after posting; reversals create new entries

**FiscalPeriod**
- Calendar periods for financial reporting
- Fields: start_date, end_date, status, closed_at
- States: open, closing, closed

**ChartOfAccount**
- General ledger accounts
- Fields: account_code, name, type (asset/liability/equity/revenue/expense), is_posting_account
- Hierarchical structure

**FxRate**
- Foreign exchange rates
- Fields: currency_pair, rate_date, rate, source
- Used for revaluation calculations

**IntercompanyTransaction**
- Cross-entity transactions
- Fields: initiating_entity, receiving_entity, amount, transaction_type, status
- States: pending, confirmed, reconciled, disputed, settled, closed
- Supports dispute lifecycle

**ConsolidationRun**
- Multi-entity consolidation process
- Fields: consolidation_date, entities, eliminations_applied, status
- Generates consolidated financial statements

## Integration Points

- **Shadow Ledger:** Economic events flow through Shadow Ledger for real-time posting
- **Payments:** Payment execution triggers economic events
- **Reporting:** Reports consume consolidated journal entries and trial balances
- **Work Management:** Payroll-related events feed into accounting

## Key Workflows

**Journal Draft Workflow:** draft → submitted → approved → posted

**Fiscal Period:** open → closing (no new entries) → closed

**Intercompany Settlement:** pending → confirmed → reconciled → settled → closed
- Disputes can occur at reconciliation stage and must be resolved

**Consolidation:** Runs across multiple entities, eliminating intercompany transactions and applying FX revaluation

## Scope

Company-level access; multi-entity consolidation follows entity hierarchy.
