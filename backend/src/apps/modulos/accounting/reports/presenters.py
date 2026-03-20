from __future__ import annotations

from decimal import Decimal
from typing import Any


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value or "0"))


def present_trial_balance(rows: list[dict[str, Any]]) -> tuple[list[dict[str, str]], dict[str, str]]:
    rendered: list[dict[str, str]] = []
    total_debit = Decimal("0")
    total_credit = Decimal("0")
    for row in rows:
        debit = _to_decimal(row["debit_total"])
        credit = _to_decimal(row["credit_total"])
        total_debit += debit
        total_credit += credit
        rendered.append(
            {
                "account_code": str(row["account__code"]),
                "account_name": str(row["account__name"]),
                "account_type": str(row["account__account_type"]),
                "debit_total": str(debit),
                "credit_total": str(credit),
                "net_balance": str(debit - credit),
            }
        )
    return rendered, {"debit_total": str(total_debit), "credit_total": str(total_credit), "accounts": str(len(rendered))}


def present_general_ledger(rows: list[Any]) -> tuple[list[dict[str, Any]], dict[str, str]]:
    rendered: list[dict[str, Any]] = []
    total_debit = Decimal("0")
    total_credit = Decimal("0")
    for row in rows:
        debit = _to_decimal(row.debit_base)
        credit = _to_decimal(row.credit_base)
        total_debit += debit
        total_credit += credit
        rendered.append(
            {
                "journal_entry_id": int(row.journal_entry_id),
                "entry_date": row.journal_entry.entry_date,
                "description": row.journal_entry.description,
                "line_no": int(row.line_no),
                "account_code": row.account_code_snapshot,
                "currency": row.currency,
                "fx_rate": str(row.fx_rate),
                "amount_tx": str(row.amount_tx),
                "debit_base": str(debit),
                "credit_base": str(credit),
                "posted_at": row.journal_entry.posted_at,
            }
        )
    return rendered, {"debit_total": str(total_debit), "credit_total": str(total_credit), "lines": str(len(rendered))}


def present_pnl(report: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    totals = dict(report.get("totals") or {})
    rows = list(report.get("rows") or [])
    summary = {
        "rows": len(rows),
        "revenue": str(totals.get("revenue") or "0.00"),
        "expense": str(totals.get("expense") or "0.00"),
        "net_income": str(totals.get("net_income") or "0.00"),
    }
    return rows, summary


def present_balance_sheet(report: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    totals = dict(report.get("totals") or {})
    summary = {
        "assets": str(totals.get("assets") or "0.00"),
        "liabilities_plus_equity": str(totals.get("liabilities_plus_equity") or "0.00"),
        "as_of": str(report.get("as_of") or ""),
    }
    results = {
        "assets": dict(report.get("assets") or {}),
        "liabilities": dict(report.get("liabilities") or {}),
        "equity": dict(report.get("equity") or {}),
    }
    return results, summary


def present_operational_reconciliation(report: dict[str, Any]) -> tuple[list[dict[str, Any]], dict[str, Any], list[dict[str, Any]]]:
    summary = dict(report.get("summary") or {})
    rows = list(report.get("by_event_type") or [])
    pending = list(report.get("pending_operational_events") or [])
    summary["event_types"] = len(rows)
    summary["pending_sample_size"] = len(pending)
    return rows, summary, pending

