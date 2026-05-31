# Billing Kernel (Facturación)

Fiscal document issuance, contingency management, and compliance tracking. Generates tax-compliant billing documents with state transitions and audit trails.

**Base Path:** `/api/billing/`

## API Endpoints

| HTTP | Endpoint | Description | Permission |
|------|----------|-------------|-----------|
| GET | `/health/` | Service health check | Public |
| GET | `/fiscal/branch-config/` | List branch fiscal configurations | IsAuthenticated |
| POST | `/fiscal/branch-config/` | Create/update branch fiscal config | IsAuthenticated |
| GET | `/docs/` | List billing documents | IsAuthenticated |
| POST | `/docs/` | Create billing document (DRAFT) | IsAuthenticated |
| GET | `/docs/{doc_id}/` | Retrieve document detail | IsAuthenticated |
| POST | `/docs/{doc_id}/issue/` | Issue document (DRAFT → ISSUED) | IsAuthenticated |
| POST | `/docs/{doc_id}/print/` | Print document | IsAuthenticated |
| POST | `/docs/{doc_id}/contingency/` | Mark document contingency | IsAuthenticated |
| POST | `/docs/{doc_id}/contingency/resolve/` | Resolve contingency (CONTINGENCY → ISSUED) | IsAuthenticated |
| POST | `/docs/{doc_id}/void/` | Void issued document (ISSUED → VOIDED) | IsAuthenticated |

### Query Parameters

**Documents Filters:**
- `status` - Filter by document status (draft, issued, voided, contingency)
- `date_from` - Start date (ISO 8601)
- `date_to` - End date (ISO 8601)
- `branch_id` - Filter by branch
- `document_type` - Filter by type (invoice, credit_note, debit_note)

## Models

**BillingDocument**
- Tax-compliant fiscal document
- Fields: document_type, series_number, consecutive, issue_date, customer, line_items, total, status
- Tracks document sequence for fiscal compliance
- Includes customer info, itemization, and tax summary

**FiscalConfig**
- Branch-level fiscal setup
- Fields: branch, tax_id, resolution_number, series_prefix, next_consecutive, responsible_name
- Required for document issuance

## Document States

```
DRAFT
  ↓ (issue)
ISSUED ←→ CONTINGENCY (contingency) ↓ (resolve)
  ↓ (void)
VOIDED
```

- **DRAFT:** Editable, not fiscally valid
- **ISSUED:** Locked, fiscally valid, reported to tax authority
- **CONTINGENCY:** Temporary hold (e.g., connectivity issue). Can be issued via /contingency/resolve/
- **VOIDED:** Permanently canceled, generates credit note or debit note

## Integration Points

- **Accounting:** Issued documents create journal entries; voided documents trigger reversal entries
- **Portfolio:** Line items mapped to portfolio instruments for allocation tracking
- **Reporting:** Document issuance feeds into tax compliance and revenue reporting

## Scoping

Branch-level; fiscal configuration and document sequences managed per branch.
