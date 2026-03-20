from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from django.utils import timezone

from apps.modulos.accounting.phase7 import (
    balance_sheet_report,
    pnl_report,
)
from apps.modulos.common.pagination import paginate_queryset

from . import presenters, selectors


@dataclass(frozen=True)
class ReportBuildResult:
    summary: dict[str, Any]
    results: Any
    pagination: dict[str, int] | None
    legacy_payload: dict[str, Any]
    meta_extra: dict[str, Any] | None = None


def build_trial_balance(
    *,
    company,
    branch,
    validated: dict[str, Any],
    limit: int,
    offset: int,
) -> ReportBuildResult:
    date_from, date_to = selectors.resolve_range_payload(validated)
    qs = selectors.select_trial_balance(company=company, branch=branch, date_from=date_from, date_to=date_to)
    total, rows = paginate_queryset(qs, limit=limit, offset=offset)
    rendered_rows, totals = presenters.present_trial_balance(list(rows))
    filters = {
        "date_from": str(date_from) if date_from else "",
        "date_to": str(date_to) if date_to else "",
    }
    return ReportBuildResult(
        summary={"filters": filters, "totals": totals},
        results=rendered_rows,
        pagination={"count": int(total), "limit": int(limit), "offset": int(offset)},
        legacy_payload={
            "count": int(total),
            "limit": int(limit),
            "offset": int(offset),
            "filters": filters,
            "results": rendered_rows,
        },
    )


def build_general_ledger(
    *,
    company,
    branch,
    validated: dict[str, Any],
    limit: int,
    offset: int,
) -> ReportBuildResult:
    date_from, date_to = selectors.resolve_range_payload(validated)
    qs = selectors.select_general_ledger(
        company=company,
        branch=branch,
        account_code=str(validated["account_code"]),
        date_from=date_from,
        date_to=date_to,
    )
    total, rows = paginate_queryset(qs, limit=limit, offset=offset)
    rendered_rows, totals = presenters.present_general_ledger(list(rows))
    filters = {
        "account_code": str(validated["account_code"]).strip().upper(),
        "date_from": str(date_from) if date_from else "",
        "date_to": str(date_to) if date_to else "",
    }
    return ReportBuildResult(
        summary={"filters": filters, "totals": totals},
        results=rendered_rows,
        pagination={"count": int(total), "limit": int(limit), "offset": int(offset)},
        legacy_payload={
            "count": int(total),
            "limit": int(limit),
            "offset": int(offset),
            "filters": filters,
            "results": rendered_rows,
        },
    )


def build_pnl(
    *,
    company,
    branch,
    validated: dict[str, Any],
) -> ReportBuildResult:
    date_from, date_to = selectors.resolve_range_payload(validated)
    report = pnl_report(company=company, branch=branch, date_from=date_from, date_to=date_to)
    rendered_rows, summary = presenters.present_pnl(report)
    filters = {
        "date_from": str(date_from) if date_from else "",
        "date_to": str(date_to) if date_to else "",
    }
    return ReportBuildResult(
        summary={"filters": filters, **summary},
        results=rendered_rows,
        pagination={},
        legacy_payload={
            "filters": filters,
            "rows": rendered_rows,
            "totals": dict(report.get("totals") or {}),
        },
    )


def build_balance_sheet(
    *,
    company,
    branch,
    validated: dict[str, Any],
) -> ReportBuildResult:
    as_of = selectors.resolve_as_of_payload(validated, default_as_of=timezone.localdate())
    report = balance_sheet_report(company=company, branch=branch, as_of=as_of)
    rendered_results, summary = presenters.present_balance_sheet(report)
    return ReportBuildResult(
        summary=summary,
        results=rendered_results,
        pagination={},
        legacy_payload=report,
    )


def build_operational_reconciliation(
    *,
    company,
    branch,
    validated: dict[str, Any],
) -> ReportBuildResult:
    report = selectors.select_operational_reconciliation(
        company=company,
        branch=branch,
        date_from=validated.get("date_from"),
        date_to=validated.get("date_to"),
    )
    rows, summary, pending = presenters.present_operational_reconciliation(report)
    filters = {
        "date_from": str(validated.get("date_from") or ""),
        "date_to": str(validated.get("date_to") or ""),
        "branch_id": getattr(branch, "id", None),
    }
    return ReportBuildResult(
        summary={"filters": filters, **summary},
        results={"by_event_type": rows, "pending_operational_events": pending[:200]},
        pagination={},
        legacy_payload={
            "summary": dict(report.get("summary") or {}),
            "by_event_type": rows,
            "pending_operational_events": pending[:200],
            "filters": filters,
        },
    )
