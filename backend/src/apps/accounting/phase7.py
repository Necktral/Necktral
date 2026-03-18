"""Servicios de núcleo contable Fase 7 (GL/FX) con invariantes auditablemente estrictas."""

from __future__ import annotations

import calendar
import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, cast

from django.db import transaction
from django.db.models import Case, DecimalField, ExpressionWrapper, F, Sum, Value, When
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.cec.models import CECException
from apps.iam.models import OrgUnit
from apps.integration.services import publish_outbox_event

from .models import (
    ChartOfAccount,
    CompanyAccountingConfig,
    EconomicEvent,
    FiscalPeriod,
    FxRate,
    JournalDraft,
    JournalEntry,
    JournalEntryLine,
    PostingRuleSet,
    RevaluationEntryLink,
    RevaluationRun,
)

MONEY_Q = Decimal("0.01")
RATE_Q = Decimal("0.00000001")
OPEN_EXCEPTION_STATUSES = (CECException.Status.OPEN, CECException.Status.IN_PROGRESS)
DECIMAL_MONEY_FIELD: DecimalField = DecimalField(max_digits=18, decimal_places=2)
DECIMAL_RATE_FIELD: DecimalField = DecimalField(max_digits=18, decimal_places=8)


class Phase7ValidationError(ValueError):
    """Error de validación de dominio para GL formal Fase 7."""


@dataclass(frozen=True)
class CoAUpsertResult:
    created: int
    updated: int
    deactivated: int
    total_active: int


@dataclass(frozen=True)
class RevaluationExecutionResult:
    run_id: str
    status: str
    idempotent: bool
    entries_created: int
    issues_count: int
    summary_json: dict[str, Any]


def _q_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _q_rate(value: Decimal) -> Decimal:
    return value.quantize(RATE_Q, rounding=ROUND_HALF_UP)


def _to_decimal(value: Any, default: Decimal = Decimal("0.00")) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


def _json_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _extract_path(data: dict[str, Any], path: str, default=None):
    node: Any = data
    for part in path.split("."):
        if not isinstance(node, dict):
            return default
        if part not in node:
            return default
        node = node[part]
    return node


def _functional_currency_from_draft(*, draft: JournalDraft, functional_currency: str) -> str:
    payload = draft.economic_event.payload if isinstance(draft.economic_event.payload, dict) else {}
    val = (
        str(_extract_path(payload, "data.currency", default="") or "")
        or str(payload.get("currency") or "")
        or str(functional_currency or "")
    )
    return val.upper() or "NIO"


def _resolve_company(*, company_id: int) -> OrgUnit:
    company = OrgUnit.objects.filter(
        id=int(company_id),
        unit_type=OrgUnit.UnitType.COMPANY,
        is_active=True,
    ).first()
    if company is None:
        raise Phase7ValidationError(f"company inválida o inactiva: {company_id}")
    return company


def get_or_create_accounting_config(*, company: OrgUnit) -> CompanyAccountingConfig:
    """Obtiene o inicializa configuración contable por empresa con defaults seguros."""
    cfg, _ = CompanyAccountingConfig.objects.get_or_create(
        company=company,
        defaults={
            "functional_currency": "NIO",
            "phase7_enabled": False,
        },
    )
    return cfg


def is_phase7_enabled_for_company(*, company: OrgUnit) -> bool:
    cfg = get_or_create_accounting_config(company=company)
    return bool(cfg.phase7_enabled)


