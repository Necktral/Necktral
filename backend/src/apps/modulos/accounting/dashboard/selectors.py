from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Any

from django.db.models import Count, Sum
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.modulos.accounting.models import JournalEntry
from apps.modulos.accounting.phase7 import Phase7ValidationError, resolve_period_range
from apps.modulos.accounting.reports import selectors as report_selectors

DECIMAL_ZERO = Decimal("0.00")


def resolve_period_window(*, validated: dict[str, Any], default_months: int = 6) -> tuple[date, date]:
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


def resolve_as_of(*, validated: dict[str, Any]) -> date:
    return report_selectors.resolve_as_of_payload(validated, default_as_of=timezone.localdate())


def select_cash_position_rows(*, company, branch, as_of: date) -> list[dict[str, Any]]:
    queryset = report_selectors.select_trial_balance(company=company, branch=branch, date_from=None, date_to=as_of)
    return list(queryset)


def select_reconciliation(*, company, branch, date_from: date, date_to: date) -> dict[str, Any]:
    return report_selectors.select_operational_reconciliation(
        company=company,
        branch=branch,
        date_from=date_from,
        date_to=date_to,
    )


def select_branch_performance(*, company, branch, date_from: date, date_to: date) -> list[dict[str, Any]]:
    queryset = JournalEntry.objects.filter(
        company=company,
        is_posted=True,
        entry_date__gte=date_from,
        entry_date__lte=date_to,
    )
    if branch is not None:
        queryset = queryset.filter(branch=branch)
    return list(
        queryset.values("branch_id")
        .annotate(
            entries=Count("id"),
            debit_total=Coalesce(Sum("debit_total"), DECIMAL_ZERO),
            credit_total=Coalesce(Sum("credit_total"), DECIMAL_ZERO),
        )
        .order_by("branch_id")
    )

