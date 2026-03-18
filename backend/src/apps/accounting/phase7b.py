from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any

from django.db import transaction
from django.db.models import DecimalField, Q, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from apps.cec.models import CECException
from apps.iam.models import OrgUnit
from apps.iam.selectors import has_intercompany_grant
from apps.integration.services import publish_outbox_event

from .models import (
    ChartOfAccount,
    ConsolidationEliminationLink,
    ConsolidationRun,
    IntercompanyDisputeCase,
    IntercompanyDisputeEvidence,
    IntercompanyDisputeReason,
    IntercompanyReconciliation,
    IntercompanyTransaction,
    JournalEntry,
    JournalEntryLine,
)
from .phase7 import resolve_period_range

MONEY_Q = Decimal("0.01")
DECIMAL_MONEY_FIELD: DecimalField = DecimalField(max_digits=18, decimal_places=2)
OPEN_EXCEPTION_STATUSES = (CECException.Status.OPEN, CECException.Status.IN_PROGRESS)
PHASE11_SLA_EXCEPTION_CODES = {
    "INTERCOMPANY_OPEN_SLA_BREACH",
    "INTERCOMPANY_DISPUTE_SLA_BREACH",
    "INTERCOMPANY_CONFIRMED_UNCLOSED_SLA_BREACH",
}
ACTIVE_DISPUTE_CASE_STATUSES = {
    IntercompanyDisputeCase.Status.OPEN,
    IntercompanyDisputeCase.Status.UNDER_REVIEW,
    IntercompanyDisputeCase.Status.APPROVED,
}


class Phase7BValidationError(ValueError):
    """Error de validación de dominio para Fase 7B."""


@dataclass(frozen=True)
class IntercompanyActionResult:
    tx_id: str
    status: str
    reconciliation_status: str
    difference_amount: str


@dataclass(frozen=True)
class IntercompanyCycleResult:
    processed: int
    confirmed: int
    differences: int
    disputed: int
    closed: int
    open_items: int
    report_hash: str
    report: dict[str, Any]


@dataclass(frozen=True)
class ConsolidationExecutionResult:
    run_id: str
    status: str
    idempotent: bool
    manifest_hash: str
    issues_count: int
    summary_json: dict[str, Any]


def _json_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _q_money(value: Decimal) -> Decimal:
    return value.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _to_decimal(value: Any, default: Decimal = Decimal("0.00")) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if value is None:
        return default
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return default


def _resolve_company(*, company_id: int) -> OrgUnit:
    company = OrgUnit.objects.filter(id=int(company_id), unit_type=OrgUnit.UnitType.COMPANY, is_active=True).first()
    if company is None:
        raise Phase7BValidationError(f"company inválida o inactiva: {company_id}")
    return company


def _load_journal_entry_for_company(*, entry_id: int | None, company: OrgUnit, field_name: str) -> JournalEntry | None:
    if entry_id is None:
        return None
    row = JournalEntry.objects.filter(id=int(entry_id), company=company).first()
    if row is None:
        raise Phase7BValidationError(f"{field_name} inválido o fuera de company={company.id}: {entry_id}")
    return row


def _open_intercompany_exception(
    *,
    tx: IntercompanyTransaction,
    code: str,
    details_json: dict[str, Any],
    severity: str = CECException.Severity.HIGH,
    blocking: bool = True,
) -> CECException:
    fp_seed = f"{tx.tx_id}|{code}|{details_json.get('reason', '')}"
    fp = hashlib.sha256(fp_seed.encode("utf-8")).hexdigest()
    existing = CECException.objects.filter(
        source_module="ACCOUNTING",
        code=code,
        company=tx.source_company,
        related_object_type="INTERCOMPANY_TX",
        related_object_id=str(tx.tx_id),
        fingerprint=fp,
        status__in=OPEN_EXCEPTION_STATUSES,
    ).first()
    if existing:
        if existing.details_json != details_json:
            existing.details_json = details_json
            existing.save(update_fields=["details_json"])
        return existing
    return CECException.objects.create(
        source_module="ACCOUNTING",
        code=code,
        severity=severity,
        status=CECException.Status.OPEN,
        company=tx.source_company,
        branch=None,
        related_object_type="INTERCOMPANY_TX",
        related_object_id=str(tx.tx_id),
        fingerprint=fp,
        is_blocking=blocking,
        details_json=details_json,
    )


def _resolve_intercompany_exceptions(*, tx: IntercompanyTransaction, note: str = "Reconciliación confirmada.") -> int:
    rows = list(
        CECException.objects.filter(
            source_module="ACCOUNTING",
            company=tx.source_company,
            related_object_type="INTERCOMPANY_TX",
            related_object_id=str(tx.tx_id),
            status__in=OPEN_EXCEPTION_STATUSES,
        )
    )
    if not rows:
        return 0
    now = timezone.now()
    for row in rows:
        row.status = CECException.Status.RESOLVED
        row.resolved_at = now
        row.resolution_note = note
        row.save(update_fields=["status", "resolved_at", "resolution_note"])
    return len(rows)


def _resolve_dispute_reason(*, company: OrgUnit, reason_code: str) -> IntercompanyDisputeReason:
    code = str(reason_code or "").strip().upper()
    if not code:
        raise Phase7BValidationError("reason_code es requerido.")
    row = (
        IntercompanyDisputeReason.objects.filter(company=company, code=code, is_active=True)
        .order_by("-version", "-id")
        .first()
    )
    if row is None:
        raise Phase7BValidationError(f"reason_code no encontrado o inactivo: {code}")
    return row


def _ensure_dispute_evidence(
    *,
    dispute_case: IntercompanyDisputeCase,
    evidence_refs: list[str],
    actor_user=None,
) -> int:
    refs = [str(x).strip() for x in (evidence_refs or []) if str(x).strip()]
    created = 0
    for ref in refs:
        evidence_hash = hashlib.sha256(ref.encode("utf-8")).hexdigest()
        row, was_created = IntercompanyDisputeEvidence.objects.get_or_create(
            dispute_case=dispute_case,
            evidence_hash=evidence_hash,
            defaults={
                "reference": ref,
                "mime_type": "application/octet-stream",
                "note": "evidence_ref",
                "metadata_json": {"reference": ref},
                "created_by": actor_user,
            },
        )
        if not was_created and row.reference != ref:
            row.reference = ref
            row.metadata_json = {"reference": ref}
            row.save(update_fields=["reference", "metadata_json"])
        if was_created:
            created += 1
    return created