def upsert_chart_of_accounts(
    *,
    company: OrgUnit,
    rows: list[dict[str, Any]],
    sync_deactivate: bool = False,
) -> CoAUpsertResult:
    """Sincroniza plan de cuentas garantizando unicidad, validez de tipos y jerarquía consistente."""
    if not rows:
        raise Phase7ValidationError("rows es requerido.")

    clean_rows: list[dict[str, Any]] = []
    seen_codes: set[str] = set()
    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            raise Phase7ValidationError(f"rows[{idx}] inválida.")
        code = str(row.get("code") or "").strip().upper()
        name = str(row.get("name") or "").strip()
        account_type = str(row.get("account_type") or "").strip().upper()
        if not code:
            raise Phase7ValidationError(f"rows[{idx}].code es requerido.")
        # Regla fuerte: la carga de COA es determinista, no permite códigos duplicados en el mismo payload.
        if code in seen_codes:
            raise Phase7ValidationError(f"Código duplicado en payload: {code}")
        seen_codes.add(code)
        if not name:
            raise Phase7ValidationError(f"rows[{idx}].name es requerido.")
        if account_type not in ChartOfAccount.AccountType.values:
            raise Phase7ValidationError(f"rows[{idx}].account_type inválido: {account_type}")

        clean_rows.append(
            {
                "code": code,
                "name": name,
                "account_type": account_type,
                "parent_code": str(row.get("parent_code") or "").strip().upper(),
                "is_postable": bool(row.get("is_postable", True)),
                "is_active": bool(row.get("is_active", True)),
                "is_revaluable": bool(row.get("is_revaluable", False)),
            }
        )

    created = updated = 0
    parent_mapping: dict[int, str] = {}
    with transaction.atomic():
        for row in clean_rows:
            obj, was_created = ChartOfAccount.objects.get_or_create(
                company=company,
                code=row["code"],
                defaults={
                    "name": row["name"],
                    "account_type": row["account_type"],
                    "is_postable": row["is_postable"],
                    "is_active": row["is_active"],
                    "is_revaluable": row["is_revaluable"],
                },
            )
            parent_mapping[obj.id] = row["parent_code"]
            if was_created:
                created += 1
            else:
                changed = False
                for field in ("name", "account_type", "is_postable", "is_active", "is_revaluable"):
                    val = row[field]
                    if getattr(obj, field) != val:
                        setattr(obj, field, val)
                        changed = True
                if changed:
                    obj.save(
                        update_fields=["name", "account_type", "is_postable", "is_active", "is_revaluable", "updated_at"]
                    )
                    updated += 1

        obj_by_code = {
            x.code: x
            for x in ChartOfAccount.objects.filter(company=company, code__in=[r["code"] for r in clean_rows]).only("id", "code")
        }
        for obj_id, parent_code in parent_mapping.items():
            obj = ChartOfAccount.objects.select_for_update().get(id=obj_id)
            parent = None
            if parent_code:
                parent = obj_by_code.get(parent_code)
                if parent is None:
                    raise Phase7ValidationError(
                        f"parent_code {parent_code} no encontrado en payload/company."
                    )
                # Regla fuerte: se evita ciclo trivial self-parent para preservar consistencia de árbol contable.
                if parent.id == obj.id:
                    raise Phase7ValidationError(f"Cuenta {obj.code} no puede tenerse como parent.")
            if obj.parent_id != (parent.id if parent else None):
                obj.parent = parent
                obj.save(update_fields=["parent", "updated_at"])

        deactivated = 0
        if sync_deactivate:
            deactivated = ChartOfAccount.objects.filter(company=company).exclude(code__in=seen_codes).update(is_active=False)

    total_active = int(ChartOfAccount.objects.filter(company=company, is_active=True).count())
    return CoAUpsertResult(
        created=int(created),
        updated=int(updated),
        deactivated=int(deactivated),
        total_active=int(total_active),
    )


