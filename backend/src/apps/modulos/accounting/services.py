from __future__ import annotations

import hashlib
import json
import logging
from datetime import date, datetime, time, timedelta
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from django.conf import settings
from django.db import IntegrityError, transaction
from django.db.models import Case, Count, IntegerField, Q, Value, When
from django.utils import timezone

from apps.modulos.common.domain_errors import DomainError, IntegrationError
from apps.modulos.cec.models import CECException, CloseRun
from apps.modulos.cec.services import advance_close_run_state
from apps.modulos.iam.models import OrgUnit
from apps.modulos.integration.models import InboxEvent, OutboxEvent
from apps.modulos.integration.services import create_or_get_inbox_event, publish_outbox_event
from modulos.facturacion.models import BillingDocument

from .models import (
    DraftValidationResult,
    EconomicEvent,
    ExceptionLink,
    FiscalPeriod,
    JournalDraft,
    JournalEntry,
    OperationalPostingConfig,
    RevaluationRun,
    PostingRuleSet,
)
from .phase7 import Phase7ValidationError, ensure_journal_entry_lines, get_or_create_accounting_config

MONEY_Q = Decimal("0.01")
PROJECTOR_CONSUMER = "accounting.projector"
OPEN_EXCEPTION_STATUSES = (CECException.Status.OPEN, CECException.Status.IN_PROGRESS)
SCORE_WEIGHTS: dict[str, int] = {
    CECException.Severity.CRITICAL: 40,
    CECException.Severity.HIGH: 20,
    CECException.Severity.MEDIUM: 10,
}
SUPPORTED_ECONOMIC_EVENTS = {
    ("BILLING", "DocumentIssued"),
    ("BILLING", "DocumentVoided"),
    ("INVENTORY", "InventoryMovementPosted"),
    ("INVENTORY", "InventoryAdjusted"),
    ("INVENTORY", "InventoryTransferCompleted"),
    ("PAYMENTS", "CashMovementPosted"),
    ("PAYMENTS", "CashSessionClosed"),
    ("PROCUREMENT", "ProcurementDocumentPosted"),
    ("PROCUREMENT", "ProcurementDocumentVoided"),
}

OPERATIONAL_ACCOUNTING_EVENTS = {
    ("BILLING", "DocumentIssued"),
    ("BILLING", "DocumentVoided"),
    ("INVENTORY", "InventoryMovementPosted"),
    ("INVENTORY", "InventoryAdjusted"),
    ("INVENTORY", "InventoryTransferCompleted"),
    ("PROCUREMENT", "ProcurementDocumentPosted"),
    ("PROCUREMENT", "ProcurementDocumentVoided"),
}
PERIOD_CLOSE_FAILED_OUTBOX_MODULES = ("BILLING", "INVENTORY", "ACCOUNTING")
logger = logging.getLogger(__name__)


class AccountingConflictError(ValueError):
    """Error de dominio para conflictos de estado/transición en accounting."""


@dataclass(frozen=True)
class ShadowProjectionResult:
    run_id: str
    close_run_status: str
    economic_events_created: int
    journal_drafts_generated: int
    exceptions_opened: int
    blocked: bool
    manifest_hash: str


@dataclass(frozen=True)
class ShadowProjectionBatchResult:
    attempted: int
    processed: int
    blocked: int
    skipped: int
    failed: int


@dataclass(frozen=True)
class OperationalPostingRuntime:
    posting_mode: str
    enable_billing: bool
    enable_inventory: bool
    enable_procurement: bool
    auto_post_on_write: bool

    def allows_module(self, source_module: str) -> bool:
        if self.posting_mode == OperationalPostingConfig.PostingMode.DISABLED:
            return False
        if source_module == "BILLING":
            return bool(self.enable_billing)
        if source_module == "INVENTORY":
            return bool(self.enable_inventory)
        if source_module == "PROCUREMENT":
            return bool(self.enable_procurement)
        return False


@dataclass(frozen=True)
class OperationalAccountingLinkResult:
    status: str
    economic_event_id: int | None = None
    journal_draft_id: int | None = None
    journal_entry_id: int | None = None
    error: str = ""


def _q_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def resolve_operational_posting_runtime(*, company, branch=None) -> OperationalPostingRuntime:
    row = None
    if branch is not None:
        row = (
            OperationalPostingConfig.objects.filter(company=company, branch=branch, is_active=True)
            .order_by("-updated_at", "-id")
            .first()
        )
    if row is None:
        row = (
            OperationalPostingConfig.objects.filter(company=company, branch__isnull=True, is_active=True)
            .order_by("-updated_at", "-id")
            .first()
        )

    if row is not None:
        mode = str(row.posting_mode or OperationalPostingConfig.PostingMode.HYBRID).upper()
        if mode not in OperationalPostingConfig.PostingMode.values:
            mode = OperationalPostingConfig.PostingMode.HYBRID
        return OperationalPostingRuntime(
            posting_mode=mode,
            enable_billing=bool(row.enable_billing),
            enable_inventory=bool(row.enable_inventory),
            enable_procurement=bool(getattr(settings, "ACCOUNTING_POSTING_ENABLE_PROCUREMENT", True)),
            auto_post_on_write=bool(row.auto_post_on_write),
        )

    mode = str(getattr(settings, "ACCOUNTING_POSTING_MODE", OperationalPostingConfig.PostingMode.HYBRID) or "").upper()
    if mode not in OperationalPostingConfig.PostingMode.values:
        mode = OperationalPostingConfig.PostingMode.HYBRID
    return OperationalPostingRuntime(
        posting_mode=mode,
        enable_billing=bool(getattr(settings, "ACCOUNTING_POSTING_ENABLE_BILLING", True)),
        enable_inventory=bool(getattr(settings, "ACCOUNTING_POSTING_ENABLE_INVENTORY", True)),
        enable_procurement=bool(getattr(settings, "ACCOUNTING_POSTING_ENABLE_PROCUREMENT", True)),
        auto_post_on_write=bool(getattr(settings, "ACCOUNTING_POSTING_AUTO_POST_ON_WRITE", False)),
    )


def _to_decimal(value: Any) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return Decimal("0.00")
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0.00")


def _json_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _fingerprint(*, run_id: str, code: str, related_object_type: str, related_object_id: str) -> str:
    raw = f"{run_id}|{code}|{related_object_type}|{related_object_id}"
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


def _event_data(event: OutboxEvent) -> dict[str, Any]:
    payload = event.payload if isinstance(event.payload, dict) else {}
    data = payload.get("data", {})
    return dict(data) if isinstance(data, dict) else {}


def _run_id_from_trigger(event: OutboxEvent) -> str:
    data = _event_data(event)
    run_id = data.get("run_id")
    if run_id is None:
        return ""
    return str(run_id)


def _event_is_supported(event: OutboxEvent) -> bool:
    key = (event.source_module, event.event_type)
    if key not in SUPPORTED_ECONOMIC_EVENTS:
        return False
    if key == ("PAYMENTS", "CashSessionClosed"):
        data = _event_data(event)
        return abs(_to_decimal(data.get("difference_amount"))) > Decimal("0.00")
    return True


def _enrich_event_data(event: OutboxEvent, *, base_data: dict[str, Any]) -> dict[str, Any]:
    data = dict(base_data)

    if event.source_module == "BILLING" and event.event_type == "DocumentVoided":
        if ("total" not in data or "subtotal" not in data or "tax_total" not in data) and data.get("doc_id"):
            doc = (
                BillingDocument.objects.filter(id=data["doc_id"])
                .values("subtotal", "tax_total", "total")
                .first()
            )
            if doc:
                data["subtotal"] = str(doc["subtotal"])
                data["tax_total"] = str(doc["tax_total"])
                data["total"] = str(doc["total"])

    if event.source_module == "INVENTORY":
        data["total_cost_abs"] = str(abs(_to_decimal(data.get("total_cost"))))
        data["qty_delta_abs"] = str(abs(_to_decimal(data.get("qty_delta") or data.get("qty"))))
        movement_type = str(data.get("movement_type", "")).upper()
        data["is_adjust_increase"] = movement_type == "ADJUST" and _to_decimal(data.get("qty_delta")) > Decimal("0.00")
        data["is_adjust_decrease"] = movement_type == "ADJUST" and _to_decimal(data.get("qty_delta")) < Decimal("0.00")
        if event.event_type == "InventoryAdjusted":
            adjust_total = _to_decimal(data.get("qty_delta")) * _to_decimal(data.get("avg_cost"))
            data["adjust_total_cost"] = str(adjust_total)
            data["adjust_total_cost_abs"] = str(abs(adjust_total))
        if event.event_type == "InventoryTransferCompleted":
            transfer_total = _to_decimal(data.get("qty")) * _to_decimal(data.get("unit_cost"))
            data["transfer_total_cost"] = str(transfer_total)
            data["transfer_total_cost_abs"] = str(abs(transfer_total))

    if event.source_module == "PAYMENTS":
        if event.event_type == "CashMovementPosted":
            data["amount_abs"] = str(abs(_to_decimal(data.get("amount"))))
        if event.event_type == "CashSessionClosed":
            diff = _to_decimal(data.get("difference_amount"))
            data["difference_abs"] = str(abs(diff))
            data["difference_is_short"] = diff < Decimal("0.00")
            data["difference_is_over"] = diff > Decimal("0.00")

    if event.source_module == "PROCUREMENT":
        subtotal = _to_decimal(data.get("subtotal"))
        tax_total = _to_decimal(data.get("tax_total"))
        total = _to_decimal(data.get("total"))
        data["subtotal_abs"] = str(abs(subtotal))
        data["tax_total_abs"] = str(abs(tax_total))
        data["total_abs"] = str(abs(total))
        doc_type = str(data.get("doc_type", "")).upper()
        data["is_supplier_invoice"] = doc_type == "SUPPLIER_INVOICE"
        data["is_supplier_credit_note"] = doc_type == "SUPPLIER_CREDIT_NOTE"
        data["is_goods_receipt"] = doc_type == "GOODS_RECEIPT"
        data["is_supplier_payment"] = doc_type == "SUPPLIER_PAYMENT"
        data["is_adjustment"] = doc_type == "ADJUSTMENT"

    return data


def _normalize_operational_event(*, run: CloseRun, outbox_event: OutboxEvent) -> dict[str, Any]:
    payload = outbox_event.payload if isinstance(outbox_event.payload, dict) else {}
    data = _enrich_event_data(outbox_event, base_data=_event_data(outbox_event))
    occurred_at = payload.get("occurred_at") or outbox_event.occurred_at.isoformat()
    return {
        "source_module": outbox_event.source_module,
        "event_type": outbox_event.event_type,
        "schema_version": int(payload.get("schema_version") or outbox_event.schema_version or 1),
        "contract_version": str(payload.get("contract_version") or "1.0"),
        "occurred_at": occurred_at,
        "correlation_id": str(payload.get("correlation_id") or outbox_event.correlation_id or ""),
        "causation_id": str(payload.get("causation_id") or outbox_event.causation_id or ""),
        "close_run_id": str(run.run_id),
        "source_outbox_event_id": str(outbox_event.event_id),
        "data": data,
        "scope": {
            "company_id": run.company_id,
            "branch_id": run.branch_id,
        },
    }


def _normalize_operational_event_for_link(
    *,
    outbox_event: OutboxEvent,
    company,
    branch,
) -> dict[str, Any]:
    payload = outbox_event.payload if isinstance(outbox_event.payload, dict) else {}
    data = _enrich_event_data(outbox_event, base_data=_event_data(outbox_event))
    occurred_at = payload.get("occurred_at") or outbox_event.occurred_at.isoformat()
    return {
        "source_module": outbox_event.source_module,
        "event_type": outbox_event.event_type,
        "schema_version": int(payload.get("schema_version") or outbox_event.schema_version or 1),
        "contract_version": str(payload.get("contract_version") or "1.0"),
        "occurred_at": occurred_at,
        "correlation_id": str(payload.get("correlation_id") or outbox_event.correlation_id or ""),
        "causation_id": str(payload.get("causation_id") or outbox_event.causation_id or ""),
        "source_outbox_event_id": str(outbox_event.event_id),
        "data": data,
        "scope": {
            "company_id": company.id,
            "branch_id": getattr(branch, "id", None),
        },
    }