def _open_or_update_dispute_case(
    *,
    tx: IntercompanyTransaction,
    reason: IntercompanyDisputeReason,
    evidence_refs: list[str],
    note: str,
    actor_user=None,
    sla_hours: int = 24,
) -> IntercompanyDisputeCase:
    active_case = (
        IntercompanyDisputeCase.objects.filter(transaction=tx, status__in=ACTIVE_DISPUTE_CASE_STATUSES)
        .order_by("-updated_at", "-id")
        .first()
    )
    now = timezone.now()
    sla_due_at = now + timedelta(hours=max(1, int(sla_hours)))
    if active_case is None:
        active_case = IntercompanyDisputeCase.objects.create(
            transaction=tx,
            reason=reason,
            status=IntercompanyDisputeCase.Status.OPEN,
            summary=str(note or "Disputa intercompany abierta.").strip(),
            details_json={
                "tx_id": str(tx.tx_id),
                "reason_code": reason.code,
            },
            opened_by=actor_user,
            opened_at=now,
            sla_due_at=sla_due_at,
        )
    else:
        active_case.reason = reason
        active_case.status = IntercompanyDisputeCase.Status.OPEN
        active_case.summary = str(note or active_case.summary or "Disputa intercompany abierta.").strip()
        active_case.details_json = {
            **dict(active_case.details_json or {}),
            "tx_id": str(tx.tx_id),
            "reason_code": reason.code,
        }
        active_case.reviewed_by = None
        active_case.reviewed_at = None
        active_case.settled_by = None
        active_case.settled_at = None
        active_case.closed_at = None
        active_case.sla_due_at = sla_due_at
        active_case.save(
            update_fields=[
                "reason",
                "status",
                "summary",
                "details_json",
                "reviewed_by",
                "reviewed_at",
                "settled_by",
                "settled_at",
                "closed_at",
                "sla_due_at",
                "updated_at",
            ]
        )
    created_evidence = _ensure_dispute_evidence(dispute_case=active_case, evidence_refs=evidence_refs, actor_user=actor_user)
    if reason.requires_evidence and active_case.evidences.count() <= 0:
        raise Phase7BValidationError(
            f"reason_code={reason.code} requiere evidencia. evidence_refs[] no puede estar vacío."
        )
    active_case.details_json = {
        **dict(active_case.details_json or {}),
        "evidence_count": int(active_case.evidences.count()),
        "created_evidence_count": int(created_evidence),
    }
    active_case.save(update_fields=["details_json", "updated_at"])
    return active_case


def _resolve_active_dispute_case(*, tx: IntercompanyTransaction, actor_user=None, note: str = "") -> int:
    rows = list(
        IntercompanyDisputeCase.objects.filter(transaction=tx, status__in=ACTIVE_DISPUTE_CASE_STATUSES).order_by("-id")
    )
    if not rows:
        return 0
    now = timezone.now()
    for row in rows:
        row.status = IntercompanyDisputeCase.Status.SETTLED
        row.resolution_note = str(note or "Disputa resuelta por settlement/cierre.").strip()
        row.settled_by = actor_user
        row.settled_at = now
        row.closed_at = now
        row.save(update_fields=["status", "resolution_note", "settled_by", "settled_at", "closed_at", "updated_at"])
    return len(rows)


def _ensure_transition(*, tx: IntercompanyTransaction, target_status: str) -> None:
    if tx.can_transition_to(target_status):
        return
    raise Phase7BValidationError(
        f"Transición intercompany inválida: {tx.status} -> {target_status} para tx={tx.tx_id}"
    )


def _enforce_intercompany_write_grant(
    *,
    acting_company: OrgUnit,
    counterparty_company: OrgUnit,
    permission_code: str,
) -> None:
    if int(acting_company.id) == int(counterparty_company.id):
        return
    granted = has_intercompany_grant(
        from_company=counterparty_company,
        to_company=acting_company,
        permission_code=permission_code,
        mode="WRITE",
        scope_branch=None,
    )
    if granted:
        return
    raise Phase7BValidationError(
        "Intercompany WRITE denegado: falta grant activo "
        f"from_company={counterparty_company.id} -> to_company={acting_company.id} "
        f"perm={permission_code} mode=WRITE."
    )


def _resolve_acting_company_for_tx(*, tx: IntercompanyTransaction, effective_company_id: int | None) -> OrgUnit:
    if effective_company_id is None:
        # F11: la matriz intercompany WRITE se exige siempre.
        # Sin contexto explícito, asumimos acción del source_company.
        return tx.source_company
    if int(effective_company_id) == int(tx.source_company_id):
        return tx.source_company
    if int(effective_company_id) == int(tx.target_company_id):
        if tx.target_company is None:
            raise Phase7BValidationError(f"target_company no disponible para tx={tx.tx_id}.")
        return tx.target_company
    raise Phase7BValidationError(
        f"effective_company_id={effective_company_id} no pertenece a tx={tx.tx_id} "
        f"(source={tx.source_company_id}, target={tx.target_company_id})."
    )


def create_intercompany_transaction(
    *,
    source_company_id: int,
    target_company_id: int,
    amount: Decimal,
    currency: str = "NIO",
    source_account_code: str = "",
    target_account_code: str = "",
    source_side: str = IntercompanyTransaction.Side.CREDIT,
    target_side: str = IntercompanyTransaction.Side.DEBIT,
    description: str = "",
    reference_code: str = "",
    source_journal_entry_id: int | None = None,
    target_journal_entry_id: int | None = None,
    actor_user=None,
    effective_company_id: int | None = None,
) -> IntercompanyTransaction:
    source_company = _resolve_company(company_id=source_company_id)
    target_company = _resolve_company(company_id=target_company_id)
    if source_company.id == target_company.id:
        raise Phase7BValidationError("source_company y target_company deben ser distintos.")
    acting_company = source_company
    if effective_company_id is not None and int(effective_company_id) != int(source_company.id):
        raise Phase7BValidationError(
            f"effective_company_id={effective_company_id} debe coincidir con source_company_id={source_company.id}."
        )
    _enforce_intercompany_write_grant(
        acting_company=acting_company,
        counterparty_company=target_company,
        permission_code="accounting.intercompany.write",
    )

    money = _q_money(abs(_to_decimal(amount)))
    if money <= Decimal("0.00"):
        raise Phase7BValidationError("amount debe ser mayor que cero.")

    source_side_clean = str(source_side or IntercompanyTransaction.Side.CREDIT).strip().upper()
    target_side_clean = str(target_side or IntercompanyTransaction.Side.DEBIT).strip().upper()
    if source_side_clean not in IntercompanyTransaction.Side.values:
        raise Phase7BValidationError(f"source_side inválido: {source_side_clean}")
    if target_side_clean not in IntercompanyTransaction.Side.values:
        raise Phase7BValidationError(f"target_side inválido: {target_side_clean}")

    with transaction.atomic():
        source_entry = _load_journal_entry_for_company(
            entry_id=source_journal_entry_id,
            company=source_company,
            field_name="source_journal_entry_id",
        )
        target_entry = _load_journal_entry_for_company(
            entry_id=target_journal_entry_id,
            company=target_company,
            field_name="target_journal_entry_id",
        )
        tx = IntercompanyTransaction.objects.create(
            source_company=source_company,
            target_company=target_company,
            source_journal_entry=source_entry,
            target_journal_entry=target_entry,
            status=IntercompanyTransaction.Status.PENDING,
            reference_code=str(reference_code or "").strip(),
            currency=str(currency or "NIO").strip().upper() or "NIO",
            amount=money,
            source_account_code=str(source_account_code or "").strip().upper(),
            target_account_code=str(target_account_code or "").strip().upper(),
            source_side=source_side_clean,
            target_side=target_side_clean,
            matched_amount_source=money,
            matched_amount_target=Decimal("0.00"),
            difference_amount=money,
            description=str(description or "").strip(),
            created_by=actor_user,
        )
        IntercompanyReconciliation.objects.create(
            transaction=tx,
            status=IntercompanyReconciliation.Status.PENDING,
            source_amount=money,
            target_amount=Decimal("0.00"),
            difference_amount=money,
            note="Pendiente de confirmación de contraparte.",
            details_json={"stage": "CREATED"},
            created_by=actor_user,
        )
        publish_outbox_event(
            source_module="ACCOUNTING",
            event_type="IntercompanyTransactionCreated",
            payload={
                "tx_id": str(tx.tx_id),
                "source_company_id": int(source_company.id),
                "target_company_id": int(target_company.id),
                "amount": str(money),
                "currency": tx.currency,
                "status": tx.status,
                "source_account_code": tx.source_account_code,
                "target_account_code": tx.target_account_code,
            },
            company=source_company,
            actor_user=actor_user,
        )
        return tx


