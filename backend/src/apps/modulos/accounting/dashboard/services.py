from __future__ import annotations

from typing import Any

from django.utils import timezone

from apps.modulos.accounting.phase7 import balance_sheet_report, pnl_report, resolve_period_range

from . import presenters, selectors


def build_executive_summary(*, company, branch, validated: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    date_from, date_to = selectors.resolve_period_window(validated=validated, default_months=1)
    pnl_data = pnl_report(company=company, branch=branch, date_from=date_from, date_to=date_to)
    balance_sheet_data = balance_sheet_report(company=company, branch=branch, as_of=date_to)
    pnl_totals = dict(pnl_data.get("totals") or {})
    balance_sheet_totals = dict(balance_sheet_data.get("totals") or {})
    return presenters.present_executive_summary(
        date_from=date_from,
        date_to=date_to,
        pnl_totals=pnl_totals,
        balance_sheet_totals=balance_sheet_totals,
    )


def build_revenue_vs_expense(*, company, branch, validated: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    date_from, date_to = selectors.resolve_period_window(validated=validated, default_months=1)
    totals = dict(pnl_report(company=company, branch=branch, date_from=date_from, date_to=date_to).get("totals") or {})
    return presenters.present_revenue_vs_expense(date_from=date_from, date_to=date_to, totals=totals)


def build_cash_position(*, company, branch, validated: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    as_of = selectors.resolve_as_of(validated=validated)
    rows = selectors.select_cash_position_rows(company=company, branch=branch, as_of=as_of)
    return presenters.present_cash_position(as_of=as_of, rows=rows)


def build_reconciliation_health(*, company, branch, validated: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    date_from, date_to = selectors.resolve_period_window(validated=validated, default_months=1)
    payload = selectors.select_reconciliation(company=company, branch=branch, date_from=date_from, date_to=date_to)
    return presenters.present_reconciliation_health(date_from=date_from, date_to=date_to, payload=payload)


def build_branch_performance(*, company, branch, validated: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    date_from, date_to = selectors.resolve_period_window(validated=validated, default_months=1)
    rows = selectors.select_branch_performance(company=company, branch=branch, date_from=date_from, date_to=date_to)
    return presenters.present_branch_performance(date_from=date_from, date_to=date_to, rows=rows)


def build_monthly_trends(*, company, branch, validated: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
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
    return presenters.present_monthly_trends(months=months, as_of=now, rows=rows)

