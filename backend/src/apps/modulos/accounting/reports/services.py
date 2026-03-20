from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from typing import Any

from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.modulos.accounting.models import JournalEntry
from apps.modulos.accounting.phase7 import (
    Phase7ValidationError,
    balance_sheet_report,
    pnl_report,
    resolve_period_range,
)
from apps.modulos.common.pagination import paginate_queryset

from . import presenters, selectors


DECIMAL_ZERO = Decimal("0.00")


@dataclass(frozen=True)
class ReportBuildResult:
    summary: dict[str, Any]
    results: Any
    pagination: dict[str, int] | None
    legacy_payload: dict[str, Any]
    meta_extra: dict[str, Any] | None = None


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value or "0"))


def _resolve_period_window(
    *,
    validated: dict[str, Any],
    default_months: int = 6,
) -> tuple[date, date]:
    period = resolve_period_range(year=validated.get("year"), month=validated.get("month"))
    if period is not None:
        return period

    date_from = validated.get("date_from")
    date_to = validated.get("date_to")
    if date_from is not None and date_to is not None:
        return date_from, date_to

    today = timezone.localdate()
    if date_to is None:
        date_to = today
    if date_from is None:
        months = int(validated.get("months") or default_months)
        months = max(1, min(months, 24))
        start_month = int(date_to.month) - (months - 1)
        start_year = int(date_to.year)
        while start_month <= 0:
            start_month += 12
            start_year -= 1
        date_from = date(start_year, start_month, 1)
    if date_from > date_to:
        raise Phase7ValidationError("date_from debe ser menor o igual que date_to.")
    return date_from, date_to


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


def dashboard_executive_summary(*, company, branch, validated: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    date_from, date_to = _resolve_period_window(validated=validated, default_months=1)
    pnl_data = pnl_report(company=company, branch=branch, date_from=date_from, date_to=date_to)
    bs_data = balance_sheet_report(company=company, branch=branch, as_of=date_to)
    totals = dict(pnl_data.get("totals") or {})
    bs_totals = dict(bs_data.get("totals") or {})
    summary = {
        "period": {"date_from": str(date_from), "date_to": str(date_to)},
        "revenue": str(totals.get("revenue") or "0.00"),
        "expense": str(totals.get("expense") or "0.00"),
        "net_income": str(totals.get("net_income") or "0.00"),
        "assets": str(bs_totals.get("assets") or "0.00"),
        "liabilities_plus_equity": str(bs_totals.get("liabilities_plus_equity") or "0.00"),
    }
    return summary, {
        "pnl_totals": totals,
        "balance_sheet_totals": bs_totals,
    }


def dashboard_revenue_vs_expense(*, company, branch, validated: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    date_from, date_to = _resolve_period_window(validated=validated, default_months=1)
    data = pnl_report(company=company, branch=branch, date_from=date_from, date_to=date_to)
    totals = dict(data.get("totals") or {})
    rows = [
        {"metric": "revenue", "value": str(totals.get("revenue") or "0.00")},
        {"metric": "expense", "value": str(totals.get("expense") or "0.00")},
        {"metric": "net_income", "value": str(totals.get("net_income") or "0.00")},
    ]
    return {"period": {"date_from": str(date_from), "date_to": str(date_to)}}, rows


def dashboard_cash_position(*, company, branch, validated: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    as_of = selectors.resolve_as_of_payload(validated, default_as_of=timezone.localdate())
    tb_qs = selectors.select_trial_balance(company=company, branch=branch, date_from=None, date_to=as_of)
    cash_total = DECIMAL_ZERO
    bank_total = DECIMAL_ZERO
    for row in list(tb_qs):
        code = str(row["account__code"] or "")
        debit = _to_decimal(row["debit_total"])
        credit = _to_decimal(row["credit_total"])
        balance = debit - credit
        if code.startswith("1101"):
            cash_total += balance
        elif code.startswith("1102") or code.startswith("1103"):
            bank_total += balance
    total = cash_total + bank_total
    summary = {"as_of": str(as_of), "total_cash_position": str(total)}
    return summary, {
        "cash_on_hand": str(cash_total),
        "bank_accounts": str(bank_total),
        "total": str(total),
    }


def dashboard_reconciliation_health(*, company, branch, validated: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    date_from, date_to = _resolve_period_window(validated=validated, default_months=1)
    report = selectors.select_operational_reconciliation(company=company, branch=branch, date_from=date_from, date_to=date_to)
    summary = dict(report.get("summary") or {})
    pending = int(summary.get("pending_operational_events") or 0)
    linked = int(summary.get("economic_events_linked") or 0)
    operational = int(summary.get("operational_events") or 0)
    linkage_ratio = float(linked / operational) if operational > 0 else 1.0
    return {
        "period": {"date_from": str(date_from), "date_to": str(date_to)},
        "operational_events": operational,
        "linked_events": linked,
        "pending_events": pending,
        "linkage_ratio": round(linkage_ratio, 4),
    }, {
        "by_event_type": list(report.get("by_event_type") or []),
    }


def dashboard_branch_performance(*, company, branch, validated: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    date_from, date_to = _resolve_period_window(validated=validated, default_months=1)
    qs = JournalEntry.objects.filter(
        company=company,
        is_posted=True,
        entry_date__gte=date_from,
        entry_date__lte=date_to,
    )
    if branch is not None:
        qs = qs.filter(branch=branch)
    rows = list(
        qs.values("branch_id")
        .annotate(
            entries=Count("id"),
            debit_total=Coalesce(Sum("debit_total"), DECIMAL_ZERO),
            credit_total=Coalesce(Sum("credit_total"), DECIMAL_ZERO),
        )
        .order_by("branch_id")
    )
    entry_counts: list[int] = [int((row.get("entries") or 0)) for row in rows]
    results = [
        {
            "branch_id": int(row["branch_id"]) if row["branch_id"] is not None else None,
            "entries": entry_counts[idx],
            "debit_total": str(row["debit_total"]),
            "credit_total": str(row["credit_total"]),
        }
        for idx, row in enumerate(rows)
    ]
    total_entries = sum(entry_counts)
    return {
        "period": {"date_from": str(date_from), "date_to": str(date_to)},
        "branches": len(results),
        "entries": total_entries,
    }, results


def dashboard_monthly_trends(*, company, branch, validated: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    months = int(validated.get("months") or 6)
    months = max(1, min(months, 12))
    now = timezone.localdate()
    rows: list[dict[str, Any]] = []
    for offset in range(months - 1, -1, -1):
        year = int(now.year)
        month = int(now.month) - offset
        while month <= 0:
            month += 12
            year -= 1
        period = resolve_period_range(year=year, month=month)
        if period is None:
            continue
        start, end = period
        totals = pnl_report(company=company, branch=branch, date_from=start, date_to=end).get("totals") or {}
        rows.append(
            {
                "year": year,
                "month": month,
                "revenue": str(totals.get("revenue") or "0.00"),
                "expense": str(totals.get("expense") or "0.00"),
                "net_income": str(totals.get("net_income") or "0.00"),
            }
        )
    return {"months": months, "as_of": str(now)}, rows