def confirm_intercompany_transaction(
    *,
    tx_id: str,
    actor_user=None,
    target_journal_entry_id: int | None = None,
    allow_same_actor: bool = False,
    effective_company_id: int | None = None,
) -> IntercompanyActionResult:
    with transaction.atomic():
        tx = IntercompanyTransaction.objects.select_for_update().filter(tx_id=tx_id).first()
        if tx is None:
            raise Phase7BValidationError(f"Intercompany tx no encontrada: {tx_id}")
        acting_company = _resolve_acting_company_for_tx(tx=tx, effective_company_id=effective_company_id)
        counterparty = tx.target_company if int(acting_company.id) == int(tx.source_company_id) else tx.source_company
        _enforce_intercompany_write_grant(
            acting_company=acting_company,
            counterparty_company=counterparty,
            permission_code="accounting.intercompany.write",
        )
        _ensure_transition(tx=tx, target_status=IntercompanyTransaction.Status.CONFIRMED)
        if (
            not allow_same_actor
            and actor_user is not None
            and tx.created_by_id is not None
            and int(tx.created_by_id) == int(actor_user.id)
        ):
            raise Phase7BValidationError("SoD: el creador no puede confirmar la misma transacción sin override.")
        if target_journal_entry_id is not None:
            tx.target_journal_entry = _load_journal_entry_for_company(
                entry_id=target_journal_entry_id,
                company=tx.target_company,
                field_name="target_journal_entry_id",
            )

        tx.status = IntercompanyTransaction.Status.CONFIRMED
        tx.confirmed_by = actor_user
        tx.confirmed_at = timezone.now()
        tx.matched_amount_source = _q_money(tx.amount)
        tx.matched_amount_target = _q_money(tx.amount)
        tx.difference_amount = Decimal("0.00")
        tx.save(
            update_fields=[
                "status",
                "confirmed_by",
                "confirmed_at",
                "matched_amount_source",
                "matched_amount_target",
                "difference_amount",
                "target_journal_entry",
                "updated_at",
            ]
        )
        IntercompanyReconciliation.objects.create(
            transaction=tx,
            status=IntercompanyReconciliation.Status.CONFIRMED,
            source_amount=tx.matched_amount_source,
            target_amount=tx.matched_amount_target,
            difference_amount=tx.difference_amount,
            note="Confirmada por contraparte.",
            details_json={"stage": "CONFIRMED"},
            created_by=actor_user,
        )
        _resolve_intercompany_exceptions(tx=tx)
        publish_outbox_event(
            source_module="ACCOUNTING",
            event_type="IntercompanyTransactionConfirmed",
            payload={
                "tx_id": str(tx.tx_id),
                "status": tx.status,
                "source_company_id": int(tx.source_company_id),
                "target_company_id": int(tx.target_company_id),
                "matched_amount_source": str(tx.matched_amount_source),
                "matched_amount_target": str(tx.matched_amount_target),
                "difference_amount": str(tx.difference_amount),
            },
            company=tx.source_company,
            actor_user=actor_user,
        )
        return IntercompanyActionResult(
            tx_id=str(tx.tx_id),
            status=tx.status,
            reconciliation_status=IntercompanyReconciliation.Status.CONFIRMED,
            difference_amount=str(tx.difference_amount),
        )


def reconcile_intercompany_transaction(
    *,
    tx_id: str,
    source_amount: Decimal,
    target_amount: Decimal,
    actor_user=None,
    mark_dispute: bool = False,
    note: str = "",
    effective_company_id: int | None = None,
) -> IntercompanyActionResult:
    src = _q_money(abs(_to_decimal(source_amount)))
    tgt = _q_money(abs(_to_decimal(target_amount)))
    if src <= Decimal("0.00") or tgt < Decimal("0.00"):
        raise Phase7BValidationError("source_amount/target_amount inválidos.")
    diff = _q_money(src - tgt)
    difference_abs = _q_money(abs(diff))
    if mark_dispute:
        next_status = IntercompanyTransaction.Status.DISPUTED
        rec_status = IntercompanyReconciliation.Status.DISPUTED
    elif difference_abs <= MONEY_Q:
        next_status = IntercompanyTransaction.Status.CONFIRMED
        rec_status = IntercompanyReconciliation.Status.CONFIRMED
    else:
        next_status = IntercompanyTransaction.Status.DIFFERENCE
        rec_status = IntercompanyReconciliation.Status.DIFFERENCE

    with transaction.atomic():
        tx = IntercompanyTransaction.objects.select_for_update().filter(tx_id=tx_id).first()
        if tx is None:
            raise Phase7BValidationError(f"Intercompany tx no encontrada: {tx_id}")
        acting_company = _resolve_acting_company_for_tx(tx=tx, effective_company_id=effective_company_id)
        counterparty = tx.target_company if int(acting_company.id) == int(tx.source_company_id) else tx.source_company
        _enforce_intercompany_write_grant(
            acting_company=acting_company,
            counterparty_company=counterparty,
            permission_code="accounting.intercompany.reconcile",
        )
        _ensure_transition(tx=tx, target_status=next_status)

        tx.status = next_status
        tx.matched_amount_source = src
        tx.matched_amount_target = tgt
        tx.difference_amount = difference_abs
        if next_status == IntercompanyTransaction.Status.CONFIRMED and tx.confirmed_at is None:
            tx.confirmed_at = timezone.now()
            tx.confirmed_by = actor_user
        tx.save(
            update_fields=[
                "status",
                "matched_amount_source",
                "matched_amount_target",
                "difference_amount",
                "confirmed_at",
                "confirmed_by",
                "updated_at",
            ]
        )

        rec_note = note.strip() or (
            "Conciliación confirmada."
            if rec_status == IntercompanyReconciliation.Status.CONFIRMED
            else "Conciliación con diferencia/disputa."
        )
        IntercompanyReconciliation.objects.create(
            transaction=tx,
            status=rec_status,
            source_amount=src,
            target_amount=tgt,
            difference_amount=difference_abs,
            note=rec_note,
            details_json={
                "stage": "RECONCILED",
                "mark_dispute": bool(mark_dispute),
                "difference": str(difference_abs),
            },
            created_by=actor_user,
        )

        if next_status == IntercompanyTransaction.Status.CONFIRMED:
            _resolve_intercompany_exceptions(tx=tx)
        else:
            issue_code = "INTERCOMPANY_DISPUTE" if next_status == IntercompanyTransaction.Status.DISPUTED else "INTERCOMPANY_DIFFERENCE"
            _open_intercompany_exception(
                tx=tx,
                code=issue_code,
                details_json={
                    "tx_id": str(tx.tx_id),
                    "source_amount": str(src),
                    "target_amount": str(tgt),
                    "difference_amount": str(difference_abs),
                    "reason": rec_note,
                },
            )
        publish_outbox_event(
            source_module="ACCOUNTING",
            event_type="IntercompanyTransactionAdjusted",
            payload={
                "tx_id": str(tx.tx_id),
                "status": tx.status,
                "source_amount": str(src),
                "target_amount": str(tgt),
                "difference_amount": str(difference_abs),
                "mark_dispute": bool(mark_dispute),
            },
            company=tx.source_company,
            actor_user=actor_user,
        )
        return IntercompanyActionResult(
            tx_id=str(tx.tx_id),
            status=tx.status,
            reconciliation_status=rec_status,
            difference_amount=str(difference_abs),
        )