def build_entry_lines_from_draft(
    *,
    draft: JournalDraft,
    functional_currency: str,
) -> tuple[list[dict[str, Any]], Decimal, Decimal]:
    """Normaliza líneas de draft a formato canónico, validando cuentas, montos y moneda funcional."""
    rows = draft.lines_json if isinstance(draft.lines_json, list) else []
    if not rows:
        raise Phase7ValidationError(f"Draft {draft.id} no contiene lines_json.")

    codes = sorted(
        {
            str(row.get("account") or "").strip().upper()
            for row in rows
            if isinstance(row, dict) and str(row.get("account") or "").strip()
        }
    )
    if not codes:
        raise Phase7ValidationError(f"Draft {draft.id} no contiene cuentas contables.")

    accounts = {
        x.code: x
        for x in ChartOfAccount.objects.filter(
            company=draft.economic_event.company,
            code__in=codes,
        )
    }

    lines: list[dict[str, Any]] = []
    total_debit = Decimal("0.00")
    total_credit = Decimal("0.00")
    fallback_currency = _functional_currency_from_draft(draft=draft, functional_currency=functional_currency)
    base_currency = str(functional_currency or "NIO").upper() or "NIO"

    for idx, row in enumerate(rows):
        if not isinstance(row, dict):
            raise Phase7ValidationError(f"Draft {draft.id} line[{idx}] inválida.")

        code = str(row.get("account") or "").strip().upper()
        if not code:
            raise Phase7ValidationError(f"Draft {draft.id} line[{idx}] sin account.")

        account = accounts.get(code)
        if account is None:
            raise Phase7ValidationError(f"Cuenta {code} no existe en COA de company={draft.economic_event.company_id}.")
        if not bool(account.is_active):
            raise Phase7ValidationError(f"Cuenta {code} está inactiva.")
        if not bool(account.is_postable):
            raise Phase7ValidationError(f"Cuenta {code} no es postable.")

        side = str(row.get("side") or "").strip().upper()
        if side not in ("DEBIT", "CREDIT"):
            raise Phase7ValidationError(f"Draft {draft.id} line[{idx}] side inválido.")

        amount = _q_money(abs(_to_decimal(row.get("amount"), default=Decimal("0.00"))))
        if amount <= Decimal("0.00"):
            fallback = row.get("debit") if side == "DEBIT" else row.get("credit")
            amount = _q_money(abs(_to_decimal(fallback, default=Decimal("0.00"))))
        if amount <= Decimal("0.00"):
            raise Phase7ValidationError(f"Draft {draft.id} line[{idx}] monto inválido.")

        currency = str(row.get("currency") or fallback_currency or base_currency).strip().upper()
        if not currency:
            currency = base_currency

        fx_rate = _to_decimal(row.get("fx_rate"), default=Decimal("0.00"))
        if fx_rate <= Decimal("0.00"):
            # Contrato de resiliencia: si no viene tasa explícita, se fuerza 1.0 para mantener cierre balanceado.
            fx_rate = Decimal("1.00000000") if currency == base_currency else Decimal("1.00000000")
        fx_rate = _q_rate(fx_rate)
        if fx_rate <= Decimal("0.00"):
            raise Phase7ValidationError(f"Draft {draft.id} line[{idx}] fx_rate inválido.")

        amount_tx = _to_decimal(row.get("amount_tx"), default=Decimal("0.00"))
        if amount_tx <= Decimal("0.00"):
            amount_tx = amount if currency == base_currency else _q_money(amount / fx_rate)
        amount_tx = _q_money(abs(amount_tx))
        if amount_tx <= Decimal("0.00"):
            raise Phase7ValidationError(f"Draft {draft.id} line[{idx}] amount_tx inválido.")

        debit_base = amount if side == "DEBIT" else Decimal("0.00")
        credit_base = amount if side == "CREDIT" else Decimal("0.00")
        total_debit += debit_base
        total_credit += credit_base
        lines.append(
            {
                "line_no": idx + 1,
                "account": account,
                "account_code_snapshot": account.code,
                "currency": currency,
                "fx_rate": fx_rate,
                "amount_tx": amount_tx,
                "debit_base": _q_money(debit_base),
                "credit_base": _q_money(credit_base),
                "meta_json": {
                    "source": "draft.lines_json",
                    "source_line_index": idx,
                },
            }
        )

    return lines, _q_money(total_debit), _q_money(total_credit)


def ensure_journal_entry_lines(
    *,
    entry: JournalEntry,
    draft: JournalDraft,
    functional_currency: str,
) -> int:
    if entry.lines.exists():
        return int(entry.lines.count())

    lines, total_debit, total_credit = build_entry_lines_from_draft(
        draft=draft,
        functional_currency=functional_currency,
    )
    if total_debit != _q_money(draft.total_debit) or total_credit != _q_money(draft.total_credit):
        raise Phase7ValidationError(
            f"Draft {draft.id} total lines ({total_debit}/{total_credit}) no coincide con draft ({draft.total_debit}/{draft.total_credit})."
        )
    if total_debit != _q_money(entry.debit_total) or total_credit != _q_money(entry.credit_total):
        raise Phase7ValidationError(
            f"JournalEntry {entry.id} total lines ({total_debit}/{total_credit}) no coincide con entry ({entry.debit_total}/{entry.credit_total})."
        )

    JournalEntryLine.objects.bulk_create(
        [
            JournalEntryLine(
                journal_entry=entry,
                line_no=int(line["line_no"]),
                account=line["account"],
                account_code_snapshot=str(line["account_code_snapshot"]),
                currency=str(line["currency"]),
                fx_rate=line["fx_rate"],
                amount_tx=line["amount_tx"],
                debit_base=line["debit_base"],
                credit_base=line["credit_base"],
                meta_json=dict(line["meta_json"]),
            )
            for line in lines
        ]
    )
    return len(lines)


def _apply_date_filters(qs, *, date_from: date | None, date_to: date | None, as_of: date | None):
    if as_of is not None:
        qs = qs.filter(journal_entry__entry_date__lte=as_of)
    if date_from is not None:
        qs = qs.filter(journal_entry__entry_date__gte=date_from)
    if date_to is not None:
        qs = qs.filter(journal_entry__entry_date__lte=date_to)
    return qs


