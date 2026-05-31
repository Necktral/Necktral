# Reporting Kernel

Certified dataset catalog with execution framework, snapshots for point-in-time data capture, and saved views for dashboard persistence.

**Base Path:** `/api/reporting/`

## API Endpoints

| HTTP | Endpoint | Description | Permission |
|------|----------|-------------|-----------|
| GET | `/catalog/` | List certified dataset catalog | IsAuthenticated |
| GET | `/catalog/{dataset_key}/` | Dataset metadata and schema | IsAuthenticated |
| POST | `/datasets/{dataset_key}/run/` | Execute dataset and return results | IsAuthenticated |
| GET | `/runs/` | List dataset execution runs | IsAuthenticated |
| GET | `/runs/{run_id}/` | Run detail with execution metadata | IsAuthenticated |
| POST | `/runs/{run_id}/export/` | Export run results (CSV/Excel) | IsAuthenticated |
| GET | `/exports/{export_id}/` | Export detail and download link | IsAuthenticated |
| GET | `/snapshots/` | List data snapshots | IsAuthenticated |
| POST | `/snapshots/generate/` | Generate point-in-time snapshot | IsAuthenticated |
| GET | `/saved-views/` | List saved report views | IsAuthenticated |
| POST | `/saved-views/` | Create saved view | IsAuthenticated |
| GET | `/saved-views/{view_id}/` | Saved view detail | IsAuthenticated |

### Query Parameters

**Catalog Filters:**
- `category` - Filter by dataset category (financial, operational, compliance)
- `source_kernel` - Filter by originating kernel

**Runs Filters:**
- `dataset_key` - Filter by dataset
- `status` - Filter by run status (pending, completed, failed)
- `date_from` - Start date (ISO 8601)
- `date_to` - End date (ISO 8601)

**Saved Views Filters:**
- `creator_id` - Filter by creator
- `shared` - Filter shared vs. personal views

## Models

**DatasetCatalog**
- Certified reporting datasets
- Fields: key, name, description, source_kernel, schema, parameters, SLO
- Immutable once published
- Includes parameter schema for parameterized queries

**DatasetRun**
- Execution instance of a dataset
- Fields: dataset_key, parameters, status, started_at, completed_at, row_count, execution_ms
- States: pending, completed, failed
- Cached for re-export and reuse

**RunExport**
- Export artifact from a run
- Fields: run_id, format (csv/xlsx), file_size, generated_at, expires_at
- Includes download URL
- Configurable retention

**Snapshot**
- Point-in-time data capture for regulatory/audit purposes
- Fields: snapshot_date, datasets_included, metadata, created_by, locked
- Locked after creation; immutable archive
- Used for period-end reporting

**SavedView**
- Persisted report configuration
- Fields: name, dataset_key, filters, columns, sort_order, owner, shared_with, created_at, updated_at
- Personal or shared across team
- Can be used as dashboard tile

## Integration Points

- **Accounting:** Trial balance, general ledger, P&L, balance sheet datasets
- **Payments:** Cash movement and session datasets
- **Inventory:** Stock balance and movement history datasets
- **Billing:** Invoice and revenue recognition datasets
- **Work Management:** Attendance and shift analytics datasets

## SLO & Performance

- Dataset execution monitored for SLO compliance
- Queries optimized for <5s response for standard datasets
- Large exports queued asynchronously with email notification
- Snapshots support regulatory hold periods (retention policies)

## Scope

Company-level for standard datasets; user-level for personal saved views. Shared views enforce team-level access control.