def dispute_intercompany_transaction(
    *,
    tx_id: str,
    source_amount: Decimal,
    target_amount: Decimal,
    reason_code: str,
    evidence_refs: list[str] | None = None,
    actor_user=None,
    note: str = "",
    effective_company_id: int | None = None,
) -> IntercompanyActionResult:
    tx_for_reason = IntercompanyTransaction.objects.select_related("source_company").filter(tx_id=tx_id).first()
    if tx_for_reason is None:
        raise Phase7BValidationError(f"Intercompany tx no encontrada: {tx_id}")
    acting_company = _resolve_acting_company_for_tx(tx=tx_for_reason, effective_company_id=effective_company_id)
    counterparty = (
        tx_for_reason.target_company
        if int(acting_company.id) == int(tx_for_reason.source_company_id)
        else tx_for_reason.source_company
    )
    _enforce_intercompany_write_grant(
        acting_company=acting_company,
        counterparty_company=counterparty,
        permission_code="accounting.intercompany.dispute",
    )
    reason = _resolve_dispute_reason(company=tx_for_reason.source_company, reason_code=reason_code)
    result = reconcile_intercompany_transaction(
        tx_id=tx_id,
        source_amount=source_amount,
        target_amount=target_amount,
        actor_user=actor_user,
        mark_dispute=True,
        note=note or "Disputa intercompany abierta.",
        effective_company_id=effective_company_id,
    )
    tx = IntercompanyTransaction.objects.filter(tx_id=tx_id).select_related("source_company").first()
    if tx is not None:
        dispute_case = _open_or_update_dispute_case(
            tx=tx,
            reason=reason,
            evidence_refs=list(evidence_refs or []),
            note=note or "Disputa intercompany abierta.",
            actor_user=actor_user,
            sla_hours=24,
        )
        publish_outbox_event(
            source_module="ACCOUNTING",
            event_type="IntercompanyDisputeOpened",
            payload={
                "tx_id": str(tx.tx_id),
                "status": tx.status,
                "difference_amount": str(tx.difference_amount),
                "dispute_case_id": str(dispute_case.case_id),
                "reason_code": str(reason.code),
                "requires_evidence": bool(reason.requires_evidence),
                "note": note or "Disputa intercompany abierta.",
            },
            company=tx.source_company,
            actor_user=actor_user,
        )
    return result


def settle_intercompany_transaction(
    *,
    tx_id: str,
    source_amount: Decimal,
    target_amount: Decimal,
    actor_user=None,
    note: str = "",
    close_when_confirmed: bool = True,
    allow_difference: bool = False,
    effective_company_id: int | None = None,
) -> IntercompanyActionResult:
    tx = IntercompanyTransaction.objects.select_related("source_company", "target_company").filter(tx_id=tx_id).first()
    if tx is None:
        raise Phase7BValidationError(f"Intercompany tx no encontrada: {tx_id}")
    acting_company = _resolve_acting_company_for_tx(tx=tx, effective_company_id=effective_company_id)
    counterparty = tx.target_company if int(acting_company.id) == int(tx.source_company_id) else tx.source_company
    _enforce_intercompany_write_grant(
        acting_company=acting_company,
        counterparty_company=counterparty,
        permission_code="accounting.intercompany.settle",
    )

    src = _q_money(abs(_to_decimal(source_amount)))
    tgt = _q_money(abs(_to_decimal(target_amount)))
    difference_abs = _q_money(abs(src - tgt))
    # F11: settlement con tolerancia cero.
    # Si no cuadra exacto, se mantiene en disputa.
    mark_dispute = difference_abs > Decimal("0.00")
    result = reconcile_intercompany_transaction(
        tx_id=tx_id,
        source_amount=src,
        target_amount=tgt,
        actor_user=actor_user,
        mark_dispute=bool(mark_dispute),
        note=note or "Resolución de disputa intercompany.",
        effective_company_id=effective_company_id,
    )
    final_result = result
    if bool(close_when_confirmed) and result.status == IntercompanyTransaction.Status.CONFIRMED:
        final_result = close_intercompany_transaction(
            tx_id=tx_id,
            actor_user=actor_user,
            allow_difference=bool(allow_difference),
            effective_company_id=effective_company_id,
        )
    tx = IntercompanyTransaction.objects.filter(tx_id=tx_id).select_related("source_company").first()
    if tx is not None:
        if final_result.status == IntercompanyTransaction.Status.CLOSED:
            _resolve_active_dispute_case(
                tx=tx,
                actor_user=actor_user,
                note=note or "Disputa resuelta por settlement.",
            )
        publish_outbox_event(
            source_module="ACCOUNTING",
            event_type="IntercompanyDisputeSettled",
            payload={
                "tx_id": str(tx.tx_id),
                "status": tx.status,
                "difference_amount": str(tx.difference_amount),
                "closed": bool(tx.status == IntercompanyTransaction.Status.CLOSED),
                "zero_tolerance_ok": bool(difference_abs == Decimal("0.00")),
                "note": note or "Resolución de disputa intercompany.",
            },
            company=tx.source_company,
            actor_user=actor_user,
        )
    return final_result


def close_intercompany_transaction(
    *,
    tx_id: str,
    actor_user=None,
    allow_difference: bool = False,
    effective_company_id: int | None = None,
) -> IntercompanyActionResult:
    with transaction.atomic():
        tx = IntercompanyTransaction.objects.select_for_update().filter(tx_id=tx_id).first()
        if tx is None:
            raise Phase7BValidationError(f"Intercompany tx no encontrada: {tx_id}")
        acting_company = _resolve_acting_company_for_tx(tx=tx, effective_company_id=effective_company_id)
        counterparty = tx.target_company if int(acting_company.id) == int(tx.source_company_id) else tx.source_company
        _enforce_intercompany_write_grant(
            acting_company=acting_company,
            counterparty_company=counterparty,
            permission_code="accounting.intercompany.write",
        )

        valid_close_statuses = {IntercompanyTransaction.Status.CONFIRMED}
        if allow_difference:
            valid_close_statuses.add(IntercompanyTransaction.Status.DIFFERENCE)
            valid_close_statuses.add(IntercompanyTransaction.Status.DISPUTED)
        if tx.status not in valid_close_statuses:
            raise Phase7BValidationError(f"No se puede cerrar tx={tx.tx_id} en estado={tx.status}")
        _ensure_transition(tx=tx, target_status=IntercompanyTransaction.Status.CLOSED)

        tx.status = IntercompanyTransaction.Status.CLOSED
        tx.closed_at = timezone.now()
        tx.closed_by = actor_user
        tx.save(update_fields=["status", "closed_at", "closed_by", "updated_at"])
        IntercompanyReconciliation.objects.create(
            transaction=tx,
            status=IntercompanyReconciliation.Status.CLOSED,
            source_amount=tx.matched_amount_source,
            target_amount=tx.matched_amount_target,
            difference_amount=tx.difference_amount,
            note="Cierre de ciclo intercompany.",
            details_json={"stage": "CLOSED", "allow_difference": bool(allow_difference)},
            created_by=actor_user,
        )
        publish_outbox_event(
            source_module="ACCOUNTING",
            event_type="IntercompanyTransactionClosed",
            payload={
                "tx_id": str(tx.tx_id),
                "status": tx.status,
                "difference_amount": str(tx.difference_amount),
                "allow_difference": bool(allow_difference),
            },
            company=tx.source_company,
            actor_user=actor_user,
        )
        _resolve_intercompany_exceptions(tx=tx, note="Cierre intercompany completado.")
        _resolve_active_dispute_case(
            tx=tx,
            actor_user=actor_user,
            note="Disputa cerrada por cierre de transacción intercompany.",
        )
        return IntercompanyActionResult(
            tx_id=str(tx.tx_id),
            status=tx.status,
            reconciliation_status=IntercompanyReconciliation.Status.CLOSED,
            difference_amount=str(tx.difference_amount),
        )


