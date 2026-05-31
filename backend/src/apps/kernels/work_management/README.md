# Work Management Kernel

Manages work shifts, employee attendance tracking, and maintenance logging for operational personnel.

**Base Path:** `/api/work-management/`

## API Endpoints

| HTTP | Endpoint | Description | Permission |
|------|----------|-------------|-----------|
| GET | `/shifts/` | List work shifts | IsAuthenticated |
| POST | `/shifts/` | Create work shift | IsAuthenticated |
| GET | `/shifts/{id}/` | Retrieve shift details | IsAuthenticated |
| PATCH | `/shifts/{id}/` | Update shift | IsAuthenticated |
| POST | `/attendance/check-in/` | Employee check-in | IsAuthenticated |
| POST | `/attendance/{id}/check-out/` | Employee check-out | IsAuthenticated |
| POST | `/attendance/manual/` | Manual attendance registration | IsAuthenticated |
| GET | `/attendance/` | List attendance records | IsAuthenticated |
| GET | `/maintenance/` | List maintenance logs | IsAuthenticated |
| POST | `/maintenance/` | Create maintenance log | IsAuthenticated |
| GET | `/maintenance/{id}/` | Retrieve maintenance log | IsAuthenticated |
| PATCH | `/maintenance/{id}/` | Update maintenance log | IsAuthenticated |
| POST | `/maintenance/{id}/submit/` | Submit maintenance log | IsAuthenticated |

### Query Parameters

**Attendance Filters:**
- `employee_id` - Filter by employee
- `date_from` - Start date (ISO 8601)
- `date_to` - End date (ISO 8601)
- `status` - Filter by status (checked_in, checked_out)
- `branch_id` - Filter by branch

## Models

**WorkShift**
- Represents scheduled work periods
- Fields: employee, branch, start_time, end_time, status
- Scope: Company-level

**Attendance**
- Tracks employee check-in/check-out events
- Fields: employee, shift, check_in_time, check_out_time, manual_flag, notes
- States: pending, completed, reviewed
- Scope: Company-level

**MaintenanceLog**
- Records maintenance tasks and inspections
- Fields: equipment, worker, log_date, description, status, submitted_at
- States: draft, submitted, reviewed
- Scope: Company-level

## Integration Points

- **Accounting:** Attendance data feeds into payroll calculations
- **Portfolio:** Shift assignments tracked for resource allocation
- **Reporting:** Maintenance logs aggregated for compliance and KPI reporting

## Scoping

All endpoints extract `company` scope from request context and filter data accordingly.