def _select_active_rule_set_for_scope(*, company, normalized: dict[str, Any]) -> PostingRuleSet | None:
    occurred_at = datetime.fromisoformat(str(normalized["occurred_at"]).replace("Z", "+00:00"))
    fiscal_mode = _infer_fiscal_mode(normalized)
    qs = PostingRuleSet.objects.filter(
        status=PostingRuleSet.Status.ACTIVE,
    ).filter(
        Q(scope_company=company) | Q(scope_company__isnull=True),
        Q(effective_from__isnull=True) | Q(effective_from__lte=occurred_at),
        Q(effective_to__isnull=True) | Q(effective_to__gte=occurred_at),
    )

    if fiscal_mode in (PostingRuleSet.FiscalMode.A, PostingRuleSet.FiscalMode.B):
        qs = qs.filter(fiscal_mode__in=[fiscal_mode, PostingRuleSet.FiscalMode.BOTH]).annotate(
            fiscal_rank=Case(
                When(fiscal_mode=fiscal_mode, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        )
    else:
        qs = qs.filter(fiscal_mode=PostingRuleSet.FiscalMode.BOTH).annotate(
            fiscal_rank=Value(0, output_field=IntegerField())
        )

    qs = qs.annotate(
        scope_rank=Case(
            When(scope_company=company, then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        )
    )
    return qs.order_by("scope_rank", "fiscal_rank", "-version", "-id").first()


def _post_single_journal_draft(
    *,
    draft: JournalDraft,
    actor_user=None,
) -> JournalEntry:
    if draft.total_debit != draft.total_credit:
        raise AccountingConflictError("Draft no balanceado (debit != credit).")

    period = _period_for_occurrence(
        company=draft.economic_event.company,
        occurred_at=draft.economic_event.occurred_at,
    )
    if period.status == FiscalPeriod.Status.CLOSED:
        raise AccountingConflictError(f"Periodo cerrado: {period.year}-{period.month:02d}.")

    cfg = get_or_create_accounting_config(company=draft.economic_event.company)
    phase7_enabled = bool(cfg.phase7_enabled)
    functional_currency = str(cfg.functional_currency or "NIO").upper() or "NIO"
    entry_date = timezone.localtime(draft.economic_event.occurred_at).date()
    description = f"{draft.economic_event.source_module}.{draft.economic_event.event_type}"

    entry, created = JournalEntry.objects.get_or_create(
        draft=draft,
        defaults={
            "period": period,
            "company": draft.economic_event.company,
            "branch": draft.economic_event.branch,
            "entry_date": entry_date,
            "description": description,
            "debit_total": draft.total_debit,
            "credit_total": draft.total_credit,
            "is_posted": True,
            "posted_at": timezone.now(),
            "posted_by": actor_user,
            "metadata": {
                "close_run_id": draft.close_run_id,
                "input_manifest_hash": draft.input_manifest_hash,
                "contract_version": draft.contract_version,
                "schema_version": int(draft.schema_version),
                "economic_event_id": int(draft.economic_event_id),
            },
        },
    )
    if not created:
        if draft.state != JournalDraft.State.POSTED:
            draft.state = JournalDraft.State.POSTED
            draft.posted_at = entry.posted_at
            draft.save(update_fields=["state", "posted_at"])
        return entry

    if phase7_enabled:
        ensure_journal_entry_lines(
            entry=entry,
            draft=draft,
            functional_currency=functional_currency,
        )

    draft.state = JournalDraft.State.POSTED
    draft.posted_at = entry.posted_at
    draft.save(update_fields=["state", "posted_at"])

    publish_outbox_event(
        source_module="ACCOUNTING",
        event_type="JournalPosted",
        payload={
            "journal_entry_id": entry.id,
            "journal_draft_id": draft.id,
            "economic_event_id": draft.economic_event_id,
            "run_id": draft.close_run_id,
            "period_year": int(period.year),
            "period_month": int(period.month),
            "debit_total": str(entry.debit_total),
            "credit_total": str(entry.credit_total),
            "entry_date": str(entry.entry_date),
        },
        company=draft.economic_event.company,
        branch=draft.economic_event.branch,
        actor_user=actor_user,
    )
    return entry


def link_operational_event_to_accounting(
    *,
    outbox_event: OutboxEvent,
    actor_user=None,
) -> OperationalAccountingLinkResult:
    if (outbox_event.source_module, outbox_event.event_type) not in OPERATIONAL_ACCOUNTING_EVENTS:
        return OperationalAccountingLinkResult(status="UNSUPPORTED")

    company = outbox_event.company
    branch = outbox_event.branch
    if company is None:
        return OperationalAccountingLinkResult(status="UNSUPPORTED", error="Event sin scope de company.")

    runtime = resolve_operational_posting_runtime(company=company, branch=branch)
    if not runtime.allows_module(outbox_event.source_module):
        return OperationalAccountingLinkResult(status="DISABLED")

    normalized = _normalize_operational_event_for_link(outbox_event=outbox_event, company=company, branch=branch)
    occurred_at = datetime.fromisoformat(str(normalized["occurred_at"]).replace("Z", "+00:00"))

    with transaction.atomic():
        defaults = {
            "source_module": normalized["source_module"],
            "event_type": normalized["event_type"],
            "company": company,
            "branch": branch,
            "occurred_at": occurred_at,
            "contract_version": normalized["contract_version"],
            "schema_version": int(normalized["schema_version"]),
            "correlation_id": normalized["correlation_id"],
            "causation_id": normalized["causation_id"],
            "payload": normalized,
            "input_manifest_hash": "",
            "close_run_id": "",
            "source_outbox_event_id": outbox_event.event_id,
        }
        economic_event, _ = EconomicEvent.objects.get_or_create(
            company=company,
            source_outbox_event_id=outbox_event.event_id,
            defaults=defaults,
        )
        if economic_event.payload != normalized:
            economic_event.payload = normalized
            economic_event.correlation_id = normalized["correlation_id"]
            economic_event.causation_id = normalized["causation_id"]
            economic_event.save(update_fields=["payload", "correlation_id", "causation_id"])

        rule_set = _select_active_rule_set_for_scope(company=company, normalized=normalized)
        if rule_set is None:
            seeded_rule_set, _ = seed_posting_rules_v1_for_company(company=company)
            rule_set = _select_active_rule_set_for_scope(company=company, normalized=normalized)
            if rule_set is None and seeded_rule_set.status == PostingRuleSet.Status.ACTIVE:
                # Fallback para primer evento cuando occurred_at queda milisegundos antes de effective_from.
                rule_set = seeded_rule_set
        if rule_set is None:
            return OperationalAccountingLinkResult(
                status="PENDING_RULESET",
                economic_event_id=economic_event.id,
                error="No hay PostingRuleSet ACTIVE para el scope.",
            )

        matched_rule = _select_rule(rule_set=rule_set, normalized=normalized)
        if matched_rule is None:
            return OperationalAccountingLinkResult(
                status="PENDING_RULE",
                economic_event_id=economic_event.id,
                error="No hay regla aplicable para el evento.",
            )

        lines_json, total_debit, total_credit, line_errors = _build_lines_from_rule(
            normalized=normalized,
            rule=matched_rule,
        )
        if total_debit != total_credit:
            line_errors.append("Draft no balanceado: debit != credit.")
        if not lines_json:
            line_errors.append("Draft sin líneas contables.")

        draft_defaults = {
            "state": JournalDraft.State.GENERATED,
            "contract_version": economic_event.contract_version,
            "schema_version": economic_event.schema_version,
            "close_run_id": "",
            "input_manifest_hash": "",
            "lines_json": lines_json,
            "total_debit": total_debit,
            "total_credit": total_credit,
            "metadata": {
                "rule_id": str(matched_rule.get("id") or ""),
                "rule_set_code": rule_set.code,
                "rule_set_version": int(rule_set.version),
                "source_outbox_event_id": str(outbox_event.event_id),
                "posting_mode": runtime.posting_mode,
            },
        }
        draft, created_draft = JournalDraft.objects.get_or_create(
            economic_event=economic_event,
            rule_set=rule_set,
            defaults=draft_defaults,
        )

        if not created_draft and draft.state == JournalDraft.State.POSTED and hasattr(draft, "journal_entry"):
            return OperationalAccountingLinkResult(
                status="POSTED",
                economic_event_id=economic_event.id,
                journal_draft_id=draft.id,
                journal_entry_id=draft.journal_entry.id,
            )

        if created_draft or draft.state in (JournalDraft.State.GENERATED, JournalDraft.State.EXCEPTION):
            current_metadata = dict(draft.metadata) if isinstance(draft.metadata, dict) else {}
            default_metadata_raw = draft_defaults.get("metadata")
            if isinstance(default_metadata_raw, dict):
                default_metadata = {str(k): v for k, v in default_metadata_raw.items()}
            else:
                default_metadata = {}
            draft.lines_json = lines_json
            draft.total_debit = total_debit
            draft.total_credit = total_credit
            draft.metadata = {
                **current_metadata,
                **default_metadata,
            }

        if line_errors:
            draft.state = JournalDraft.State.EXCEPTION
            draft.validated_at = None
            draft.save(update_fields=["state", "validated_at", "lines_json", "total_debit", "total_credit", "metadata"])
            _upsert_validation_result(draft=draft, passed=False, errors=line_errors, is_blocking=True)
            return OperationalAccountingLinkResult(
                status="DRAFT_EXCEPTION",
                economic_event_id=economic_event.id,
                journal_draft_id=draft.id,
                error="; ".join(line_errors)[:255],
            )

        draft.state = JournalDraft.State.VALIDATED
        draft.validated_at = timezone.now()
        draft.save(update_fields=["state", "validated_at", "lines_json", "total_debit", "total_credit", "metadata"])
        _upsert_validation_result(draft=draft, passed=True, errors=[], is_blocking=False)

        journal_entry_id = None
        status = "DRAFT_VALIDATED"
        if runtime.auto_post_on_write and runtime.posting_mode in (
            OperationalPostingConfig.PostingMode.SYNC,
            OperationalPostingConfig.PostingMode.HYBRID,
        ):
            try:
                entry = _post_single_journal_draft(draft=draft, actor_user=actor_user)
                journal_entry_id = entry.id
                status = "POSTED"
            except (AccountingConflictError, Phase7ValidationError) as exc:
                status = "DRAFT_EXCEPTION"
                return OperationalAccountingLinkResult(
                    status=status,
                    economic_event_id=economic_event.id,
                    journal_draft_id=draft.id,
                    error=str(exc)[:255],
                )

        return OperationalAccountingLinkResult(
            status=status,
            economic_event_id=economic_event.id,
            journal_draft_id=draft.id,
            journal_entry_id=journal_entry_id,
        )


def apply_accounting_link_to_outbox_event(
    *,
    outbox_event: OutboxEvent,
    link: OperationalAccountingLinkResult,
) -> None:
    payload = outbox_event.payload if isinstance(outbox_event.payload, dict) else {}
    data = payload.get("data", {})
    if not isinstance(data, dict):
        data = {}
    data["accounting_status"] = link.status
    data["economic_event_id"] = link.economic_event_id
    data["journal_draft_id"] = link.journal_draft_id
    data["journal_entry_id"] = link.journal_entry_id
    if link.error:
        data["accounting_error"] = link.error
    payload["data"] = data
    payload["schema_version"] = int(payload.get("schema_version") or outbox_event.schema_version or 1)
    outbox_event.payload = payload
    outbox_event.save(update_fields=["payload"])

def _extract_when_value(*, normalized: dict[str, Any], key: str):
    if "." in key:
        return _extract_path(normalized, key)
    if key in normalized:
        return normalized.get(key)
    return _extract_path(normalized, f"data.{key}")


def _matches_when(*, normalized: dict[str, Any], when: dict[str, Any]) -> bool:
    for key, expected in when.items():
        actual = _extract_when_value(normalized=normalized, key=key)
        if isinstance(expected, (list, tuple, set)):
            if actual not in expected:
                return False
            continue
        if actual != expected:
            return False
    return True


def _select_rule(*, rule_set: PostingRuleSet, normalized: dict[str, Any]) -> dict[str, Any] | None:
    rules_payload = rule_set.rules_json if isinstance(rule_set.rules_json, dict) else {}
    rules = rules_payload.get("rules", [])
    if not isinstance(rules, list):
        return None

    for row in rules:
        if not isinstance(row, dict):
            continue
        rule_module = str(row.get("source_module") or "")
        rule_event = str(row.get("event_type") or "")
        if rule_module not in ("*", normalized["source_module"]):
            continue
        if rule_event not in ("*", normalized["event_type"]):
            continue
        when = row.get("when", {})
        if not isinstance(when, dict):
            continue
        if _matches_when(normalized=normalized, when=when):
            return row
    return None


def _build_lines_from_rule(*, normalized: dict[str, Any], rule: dict[str, Any]) -> tuple[list[dict[str, Any]], Decimal, Decimal, list[str]]:
    rows = rule.get("lines", [])
    if not isinstance(rows, list):
        return [], Decimal("0.00"), Decimal("0.00"), ["rule.lines debe ser una lista."]

    lines: list[dict[str, Any]] = []
    errors: list[str] = []
    total_debit = Decimal("0.00")
    total_credit = Decimal("0.00")
    for idx, line in enumerate(rows):
        if not isinstance(line, dict):
            errors.append(f"lines[{idx}] inválida")
            continue
        account = str(line.get("account") or "").strip()
        side = str(line.get("side") or "").upper().strip()
        amount_from = str(line.get("amount_from") or "").strip()
        sign = _to_decimal(line.get("sign", "1"))
        if not account:
            errors.append(f"lines[{idx}] sin account")
            continue
        if side not in ("DEBIT", "CREDIT"):
            errors.append(f"lines[{idx}] side inválido")
            continue
        if not amount_from:
            errors.append(f"lines[{idx}] sin amount_from")
            continue

        amount_raw = _extract_when_value(normalized=normalized, key=amount_from)
        amount = _q_money(abs(_to_decimal(amount_raw) * sign))

        debit = amount if side == "DEBIT" else Decimal("0.00")
        credit = amount if side == "CREDIT" else Decimal("0.00")
        total_debit += debit
        total_credit += credit
        lines.append(
            {
                "account": account,
                "side": side,
                "amount": str(amount),
                "debit": str(debit),
                "credit": str(credit),
                "amount_from": amount_from,
                "sign": str(sign),
            }
        )

    return lines, _q_money(total_debit), _q_money(total_credit), errors


def _infer_fiscal_mode(normalized: dict[str, Any]) -> str:
    mode = str(_extract_path(normalized, "data.fiscal_adapter_mode", default="") or "").upper()
    if mode in (PostingRuleSet.FiscalMode.A, PostingRuleSet.FiscalMode.B):
        return mode
    return PostingRuleSet.FiscalMode.BOTH


def _select_active_rule_set(*, run: CloseRun, normalized: dict[str, Any]) -> PostingRuleSet | None:
    occurred_at = datetime.fromisoformat(str(normalized["occurred_at"]).replace("Z", "+00:00"))
    fiscal_mode = _infer_fiscal_mode(normalized)
    qs = PostingRuleSet.objects.filter(
        status=PostingRuleSet.Status.ACTIVE,
    ).filter(
        Q(scope_company=run.company) | Q(scope_company__isnull=True),
        Q(effective_from__isnull=True) | Q(effective_from__lte=occurred_at),
        Q(effective_to__isnull=True) | Q(effective_to__gte=occurred_at),
    )

    if fiscal_mode in (PostingRuleSet.FiscalMode.A, PostingRuleSet.FiscalMode.B):
        qs = qs.filter(fiscal_mode__in=[fiscal_mode, PostingRuleSet.FiscalMode.BOTH]).annotate(
            fiscal_rank=Case(
                When(fiscal_mode=fiscal_mode, then=Value(0)),
                default=Value(1),
                output_field=IntegerField(),
            )
        )
    else:
        qs = qs.filter(fiscal_mode=PostingRuleSet.FiscalMode.BOTH).annotate(
            fiscal_rank=Value(0, output_field=IntegerField())
        )

    qs = qs.annotate(
        scope_rank=Case(
            When(scope_company=run.company, then=Value(0)),
            default=Value(1),
            output_field=IntegerField(),
        )
    )
    return qs.order_by("scope_rank", "fiscal_rank", "-version", "-id").first()


def _register_projection_exception(
    *,
    run: CloseRun,
    code: str,
    severity: str,
    related_object_type: str,
    related_object_id: str,
    details_json: dict[str, Any],
    draft: JournalDraft | None = None,
) -> tuple[CECException, bool]:
    fp = _fingerprint(
        run_id=str(run.run_id),
        code=code,
        related_object_type=related_object_type,
        related_object_id=related_object_id,
    )

    existing = (
        CECException.objects.select_for_update()
        .filter(
            close_run=run,
            source_module="ACCOUNTING",
            fingerprint=fp,
            status__in=OPEN_EXCEPTION_STATUSES,
        )
        .first()
    )
    if existing:
        update_fields: list[str] = []
        if existing.severity != severity:
            existing.severity = severity
            update_fields.append("severity")
        if existing.details_json != details_json:
            existing.details_json = details_json
            update_fields.append("details_json")
        if existing.is_blocking is not True:
            existing.is_blocking = True
            update_fields.append("is_blocking")
        if update_fields:
            existing.save(update_fields=update_fields)
        if draft is not None:
            ExceptionLink.objects.get_or_create(draft=draft, exception=existing)
        return existing, False

    created = CECException.objects.create(
        source_module="ACCOUNTING",
        code=code,
        severity=severity,
        status=CECException.Status.OPEN,
        company=run.company,
        branch=run.branch,
        related_object_type=related_object_type,
        related_object_id=related_object_id,
        details_json=details_json,
        fingerprint=fp,
        is_blocking=True,
        close_run=run,
    )
    if draft is not None:
        ExceptionLink.objects.get_or_create(draft=draft, exception=created)
    return created, True


def _upsert_validation_result(*, draft: JournalDraft, passed: bool, errors: list[str], is_blocking: bool) -> None:
    DraftValidationResult.objects.update_or_create(
        draft=draft,
        defaults={
            "passed": bool(passed),
            "errors_json": list(errors),
            "is_blocking": bool(is_blocking),
            "validated_at": timezone.now(),
        },
    )


def _update_run_quality_metrics(*, run: CloseRun) -> None:
    severity_counts = (
        CECException.objects.filter(close_run=run, status__in=OPEN_EXCEPTION_STATUSES)
        .values("severity")
        .annotate(cnt=Count("id"))
    )
    score = 100
    for row in severity_counts:
        score -= SCORE_WEIGHTS.get(str(row["severity"]), 0) * int(row["cnt"])

    blocking_count = CECException.objects.filter(
        close_run=run,
        status__in=OPEN_EXCEPTION_STATUSES,
        is_blocking=True,
    ).count()
    run.consistency_score = max(0, int(score))
    run.blocking_exceptions_count = int(blocking_count)
    run.save(update_fields=["consistency_score", "blocking_exceptions_count", "updated_at"])


def _operational_events_for_run(*, run: CloseRun) -> list[OutboxEvent]:
    if run.window_start is None or run.window_end is None:
        return []
    qs = OutboxEvent.objects.filter(
        source_module__in=["BILLING", "INVENTORY", "PAYMENTS", "PROCUREMENT"],
        company=run.company,
        occurred_at__gte=run.window_start,
        occurred_at__lte=run.window_end,
    )
    if run.branch is not None:
        qs = qs.filter(branch=run.branch)
    rows = list(qs.order_by("occurred_at", "id"))
    return [r for r in rows if _event_is_supported(r)]


def _find_trigger_event_for_run(*, run_id: str, company_id: int | None = None) -> OutboxEvent | None:
    qs = OutboxEvent.objects.filter(source_module="CEC", event_type="CloseRunPackaged").order_by("-occurred_at", "-id")
    if company_id is not None:
        qs = qs.filter(company_id=company_id)
    for event in qs:
        if _run_id_from_trigger(event) == str(run_id):
            return event
    return None


def _projection_manifest(
    *,
    run: CloseRun,
    operational_events: list[OutboxEvent],
    economic_event_ids: list[int],
    draft_ids: list[int],
    exception_codes: list[str],
) -> tuple[str, dict[str, Any]]:
    payload = {
        "schema_version": 1,
        "contract_version": "1.0",
        "run_id": str(run.run_id),
        "window_start": run.window_start.isoformat() if run.window_start else "",
        "window_end": run.window_end.isoformat() if run.window_end else "",
        "close_run_manifest_hash": run.output_manifest_hash,
        "operational_outbox_event_ids": sorted(str(x.event_id) for x in operational_events),
        "economic_event_ids": sorted(int(x) for x in economic_event_ids),
        "journal_draft_ids": sorted(int(x) for x in draft_ids),
        "exception_codes": sorted(exception_codes),
    }
    return _json_hash(payload), payload


def project_close_run_from_trigger(*, trigger_event: OutboxEvent) -> ShadowProjectionResult:
    run_id = _run_id_from_trigger(trigger_event)
    if not run_id:
        raise ValueError("Trigger CloseRunPackaged sin run_id.")

    with transaction.atomic():
        run = CloseRun.objects.select_for_update().filter(run_id=run_id).first()
        if run is None:
            raise ValueError(f"CloseRun {run_id} no existe.")
        if run.status != CloseRun.Status.PACKAGED:
            raise ValueError(f"CloseRun {run_id} debe estar PACKAGED para proyectar shadow ledger.")
        if run.window_start is None or run.window_end is None:
            raise ValueError("CloseRun requiere window_start/window_end para proyectar shadow ledger.")

        operational_events = _operational_events_for_run(run=run)
        economic_events_created = 0
        journal_drafts_generated = 0
        exceptions_opened = 0
        economic_event_ids: list[int] = []
        draft_ids: list[int] = []
        exception_codes: list[str] = []

        for source_event in operational_events:
            normalized = _normalize_operational_event(run=run, outbox_event=source_event)
            occurred_at = datetime.fromisoformat(str(normalized["occurred_at"]).replace("Z", "+00:00"))
            event_defaults = {
                "source_module": normalized["source_module"],
                "event_type": normalized["event_type"],
                "company": run.company,
                "branch": run.branch,
                "occurred_at": occurred_at,
                "contract_version": normalized["contract_version"],
                "schema_version": int(normalized["schema_version"]),
                "correlation_id": normalized["correlation_id"],
                "causation_id": normalized["causation_id"],
                "payload": normalized,
                "input_manifest_hash": run.output_manifest_hash,
                "close_run_id": str(run.run_id),
                "source_outbox_event_id": source_event.event_id,
            }
            try:
                economic_event, created = EconomicEvent.objects.get_or_create(
                    company=run.company,
                    source_outbox_event_id=source_event.event_id,
                    defaults=event_defaults,
                )
            except IntegrityError:
                economic_event = EconomicEvent.objects.get(
                    company=run.company,
                    source_outbox_event_id=source_event.event_id,
                )
                created = False

            economic_event_ids.append(economic_event.id)
            if created:
                economic_events_created += 1
                publish_outbox_event(
                    source_module="ACCOUNTING",
                    event_type="EconomicEventRegistered",
                    payload={
                        "run_id": str(run.run_id),
                        "economic_event_id": economic_event.id,
                        "source_outbox_event_id": str(source_event.event_id),
                        "source_module": economic_event.source_module,
                        "event_type": economic_event.event_type,
                    },
                    company=run.company,
                    branch=run.branch,
                    actor_user=run.created_by,
                )

            rule_set = _select_active_rule_set(run=run, normalized=normalized)
            if rule_set is None:
                _, opened = _register_projection_exception(
                    run=run,
                    code="SHADOW_RULESET_NOT_FOUND",
                    severity=CECException.Severity.HIGH,
                    related_object_type="OUTBOX_EVENT",
                    related_object_id=str(source_event.event_id),
                    details_json={
                        "source_module": source_event.source_module,
                        "event_type": source_event.event_type,
                        "message": "No hay PostingRuleSet ACTIVE aplicable.",
                    },
                )
                exception_codes.append("SHADOW_RULESET_NOT_FOUND")
                if opened:
                    exceptions_opened += 1
                continue

            matched_rule = _select_rule(rule_set=rule_set, normalized=normalized)
            if matched_rule is None:
                _, opened = _register_projection_exception(
                    run=run,
                    code="SHADOW_RULE_NOT_FOUND",
                    severity=CECException.Severity.HIGH,
                    related_object_type="OUTBOX_EVENT",
                    related_object_id=str(source_event.event_id),
                    details_json={
                        "rule_set_code": rule_set.code,
                        "rule_set_version": rule_set.version,
                        "source_module": source_event.source_module,
                        "event_type": source_event.event_type,
                        "message": "No existe regla compatible para el evento.",
                    },
                )
                exception_codes.append("SHADOW_RULE_NOT_FOUND")
                if opened:
                    exceptions_opened += 1
                continue

            lines_json, total_debit, total_credit, line_errors = _build_lines_from_rule(
                normalized=normalized,
                rule=matched_rule,
            )
            rule_id = str(matched_rule.get("id") or "")
            draft_defaults = {
                "state": JournalDraft.State.GENERATED,
                "contract_version": economic_event.contract_version,
                "schema_version": economic_event.schema_version,
                "close_run_id": str(run.run_id),
                "input_manifest_hash": run.output_manifest_hash,
                "lines_json": lines_json,
                "total_debit": total_debit,
                "total_credit": total_credit,
                "metadata": {
                    "rule_id": rule_id,
                    "rule_set_code": rule_set.code,
                    "rule_set_version": int(rule_set.version),
                    "source_outbox_event_id": str(source_event.event_id),
                },
            }
            draft, created_draft = JournalDraft.objects.get_or_create(
                economic_event=economic_event,
                rule_set=rule_set,
                defaults=draft_defaults,
            )
            draft_ids.append(draft.id)

            validation_errors = list(line_errors)
            if total_debit != total_credit:
                validation_errors.append("Draft no balanceado: debit != credit.")
            if not lines_json:
                validation_errors.append("Draft sin lineas contables.")

            if created_draft:
                journal_drafts_generated += 1
            else:
                if (
                    draft.lines_json != lines_json
                    or draft.total_debit != total_debit
                    or draft.total_credit != total_credit
                ):
                    validation_errors.append("Draft existente no coincide con proyeccion determinista.")

            if validation_errors:
                if (
                    draft.state != JournalDraft.State.EXCEPTION
                    or draft.lines_json != lines_json
                    or draft.total_debit != total_debit
                    or draft.total_credit != total_credit
                ):
                    draft.state = JournalDraft.State.EXCEPTION
                    draft.lines_json = lines_json
                    draft.total_debit = total_debit
                    draft.total_credit = total_credit
                    draft.metadata = {
                        **(draft.metadata or {}),
                        "rule_id": rule_id,
                        "rule_set_code": rule_set.code,
                        "rule_set_version": int(rule_set.version),
                        "source_outbox_event_id": str(source_event.event_id),
                    }
                    draft.save(update_fields=["state", "lines_json", "total_debit", "total_credit", "metadata"])

                _upsert_validation_result(draft=draft, passed=False, errors=validation_errors, is_blocking=True)
                _, opened = _register_projection_exception(
                    run=run,
                    code="SHADOW_DRAFT_INVALID",
                    severity=CECException.Severity.CRITICAL,
                    related_object_type="JOURNAL_DRAFT",
                    related_object_id=str(draft.id),
                    details_json={
                        "rule_set_code": rule_set.code,
                        "rule_set_version": int(rule_set.version),
                        "errors": validation_errors,
                    },
                    draft=draft,
                )
                exception_codes.append("SHADOW_DRAFT_INVALID")
                if opened:
                    exceptions_opened += 1
                continue

            if draft.state != JournalDraft.State.VALIDATED:
                draft.state = JournalDraft.State.VALIDATED
                draft.validated_at = timezone.now()
                if created_draft:
                    draft.lines_json = lines_json
                    draft.total_debit = total_debit
                    draft.total_credit = total_credit
                draft.save(
                    update_fields=["state", "validated_at", "lines_json", "total_debit", "total_credit", "metadata"]
                )
            _upsert_validation_result(draft=draft, passed=True, errors=[], is_blocking=False)
            if created_draft:
                publish_outbox_event(
                    source_module="ACCOUNTING",
                    event_type="JournalDraftGenerated",
                    payload={
                        "run_id": str(run.run_id),
                        "journal_draft_id": draft.id,
                        "economic_event_id": economic_event.id,
                        "rule_set_code": rule_set.code,
                        "rule_set_version": int(rule_set.version),
                        "state": draft.state,
                        "total_debit": str(draft.total_debit),
                        "total_credit": str(draft.total_credit),
                    },
                    company=run.company,
                    branch=run.branch,
                    actor_user=run.created_by,
                )

        _update_run_quality_metrics(run=run)
        accounting_blocking_count = CECException.objects.filter(
            close_run=run,
            source_module="ACCOUNTING",
            status__in=OPEN_EXCEPTION_STATUSES,
            is_blocking=True,
        ).count()

        manifest_hash, manifest_payload = _projection_manifest(
            run=run,
            operational_events=operational_events,
            economic_event_ids=economic_event_ids,
            draft_ids=draft_ids,
            exception_codes=exception_codes,
        )

        blocked = int(accounting_blocking_count) > 0
        if blocked and run.status == CloseRun.Status.PACKAGED and run.can_transition_to(CloseRun.Status.REOPENED_EXCEPTION):
            advance_close_run_state(run=run, target_status=CloseRun.Status.REOPENED_EXCEPTION)
            _update_run_quality_metrics(run=run)
            publish_outbox_event(
                source_module="CEC",
                event_type="CloseRunBlocked",
                payload={
                    "run_id": str(run.run_id),
                    "reason_code": "ACCOUNTING_PROJECTION_BLOCKED",
                    "blocking_exceptions_count": int(run.blocking_exceptions_count),
                    "consistency_score": int(run.consistency_score),
                },
                company=run.company,
                branch=run.branch,
                actor_user=run.created_by,
            )
        elif not blocked:
            publish_outbox_event(
                source_module="ACCOUNTING",
                event_type="ShadowLedgerProjected",
                payload={
                    "run_id": str(run.run_id),
                    "status": run.status,
                    "economic_events_created": int(economic_events_created),
                    "journal_drafts_generated": int(journal_drafts_generated),
                    "exceptions_opened": int(exceptions_opened),
                    "manifest_hash": manifest_hash,
                },
                company=run.company,
                branch=run.branch,
                actor_user=run.created_by,
            )

        summary_json = dict(run.summary_json or {})
        summary_json["accounting_projection"] = {
            "schema_version": 1,
            "contract_version": "1.0",
            "trigger_event_id": str(trigger_event.event_id),
            "run_id": str(run.run_id),
            "status": run.status,
            "blocked": bool(blocked),
            "manifest_hash": manifest_hash,
            "manifest": manifest_payload,
            "economic_events_created": int(economic_events_created),
            "journal_drafts_generated": int(journal_drafts_generated),
            "exceptions_opened": int(exceptions_opened),
            "blocking_exceptions_count": int(run.blocking_exceptions_count),
            "consistency_score": int(run.consistency_score),
        }
        run.summary_json = summary_json
        run.save(update_fields=["summary_json", "updated_at"])

        return ShadowProjectionResult(
            run_id=str(run.run_id),
            close_run_status=run.status,
            economic_events_created=int(economic_events_created),
            journal_drafts_generated=int(journal_drafts_generated),
            exceptions_opened=int(exceptions_opened),
            blocked=bool(blocked),
            manifest_hash=manifest_hash,
        )


def project_shadow_ledger_for_run(*, run_id: str, company_id: int | None = None) -> ShadowProjectionResult:
    trigger = _find_trigger_event_for_run(run_id=str(run_id), company_id=company_id)
    if trigger is None:
        raise ValueError(f"No existe trigger CEC.CloseRunPackaged para run_id={run_id}.")
    return project_close_run_from_trigger(trigger_event=trigger)


def _lock_or_create_inbox(*, event: OutboxEvent) -> InboxEvent:
    inbox, _ = create_or_get_inbox_event(
        event=event,
        consumer=PROJECTOR_CONSUMER,
        status=InboxEvent.Status.RECEIVED,
    )
    return inbox


def project_pending_shadow_ledger_triggers(*, limit: int = 100, company_id: int | None = None) -> ShadowProjectionBatchResult:
    qs = OutboxEvent.objects.filter(source_module="CEC", event_type="CloseRunPackaged").order_by("occurred_at", "id")
    if company_id is not None:
        qs = qs.filter(company_id=company_id)
    rows = list(qs[: int(limit)])

    attempted = processed = blocked = skipped = failed = 0
    for trigger in rows:
        attempted += 1
        run_id = _run_id_from_trigger(trigger)
        if not run_id:
            skipped += 1
            continue

        inbox = _lock_or_create_inbox(event=trigger)
        if inbox.status == InboxEvent.Status.PROCESSED:
            skipped += 1
            continue

        run = CloseRun.objects.filter(run_id=run_id).only("id", "status").first()
        if run is None:
            inbox.status = InboxEvent.Status.FAILED
            inbox.last_error = f"CloseRun {run_id} no existe."[:255]
            inbox.processed_at = None
            inbox.save(update_fields=["status", "last_error", "processed_at"])
            failed += 1
            continue
        if run.status != CloseRun.Status.PACKAGED:
            # Trigger ya no proyectable (por ejemplo, corrida bloqueada y reabierta).
            inbox.status = InboxEvent.Status.PROCESSED
            inbox.last_error = f"SKIPPED_NON_PACKAGED:{run.status}"[:255]
            inbox.processed_at = timezone.now()
            inbox.save(update_fields=["status", "last_error", "processed_at"])
            skipped += 1
            continue

        try:
            result = project_close_run_from_trigger(trigger_event=trigger)
            inbox.status = InboxEvent.Status.PROCESSED
            inbox.last_error = ""
            inbox.processed_at = timezone.now()
            inbox.save(update_fields=["status", "last_error", "processed_at"])
            processed += 1
            if result.blocked:
                blocked += 1
        except DomainError as exc:
            logger.warning(
                "shadow_ledger projector domain error",
                extra={
                    "request_id": str(trigger.correlation_id or ""),
                    "company_id": trigger.company_id,
                    "branch_id": trigger.branch_id,
                    "event_id": str(trigger.event_id),
                    "command_id": str(trigger.event_id),
                    "consumer": PROJECTOR_CONSUMER,
                    "error_code": exc.code,
                },
            )
            inbox.status = InboxEvent.Status.FAILED
            inbox.last_error = f"{exc.code}:{exc.message}"[:255]
            inbox.processed_at = None
            inbox.save(update_fields=["status", "last_error", "processed_at"])
            failed += 1
        except Exception as exc:  # noqa: BLE001
            wrapped = IntegrationError(
                "Unexpected projector failure.",
                code="SHADOW_PROJECTOR_UNHANDLED",
                context={
                    "request_id": str(trigger.correlation_id or ""),
                    "company_id": trigger.company_id,
                    "branch_id": trigger.branch_id,
                    "event_id": str(trigger.event_id),
                    "command_id": str(trigger.event_id),
                },
            )
            logger.exception(
                "shadow_ledger projector unhandled error",
                extra={
                    **wrapped.context,
                    "consumer": PROJECTOR_CONSUMER,
                    "source_module": str(trigger.source_module),
                    "event_type": str(trigger.event_type),
                },
            )
            inbox.status = InboxEvent.Status.FAILED
            inbox.last_error = f"{wrapped.code}:{exc}"[:255]
            inbox.processed_at = None
            inbox.save(update_fields=["status", "last_error", "processed_at"])
            failed += 1

    return ShadowProjectionBatchResult(
        attempted=int(attempted),
        processed=int(processed),
        blocked=int(blocked),
        skipped=int(skipped),
        failed=int(failed),
    )


def build_rules_json_v1() -> dict[str, Any]:
    return {
        "version": "1.0",
        "fiscal_mode": "BOTH",
        "rules": [
            {
                "id": "billing_invoice_issued",
                "source_module": "BILLING",
                "event_type": "DocumentIssued",
                "when": {"doc_type": "INVOICE"},
                "lines": [
                    {"account": "1101", "side": "DEBIT", "amount_from": "total", "sign": 1},
                    {"account": "4101", "side": "CREDIT", "amount_from": "subtotal", "sign": 1},
                    {"account": "2101", "side": "CREDIT", "amount_from": "tax_total", "sign": 1},
                ],
            },
            {
                "id": "billing_credit_note_issued",
                "source_module": "BILLING",
                "event_type": "DocumentIssued",
                "when": {"doc_type": "CREDIT_NOTE"},
                "lines": [
                    {"account": "4102", "side": "DEBIT", "amount_from": "subtotal", "sign": 1},
                    {"account": "2101", "side": "DEBIT", "amount_from": "tax_total", "sign": 1},
                    {"account": "1101", "side": "CREDIT", "amount_from": "total", "sign": 1},
                ],
            },
            {
                "id": "billing_invoice_voided",
                "source_module": "BILLING",
                "event_type": "DocumentVoided",
                "when": {"doc_type": "INVOICE"},
                "lines": [
                    {"account": "4102", "side": "DEBIT", "amount_from": "subtotal", "sign": 1},
                    {"account": "2101", "side": "DEBIT", "amount_from": "tax_total", "sign": 1},
                    {"account": "1101", "side": "CREDIT", "amount_from": "total", "sign": 1},
                ],
            },
            {
                "id": "billing_credit_note_voided",
                "source_module": "BILLING",
                "event_type": "DocumentVoided",
                "when": {"doc_type": "CREDIT_NOTE"},
                "lines": [
                    {"account": "1101", "side": "DEBIT", "amount_from": "total", "sign": 1},
                    {"account": "4102", "side": "CREDIT", "amount_from": "subtotal", "sign": 1},
                    {"account": "2101", "side": "CREDIT", "amount_from": "tax_total", "sign": 1},
                ],
            },
            {
                "id": "procurement_supplier_invoice_posted",
                "source_module": "PROCUREMENT",
                "event_type": "ProcurementDocumentPosted",
                "when": {"doc_type": "SUPPLIER_INVOICE"},
                "lines": [
                    {"account": "1201", "side": "DEBIT", "amount_from": "subtotal_abs", "sign": 1},
                    {"account": "2101", "side": "DEBIT", "amount_from": "tax_total_abs", "sign": 1},
                    {"account": "2205", "side": "CREDIT", "amount_from": "total_abs", "sign": 1},
                ],
            },
            {
                "id": "procurement_supplier_credit_note_posted",
                "source_module": "PROCUREMENT",
                "event_type": "ProcurementDocumentPosted",
                "when": {"doc_type": "SUPPLIER_CREDIT_NOTE"},
                "lines": [
                    {"account": "2205", "side": "DEBIT", "amount_from": "total_abs", "sign": 1},
                    {"account": "1201", "side": "CREDIT", "amount_from": "subtotal_abs", "sign": 1},
                    {"account": "2101", "side": "CREDIT", "amount_from": "tax_total_abs", "sign": 1},
                ],
            },
            {
                "id": "procurement_goods_receipt_posted",
                "source_module": "PROCUREMENT",
                "event_type": "ProcurementDocumentPosted",
                "when": {"doc_type": "GOODS_RECEIPT"},
                "lines": [
                    {"account": "1201", "side": "DEBIT", "amount_from": "total_abs", "sign": 1},
                    {"account": "2205", "side": "CREDIT", "amount_from": "total_abs", "sign": 1},
                ],
            },
            {
                "id": "procurement_supplier_payment_posted",
                "source_module": "PROCUREMENT",
                "event_type": "ProcurementDocumentPosted",
                "when": {"doc_type": "SUPPLIER_PAYMENT"},
                "lines": [
                    {"account": "2205", "side": "DEBIT", "amount_from": "total_abs", "sign": 1},
                    {"account": "1101", "side": "CREDIT", "amount_from": "total_abs", "sign": 1},
                ],
            },
            {
                "id": "procurement_adjustment_posted",
                "source_module": "PROCUREMENT",
                "event_type": "ProcurementDocumentPosted",
                "when": {"doc_type": "ADJUSTMENT"},
                "lines": [
                    {"account": "1201", "side": "DEBIT", "amount_from": "total_abs", "sign": 1},
                    {"account": "1201", "side": "CREDIT", "amount_from": "total_abs", "sign": 1},
                ],
            },
            {
                "id": "procurement_supplier_invoice_voided",
                "source_module": "PROCUREMENT",
                "event_type": "ProcurementDocumentVoided",
                "when": {"doc_type": "SUPPLIER_INVOICE"},
                "lines": [
                    {"account": "2205", "side": "DEBIT", "amount_from": "total_abs", "sign": 1},
                    {"account": "1201", "side": "CREDIT", "amount_from": "subtotal_abs", "sign": 1},
                    {"account": "2101", "side": "CREDIT", "amount_from": "tax_total_abs", "sign": 1},
                ],
            },
            {
                "id": "procurement_supplier_credit_note_voided",
                "source_module": "PROCUREMENT",
                "event_type": "ProcurementDocumentVoided",
                "when": {"doc_type": "SUPPLIER_CREDIT_NOTE"},
                "lines": [
                    {"account": "1201", "side": "DEBIT", "amount_from": "subtotal_abs", "sign": 1},
                    {"account": "2101", "side": "DEBIT", "amount_from": "tax_total_abs", "sign": 1},
                    {"account": "2205", "side": "CREDIT", "amount_from": "total_abs", "sign": 1},
                ],
            },
            {
                "id": "procurement_goods_receipt_voided",
                "source_module": "PROCUREMENT",
                "event_type": "ProcurementDocumentVoided",
                "when": {"doc_type": "GOODS_RECEIPT"},
                "lines": [
                    {"account": "2205", "side": "DEBIT", "amount_from": "total_abs", "sign": 1},
                    {"account": "1201", "side": "CREDIT", "amount_from": "total_abs", "sign": 1},
                ],
            },
            {
                "id": "procurement_supplier_payment_voided",
                "source_module": "PROCUREMENT",
                "event_type": "ProcurementDocumentVoided",
                "when": {"doc_type": "SUPPLIER_PAYMENT"},
                "lines": [
                    {"account": "1101", "side": "DEBIT", "amount_from": "total_abs", "sign": 1},
                    {"account": "2205", "side": "CREDIT", "amount_from": "total_abs", "sign": 1},
                ],
            },
            {
                "id": "procurement_adjustment_voided",
                "source_module": "PROCUREMENT",
                "event_type": "ProcurementDocumentVoided",
                "when": {"doc_type": "ADJUSTMENT"},
                "lines": [
                    {"account": "1201", "side": "DEBIT", "amount_from": "total_abs", "sign": 1},
                    {"account": "1201", "side": "CREDIT", "amount_from": "total_abs", "sign": 1},
                ],
            },
            {
                "id": "inventory_receive",
                "source_module": "INVENTORY",
                "event_type": "InventoryMovementPosted",
                "when": {"movement_type": "RECEIVE"},
                "lines": [
                    {"account": "1201", "side": "DEBIT", "amount_from": "total_cost_abs", "sign": 1},
                    {"account": "2205", "side": "CREDIT", "amount_from": "total_cost_abs", "sign": 1},
                ],
            },
            {
                "id": "inventory_issue",
                "source_module": "INVENTORY",
                "event_type": "InventoryMovementPosted",
                "when": {"movement_type": "ISSUE"},
                "lines": [
                    {"account": "5101", "side": "DEBIT", "amount_from": "total_cost_abs", "sign": 1},
                    {"account": "1201", "side": "CREDIT", "amount_from": "total_cost_abs", "sign": 1},
                ],
            },
            {
                "id": "inventory_adjust_increase",
                "source_module": "INVENTORY",
                "event_type": "InventoryAdjusted",
                "when": {"is_adjust_increase": True},
                "lines": [
                    {"account": "1201", "side": "DEBIT", "amount_from": "adjust_total_cost_abs", "sign": 1},
                    {"account": "4206", "side": "CREDIT", "amount_from": "adjust_total_cost_abs", "sign": 1},
                ],
            },
            {
                "id": "inventory_adjust_decrease",
                "source_module": "INVENTORY",
                "event_type": "InventoryAdjusted",
                "when": {"is_adjust_decrease": True},
                "lines": [
                    {"account": "5102", "side": "DEBIT", "amount_from": "adjust_total_cost_abs", "sign": 1},
                    {"account": "1201", "side": "CREDIT", "amount_from": "adjust_total_cost_abs", "sign": 1},
                ],
            },
            {
                "id": "inventory_transfer_internal",
                "source_module": "INVENTORY",
                "event_type": "InventoryTransferCompleted",
                "when": {},
                "lines": [
                    {"account": "1201", "side": "DEBIT", "amount_from": "transfer_total_cost_abs", "sign": 1},
                    {"account": "1201", "side": "CREDIT", "amount_from": "transfer_total_cost_abs", "sign": 1},
                ],
            },
            {
                "id": "cash_movement_income",
                "source_module": "PAYMENTS",
                "event_type": "CashMovementPosted",
                "when": {"movement_type": "INCOME"},
                "lines": [
                    {"account": "1102", "side": "DEBIT", "amount_from": "amount_abs", "sign": 1},
                    {"account": "1101", "side": "CREDIT", "amount_from": "amount_abs", "sign": 1},
                ],
            },
            {
                "id": "cash_movement_expense",
                "source_module": "PAYMENTS",
                "event_type": "CashMovementPosted",
                "when": {"movement_type": "EXPENSE"},
                "lines": [
                    {"account": "6102", "side": "DEBIT", "amount_from": "amount_abs", "sign": 1},
                    {"account": "1102", "side": "CREDIT", "amount_from": "amount_abs", "sign": 1},
                ],
            },
            {
                "id": "cash_movement_refund",
                "source_module": "PAYMENTS",
                "event_type": "CashMovementPosted",
                "when": {"movement_type": "REFUND"},
                "lines": [
                    {"account": "4102", "side": "DEBIT", "amount_from": "amount_abs", "sign": 1},
                    {"account": "1102", "side": "CREDIT", "amount_from": "amount_abs", "sign": 1},
                ],
            },
            {
                "id": "cash_movement_adjustment",
                "source_module": "PAYMENTS",
                "event_type": "CashMovementPosted",
                "when": {"movement_type": "ADJUSTMENT"},
                "lines": [
                    {"account": "1102", "side": "DEBIT", "amount_from": "amount_abs", "sign": 1},
                    {"account": "1102", "side": "CREDIT", "amount_from": "amount_abs", "sign": 1},
                ],
            },
            {
                "id": "cash_session_short",
                "source_module": "PAYMENTS",
                "event_type": "CashSessionClosed",
                "when": {"difference_is_short": True},
                "lines": [
                    {"account": "6103", "side": "DEBIT", "amount_from": "difference_abs", "sign": 1},
                    {"account": "1102", "side": "CREDIT", "amount_from": "difference_abs", "sign": 1},
                ],
            },
            {
                "id": "cash_session_over",
                "source_module": "PAYMENTS",
                "event_type": "CashSessionClosed",
                "when": {"difference_is_over": True},
                "lines": [
                    {"account": "1102", "side": "DEBIT", "amount_from": "difference_abs", "sign": 1},
                    {"account": "4205", "side": "CREDIT", "amount_from": "difference_abs", "sign": 1},
                ],
            },
        ],
    }


def seed_posting_rules_v1_for_company(*, company) -> tuple[PostingRuleSet, bool]:
    rules_json = build_rules_json_v1()
    latest = (
        PostingRuleSet.objects.filter(code="shadow_ledger_v1", scope_company=company)
        .order_by("-version", "-id")
        .first()
    )
    if latest and latest.rules_json == rules_json and latest.status == PostingRuleSet.Status.ACTIVE:
        return latest, False

    # uq_acc_posting_rule_code_version es global por (code, version),
    # así que la siguiente versión debe calcularse a nivel de code, no por compañía.
    global_latest = PostingRuleSet.objects.filter(code="shadow_ledger_v1").order_by("-version", "-id").first()
    next_version = int(global_latest.version + 1) if global_latest else 1
    PostingRuleSet.objects.filter(
        code="shadow_ledger_v1",
        scope_company=company,
        status=PostingRuleSet.Status.ACTIVE,
    ).update(status=PostingRuleSet.Status.DEPRECATED)

    created = PostingRuleSet.objects.create(
        code="shadow_ledger_v1",
        version=next_version,
        status=PostingRuleSet.Status.ACTIVE,
        fiscal_mode=PostingRuleSet.FiscalMode.BOTH,
        scope_company=company,
        rules_json=rules_json,
        effective_from=timezone.now(),
    )
    return created, True


@dataclass(frozen=True)
class PostingBatchResult:
    attempted: int
    approved: int
    posted: int
    skipped: int
    failed: int
    errors: list[dict[str, str]]


@dataclass(frozen=True)
class ApprovalBatchResult:
    attempted: int
    approved: int
    skipped: int
    failed: int
    errors: list[dict[str, str]]


@dataclass(frozen=True)
class PeriodCloseResult:
    company_id: int
    year: int
    month: int
    status: str
    pending_drafts: int
    period_id: int
    was_already_closed: bool
    gate_summary: dict[str, Any]
    force_applied: bool


@dataclass(frozen=True)
class PeriodCloseGateEvaluation:
    pending_drafts_count: int
    failed_outbox_count: int
    reconciliation_mismatch_count: int
    draft_exception_count: int
    pending_operational_events_count: int
    force_applied: bool
    blocked: bool
    blocking_reasons: list[str]
    failed_outbox_sample: list[dict[str, Any]]
    period_start: str
    period_end: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "pending_drafts_count": int(self.pending_drafts_count),
            "failed_outbox_count": int(self.failed_outbox_count),
            "reconciliation_mismatch_count": int(self.reconciliation_mismatch_count),
            "draft_exception_count": int(self.draft_exception_count),
            "pending_operational_events_count": int(self.pending_operational_events_count),
            "force_applied": bool(self.force_applied),
            "blocked": bool(self.blocked),
            "blocking_reasons": list(self.blocking_reasons),
            "failed_outbox_sample": list(self.failed_outbox_sample),
            "period_start": str(self.period_start),
            "period_end": str(self.period_end),
        }


@dataclass(frozen=True)
class JournalReversalResult:
    original_entry_id: int
    reversal_entry_id: int
    period_id: int
    period_year: int
    period_month: int
    idempotent: bool


@dataclass(frozen=True)
class JournalReversalBatchResult:
    attempted: int
    reversed: int
    idempotent: int
    failed: int
    errors: list[dict[str, str]]


def _period_for_occurrence(*, company, occurred_at) -> FiscalPeriod:
    local_occurrence = timezone.localtime(occurred_at)
    period, _ = FiscalPeriod.objects.get_or_create(
        company=company,
        year=int(local_occurrence.year),
        month=int(local_occurrence.month),
        defaults={"status": FiscalPeriod.Status.OPEN},
    )
    return period


def _period_date_bounds(*, year: int, month: int) -> tuple[date, date]:
    if month < 1 or month > 12:
        raise ValueError("month debe estar en rango 1..12.")
    start = date(int(year), int(month), 1)
    if int(month) == 12:
        end = date(int(year) + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(int(year), int(month) + 1, 1) - timedelta(days=1)
    return start, end


def _period_datetime_bounds(*, date_from: date, date_to: date) -> tuple[datetime, datetime]:
    tz = timezone.get_current_timezone()
    dt_from = timezone.make_aware(datetime.combine(date_from, time.min), tz)
    dt_to = timezone.make_aware(datetime.combine(date_to, time.max), tz)
    return dt_from, dt_to


def _period_close_block_message(*, year: int, month: int, gate: PeriodCloseGateEvaluation) -> str:
    parts: list[str] = []
    if gate.pending_drafts_count > 0 and not gate.force_applied:
        parts.append(f"drafts pendientes={gate.pending_drafts_count}")
    if gate.failed_outbox_count > 0:
        parts.append(f"outbox fallido={gate.failed_outbox_count}")
    if gate.reconciliation_mismatch_count > 0:
        parts.append(f"descuadres reconciliación={gate.reconciliation_mismatch_count}")
    if gate.draft_exception_count > 0:
        parts.append(f"drafts en excepción={gate.draft_exception_count}")
    if gate.pending_operational_events_count > 0:
        parts.append(f"eventos operacionales pendientes={gate.pending_operational_events_count}")
    details = "; ".join(parts) if parts else "gates de cierre no superados"
    return f"No se puede cerrar periodo {year}-{month:02d}: {details}."


def _zero_gate_summary(*, year: int, month: int, force: bool) -> dict[str, Any]:
    date_from, date_to = _period_date_bounds(year=int(year), month=int(month))
    return {
        "pending_drafts_count": 0,
        "failed_outbox_count": 0,
        "reconciliation_mismatch_count": 0,
        "draft_exception_count": 0,
        "pending_operational_events_count": 0,
        "force_applied": bool(force),
        "blocked": False,
        "blocking_reasons": [],
        "failed_outbox_sample": [],
        "period_start": str(date_from),
        "period_end": str(date_to),
    }


def evaluate_period_close_gates(
    *,
    company,
    year: int,
    month: int,
    force: bool = False,
    max_failed_outbox_sample: int = 20,
) -> PeriodCloseGateEvaluation:
    date_from, date_to = _period_date_bounds(year=int(year), month=int(month))
    dt_from, dt_to = _period_datetime_bounds(date_from=date_from, date_to=date_to)

    pending_states = [
        JournalDraft.State.GENERATED,
        JournalDraft.State.VALIDATED,
        JournalDraft.State.EXCEPTION,
        JournalDraft.State.APPROVED_FOR_POSTING,
    ]
    pending_drafts_count = int(
        JournalDraft.objects.filter(
            economic_event__company=company,
            economic_event__occurred_at__gte=dt_from,
            economic_event__occurred_at__lte=dt_to,
            state__in=pending_states,
        ).count()
    )

    failed_outbox_qs = OutboxEvent.objects.filter(
        company=company,
        source_module__in=list(PERIOD_CLOSE_FAILED_OUTBOX_MODULES),
        status=OutboxEvent.Status.FAILED,
        occurred_at__gte=dt_from,
        occurred_at__lte=dt_to,
    ).order_by("-occurred_at", "-id")
    failed_outbox_count = int(failed_outbox_qs.count())
    failed_outbox_sample = [
        {
            "event_id": str(row.event_id),
            "source_module": str(row.source_module),
            "event_type": str(row.event_type),
            "occurred_at": row.occurred_at.isoformat() if row.occurred_at else "",
            "attempt_count": int(row.attempt_count),
            "last_error": str(row.last_error or ""),
        }
        for row in failed_outbox_qs[: int(max_failed_outbox_sample)]
    ]

    reconciliation = reconcile_operational_vs_accounting(
        company=company,
        date_from=date_from,
        date_to=date_to,
    )
    rec_summary = reconciliation.get("summary", {}) if isinstance(reconciliation, dict) else {}
    draft_exception_count = int(rec_summary.get("drafts_exception") or 0)
    pending_operational_events_count = int(rec_summary.get("pending_operational_events") or 0)

    reconciliation_mismatch_count = 0
    by_event_type = reconciliation.get("by_event_type", []) if isinstance(reconciliation, dict) else []
    if isinstance(by_event_type, list):
        for row in by_event_type:
            if not isinstance(row, dict):
                continue
            operational_count = int(row.get("operational_count") or 0)
            linked_count = int(row.get("linked_count") or 0)
            operational_amount = _q_money(_to_decimal(row.get("operational_amount")))
            draft_amount = _q_money(_to_decimal(row.get("draft_amount")))
            if operational_count != linked_count or operational_amount != draft_amount:
                reconciliation_mismatch_count += 1

    blocking_reasons: list[str] = []
    if pending_drafts_count > 0 and not bool(force):
        blocking_reasons.append("PENDING_DRAFTS")
    if failed_outbox_count > 0:
        blocking_reasons.append("FAILED_OUTBOX")
    if reconciliation_mismatch_count > 0:
        blocking_reasons.append("RECONCILIATION_MISMATCH")
    if draft_exception_count > 0:
        blocking_reasons.append("DRAFT_EXCEPTION")
    if pending_operational_events_count > 0:
        blocking_reasons.append("PENDING_OPERATIONAL_EVENTS")

    return PeriodCloseGateEvaluation(
        pending_drafts_count=int(pending_drafts_count),
        failed_outbox_count=int(failed_outbox_count),
        reconciliation_mismatch_count=int(reconciliation_mismatch_count),
        draft_exception_count=int(draft_exception_count),
        pending_operational_events_count=int(pending_operational_events_count),
        force_applied=bool(force),
        blocked=bool(blocking_reasons),
        blocking_reasons=blocking_reasons,
        failed_outbox_sample=failed_outbox_sample,
        period_start=str(date_from),
        period_end=str(date_to),
    )


def _posting_candidates_qs(*, company_id: int | None, run_id: str, require_approved: bool):
    states = [JournalDraft.State.VALIDATED, JournalDraft.State.APPROVED_FOR_POSTING]

    qs = JournalDraft.objects.select_related(
        "economic_event",
        "economic_event__company",
        "economic_event__branch",
    ).filter(
        state__in=states,
    )
    if company_id is not None:
        qs = qs.filter(economic_event__company_id=int(company_id))
    if run_id:
        qs = qs.filter(close_run_id=str(run_id))
    return qs.order_by("generated_at", "id")


def _reverse_batch_candidates_qs(
    *,
    company_id: int,
    run_id: str = "",
    year: int | None = None,
    month: int | None = None,
    entry_ids: list[int] | None = None,
):
    qs = JournalEntry.objects.filter(
        company_id=int(company_id),
        is_posted=True,
        reversed_entry__isnull=True,
    )
    if entry_ids:
        qs = qs.filter(id__in=entry_ids)
    elif run_id:
        qs = qs.filter(draft__close_run_id=str(run_id))
    elif year is not None and month is not None:
        qs = qs.filter(period__year=int(year), period__month=int(month))
    return qs.order_by("id")


def _reverse_lines(lines_json: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], Decimal, Decimal]:
    reversed_lines: list[dict[str, Any]] = []
    total_debit = Decimal("0.00")
    total_credit = Decimal("0.00")

    for idx, line in enumerate(lines_json):
        if not isinstance(line, dict):
            raise AccountingConflictError(f"Linea inválida en draft original (index={idx}).")
        side = str(line.get("side") or "").upper()
        if side not in ("DEBIT", "CREDIT"):
            raise AccountingConflictError(f"Linea inválida sin side contable (index={idx}).")
        new_side = "CREDIT" if side == "DEBIT" else "DEBIT"
        amount = _q_money(abs(_to_decimal(line.get("amount"))))
        debit = amount if new_side == "DEBIT" else Decimal("0.00")
        credit = amount if new_side == "CREDIT" else Decimal("0.00")
        total_debit += debit
        total_credit += credit

        reversed_lines.append(
            {
                **line,
                "side": new_side,
                "amount": str(amount),
                "debit": str(debit),
                "credit": str(credit),
            }
        )

    return reversed_lines, _q_money(total_debit), _q_money(total_credit)


def approve_journal_drafts(
    *,
    company_id: int | None = None,
    run_id: str = "",
    limit: int = 200,
    require_passed_validation: bool = True,
    actor_user=None,
) -> ApprovalBatchResult:
    run_id = str(run_id or "").strip()
    qs = JournalDraft.objects.select_related("economic_event").filter(state=JournalDraft.State.VALIDATED)
    if company_id is not None:
        qs = qs.filter(economic_event__company_id=int(company_id))
    if run_id:
        qs = qs.filter(close_run_id=run_id)
    rows = list(qs.order_by("generated_at", "id")[: int(limit)])

    attempted = approved = skipped = failed = 0
    errors: list[dict[str, str]] = []

    for row in rows:
        attempted += 1
        with transaction.atomic():
            draft = JournalDraft.objects.select_for_update().get(pk=row.pk)
            if draft.state != JournalDraft.State.VALIDATED:
                skipped += 1
                continue

            if require_passed_validation:
                result = DraftValidationResult.objects.filter(draft=draft).first()
                if result is None or not bool(result.passed):
                    failed += 1
                    errors.append(
                        {
                            "draft_id": str(draft.id),
                            "error": "Draft sin validación aprobada.",
                        }
                    )
                    continue

            draft.state = JournalDraft.State.APPROVED_FOR_POSTING
            draft.approved_at = timezone.now()
            draft.approved_by = actor_user
            draft.save(update_fields=["state", "approved_at", "approved_by"])
            approved += 1

            publish_outbox_event(
                source_module="ACCOUNTING",
                event_type="JournalDraftApproved",
                payload={
                    "journal_draft_id": draft.id,
                    "economic_event_id": draft.economic_event_id,
                    "run_id": draft.close_run_id,
                },
                company=draft.economic_event.company,
                branch=draft.economic_event.branch,
                actor_user=actor_user,
            )

    return ApprovalBatchResult(
        attempted=int(attempted),
        approved=int(approved),
        skipped=int(skipped),
        failed=int(failed),
        errors=errors,
    )


def post_journal_drafts(
    *,
    company_id: int | None = None,
    run_id: str = "",
    limit: int = 200,
    require_approved: bool = False,
    auto_approve: bool = False,
    allow_same_approver: bool = False,
    actor_user=None,
) -> PostingBatchResult:
    run_id = str(run_id or "").strip()
    if run_id:
        run = CloseRun.objects.filter(run_id=run_id).only("run_id", "status").first()
        if run is None:
            raise ValueError(f"CloseRun {run_id} no existe.")
        if run.status != CloseRun.Status.PACKAGED:
            raise AccountingConflictError(f"CloseRun {run_id} debe estar PACKAGED para posting.")

    attempted = approved = posted = skipped = failed = 0
    errors: list[dict[str, str]] = []
    rows = list(_posting_candidates_qs(company_id=company_id, run_id=run_id, require_approved=require_approved)[: int(limit)])

    for row in rows:
        attempted += 1
        with transaction.atomic():
            draft = JournalDraft.objects.select_for_update().get(pk=row.pk)

            if require_approved and draft.state != JournalDraft.State.APPROVED_FOR_POSTING:
                if auto_approve and draft.state == JournalDraft.State.VALIDATED:
                    draft.state = JournalDraft.State.APPROVED_FOR_POSTING
                    draft.approved_at = timezone.now()
                    draft.approved_by = actor_user
                    draft.save(update_fields=["state", "approved_at", "approved_by"])
                    approved += 1
                else:
                    skipped += 1
                    continue
            elif auto_approve and draft.state == JournalDraft.State.VALIDATED:
                draft.state = JournalDraft.State.APPROVED_FOR_POSTING
                draft.approved_at = timezone.now()
                draft.approved_by = actor_user
                draft.save(update_fields=["state", "approved_at", "approved_by"])
                approved += 1

            if (
                actor_user is not None
                and draft.approved_by_id is not None
                and int(draft.approved_by_id) == int(actor_user.id)
                and not bool(allow_same_approver)
            ):
                failed += 1
                errors.append(
                    {
                        "draft_id": str(draft.id),
                        "error": "SoD: el mismo usuario no puede aprobar y postear el mismo draft.",
                    }
                )
                continue

            if draft.total_debit != draft.total_credit:
                failed += 1
                errors.append(
                    {
                        "draft_id": str(draft.id),
                        "error": "Draft no balanceado (debit != credit).",
                    }
                )
                continue

            period = _period_for_occurrence(
                company=draft.economic_event.company,
                occurred_at=draft.economic_event.occurred_at,
            )
            if period.status == FiscalPeriod.Status.CLOSED:
                failed += 1
                errors.append(
                    {
                        "draft_id": str(draft.id),
                        "error": f"Periodo cerrado: {period.year}-{period.month:02d}.",
                    }
                )
                continue

            cfg = get_or_create_accounting_config(company=draft.economic_event.company)
            phase7_enabled = bool(cfg.phase7_enabled)
            functional_currency = str(cfg.functional_currency or "NIO").upper() or "NIO"

            entry_date = timezone.localtime(draft.economic_event.occurred_at).date()
            description = f"{draft.economic_event.source_module}.{draft.economic_event.event_type}"
            entry, created = JournalEntry.objects.get_or_create(
                draft=draft,
                defaults={
                    "period": period,
                    "company": draft.economic_event.company,
                    "branch": draft.economic_event.branch,
                    "entry_date": entry_date,
                    "description": description,
                    "debit_total": draft.total_debit,
                    "credit_total": draft.total_credit,
                    "is_posted": True,
                    "posted_at": timezone.now(),
                    "posted_by": actor_user,
                    "metadata": {
                        "close_run_id": draft.close_run_id,
                        "input_manifest_hash": draft.input_manifest_hash,
                        "contract_version": draft.contract_version,
                        "schema_version": int(draft.schema_version),
                        "economic_event_id": int(draft.economic_event_id),
                    },
                },
            )
            if not created:
                if draft.state != JournalDraft.State.POSTED:
                    draft.state = JournalDraft.State.POSTED
                    draft.posted_at = entry.posted_at
                    draft.save(update_fields=["state", "posted_at"])
                if phase7_enabled and not entry.lines.exists():
                    failed += 1
                    errors.append(
                        {
                            "draft_id": str(draft.id),
                            "error": f"GL Fase7: JournalEntry {entry.id} existe sin JournalEntryLine.",
                        }
                    )
                else:
                    skipped += 1
                continue

            if phase7_enabled:
                try:
                    ensure_journal_entry_lines(
                        entry=entry,
                        draft=draft,
                        functional_currency=functional_currency,
                    )
                except Phase7ValidationError as exc:
                    entry.delete()
                    failed += 1
                    errors.append(
                        {
                            "draft_id": str(draft.id),
                            "error": f"GL Fase7 invalid: {exc}",
                        }
                    )
                    continue

            draft.state = JournalDraft.State.POSTED
            draft.posted_at = entry.posted_at
            draft.save(update_fields=["state", "posted_at"])
            posted += 1

            publish_outbox_event(
                source_module="ACCOUNTING",
                event_type="JournalPosted",
                payload={
                    "journal_entry_id": entry.id,
                    "journal_draft_id": draft.id,
                    "economic_event_id": draft.economic_event_id,
                    "run_id": draft.close_run_id,
                    "period_year": int(period.year),
                    "period_month": int(period.month),
                    "debit_total": str(entry.debit_total),
                    "credit_total": str(entry.credit_total),
                    "entry_date": str(entry.entry_date),
                },
                company=draft.economic_event.company,
                branch=draft.economic_event.branch,
                actor_user=actor_user,
            )

    return PostingBatchResult(
        attempted=int(attempted),
        approved=int(approved),
        posted=int(posted),
        skipped=int(skipped),
        failed=int(failed),
        errors=errors,
    )


def close_fiscal_period(
    *,
    company_id: int,
    year: int,
    month: int,
    force: bool = False,
    allow_same_poster: bool = False,
    actor_user=None,
) -> PeriodCloseResult:
    company = OrgUnit.objects.filter(
        id=int(company_id),
        unit_type=OrgUnit.UnitType.COMPANY,
        is_active=True,
    ).first()
    if company is None:
        raise ValueError(f"company inválida o inactiva: {company_id}")
    if month < 1 or month > 12:
        raise ValueError("month debe estar en rango 1..12.")

    gate_block_summary: dict[str, Any] | None = None
    with transaction.atomic():
        period, _ = FiscalPeriod.objects.select_for_update().get_or_create(
            company=company,
            year=int(year),
            month=int(month),
            defaults={"status": FiscalPeriod.Status.OPEN},
        )
        if period.status == FiscalPeriod.Status.CLOSED:
            empty_gate = _zero_gate_summary(
                year=int(year),
                month=int(month),
                force=bool(force),
            )
            return PeriodCloseResult(
                company_id=int(company.id),
                year=int(year),
                month=int(month),
                status=period.status,
                pending_drafts=0,
                period_id=int(period.id),
                was_already_closed=True,
                gate_summary=empty_gate,
                force_applied=bool(force),
            )

        gate_eval = evaluate_period_close_gates(
            company=company,
            year=int(year),
            month=int(month),
            force=bool(force),
        )
        gate_summary = gate_eval.as_dict()
        pending_count = int(gate_eval.pending_drafts_count)
        if gate_eval.blocked:
            gate_block_summary = gate_summary
        else:
            if actor_user is not None and not bool(allow_same_poster):
                posted_by_actor = JournalEntry.objects.filter(
                    company=company,
                    period=period,
                    is_posted=True,
                    posted_by=actor_user,
                ).exists()
                if posted_by_actor:
                    raise AccountingConflictError(
                        f"SoD: usuario {actor_user.id} no puede cerrar periodo {year}-{month:02d} si posteó asientos en el mismo periodo."
                    )
                revaluation_by_actor = RevaluationRun.objects.filter(
                    company=company,
                    year=int(year),
                    month=int(month),
                    status=RevaluationRun.Status.COMPLETED,
                    executed_by=actor_user,
                ).exists()
                if revaluation_by_actor:
                    raise AccountingConflictError(
                        f"SoD: usuario {actor_user.id} no puede cerrar periodo {year}-{month:02d} si ejecutó revaluación FX en el mismo periodo."
                    )

            period.status = FiscalPeriod.Status.CLOSED
            period.closed_at = timezone.now()
            period.closed_by = actor_user
            period.save(update_fields=["status", "closed_at", "closed_by"])

            publish_outbox_event(
                source_module="ACCOUNTING",
                event_type="PeriodClosed",
                payload={
                    "company_id": int(company.id),
                    "year": int(year),
                    "month": int(month),
                    "pending_drafts_count": int(pending_count),
                    "forced": bool(force),
                    "gate_summary": gate_summary,
                },
                company=company,
                actor_user=actor_user,
            )

            return PeriodCloseResult(
                company_id=int(company.id),
                year=int(year),
                month=int(month),
                status=period.status,
                pending_drafts=int(pending_count),
                period_id=int(period.id),
                was_already_closed=False,
                gate_summary=gate_summary,
                force_applied=bool(force),
            )

    if gate_block_summary is not None:
        publish_outbox_event(
            source_module="ACCOUNTING",
            event_type="PeriodCloseBlocked",
            payload={
                "company_id": int(company.id),
                "year": int(year),
                "month": int(month),
                "gate_summary": gate_block_summary,
            },
            company=company,
            actor_user=actor_user,
        )
        gate_for_msg = PeriodCloseGateEvaluation(
            pending_drafts_count=int(gate_block_summary.get("pending_drafts_count") or 0),
            failed_outbox_count=int(gate_block_summary.get("failed_outbox_count") or 0),
            reconciliation_mismatch_count=int(gate_block_summary.get("reconciliation_mismatch_count") or 0),
            draft_exception_count=int(gate_block_summary.get("draft_exception_count") or 0),
            pending_operational_events_count=int(gate_block_summary.get("pending_operational_events_count") or 0),
            force_applied=bool(gate_block_summary.get("force_applied")),
            blocked=bool(gate_block_summary.get("blocked")),
            blocking_reasons=[str(x) for x in gate_block_summary.get("blocking_reasons", [])],
            failed_outbox_sample=[],
            period_start=str(gate_block_summary.get("period_start") or ""),
            period_end=str(gate_block_summary.get("period_end") or ""),
        )
        exc = AccountingConflictError(
            _period_close_block_message(
                year=int(year),
                month=int(month),
                gate=gate_for_msg,
            )
        )
        setattr(exc, "gate_summary", gate_block_summary)
        raise exc


def reverse_journal_entry(
    *,
    company_id: int,
    journal_entry_id: int,
    reason: str,
    reversal_date=None,
    allow_same_poster: bool = False,
    actor_user=None,
) -> JournalReversalResult:
    reason_clean = str(reason or "").strip()
    if not reason_clean:
        raise ValueError("reason es requerido para reversa contable.")

    with transaction.atomic():
        original = (
            JournalEntry.objects.select_for_update()
            .filter(id=int(journal_entry_id), company_id=int(company_id), is_posted=True)
            .first()
        )
        if original is None:
            raise ValueError(f"JournalEntry {journal_entry_id} no existe en company={company_id}.")

        if original.reversed_entry_id is not None:
            raise AccountingConflictError(
                f"JournalEntry {journal_entry_id} ya es una reversa de {original.reversed_entry_id}; no se permite reversar una reversa."
            )

        existing = (
            JournalEntry.objects.select_for_update()
            .filter(company_id=int(company_id), reversed_entry=original, is_posted=True)
            .order_by("-id")
            .first()
        )
        if existing is not None:
            return JournalReversalResult(
                original_entry_id=int(original.id),
                reversal_entry_id=int(existing.id),
                period_id=int(existing.period_id),
                period_year=int(existing.period.year),
                period_month=int(existing.period.month),
                idempotent=True,
            )

        if (
            actor_user is not None
            and original.posted_by_id is not None
            and int(original.posted_by_id) == int(actor_user.id)
            and not bool(allow_same_poster)
        ):
            raise AccountingConflictError(
                f"SoD: usuario {actor_user.id} no puede reversar su propio JournalEntry {journal_entry_id} sin override."
            )

        if reversal_date is None:
            reversal_local_date = timezone.localdate()
        else:
            reversal_local_date = reversal_date
        reversal_dt = timezone.make_aware(
            datetime.combine(reversal_local_date, time(12, 0)),
            timezone.get_current_timezone(),
        )

        period, _ = FiscalPeriod.objects.select_for_update().get_or_create(
            company=original.company,
            year=int(reversal_local_date.year),
            month=int(reversal_local_date.month),
            defaults={"status": FiscalPeriod.Status.OPEN},
        )
        if period.status == FiscalPeriod.Status.CLOSED:
            raise AccountingConflictError(
                f"Periodo de reversa cerrado: {period.year}-{period.month:02d}."
            )

        original_lines = original.draft.lines_json if isinstance(original.draft.lines_json, list) else []
        if not original_lines:
            raise AccountingConflictError(
                f"JournalEntry {journal_entry_id} no tiene lines_json en draft para construir reversa."
            )
        reversed_lines, total_debit, total_credit = _reverse_lines(original_lines)
        if total_debit != total_credit:
            raise AccountingConflictError("Draft de reversa no balanceado (debit != credit).")

        reversal_event = EconomicEvent.objects.create(
            source_module="ACCOUNTING",
            event_type="JournalReversed",
            company=original.company,
            branch=original.branch,
            occurred_at=reversal_dt,
            contract_version=original.draft.contract_version,
            schema_version=int(original.draft.schema_version or 1),
            correlation_id=f"je-reversal-{original.id}",
            causation_id=str(original.id),
            payload={
                "source_module": "ACCOUNTING",
                "event_type": "JournalReversed",
                "schema_version": int(original.draft.schema_version or 1),
                "contract_version": original.draft.contract_version,
                "occurred_at": reversal_dt.isoformat(),
                "correlation_id": f"je-reversal-{original.id}",
                "causation_id": str(original.id),
                "close_run_id": original.draft.close_run_id,
                "source_outbox_event_id": "",
                "data": {
                    "original_journal_entry_id": int(original.id),
                    "reason": reason_clean,
                    "reversal_date": str(reversal_local_date),
                },
                "scope": {
                    "company_id": int(original.company_id),
                    "branch_id": original.branch_id,
                },
            },
            input_manifest_hash=original.draft.input_manifest_hash,
            close_run_id=original.draft.close_run_id,
        )

        reversal_draft = JournalDraft.objects.create(
            economic_event=reversal_event,
            rule_set=original.draft.rule_set,
            state=JournalDraft.State.POSTED,
            contract_version=original.draft.contract_version,
            schema_version=int(original.draft.schema_version or 1),
            close_run_id=original.draft.close_run_id,
            input_manifest_hash=original.draft.input_manifest_hash,
            lines_json=reversed_lines,
            total_debit=total_debit,
            total_credit=total_credit,
            validated_at=timezone.now(),
            approved_at=timezone.now(),
            approved_by=actor_user,
            posted_at=timezone.now(),
            metadata={
                "operation": "REVERSAL",
                "original_journal_entry_id": int(original.id),
                "reason": reason_clean,
                "reversal_date": str(reversal_local_date),
            },
        )

        reversal_entry = JournalEntry.objects.create(
            draft=reversal_draft,
            period=period,
            company=original.company,
            branch=original.branch,
            entry_date=reversal_local_date,
            description=f"REVERSAL OF JE#{original.id}",
            debit_total=total_debit,
            credit_total=total_credit,
            is_posted=True,
            posted_at=timezone.now(),
            posted_by=actor_user,
            reversed_entry=original,
            metadata={
                "operation": "REVERSAL",
                "original_journal_entry_id": int(original.id),
                "reason": reason_clean,
                "reversal_date": str(reversal_local_date),
            },
        )

        publish_outbox_event(
            source_module="ACCOUNTING",
            event_type="JournalReversed",
            payload={
                "original_journal_entry_id": int(original.id),
                "reversal_journal_entry_id": int(reversal_entry.id),
                "period_year": int(period.year),
                "period_month": int(period.month),
                "reason": reason_clean,
                "reversal_date": str(reversal_local_date),
            },
            company=original.company,
            branch=original.branch,
            actor_user=actor_user,
        )

        return JournalReversalResult(
            original_entry_id=int(original.id),
            reversal_entry_id=int(reversal_entry.id),
            period_id=int(period.id),
            period_year=int(period.year),
            period_month=int(period.month),
            idempotent=False,
        )


def reverse_journal_entries_batch(
    *,
    company_id: int,
    reason: str,
    run_id: str = "",
    year: int | None = None,
    month: int | None = None,
    entry_ids: list[int] | None = None,
    limit: int = 200,
    reversal_date=None,
    allow_same_poster: bool = False,
    actor_user=None,
) -> JournalReversalBatchResult:
    reason_clean = str(reason or "").strip()
    if not reason_clean:
        raise ValueError("reason es requerido para reversa masiva.")
    if int(limit) <= 0:
        raise ValueError("limit debe ser mayor que 0.")

    selectors = 0
    if str(run_id or "").strip():
        selectors += 1
    if year is not None or month is not None:
        if year is None or month is None:
            raise ValueError("year y month deben enviarse juntos.")
        selectors += 1
    if entry_ids:
        selectors += 1
    if selectors != 1:
        raise ValueError("Debe seleccionar exactamente un scope: run_id, (year+month) o entry_ids.")

    clean_ids: list[int] | None = None
    if entry_ids:
        clean_ids = sorted({int(x) for x in entry_ids if int(x) > 0})
        if not clean_ids:
            raise ValueError("entry_ids inválido.")

    candidates = list(
        _reverse_batch_candidates_qs(
            company_id=int(company_id),
            run_id=str(run_id or "").strip(),
            year=year,
            month=month,
            entry_ids=clean_ids,
        )
        .values_list("id", flat=True)[: int(limit)]
    )

    attempted = reversed_count = idempotent_count = failed = 0
    errors: list[dict[str, str]] = []

    for entry_id in candidates:
        attempted += 1
        try:
            result = reverse_journal_entry(
                company_id=int(company_id),
                journal_entry_id=int(entry_id),
                reason=reason_clean,
                reversal_date=reversal_date,
                allow_same_poster=bool(allow_same_poster),
                actor_user=actor_user,
            )
            if result.idempotent:
                idempotent_count += 1
            else:
                reversed_count += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            errors.append({"entry_id": str(entry_id), "error": str(exc)})

    return JournalReversalBatchResult(
        attempted=int(attempted),
        reversed=int(reversed_count),
        idempotent=int(idempotent_count),
        failed=int(failed),
        errors=errors,
    )


def reconcile_operational_vs_accounting(
    *,
    company,
    branch=None,
    date_from=None,
    date_to=None,
) -> dict[str, Any]:
    qs = OutboxEvent.objects.filter(
        company=company,
        source_module__in=["BILLING", "INVENTORY"],
        event_type__in=["DocumentIssued", "DocumentVoided", "InventoryMovementPosted", "InventoryAdjusted", "InventoryTransferCompleted"],
    )
    if branch is not None:
        qs = qs.filter(branch=branch)
    if date_from is not None:
        dt_from = timezone.make_aware(datetime.combine(date_from, time.min), timezone.get_current_timezone())
        qs = qs.filter(occurred_at__gte=dt_from)
    if date_to is not None:
        dt_to = timezone.make_aware(datetime.combine(date_to, time.max), timezone.get_current_timezone())
        qs = qs.filter(occurred_at__lte=dt_to)

    operational_events = list(qs.order_by("occurred_at", "id"))
    outbox_ids = [ev.event_id for ev in operational_events]

    economic_by_outbox = {
        row.source_outbox_event_id: row
        for row in EconomicEvent.objects.filter(company=company, source_outbox_event_id__in=outbox_ids)
    }
    drafts_by_event = {
        row.economic_event_id: row
        for row in JournalDraft.objects.select_related("economic_event").filter(economic_event_id__in=[ev.id for ev in economic_by_outbox.values()])
    }

    def _operational_amount(ev: OutboxEvent) -> Decimal:
        payload = ev.payload if isinstance(ev.payload, dict) else {}
        data = payload.get("data", {})
        if not isinstance(data, dict):
            data = {}
        if ev.source_module == "BILLING":
            return abs(_to_decimal(data.get("total")))
        if ev.event_type == "InventoryTransferCompleted":
            return abs(_to_decimal(data.get("transfer_total_cost") or (_to_decimal(data.get("qty")) * _to_decimal(data.get("unit_cost")))))
        return abs(_to_decimal(data.get("total_cost")) or _to_decimal(data.get("adjust_total_cost")))

    by_type: dict[str, dict[str, Any]] = {}
    pending_outbox: list[dict[str, Any]] = []
    for ev in operational_events:
        key = f"{ev.source_module}.{ev.event_type}"
        row = by_type.setdefault(
            key,
            {
                "source_module": ev.source_module,
                "event_type": ev.event_type,
                "operational_count": 0,
                "linked_count": 0,
                "posted_count": 0,
                "draft_exception_count": 0,
                "operational_amount": "0.00",
                "draft_amount": "0.00",
                "posted_amount": "0.00",
            },
        )
        row["operational_count"] += 1
        op_amount = _operational_amount(ev)
        row["operational_amount"] = str(_q_money(_to_decimal(row["operational_amount"]) + op_amount))

        eco = economic_by_outbox.get(ev.event_id)
        if eco is None:
            pending_outbox.append(
                {
                    "outbox_event_id": str(ev.event_id),
                    "source_module": ev.source_module,
                    "event_type": ev.event_type,
                    "occurred_at": ev.occurred_at,
                }
            )
            continue

        row["linked_count"] += 1
        draft = drafts_by_event.get(eco.id)
        if draft is None:
            continue
        row["draft_amount"] = str(_q_money(_to_decimal(row["draft_amount"]) + _to_decimal(draft.total_debit)))
        if draft.state == JournalDraft.State.EXCEPTION:
            row["draft_exception_count"] += 1
        if draft.state == JournalDraft.State.POSTED and hasattr(draft, "journal_entry"):
            row["posted_count"] += 1
            row["posted_amount"] = str(
                _q_money(_to_decimal(row["posted_amount"]) + _to_decimal(draft.journal_entry.debit_total))
            )

    draft_qs = JournalDraft.objects.filter(
        economic_event__company=company,
        economic_event__source_outbox_event_id__in=outbox_ids,
    )
    summary = {
        "operational_events": len(operational_events),
        "economic_events_linked": len(economic_by_outbox),
        "drafts_total": int(draft_qs.count()),
        "drafts_validated": int(draft_qs.filter(state=JournalDraft.State.VALIDATED).count()),
        "drafts_exception": int(draft_qs.filter(state=JournalDraft.State.EXCEPTION).count()),
        "drafts_posted": int(draft_qs.filter(state=JournalDraft.State.POSTED).count()),
        "pending_operational_events": len(pending_outbox),
    }
    return {
        "summary": summary,
        "by_event_type": list(by_type.values()),
        "pending_operational_events": pending_outbox[:200],
    }


def build_operational_monitor_snapshot(
    *,
    company,
    branch=None,
    date_from: date | None = None,
    date_to: date | None = None,
) -> dict[str, Any]:
    local_today = timezone.localdate()
    if date_from is None or date_to is None:
        from_default, to_default = _period_date_bounds(year=int(local_today.year), month=int(local_today.month))
        date_from = date_from or from_default
        date_to = date_to or to_default

    dt_from, dt_to = _period_datetime_bounds(date_from=date_from, date_to=date_to)

    failed_qs = OutboxEvent.objects.filter(
        company=company,
        source_module__in=list(PERIOD_CLOSE_FAILED_OUTBOX_MODULES),
        status=OutboxEvent.Status.FAILED,
        occurred_at__gte=dt_from,
        occurred_at__lte=dt_to,
    )
    if branch is not None:
        failed_qs = failed_qs.filter(branch=branch)

    failed_by_module = {module: 0 for module in PERIOD_CLOSE_FAILED_OUTBOX_MODULES}
    for row in failed_qs.values("source_module").annotate(total=Count("id")):
        module = str(row.get("source_module") or "")
        if module in failed_by_module:
            failed_by_module[module] = int(row.get("total") or 0)

    reconciliation = reconcile_operational_vs_accounting(
        company=company,
        branch=branch,
        date_from=date_from,
        date_to=date_to,
    )

    fuel_compensation = {
        "pending_count": 0,
        "failed_count": 0,
    }
    try:
        from modulos.estacion_servicios.models import FuelSale, FuelSaleStatus

        fuel_qs = FuelSale.objects.filter(
            company=company,
            created_at__gte=dt_from,
            created_at__lte=dt_to,
        )
        if branch is not None:
            fuel_qs = fuel_qs.filter(branch=branch)

        fuel_compensation["pending_count"] = int(
            fuel_qs.filter(status=FuelSaleStatus.COMPENSATING).count()
        )
        fuel_compensation["failed_count"] = int(
            fuel_qs.filter(status=FuelSaleStatus.COMPENSATION_FAILED).count()
        )
    except Exception:  # noqa: BLE001
        logger.exception(
            "fuel_compensation_summary_unavailable",
            extra={
                "company_id": int(company.id),
                "branch_id": int(branch.id) if branch is not None else None,
                "date_from": str(date_from),
                "date_to": str(date_to),
            },
        )

    gate_summary = None
    if int(date_from.year) == int(date_to.year) and int(date_from.month) == int(date_to.month):
        gate_summary = evaluate_period_close_gates(
            company=company,
            year=int(date_from.year),
            month=int(date_from.month),
            force=False,
        ).as_dict()

    return {
        "generated_at": timezone.now().isoformat(),
        "company_id": int(company.id),
        "branch_id": int(branch.id) if branch is not None else None,
        "period": {
            "date_from": str(date_from),
            "date_to": str(date_to),
        },
        "failed_outbox": {
            "total": int(failed_qs.count()),
            "by_module": failed_by_module,
        },
        "reconciliation": reconciliation,
        "fuel_compensation": fuel_compensation,
        "gate_summary": gate_summary,
    }