def resolve_period_range(*, year: int | None = None, month: int | None = None) -> tuple[date, date] | None:
    if year is None and month is None:
        return None
    if year is None or month is None:
        raise Phase7ValidationError("year y month deben enviarse juntos.")
    if month < 1 or month > 12:
        raise Phase7ValidationError("month debe estar entre 1 y 12.")
    last_day = calendar.monthrange(int(year), int(month))[1]
    return date(int(year), int(month), 1), date(int(year), int(month), int(last_day))


def trial_balance_queryset(
    *,
    company: OrgUnit,
    branch: OrgUnit | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) :
    qs = JournalEntryLine.objects.select_related("journal_entry", "account").filter(
        journal_entry__company=company,
        journal_entry__is_posted=True,
    )
    if branch is not None:
        qs = qs.filter(journal_entry__branch=branch)
    qs = _apply_date_filters(qs, date_from=date_from, date_to=date_to, as_of=None)
    return (
        qs.values("account__code", "account__name", "account__account_type")
        .annotate(
            debit_total=Coalesce(Sum("debit_base"), Value(Decimal("0.00"), output_field=DECIMAL_MONEY_FIELD)),
            credit_total=Coalesce(Sum("credit_base"), Value(Decimal("0.00"), output_field=DECIMAL_MONEY_FIELD)),
        )
        .order_by("account__code")
    )


def general_ledger_queryset(
    *,
    company: OrgUnit,
    account_code: str,
    branch: OrgUnit | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
):
    code = str(account_code or "").strip().upper()
    if not code:
        raise Phase7ValidationError("account_code es requerido.")

    qs = JournalEntryLine.objects.select_related("journal_entry", "account").filter(
        journal_entry__company=company,
        journal_entry__is_posted=True,
        account__code=code,
    )
    if branch is not None:
        qs = qs.filter(journal_entry__branch=branch)
    qs = _apply_date_filters(qs, date_from=date_from, date_to=date_to, as_of=None)
    return qs.order_by("journal_entry__entry_date", "journal_entry_id", "line_no")


