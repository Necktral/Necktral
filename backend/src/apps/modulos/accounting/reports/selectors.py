from __future__ import annotations

from datetime import date
from typing import Any

from apps.modulos.accounting.phase7 import (
    general_ledger_queryset,
    resolve_period_range,
    trial_balance_queryset,
)
from apps.modulos.accounting.services import reconcile_operational_vs_accounting


def resolve_range_payload(validated: dict[str, Any]) -> tuple[date | None, date | None]:
    period_range = resolve_period_range(
        year=validated.get("year"),
        month=validated.get("month"),
    )
    if period_range is not None:
        return period_range[0], period_range[1]
    return validated.get("date_from"), validated.get("date_to")


def resolve_as_of_payload(validated: dict[str, Any], *, default_as_of: date) -> date:
    as_of = validated.get("as_of")
    if as_of is not None:
        return as_of
    period = resolve_period_range(year=validated.get("year"), month=validated.get("month"))
    if period is not None:
        return period[1]
    return validated.get("date_to") or default_as_of


def select_trial_balance(*, company, branch, date_from: date | None, date_to: date | None):
    return trial_balance_queryset(
        company=company,
        branch=branch,
        date_from=date_from,
        date_to=date_to,
    )


def select_general_ledger(*, company, branch, account_code: str, date_from: date | None, date_to: date | None):
    return general_ledger_queryset(
        company=company,
        branch=branch,
        account_code=account_code,
        date_from=date_from,
        date_to=date_to,
    )


def select_operational_reconciliation(*, company, branch, date_from: date | None, date_to: date | None) -> dict[str, Any]:
    return reconcile_operational_vs_accounting(
        company=company,
        branch=branch,
        date_from=date_from,
        date_to=date_to,
    )

