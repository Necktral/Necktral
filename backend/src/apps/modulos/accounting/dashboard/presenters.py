from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

DECIMAL_ZERO = Decimal("0.00")


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value or "0"))


def present_executive_summary(
    *,
    date_from: date,
    date_to: date,
    pnl_totals: dict[str, Any],
    balance_sheet_totals: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    summary = {
        "period": {"date_from": str(date_from), "date_to": str(date_to)},
        "revenue": str(pnl_totals.get("revenue") or "0.00"),
        "expense": str(pnl_totals.get("expense") or "0.00"),
        "net_income": str(pnl_totals.get("net_income") or "0.00"),
        "assets": str(balance_sheet_totals.get("assets") or "0.00"),
        "liabilities_plus_equity": str(balance_sheet_totals.get("liabilities_plus_equity") or "0.00"),
    }
    return summary, {
        "pnl_totals": pnl_totals,
        "balance_sheet_totals": balance_sheet_totals,
    }


def present_revenue_vs_expense(*, date_from: date, date_to: date, totals: dict[str, Any]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    rows = [
        {"metric": "revenue", "value": str(totals.get("revenue") or "0.00")},
        {"metric": "expense", "value": str(totals.get("expense") or "0.00")},
        {"metric": "net_income", "value": str(totals.get("net_income") or "0.00")},
    ]
    return {"period": {"date_from": str(date_from), "date_to": str(date_to)}}, rows


def present_cash_position(*, as_of: date, rows: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any]]:
    cash_total = DECIMAL_ZERO
    bank_total = DECIMAL_ZERO
    for row in rows:
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


def present_reconciliation_health(
    *,
    date_from: date,
    date_to: date,
    payload: dict[str, Any],
) -> tuple[dict[str, Any], dict[str, Any]]:
    summary = dict(payload.get("summary") or {})
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
        "by_event_type": list(payload.get("by_event_type") or []),
    }


def present_branch_performance(*, date_from: date, date_to: date, rows: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
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
    return {
        "period": {"date_from": str(date_from), "date_to": str(date_to)},
        "branches": len(results),
        "entries": sum(entry_counts),
    }, results


def present_monthly_trends(*, months: int, as_of: date, rows: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    return {"months": int(months), "as_of": str(as_of)}, rows