def review_intercompany_dispute_case(
    *,
    case_id: str,
    action: str,
    actor_user=None,
    note: str = "",
    effective_company_id: int | None = None,
) -> IntercompanyDisputeCase:
    action_clean = str(action or "").strip().upper()
    allowed_actions = {
        IntercompanyDisputeCase.Status.UNDER_REVIEW,
        IntercompanyDisputeCase.Status.APPROVED,
        IntercompanyDisputeCase.Status.REJECTED,
        IntercompanyDisputeCase.Status.CANCELLED,
    }
    if action_clean not in allowed_actions:
        raise Phase7BValidationError(f"acción de review inválida: {action_clean}")

    with transaction.atomic():
        row = (
            IntercompanyDisputeCase.objects.select_for_update()
            .select_related("transaction", "transaction__source_company", "transaction__target_company")
            .filter(case_id=case_id)
            .first()
        )
        if row is None:
            raise Phase7BValidationError(f"DisputeCase no encontrado: {case_id}")
        tx = row.transaction
        acting_company = _resolve_acting_company_for_tx(tx=tx, effective_company_id=effective_company_id)
        counterparty = tx.target_company if int(acting_company.id) == int(tx.source_company_id) else tx.source_company
        _enforce_intercompany_write_grant(
            acting_company=acting_company,
            counterparty_company=counterparty,
            permission_code="accounting.intercompany.dispute",
        )

        now = timezone.now()
        row.status = action_clean
        row.reviewed_by = actor_user
        row.reviewed_at = now
        if action_clean in {IntercompanyDisputeCase.Status.REJECTED, IntercompanyDisputeCase.Status.CANCELLED}:
            row.closed_at = now
        if note:
            row.resolution_note = str(note).strip()
        row.save(update_fields=["status", "reviewed_by", "reviewed_at", "closed_at", "resolution_note", "updated_at"])

        publish_outbox_event(
            source_module="ACCOUNTING",
            event_type="IntercompanyDisputeReviewed",
            payload={
                "case_id": str(row.case_id),
                "tx_id": str(tx.tx_id),
                "status": str(row.status),
                "note": str(note or ""),
            },
            company=tx.source_company,
            actor_user=actor_user,
        )
        return row