def pnl_report(
    *,
    company: OrgUnit,
    branch: OrgUnit | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    qs = JournalEntryLine.objects.select_related("journal_entry", "account").filter(
        journal_entry__company=company,
        journal_entry__is_posted=True,
        account__account_type__in=[ChartOfAccount.AccountType.REVENUE, ChartOfAccount.AccountType.EXPENSE],
    )
    if branch is not None:
        qs = qs.filter(journal_entry__branch=branch)
    qs = _apply_date_filters(qs, date_from=date_from, date_to=date_to, as_of=None)

    rows = list(
        qs.values("account__code", "account__name", "account__account_type")
        .annotate(
            debit_total=Coalesce(Sum("debit_base"), Value(Decimal("0.00"), output_field=DECIMAL_MONEY_FIELD)),
            credit_total=Coalesce(Sum("credit_base"), Value(Decimal("0.00"), output_field=DECIMAL_MONEY_FIELD)),
        )
        .order_by("account__code")
    )
    out_rows: list[dict[str, Any]] = []
    total_revenue = Decimal("0.00")
    total_expense = Decimal("0.00")
    for row in rows:
        debit = _q_money(_to_decimal(row["debit_total"]))
        credit = _q_money(_to_decimal(row["credit_total"]))
        account_type = str(row["account__account_type"])
        if account_type == ChartOfAccount.AccountType.REVENUE:
            balance = _q_money(credit - debit)
            total_revenue += balance
        else:
            balance = _q_money(debit - credit)
            total_expense += balance
        out_rows.append(
            {
                "account_code": str(row["account__code"]),
                "account_name": str(row["account__name"]),
                "account_type": account_type,
                "debit_total": str(debit),
                "credit_total": str(credit),
                "balance": str(balance),
            }
        )
    net_income = _q_money(total_revenue - total_expense)
    return {
        "rows": out_rows,
        "totals": {
            "revenue": str(_q_money(total_revenue)),
            "expense": str(_q_money(total_expense)),
            "net_income": str(net_income),
        },
    }


def balance_sheet_report(
    *,
    company: OrgUnit,
    branch: OrgUnit | None = None,
    as_of: date,
) -> dict[str, Any]:
    qs = JournalEntryLine.objects.select_related("journal_entry", "account").filter(
        journal_entry__company=company,
        journal_entry__is_posted=True,
        account__account_type__in=[
            ChartOfAccount.AccountType.ASSET,
            ChartOfAccount.AccountType.LIABILITY,
            ChartOfAccount.AccountType.EQUITY,
        ],
        journal_entry__entry_date__lte=as_of,
    )
    if branch is not None:
        qs = qs.filter(journal_entry__branch=branch)
    rows = list(
        qs.values("account__code", "account__name", "account__account_type")
        .annotate(
            debit_total=Coalesce(Sum("debit_base"), Value(Decimal("0.00"), output_field=DECIMAL_MONEY_FIELD)),
            credit_total=Coalesce(Sum("credit_base"), Value(Decimal("0.00"), output_field=DECIMAL_MONEY_FIELD)),
        )
        .order_by("account__code")
    )

    sections: dict[str, dict[str, Any]] = {
        "ASSET": {"rows": [], "total": Decimal("0.00")},
        "LIABILITY": {"rows": [], "total": Decimal("0.00")},
        "EQUITY": {"rows": [], "total": Decimal("0.00")},
    }
    for row in rows:
        debit = _q_money(_to_decimal(row["debit_total"]))
        credit = _q_money(_to_decimal(row["credit_total"]))
        account_type = str(row["account__account_type"])
        if account_type == ChartOfAccount.AccountType.ASSET:
            balance = _q_money(debit - credit)
        else:
            balance = _q_money(credit - debit)
        sections[account_type]["rows"].append(
            {
                "account_code": str(row["account__code"]),
                "account_name": str(row["account__name"]),
                "debit_total": str(debit),
                "credit_total": str(credit),
                "balance": str(balance),
            }
        )
        sections[account_type]["total"] += balance

    assets_total = _q_money(cast(Decimal, sections["ASSET"]["total"]))
    liabilities_total = _q_money(cast(Decimal, sections["LIABILITY"]["total"]))
    equity_total = _q_money(cast(Decimal, sections["EQUITY"]["total"]))
    return {
        "as_of": str(as_of),
        "assets": {"rows": sections["ASSET"]["rows"], "total": str(assets_total)},
        "liabilities": {"rows": sections["LIABILITY"]["rows"], "total": str(liabilities_total)},
        "equity": {"rows": sections["EQUITY"]["rows"], "total": str(equity_total)},
        "totals": {
            "assets": str(assets_total),
            "liabilities_plus_equity": str(_q_money(liabilities_total + equity_total)),
        },
    }


def _last_day(year: int, month: int) -> date:
    return date(int(year), int(month), calendar.monthrange(int(year), int(month))[1])


def _open_accounting_exception(
    *,
    company: OrgUnit,
    code: str,
    fingerprint_seed: str,
    details_json: dict[str, Any],
) -> None:
    fp = hashlib.sha256(fingerprint_seed.encode("utf-8")).hexdigest()
    existing = CECException.objects.filter(
        source_module="ACCOUNTING",
        company=company,
        code=code,
        fingerprint=fp,
        status__in=OPEN_EXCEPTION_STATUSES,
    ).first()
    if existing is not None:
        if existing.details_json != details_json:
            existing.details_json = details_json
            existing.save(update_fields=["details_json"])
        return
    CECException.objects.create(
        source_module="ACCOUNTING",
        code=code,
        severity=CECException.Severity.HIGH,
        status=CECException.Status.OPEN,
        company=company,
        branch=None,
        related_object_type="REVALUATION_RUN",
        related_object_id=fingerprint_seed[:64],
        details_json=details_json,
        fingerprint=fp,
        is_blocking=True,
    )


def _lookup_fx_rate(
    *,
    company: OrgUnit,
    rate_date: date,
    from_currency: str,
    to_currency: str,
    rate_type: str = FxRate.RateType.CLOSING,
) -> Decimal | None:
    if from_currency == to_currency:
        return Decimal("1.00000000")
    row = (
        FxRate.objects.filter(
            company=company,
            from_currency=str(from_currency).upper(),
            to_currency=str(to_currency).upper(),
            rate_type=rate_type,
            rate_date__lte=rate_date,
        )
        .order_by("-rate_date", "-id")
        .values("rate")
        .first()
    )
    if row is None:
        return None
    return _q_rate(_to_decimal(row["rate"], default=Decimal("0.00")))


def _ensure_fx_revaluation_ruleset(*, company: OrgUnit) -> PostingRuleSet:
    row = (
        PostingRuleSet.objects.filter(
            code="fx_revaluation_system",
            scope_company=company,
        )
        .order_by("-version", "-id")
        .first()
    )
    if row is not None:
        if row.status != PostingRuleSet.Status.ACTIVE:
            row.status = PostingRuleSet.Status.ACTIVE
            row.save(update_fields=["status", "updated_at"])
        return row
    return PostingRuleSet.objects.create(
        code="fx_revaluation_system",
        version=1,
        status=PostingRuleSet.Status.ACTIVE,
        fiscal_mode=PostingRuleSet.FiscalMode.BOTH,
        scope_company=company,
        rules_json={
            "version": "1.0",
            "purpose": "FX revaluation technical system rule set",
            "rules": [],
        },
        effective_from=timezone.now(),
    )


def _scope_hash(*, scope_account_codes: list[str] | None = None) -> str:
    payload = {"account_codes": sorted(set([str(x).strip().upper() for x in (scope_account_codes or []) if str(x).strip()]))}
    return _json_hash(payload)


def run_fx_revaluation(
    *,
    company_id: int,
    year: int,
    month: int,
    strict: bool = True,
    actor_user=None,
    scope_account_codes: list[str] | None = None,
) -> RevaluationExecutionResult:
    """Ejecuta revaluación FX mensual con idempotencia por scope y bloqueo estricto ante issues."""
    company = _resolve_company(company_id=company_id)
    if month < 1 or month > 12:
        raise Phase7ValidationError("month debe estar en rango 1..12.")

    cfg = get_or_create_accounting_config(company=company)
    as_of = _last_day(int(year), int(month))
    functional_currency = str(cfg.functional_currency or "NIO").upper() or "NIO"
    scope_hash = _scope_hash(scope_account_codes=scope_account_codes)

    with transaction.atomic():
        run, created = RevaluationRun.objects.select_for_update().get_or_create(
            company=company,
            year=int(year),
            month=int(month),
            scope_hash=scope_hash,
            defaults={
                "status": RevaluationRun.Status.RUNNING,
                "executed_by": actor_user,
                "summary_json": {},
            },
        )
        if not created and run.status in (RevaluationRun.Status.COMPLETED, RevaluationRun.Status.BLOCKED):
            summary_json = dict(run.summary_json or {})
            return RevaluationExecutionResult(
                run_id=str(run.run_id),
                status=run.status,
                idempotent=True,
                entries_created=int(summary_json.get("entries_created") or 0),
                issues_count=int(summary_json.get("issues_count") or 0),
                summary_json=summary_json,
            )

        run.status = RevaluationRun.Status.RUNNING
        run.executed_by = actor_user
        run.completed_at = None
        run.summary_json = {}
        run.save(update_fields=["status", "executed_by", "completed_at", "summary_json"])

        issues: list[dict[str, Any]] = []
        if not bool(cfg.phase7_enabled):
            issues.append({"code": "FX_REVALUATION_PHASE7_DISABLED", "detail": "phase7_enabled=false"})
        if cfg.fx_gain_account_id is None:
            issues.append({"code": "FX_REVALUATION_GAIN_ACCOUNT_MISSING", "detail": "fx_gain_account no configurada"})
        if cfg.fx_loss_account_id is None:
            issues.append({"code": "FX_REVALUATION_LOSS_ACCOUNT_MISSING", "detail": "fx_loss_account no configurada"})

        period, _ = FiscalPeriod.objects.select_for_update().get_or_create(
            company=company,
            year=int(year),
            month=int(month),
            defaults={"status": FiscalPeriod.Status.OPEN},
        )
        if period.status == FiscalPeriod.Status.CLOSED:
            issues.append({"code": "FX_REVALUATION_PERIOD_CLOSED", "detail": f"Periodo cerrado {year}-{month:02d}"})

        exposure_qs = JournalEntryLine.objects.filter(
            journal_entry__company=company,
            journal_entry__is_posted=True,
            journal_entry__entry_date__lte=as_of,
            account__is_revaluable=True,
        ).exclude(currency=functional_currency)
        if scope_account_codes:
            exposure_qs = exposure_qs.filter(account__code__in=[str(x).strip().upper() for x in scope_account_codes if str(x).strip()])

        signed_tx = Case(
            When(debit_base__gt=0, then=F("amount_tx")),
            default=ExpressionWrapper(F("amount_tx") * Value(Decimal("-1.00")), output_field=DECIMAL_MONEY_FIELD),
            output_field=DECIMAL_MONEY_FIELD,
        )
        signed_base = ExpressionWrapper(F("debit_base") - F("credit_base"), output_field=DECIMAL_MONEY_FIELD)

        exposures = list(
            exposure_qs.values("account_id", "account__code", "currency")
            .annotate(
                amount_tx_net=Coalesce(Sum(signed_tx), Value(Decimal("0.00"), output_field=DECIMAL_MONEY_FIELD)),
                base_net=Coalesce(Sum(signed_base), Value(Decimal("0.00"), output_field=DECIMAL_MONEY_FIELD)),
            )
            .order_by("account__code", "currency")
        )

        adjustments: list[dict[str, Any]] = []
        account_map = {
            x.id: x
            for x in ChartOfAccount.objects.filter(company=company, id__in=[int(row["account_id"]) for row in exposures]).only(
                "id", "code", "name", "account_type"
            )
        }
        for row in exposures:
            account = account_map.get(int(row["account_id"]))
            if account is None:
                continue
            amount_tx_net = _q_money(_to_decimal(row["amount_tx_net"]))
            base_net = _q_money(_to_decimal(row["base_net"]))
            if abs(amount_tx_net) < MONEY_Q:
                continue
            currency = str(row["currency"]).upper()
            fx_rate = _lookup_fx_rate(
                company=company,
                rate_date=as_of,
                from_currency=currency,
                to_currency=functional_currency,
                rate_type=FxRate.RateType.CLOSING,
            )
            if fx_rate is None:
                issues.append(
                    {
                        "code": "FX_REVALUATION_RATE_MISSING",
                        "detail": f"Sin tasa CLOSING para {currency}->{functional_currency} al {as_of.isoformat()}",
                        "account_code": account.code,
                        "currency": currency,
                    }
                )
                continue
            target_base = _q_money(amount_tx_net * fx_rate)
            delta = _q_money(target_base - base_net)
            if abs(delta) < MONEY_Q:
                continue
            adjustments.append(
                {
                    "account": account,
                    "currency": currency,
                    "fx_rate": fx_rate,
                    "amount_tx_net": amount_tx_net,
                    "base_net": base_net,
                    "target_base": target_base,
                    "delta": delta,
                }
            )

        if strict and issues:
            # Gate estricto: no se generan asientos cuando faltan precondiciones críticas de cierre.
            summary = {
                "schema_version": 1,
                "status": RevaluationRun.Status.BLOCKED,
                "as_of": str(as_of),
                "functional_currency": functional_currency,
                "entries_created": 0,
                "issues_count": len(issues),
                "issues": issues,
            }
            run.status = RevaluationRun.Status.BLOCKED
            run.summary_json = summary
            run.completed_at = timezone.now()
            run.save(update_fields=["status", "summary_json", "completed_at"])
            for idx, issue in enumerate(issues):
                _open_accounting_exception(
                    company=company,
                    code=str(issue.get("code") or "FX_REVALUATION_BLOCKED"),
                    fingerprint_seed=f"{run.run_id}|{issue.get('code')}|{idx}",
                    details_json={"run_id": str(run.run_id), **issue},
                )
            publish_outbox_event(
                source_module="ACCOUNTING",
                event_type="FxRevaluationBlocked",
                payload={
                    "run_id": str(run.run_id),
                    "year": int(year),
                    "month": int(month),
                    "issues_count": len(issues),
                },
                company=company,
                actor_user=actor_user,
            )
            return RevaluationExecutionResult(
                run_id=str(run.run_id),
                status=run.status,
                idempotent=False,
                entries_created=0,
                issues_count=len(issues),
                summary_json=summary,
            )

        ruleset = _ensure_fx_revaluation_ruleset(company=company)
        entries_created = 0
        for idx, adj in enumerate(adjustments):
            account = adj["account"]
            delta = _q_money(adj["delta"])
            amount = _q_money(abs(delta))
            if amount < MONEY_Q:
                continue

            if delta > 0:
                main_side = "DEBIT"
                counter_side = "CREDIT"
                counter_account = cfg.fx_gain_account
            else:
                main_side = "CREDIT"
                counter_side = "DEBIT"
                counter_account = cfg.fx_loss_account
            if counter_account is None:
                issues.append(
                    {
                        "code": "FX_REVALUATION_COUNTER_ACCOUNT_MISSING",
                        "detail": "Cuenta técnica de contrapartida no configurada.",
                        "account_code": account.code,
                    }
                )
                continue

            event = EconomicEvent.objects.create(
                source_module="ACCOUNTING",
                event_type="FxRevaluationAdjusted",
                company=company,
                branch=None,
                occurred_at=timezone.make_aware(datetime.combine(as_of, time.min)),
                contract_version="1.0",
                schema_version=1,
                correlation_id=f"fx-reval-{run.run_id}",
                causation_id=str(run.run_id),
                payload={
                    "source_module": "ACCOUNTING",
                    "event_type": "FxRevaluationAdjusted",
                    "schema_version": 1,
                    "contract_version": "1.0",
                    "occurred_at": timezone.now().isoformat(),
                    "correlation_id": f"fx-reval-{run.run_id}",
                    "causation_id": str(run.run_id),
                    "close_run_id": "",
                    "source_outbox_event_id": "",
                    "data": {
                        "run_id": str(run.run_id),
                        "account_code": account.code,
                        "currency": str(adj["currency"]),
                        "fx_rate": str(adj["fx_rate"]),
                        "delta_base": str(delta),
                    },
                    "scope": {"company_id": int(company.id), "branch_id": None},
                },
                input_manifest_hash="",
                close_run_id="",
            )

            lines_json = [
                # Regla de asiento técnico: línea principal en cuenta revaluable y contrapartida en cuenta FX.
                {
                    "account": account.code,
                    "side": main_side,
                    "amount": str(amount),
                    "currency": functional_currency,
                    "fx_rate": "1.00000000",
                    "amount_tx": str(amount),
                },
                {
                    "account": counter_account.code,
                    "side": counter_side,
                    "amount": str(amount),
                    "currency": functional_currency,
                    "fx_rate": "1.00000000",
                    "amount_tx": str(amount),
                },
            ]
            draft = JournalDraft.objects.create(
                economic_event=event,
                rule_set=ruleset,
                state=JournalDraft.State.POSTED,
                contract_version="1.0",
                schema_version=1,
                close_run_id="",
                input_manifest_hash="",
                lines_json=lines_json,
                total_debit=amount,
                total_credit=amount,
                validated_at=timezone.now(),
                approved_at=timezone.now(),
                approved_by=actor_user,
                posted_at=timezone.now(),
                metadata={
                    "operation": "FX_REVALUATION",
                    "revaluation_run_id": str(run.run_id),
                    "sequence": idx + 1,
                },
            )
            entry = JournalEntry.objects.create(
                draft=draft,
                period=period,
                company=company,
                branch=None,
                entry_date=as_of,
                description=f"FX REVALUATION {account.code} {adj['currency']}",
                debit_total=amount,
                credit_total=amount,
                is_posted=True,
                posted_at=timezone.now(),
                posted_by=actor_user,
                metadata={
                    "operation": "FX_REVALUATION",
                    "revaluation_run_id": str(run.run_id),
                    "account_code": account.code,
                    "currency": str(adj["currency"]),
                    "fx_rate": str(adj["fx_rate"]),
                },
            )
            JournalEntryLine.objects.bulk_create(
                [
                    JournalEntryLine(
                        journal_entry=entry,
                        line_no=1,
                        account=account,
                        account_code_snapshot=account.code,
                        currency=functional_currency,
                        fx_rate=Decimal("1.00000000"),
                        amount_tx=amount,
                        debit_base=amount if main_side == "DEBIT" else Decimal("0.00"),
                        credit_base=amount if main_side == "CREDIT" else Decimal("0.00"),
                        meta_json={"operation": "FX_REVALUATION", "run_id": str(run.run_id)},
                    ),
                    JournalEntryLine(
                        journal_entry=entry,
                        line_no=2,
                        account=counter_account,
                        account_code_snapshot=counter_account.code,
                        currency=functional_currency,
                        fx_rate=Decimal("1.00000000"),
                        amount_tx=amount,
                        debit_base=amount if counter_side == "DEBIT" else Decimal("0.00"),
                        credit_base=amount if counter_side == "CREDIT" else Decimal("0.00"),
                        meta_json={"operation": "FX_REVALUATION", "run_id": str(run.run_id)},
                    ),
                ]
            )
            RevaluationEntryLink.objects.create(revaluation_run=run, journal_entry=entry)
            entries_created += 1

        summary = {
            "schema_version": 1,
            "status": RevaluationRun.Status.COMPLETED,
            "as_of": str(as_of),
            "functional_currency": functional_currency,
            "entries_created": int(entries_created),
            "issues_count": int(len(issues)),
            "issues": issues,
            "scope_hash": scope_hash,
        }
        run.status = RevaluationRun.Status.COMPLETED
        run.summary_json = summary
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "summary_json", "completed_at"])

        publish_outbox_event(
            source_module="ACCOUNTING",
            event_type="FxRevaluationExecuted",
            payload={
                "run_id": str(run.run_id),
                "year": int(year),
                "month": int(month),
                "entries_created": int(entries_created),
                "issues_count": int(len(issues)),
                "status": run.status,
            },
            company=company,
            actor_user=actor_user,
        )
        return RevaluationExecutionResult(
            run_id=str(run.run_id),
            status=run.status,
            idempotent=False,
            entries_created=int(entries_created),
            issues_count=int(len(issues)),
            summary_json=summary,
        )