def enforce_intercompany_sla(
    *,
    company_id: int,
    open_sla_hours: int = 24,
    dispute_sla_hours: int = 24,
    actor_user=None,
) -> dict[str, int]:
    company = _resolve_company(company_id=company_id)
    now = timezone.now()
    open_cutoff = now - timedelta(hours=max(1, int(open_sla_hours)))
    dispute_cutoff = now - timedelta(hours=max(1, int(dispute_sla_hours)))

    def _bucket(ref_dt):
        if ref_dt is None:
            return "0"
        elapsed = max(0, int((now - ref_dt).total_seconds()))
        return str(elapsed // (24 * 3600))

    escalated = 0
    resolved = 0

    scope_qs = IntercompanyTransaction.objects.filter(source_company=company)
    for tx in scope_qs:
        code = ""
        breach_ref = None
        if tx.status in (IntercompanyTransaction.Status.PENDING, IntercompanyTransaction.Status.DIFFERENCE):
            if tx.created_at <= open_cutoff:
                code = "INTERCOMPANY_OPEN_SLA_BREACH"
                breach_ref = tx.created_at
        elif tx.status == IntercompanyTransaction.Status.DISPUTED:
            if tx.updated_at <= dispute_cutoff:
                code = "INTERCOMPANY_DISPUTE_SLA_BREACH"
                breach_ref = tx.updated_at
        elif tx.status == IntercompanyTransaction.Status.CONFIRMED:
            if tx.updated_at <= open_cutoff:
                code = "INTERCOMPANY_CONFIRMED_UNCLOSED_SLA_BREACH"
                breach_ref = tx.updated_at

        if code:
            bucket = _bucket(breach_ref)
            ex = _open_intercompany_exception(
                tx=tx,
                code=code,
                details_json={
                    "tx_id": str(tx.tx_id),
                    "company_id": int(company.id),
                    "status": str(tx.status),
                    "reason": f"sla_breach:{code}:{bucket}",
                    "sla_bucket": bucket,
                    "open_sla_hours": int(open_sla_hours),
                    "dispute_sla_hours": int(dispute_sla_hours),
                },
                severity=CECException.Severity.HIGH,
                blocking=True,
            )
            if ex.status in OPEN_EXCEPTION_STATUSES:
                escalated += 1
            continue

        resolved += _resolve_intercompany_exceptions(
            tx=tx,
            note="Resolución automática: transacción volvió a estado dentro de SLA.",
        )

    publish_outbox_event(
        source_module="ACCOUNTING",
        event_type="IntercompanySlaEscalationExecuted",
        payload={
            "company_id": int(company.id),
            "escalated": int(escalated),
            "resolved": int(resolved),
            "open_sla_hours": int(open_sla_hours),
            "dispute_sla_hours": int(dispute_sla_hours),
        },
        company=company,
        actor_user=actor_user,
    )
    return {
        "escalated": int(escalated),
        "resolved": int(resolved),
    }


def run_intercompany_cycle(
    *,
    company_id: int,
    limit: int = 200,
    strict: bool = True,
    actor_user=None,
) -> IntercompanyCycleResult:
    company = _resolve_company(company_id=company_id)
    rows = list(
        IntercompanyTransaction.objects.select_related("source_company", "target_company", "target_journal_entry")
        .filter(Q(source_company=company) | Q(target_company=company))
        .filter(status__in=[IntercompanyTransaction.Status.PENDING, IntercompanyTransaction.Status.DIFFERENCE, IntercompanyTransaction.Status.DISPUTED])
        .order_by("created_at", "id")[: int(limit)]
    )

    confirmed = differences = disputed = closed = 0
    issues: list[dict[str, Any]] = []
    for tx in rows:
        target_entry = tx.target_journal_entry
        target_amount = _q_money(target_entry.debit_total) if target_entry is not None else _q_money(tx.matched_amount_target)
        source_amount = _q_money(tx.amount)
        if target_amount <= Decimal("0.00"):
            issues.append(
                {
                    "code": "INTERCOMPANY_TARGET_AMOUNT_MISSING",
                    "tx_id": str(tx.tx_id),
                    "detail": "No existe monto contraparte para reconciliar.",
                }
            )
            continue

        try:
            result = reconcile_intercompany_transaction(
                tx_id=str(tx.tx_id),
                source_amount=source_amount,
                target_amount=target_amount,
                actor_user=actor_user,
                mark_dispute=False,
                note="Ciclo intercompany automático",
            )
        except Phase7BValidationError as exc:
            issues.append(
                {
                    "code": "INTERCOMPANY_GOVERNANCE_DENIED",
                    "tx_id": str(tx.tx_id),
                    "detail": str(exc),
                }
            )
            continue
        if result.status == IntercompanyTransaction.Status.CONFIRMED:
            confirmed += 1
            if tx.source_journal_entry_id and tx.target_journal_entry_id:
                close_intercompany_transaction(tx_id=str(tx.tx_id), actor_user=actor_user, allow_difference=False)
                closed += 1
        elif result.status == IntercompanyTransaction.Status.DIFFERENCE:
            differences += 1
            issues.append(
                {
                    "code": "INTERCOMPANY_DIFFERENCE",
                    "tx_id": str(tx.tx_id),
                    "difference_amount": result.difference_amount,
                }
            )
        elif result.status == IntercompanyTransaction.Status.DISPUTED:
            disputed += 1
            issues.append(
                {
                    "code": "INTERCOMPANY_DISPUTED",
                    "tx_id": str(tx.tx_id),
                }
            )

    open_items = int(
        IntercompanyTransaction.objects.filter(Q(source_company=company) | Q(target_company=company))
        .filter(status__in=[IntercompanyTransaction.Status.PENDING, IntercompanyTransaction.Status.DIFFERENCE, IntercompanyTransaction.Status.DISPUTED])
        .count()
    )
    report = {
        "schema_version": 1,
        "generated_at": timezone.now().isoformat(),
        "company_id": int(company.id),
        "processed": int(len(rows)),
        "confirmed": int(confirmed),
        "differences": int(differences),
        "disputed": int(disputed),
        "closed": int(closed),
        "open_items": int(open_items),
        "issues_count": int(len(issues)),
        "issues": issues,
    }
    report_hash = _json_hash(report)
    publish_outbox_event(
        source_module="ACCOUNTING",
        event_type="IntercompanyCycleExecuted",
        payload={
            "company_id": int(company.id),
            "processed": int(len(rows)),
            "confirmed": int(confirmed),
            "differences": int(differences),
            "disputed": int(disputed),
            "closed": int(closed),
            "open_items": int(open_items),
            "issues_count": int(len(issues)),
            "report_hash": report_hash,
        },
        company=company,
        actor_user=actor_user,
    )
    if strict and issues:
        raise Phase7BValidationError(f"Intercompany cycle con incidencias: {len(issues)}")
    return IntercompanyCycleResult(
        processed=int(len(rows)),
        confirmed=int(confirmed),
        differences=int(differences),
        disputed=int(disputed),
        closed=int(closed),
        open_items=int(open_items),
        report_hash=report_hash,
        report=report,
    )


def _scope_hash(*, company_ids: list[int]) -> str:
    payload = {"company_ids": sorted(set(int(x) for x in company_ids))}
    return _json_hash(payload)


def _collect_base_trial_rows(*, company_ids: list[int], date_from: date, date_to: date) -> list[dict[str, Any]]:
    rows = list(
        JournalEntryLine.objects.filter(
            journal_entry__company_id__in=company_ids,
            journal_entry__is_posted=True,
            journal_entry__entry_date__gte=date_from,
            journal_entry__entry_date__lte=date_to,
        )
        .values("account_code_snapshot", "account__name", "account__account_type")
        .annotate(
            debit_total=Coalesce(Sum("debit_base"), Value(Decimal("0.00"), output_field=DECIMAL_MONEY_FIELD)),
            credit_total=Coalesce(Sum("credit_base"), Value(Decimal("0.00"), output_field=DECIMAL_MONEY_FIELD)),
        )
        .order_by("account_code_snapshot")
    )
    return [
        {
            "account_code": str(r["account_code_snapshot"] or ""),
            "account_name": str(r["account__name"] or ""),
            "account_type": str(r["account__account_type"] or ""),
            "debit_total": _q_money(_to_decimal(r["debit_total"])),
            "credit_total": _q_money(_to_decimal(r["credit_total"])),
            "elimination_debit": Decimal("0.00"),
            "elimination_credit": Decimal("0.00"),
        }
        for r in rows
    ]


def _get_or_create_trial_row(
    *,
    trial_map: dict[tuple[str, str], dict[str, Any]],
    account_code: str,
    account_name: str,
    account_type: str,
) -> dict[str, Any]:
    key = (str(account_code), str(account_type))
    row = trial_map.get(key)
    if row is not None:
        return row
    row = {
        "account_code": str(account_code),
        "account_name": str(account_name),
        "account_type": str(account_type),
        "debit_total": Decimal("0.00"),
        "credit_total": Decimal("0.00"),
        "elimination_debit": Decimal("0.00"),
        "elimination_credit": Decimal("0.00"),
    }
    trial_map[key] = row
    return row


def _append_elimination(*, row: dict[str, Any], side: str, amount: Decimal) -> None:
    money = _q_money(abs(_to_decimal(amount)))
    if side == IntercompanyTransaction.Side.DEBIT:
        row["elimination_debit"] = _q_money(row["elimination_debit"] + money)
    else:
        row["elimination_credit"] = _q_money(row["elimination_credit"] + money)


def _build_trial_report(*, trial_map: dict[tuple[str, str], dict[str, Any]]) -> list[dict[str, Any]]:
    out_rows: list[dict[str, Any]] = []
    for (_code, _atype), row in sorted(trial_map.items(), key=lambda x: x[0]):
        debit_total = _q_money(_to_decimal(row["debit_total"]))
        credit_total = _q_money(_to_decimal(row["credit_total"]))
        elimination_debit = _q_money(_to_decimal(row["elimination_debit"]))
        elimination_credit = _q_money(_to_decimal(row["elimination_credit"]))
        debit_net = _q_money(debit_total + elimination_debit)
        credit_net = _q_money(credit_total + elimination_credit)
        account_type = str(row["account_type"])
        if account_type in (ChartOfAccount.AccountType.ASSET, ChartOfAccount.AccountType.EXPENSE):
            net_balance = _q_money(debit_net - credit_net)
        else:
            net_balance = _q_money(credit_net - debit_net)
        out_rows.append(
            {
                "account_code": str(row["account_code"]),
                "account_name": str(row["account_name"]),
                "account_type": account_type,
                "debit_total": str(debit_total),
                "credit_total": str(credit_total),
                "elimination_debit": str(elimination_debit),
                "elimination_credit": str(elimination_credit),
                "debit_net": str(debit_net),
                "credit_net": str(credit_net),
                "net_balance": str(net_balance),
            }
        )
    return out_rows


def _build_pnl_from_trial(*, trial_rows: list[dict[str, Any]]) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    revenue_total = Decimal("0.00")
    expense_total = Decimal("0.00")
    for row in trial_rows:
        account_type = str(row["account_type"])
        if account_type not in (ChartOfAccount.AccountType.REVENUE, ChartOfAccount.AccountType.EXPENSE):
            continue
        balance = _q_money(_to_decimal(row["net_balance"]))
        rows.append(
            {
                "account_code": str(row["account_code"]),
                "account_name": str(row["account_name"]),
                "account_type": account_type,
                "balance": str(balance),
            }
        )
        if account_type == ChartOfAccount.AccountType.REVENUE:
            revenue_total = _q_money(revenue_total + balance)
        else:
            expense_total = _q_money(expense_total + balance)
    net_income = _q_money(revenue_total - expense_total)
    return {
        "rows": rows,
        "totals": {
            "revenue": str(revenue_total),
            "expense": str(expense_total),
            "net_income": str(net_income),
        },
    }


def _build_balance_sheet_from_trial(*, trial_rows: list[dict[str, Any]], as_of: date) -> dict[str, Any]:
    sections: dict[str, dict[str, Any]] = {
        "ASSET": {"rows": [], "total": Decimal("0.00")},
        "LIABILITY": {"rows": [], "total": Decimal("0.00")},
        "EQUITY": {"rows": [], "total": Decimal("0.00")},
    }
    for row in trial_rows:
        account_type = str(row["account_type"])
        if account_type not in sections:
            continue
        balance = _q_money(_to_decimal(row["net_balance"]))
        sections[account_type]["rows"].append(
            {
                "account_code": str(row["account_code"]),
                "account_name": str(row["account_name"]),
                "balance": str(balance),
            }
        )
        sections[account_type]["total"] = _q_money(sections[account_type]["total"] + balance)
    assets_total = _q_money(sections["ASSET"]["total"])
    liabilities_total = _q_money(sections["LIABILITY"]["total"])
    equity_total = _q_money(sections["EQUITY"]["total"])
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


def _open_consolidation_exception(*, run: ConsolidationRun, code: str, details_json: dict[str, Any]) -> None:
    fp_seed = f"{run.run_id}|{code}|{details_json.get('tx_id', '')}|{details_json.get('account_code', '')}"
    fp = hashlib.sha256(fp_seed.encode("utf-8")).hexdigest()
    existing = CECException.objects.filter(
        source_module="ACCOUNTING",
        code=code,
        company=run.parent_company,
        related_object_type="CONSOLIDATION_RUN",
        related_object_id=str(run.run_id),
        fingerprint=fp,
        status__in=OPEN_EXCEPTION_STATUSES,
    ).first()
    if existing:
        if existing.details_json != details_json:
            existing.details_json = details_json
            existing.save(update_fields=["details_json"])
        return
    CECException.objects.create(
        source_module="ACCOUNTING",
        code=code,
        severity=CECException.Severity.HIGH,
        status=CECException.Status.OPEN,
        company=run.parent_company,
        branch=None,
        related_object_type="CONSOLIDATION_RUN",
        related_object_id=str(run.run_id),
        fingerprint=fp,
        is_blocking=True,
        details_json=details_json,
    )


def run_consolidation(
    *,
    parent_company_id: int,
    year: int,
    month: int,
    company_ids: list[int],
    strict: bool = True,
    actor_user=None,
) -> ConsolidationExecutionResult:
    parent_company = _resolve_company(company_id=parent_company_id)
    scope_company_ids = sorted(set(int(x) for x in company_ids))
    if not scope_company_ids:
        raise Phase7BValidationError("company_ids es requerido.")
    for cid in scope_company_ids:
        _resolve_company(company_id=cid)

    period = resolve_period_range(year=year, month=month)
    if period is None:
        raise Phase7BValidationError("year/month inválidos para consolidación.")
    date_from, date_to = period
    scope_hash = _scope_hash(company_ids=scope_company_ids)
    input_manifest_hash = _json_hash(
        {
            "year": int(year),
            "month": int(month),
            "company_ids": scope_company_ids,
            "strict": bool(strict),
        }
    )

    with transaction.atomic():
        run, created = ConsolidationRun.objects.select_for_update().get_or_create(
            parent_company=parent_company,
            year=int(year),
            month=int(month),
            scope_hash=scope_hash,
            defaults={
                "status": ConsolidationRun.Status.RUNNING,
                "company_ids_json": scope_company_ids,
                "input_manifest_hash": input_manifest_hash,
                "executed_by": actor_user,
            },
        )
        if not created and run.status in (ConsolidationRun.Status.COMPLETED, ConsolidationRun.Status.BLOCKED):
            summary = dict(run.summary_json or {})
            return ConsolidationExecutionResult(
                run_id=str(run.run_id),
                status=run.status,
                idempotent=True,
                manifest_hash=str(run.output_manifest_hash or ""),
                issues_count=int(summary.get("issues_count") or 0),
                summary_json=summary,
            )

        run.status = ConsolidationRun.Status.RUNNING
        run.company_ids_json = scope_company_ids
        run.input_manifest_hash = input_manifest_hash
        run.summary_json = {}
        run.output_manifest_hash = ""
        run.completed_at = None
        run.executed_by = actor_user
        run.save(
            update_fields=[
                "status",
                "company_ids_json",
                "input_manifest_hash",
                "summary_json",
                "output_manifest_hash",
                "completed_at",
                "executed_by",
            ]
        )

        base_rows = _collect_base_trial_rows(company_ids=scope_company_ids, date_from=date_from, date_to=date_to)
        trial_map: dict[tuple[str, str], dict[str, Any]] = {}
        for row in base_rows:
            target = _get_or_create_trial_row(
                trial_map=trial_map,
                account_code=row["account_code"],
                account_name=row["account_name"],
                account_type=row["account_type"],
            )
            target["debit_total"] = _q_money(target["debit_total"] + _q_money(_to_decimal(row["debit_total"])))
            target["credit_total"] = _q_money(target["credit_total"] + _q_money(_to_decimal(row["credit_total"])))

        start_dt = timezone.make_aware(datetime.combine(date_from, time.min))
        end_dt = timezone.make_aware(datetime.combine(date_to, time.max))
        tx_rows = list(
            IntercompanyTransaction.objects.select_related("source_company", "target_company")
            .filter(source_company_id__in=scope_company_ids, target_company_id__in=scope_company_ids)
            .filter(status__in=[IntercompanyTransaction.Status.CONFIRMED, IntercompanyTransaction.Status.CLOSED])
            .filter(created_at__gte=start_dt, created_at__lte=end_dt)
            .order_by("created_at", "id")
        )
        account_pairs: set[tuple[int, str]] = set()
        for tx in tx_rows:
            if tx.source_account_code:
                account_pairs.add((int(tx.source_company_id), str(tx.source_account_code)))
            if tx.target_account_code:
                account_pairs.add((int(tx.target_company_id), str(tx.target_account_code)))
        company_to_codes: dict[int, list[str]] = {}
        for cid, code in account_pairs:
            company_to_codes.setdefault(cid, []).append(code)

        coa_map: dict[tuple[int, str], ChartOfAccount] = {}
        for cid, codes in company_to_codes.items():
            for coa_row in ChartOfAccount.objects.filter(company_id=cid, code__in=sorted(set(codes)), is_active=True):
                coa_map[(int(cid), str(coa_row.code))] = coa_row

        issues: list[dict[str, Any]] = []
        elimination_count = 0
        for tx in tx_rows:
            amount = _q_money(_to_decimal(tx.amount))
            if amount <= Decimal("0.00"):
                continue
            source_code = str(tx.source_account_code or "").strip().upper()
            target_code = str(tx.target_account_code or "").strip().upper()
            if not source_code or not target_code:
                issues.append(
                    {
                        "code": "CONSOLIDATION_ACCOUNT_CODE_MISSING",
                        "tx_id": str(tx.tx_id),
                        "detail": "Transacción sin source_account_code/target_account_code.",
                    }
                )
                continue
            source_account = coa_map.get((int(tx.source_company_id), source_code))
            target_account = coa_map.get((int(tx.target_company_id), target_code))
            if source_account is None or target_account is None:
                issues.append(
                    {
                        "code": "CONSOLIDATION_ACCOUNT_NOT_FOUND",
                        "tx_id": str(tx.tx_id),
                        "detail": "Cuenta contable no encontrada para eliminación intercompany.",
                        "source_account_code": source_code,
                        "target_account_code": target_code,
                    }
                )
                continue
            source_elimination_side = (
                IntercompanyTransaction.Side.DEBIT
                if tx.source_side == IntercompanyTransaction.Side.CREDIT
                else IntercompanyTransaction.Side.CREDIT
            )
            target_elimination_side = (
                IntercompanyTransaction.Side.DEBIT
                if tx.target_side == IntercompanyTransaction.Side.CREDIT
                else IntercompanyTransaction.Side.CREDIT
            )

            source_row = _get_or_create_trial_row(
                trial_map=trial_map,
                account_code=source_account.code,
                account_name=source_account.name,
                account_type=source_account.account_type,
            )
            target_row = _get_or_create_trial_row(
                trial_map=trial_map,
                account_code=target_account.code,
                account_name=target_account.name,
                account_type=target_account.account_type,
            )
            _append_elimination(row=source_row, side=source_elimination_side, amount=amount)
            _append_elimination(row=target_row, side=target_elimination_side, amount=amount)
            elimination_payload = {
                "tx_id": str(tx.tx_id),
                "amount": str(amount),
                "source_company_id": int(tx.source_company_id),
                "target_company_id": int(tx.target_company_id),
                "source_account_code": source_account.code,
                "target_account_code": target_account.code,
                "source_elimination_side": source_elimination_side,
                "target_elimination_side": target_elimination_side,
            }
            ConsolidationEliminationLink.objects.update_or_create(
                consolidation_run=run,
                intercompany_transaction=tx,
                defaults={"elimination_json": elimination_payload},
            )
            elimination_count += 1

        if strict and issues:
            summary_blocked = {
                "schema_version": 1,
                "status": ConsolidationRun.Status.BLOCKED,
                "period": {"year": int(year), "month": int(month), "date_from": str(date_from), "date_to": str(date_to)},
                "company_ids": scope_company_ids,
                "issues_count": int(len(issues)),
                "issues": issues,
                "elimination_count": int(elimination_count),
                "report": {},
            }
            output_hash = _json_hash(summary_blocked)
            run.status = ConsolidationRun.Status.BLOCKED
            run.summary_json = summary_blocked
            run.output_manifest_hash = output_hash
            run.completed_at = timezone.now()
            run.save(update_fields=["status", "summary_json", "output_manifest_hash", "completed_at"])
            for issue in issues:
                _open_consolidation_exception(run=run, code=str(issue.get("code") or "CONSOLIDATION_BLOCKED"), details_json=issue)
            publish_outbox_event(
                source_module="ACCOUNTING",
                event_type="ConsolidationRunBlocked",
                payload={
                    "run_id": str(run.run_id),
                    "status": run.status,
                    "issues_count": int(len(issues)),
                    "elimination_count": int(elimination_count),
                    "manifest_hash": output_hash,
                },
                company=parent_company,
                actor_user=actor_user,
            )
            return ConsolidationExecutionResult(
                run_id=str(run.run_id),
                status=run.status,
                idempotent=False,
                manifest_hash=output_hash,
                issues_count=int(len(issues)),
                summary_json=summary_blocked,
            )

        trial_rows = _build_trial_report(trial_map=trial_map)
        pnl = _build_pnl_from_trial(trial_rows=trial_rows)
        balance_sheet = _build_balance_sheet_from_trial(trial_rows=trial_rows, as_of=date_to)
        metrics = {
            "rows_count": int(len(trial_rows)),
            "elimination_count": int(elimination_count),
            "issues_count": int(len(issues)),
            "trial_hash": _json_hash({"rows": trial_rows}),
            "pnl_hash": _json_hash(pnl),
            "balance_sheet_hash": _json_hash(balance_sheet),
        }
        summary = {
            "schema_version": 1,
            "status": ConsolidationRun.Status.COMPLETED,
            "period": {"year": int(year), "month": int(month), "date_from": str(date_from), "date_to": str(date_to)},
            "company_ids": scope_company_ids,
            "metrics": metrics,
            "issues_count": int(len(issues)),
            "issues": issues,
            "trial_balance": {"rows": trial_rows},
            "pnl": pnl,
            "balance_sheet": balance_sheet,
        }
        output_hash = _json_hash(
            {
                "run_id": str(run.run_id),
                "period": summary["period"],
                "company_ids": scope_company_ids,
                "metrics": metrics,
                "issues_count": int(len(issues)),
            }
        )
        summary["manifest_hash"] = output_hash

        run.status = ConsolidationRun.Status.COMPLETED
        run.summary_json = summary
        run.output_manifest_hash = output_hash
        run.completed_at = timezone.now()
        run.save(update_fields=["status", "summary_json", "output_manifest_hash", "completed_at"])
        publish_outbox_event(
            source_module="ACCOUNTING",
            event_type="ConsolidationRunCompleted",
            payload={
                "run_id": str(run.run_id),
                "status": run.status,
                "year": int(year),
                "month": int(month),
                "company_ids": scope_company_ids,
                "rows_count": int(len(trial_rows)),
                "elimination_count": int(elimination_count),
                "issues_count": int(len(issues)),
                "manifest_hash": output_hash,
            },
            company=parent_company,
            actor_user=actor_user,
        )
        return ConsolidationExecutionResult(
            run_id=str(run.run_id),
            status=run.status,
            idempotent=False,
            manifest_hash=output_hash,
            issues_count=int(len(issues)),
            summary_json=summary,
        )


def get_consolidation_run_summary(*, run_id: str) -> dict[str, Any]:
    row = ConsolidationRun.objects.filter(run_id=run_id).first()
    if row is None:
        raise Phase7BValidationError(f"Consolidation run no encontrada: {run_id}")
    return {
        "run_id": str(row.run_id),
        "status": row.status,
        "parent_company_id": int(row.parent_company_id),
        "year": int(row.year),
        "month": int(row.month),
        "company_ids": list(row.company_ids_json or []),
        "input_manifest_hash": str(row.input_manifest_hash or ""),
        "output_manifest_hash": str(row.output_manifest_hash or ""),
        "started_at": row.started_at,
        "completed_at": row.completed_at,
        "summary": row.summary_json,
    }
