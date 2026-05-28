from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
import logging
from typing import Any

from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from apps.modulos.audit.writer import write_event
from apps.modulos.common.api_exceptions import ConflictError
from apps.modulos.common.domain_errors import IntegrationError
from apps.modulos.common.tender import TENDER_PAYMENT_METHOD_VALUES
from apps.modulos.iam.models import OrgUnit
from apps.modulos.integration.services import publish_outbox_event
from apps.modulos.parties.models import Party, PartyRole
from apps.modulos.parties.services import assign_party_role

from .fiscal_adapters import get_fiscal_adapter, resolve_fiscal_runtime_config
from .models import (
    BillingDocument,
    BillingLine,
    BillingSequence,
    BranchFiscalConfig,
    DocStatus,
    DocType,
    FiscalMode,
    FiscalPrintJob,
    FiscalStatus,
)

MONEY_Q = Decimal("0.01")
QTY_Q = Decimal("0.0001")
PRICE_Q = Decimal("0.000001")
TAX_Q = Decimal("0.0001")
logger = logging.getLogger(__name__)


_FISCAL_TRANSITIONS: dict[str, set[str]] = {
    FiscalStatus.NUMBER_RESERVED: {FiscalStatus.ISSUED, FiscalStatus.CONTINGENCY},
    FiscalStatus.ISSUED: {FiscalStatus.PRINTED, FiscalStatus.FAILED_PRINT, FiscalStatus.CONTINGENCY, FiscalStatus.VOIDED},
    FiscalStatus.FAILED_PRINT: {FiscalStatus.PRINTED, FiscalStatus.CONTINGENCY},
    FiscalStatus.CONTINGENCY: {FiscalStatus.PRINTED, FiscalStatus.VOIDED},
    FiscalStatus.PRINTED: {FiscalStatus.VOIDED},
    FiscalStatus.VOIDED: set(),
}


def _q_money(x: Decimal) -> Decimal:
    return x.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _q_qty(x: Decimal) -> Decimal:
    return x.quantize(QTY_Q, rounding=ROUND_HALF_UP)


def _q_price(x: Decimal) -> Decimal:
    return x.quantize(PRICE_Q, rounding=ROUND_HALF_UP)


def _q_tax(x: Decimal) -> Decimal:
    return x.quantize(TAX_Q, rounding=ROUND_HALF_UP)


class BillingError(Exception):
    pass


class BillingNotFoundError(BillingError):
    pass


@dataclass(frozen=True)
class CreateResult:
    doc_id: int


@dataclass(frozen=True)
class PrintQueueResult:
    doc_id: int
    job_id: int
    status: str
    created: bool
    fiscal_status: str


@dataclass(frozen=True)
class PrintProcessSummary:
    attempted: int
    printed: int
    retried: int
    failed: int
    contingency: int


def _compute_lines_and_totals(*, lines_in: list[dict]) -> tuple[list[dict], Decimal, Decimal, Decimal]:
    computed: list[dict] = []
    subtotal = Decimal("0.00")
    tax_total = Decimal("0.00")
    total = Decimal("0.00")

    for li in lines_in:
        qty = _q_qty(Decimal(li["quantity"]))
        unit_price = _q_price(Decimal(li["unit_price"]))
        tax_rate = _q_tax(Decimal(li.get("tax_rate", "0.0000")))

        if qty <= 0:
            raise BillingError("line.quantity must be > 0")
        if unit_price < 0:
            raise BillingError("line.unit_price must be >= 0")
        if tax_rate < 0:
            raise BillingError("line.tax_rate must be >= 0")

        raw_sub = qty * unit_price
        line_sub = _q_money(raw_sub)

        raw_tax = line_sub * tax_rate
        line_tax = _q_money(raw_tax)

        line_total = _q_money(line_sub + line_tax)

        subtotal += line_sub
        tax_total += line_tax
        total += line_total

        computed.append(
            {
                "description": li["description"],
                "quantity": qty,
                "unit_price": unit_price,
                "tax_rate": tax_rate,
                "line_subtotal": line_sub,
                "line_tax": line_tax,
                "line_total": line_total,
                "inventory_item_id": li.get("inventory_item_id"),
            }
        )

    return computed, _q_money(subtotal), _q_money(tax_total), _q_money(total)


def _fiscal_payload(*, doc: BillingDocument) -> dict:
    return {
        "fiscal_mode": doc.fiscal_mode_resolved,
        "fiscal_status": doc.fiscal_status or "",
        "fiscal_reference": doc.fiscal_reference or "",
        "fiscal_evidence_id": doc.fiscal_evidence_id or "",
        "printed_at": doc.printed_at.isoformat() if doc.printed_at else "",
        "print_attempt_count": int(doc.print_attempt_count),
        "contingency_reason": doc.contingency_reason or "",
    }


def _source_payload(*, doc: BillingDocument) -> dict:
    return {
        "payment_method": str(doc.payment_method or ""),
        "source_module": str(doc.source_module or ""),
        "source_type": str(doc.source_type or ""),
        "source_id": str(doc.source_id or ""),
        "customer_party_id": int(doc.customer_party_id) if doc.customer_party_id else None,
    }


def _normalize_payment_method(payment_method: str) -> str:
    normalized = str(payment_method or "").strip().upper()
    if normalized and normalized not in TENDER_PAYMENT_METHOD_VALUES:
        raise BillingError("invalid payment_method")
    return normalized


def _load_customer_party(*, customer_party_id: int | None, company: OrgUnit) -> Party | None:
    if customer_party_id is None:
        return None
    try:
        customer_party_pk = int(customer_party_id)
    except (TypeError, ValueError) as exc:
        raise BillingError("customer_party_id inválido") from exc
    if customer_party_pk <= 0:
        raise BillingError("customer_party_id inválido")

    customer_party = Party.objects.filter(id=customer_party_pk, company=company).first()
    if customer_party is None:
        raise BillingError("customer_party no existe en esta company")
    return customer_party


def _ensure_customer_party_role(*, party: Party, request, actor) -> None:
    party = Party.objects.select_for_update().get(pk=party.pk)
    active_exists = (
        PartyRole.objects.select_for_update()
        .filter(party=party, role=PartyRole.Role.CUSTOMER, is_active=True)
        .exists()
    )
    if not active_exists:
        assign_party_role(party=party, role=PartyRole.Role.CUSTOMER, request=request, actor=actor)


def _assert_fiscal_transition(*, current: str, target: str) -> None:
    if current == target:
        return
    if not current:
        return
    allowed = _FISCAL_TRANSITIONS.get(current, set())
    if target not in allowed:
        raise ConflictError(f"Fiscal transition not allowed: {current} -> {target}", code="CONFLICT")


def _set_fiscal_status(doc: BillingDocument, *, target: str) -> None:
    current = doc.fiscal_status or ""
    _assert_fiscal_transition(current=current, target=target)
    doc.fiscal_status = target


def _resolve_config(*, company: OrgUnit, branch: OrgUnit):
    return resolve_fiscal_runtime_config(company=company, branch=branch)


def _apply_accounting_link_to_doc(*, doc: BillingDocument, status: str, error: str = "", economic_event_id=None, journal_draft_id=None, journal_entry_id=None) -> None:
    doc.accounting_status = str(status or "")[:24]
    doc.accounting_error = str(error or "")[:255]
    doc.accounting_economic_event_id = int(economic_event_id) if economic_event_id else None
    doc.accounting_journal_draft_id = int(journal_draft_id) if journal_draft_id else None
    doc.accounting_journal_entry_id = int(journal_entry_id) if journal_entry_id else None
    doc.save(
        update_fields=[
            "accounting_status",
            "accounting_error",
            "accounting_economic_event",
            "accounting_journal_draft",
            "accounting_journal_entry",
        ]
    )


def _set_fiscal_issue_fields(*, doc: BillingDocument, mode: str, reference: str, evidence_id: str, metadata: dict | None) -> None:
    doc.fiscal_mode_resolved = mode
    if reference:
        doc.fiscal_reference = reference
    if evidence_id:
        doc.fiscal_evidence_id = evidence_id
    if metadata:
        merged = dict(doc.fiscal_metadata_json or {})
        merged.update(metadata)
        doc.fiscal_metadata_json = merged


def create_draft(
    *,
    request,
    actor,
    doc_type: str,
    series: str,
    currency: str,
    customer_name: str,
    customer_ref: str,
    is_fiscal: bool,
    lines: list[dict],
    customer_party_id: int | None = None,
    idempotency_key: str = "",
    source_module: str = "",
    source_type: str = "",
    source_id: str = "",
    payment_method: str = "",
    correlation_id: str = "",
    causation_id: str = "",
) -> CreateResult:
    company: OrgUnit = request.company
    branch: OrgUnit = request.branch

    if doc_type not in (DocType.INVOICE, DocType.CREDIT_NOTE):
        raise BillingError("invalid doc_type")

    if not lines:
        raise BillingError("lines required")

    computed, subtotal, tax_total, total = _compute_lines_and_totals(lines_in=lines)
    normalized_payment_method = _normalize_payment_method(payment_method)
    customer_party = _load_customer_party(customer_party_id=customer_party_id, company=company)

    with transaction.atomic():
        if idempotency_key:
            existing = BillingDocument.objects.filter(company=company, idempotency_key=idempotency_key).first()
            if existing:
                return CreateResult(existing.id)

        doc = BillingDocument.objects.create(
            company=company,
            branch=branch,
            doc_type=doc_type,
            status=DocStatus.DRAFT,
            series=series or "A",
            number=0,
            currency=currency or "NIO",
            customer_name=customer_name or "",
            customer_ref=customer_ref or "",
            customer_party=customer_party,
            subtotal=subtotal,
            tax_total=tax_total,
            total=total,
            is_fiscal=bool(is_fiscal),
            idempotency_key=idempotency_key or "",
            payment_method=normalized_payment_method,
            source_module=source_module or "",
            source_type=source_type or "",
            source_id=source_id or "",
            created_by=actor,
            fiscal_mode_resolved=FiscalMode.NOOP,
        )
        if customer_party is not None:
            _ensure_customer_party_role(party=customer_party, request=request, actor=actor)

        for c in computed:
            BillingLine.objects.create(
                doc=doc,
                description=c["description"],
                quantity=c["quantity"],
                unit_price=c["unit_price"],
                tax_rate=c["tax_rate"],
                line_subtotal=c["line_subtotal"],
                line_tax=c["line_tax"],
                line_total=c["line_total"],
                inventory_item_id=c["inventory_item_id"],
            )

        write_event(
            request=request,
            module="BILLING",
            event_type="BILLING_DOC_CREATED",
            reason_code="BILLING_OK",
            actor_user=actor,
            subject_type="BILLING_DOC",
            subject_id=str(doc.id),
            metadata={
                "doc_type": doc.doc_type,
                "status": doc.status,
                "series": doc.series,
                "currency": doc.currency,
                "customer_party_id": int(doc.customer_party_id) if doc.customer_party_id else None,
                "subtotal": str(doc.subtotal),
                "tax_total": str(doc.tax_total),
                "total": str(doc.total),
                "is_fiscal": bool(doc.is_fiscal),
                "idempotency_key": idempotency_key,
                "payment_method": doc.payment_method,
                "source_module": doc.source_module,
                "source_type": doc.source_type,
                "source_id": doc.source_id,
            },
        )
        publish_outbox_event(
            request=request,
            source_module="BILLING",
            event_type="DocumentDrafted",
            payload={
                "doc_id": doc.id,
                "doc_type": doc.doc_type,
                "status": doc.status,
                "series": doc.series,
                "currency": doc.currency,
                "subtotal": str(doc.subtotal),
                "tax_total": str(doc.tax_total),
                "total": str(doc.total),
                "is_fiscal": bool(doc.is_fiscal),
                "idempotency_key": doc.idempotency_key,
                **_source_payload(doc=doc),
            },
            actor_user=actor,
            company=company,
            branch=branch,
            correlation_id=correlation_id or "",
            causation_id=causation_id or "",
        )

        return CreateResult(doc.id)


def _allocate_document_number(*, doc: BillingDocument) -> None:
    seq, _ = BillingSequence.objects.select_for_update().get_or_create(
        company=doc.company,
        branch=doc.branch,
        doc_type=doc.doc_type,
        series=doc.series,
        defaults={"next_number": 1, "updated_at": timezone.now()},
    )
    number = int(seq.next_number)
    seq.next_number = number + 1
    seq.updated_at = timezone.now()
    seq.save(update_fields=["next_number", "updated_at"])
    doc.number = number


def _create_or_reuse_print_job(
    *,
    request,
    actor,
    doc: BillingDocument,
    idempotency_key: str = "",
) -> tuple[FiscalPrintJob, bool]:
    normalized_key = (idempotency_key or "").strip()
    if normalized_key:
        existing = FiscalPrintJob.objects.select_for_update().filter(doc=doc, idempotency_key=normalized_key).first()
        if existing:
            return existing, False
    job = FiscalPrintJob.objects.create(
        doc=doc,
        company=doc.company,
        branch=doc.branch,
        status=FiscalPrintJob.Status.PENDING,
        attempt_count=0,
        next_attempt_at=None,
        last_error="",
        idempotency_key=normalized_key,
        requested_by=actor,
    )
    publish_outbox_event(
        request=request,
        source_module="BILLING",
        event_type="BILLING.FiscalPrintRequested",
        payload={
            "doc_id": doc.id,
            "job_id": job.id,
            "idempotency_key": normalized_key,
            **_fiscal_payload(doc=doc),
        },
        actor_user=actor,
        company=doc.company,
        branch=doc.branch,
    )
    return job, True


def issue_doc(
    *,
    request,
    actor,
    doc_id: int,
    apply_inventory: bool = False,
    print_after_issue: bool = False,
    idempotency_key: str = "",
    correlation_id: str = "",
    causation_id: str = "",
) -> dict:
    company: OrgUnit = request.company
    branch: OrgUnit = request.branch

    with transaction.atomic():
        try:
            doc = BillingDocument.objects.select_for_update().get(id=doc_id, company=company, branch=branch)
        except BillingDocument.DoesNotExist as exc:
            raise BillingNotFoundError("documento no encontrado") from exc

        if doc.status == DocStatus.VOIDED:
            raise BillingError("cannot issue a voided document")
        if doc.status == DocStatus.ISSUED:
            out: dict[str, Any] = {"ok": True, "already_issued": True, "doc_id": doc.id, "number": doc.number}
            out.update(_fiscal_payload(doc=doc))
            return out

        _allocate_document_number(doc=doc)
        before = {
            "status": doc.status,
            "number": doc.number,
            "issued_at": str(doc.issued_at or ""),
            "fiscal_status": doc.fiscal_status,
        }

        doc.status = DocStatus.ISSUED
        doc.issued_at = timezone.now()

        runtime_cfg = _resolve_config(company=company, branch=branch)
        fiscal_adapter = get_fiscal_adapter(company=company, branch=branch)

        if runtime_cfg.mode == FiscalMode.B:
            reserved_ref = fiscal_adapter.attach_or_reserve_reference(doc=doc)
            _set_fiscal_status(doc, target=FiscalStatus.NUMBER_RESERVED)
            _set_fiscal_issue_fields(
                doc=doc,
                mode=runtime_cfg.mode,
                reference=reserved_ref,
                evidence_id="",
                metadata={"adapter_code": fiscal_adapter.adapter_code},
            )
            doc.save(
                update_fields=[
                    "number",
                    "status",
                    "issued_at",
                    "fiscal_mode_resolved",
                    "fiscal_status",
                    "fiscal_reference",
                    "fiscal_metadata_json",
                ]
            )
            publish_outbox_event(
                request=request,
                source_module="BILLING",
                event_type="BILLING.FiscalNumberReserved",
                payload={"doc_id": doc.id, "number": doc.number, **_fiscal_payload(doc=doc), **_source_payload(doc=doc)},
                actor_user=actor,
                company=company,
                branch=branch,
                correlation_id=correlation_id or "",
                causation_id=causation_id or "",
            )
        else:
            doc.save(update_fields=["number", "status", "issued_at"])

        fiscal_issue = fiscal_adapter.issue_document(request=request, doc=doc)
        fiscal_evidence = fiscal_adapter.produce_fiscal_evidence(request=request, doc=doc)

        if runtime_cfg.mode == FiscalMode.B:
            _set_fiscal_status(doc, target=FiscalStatus.ISSUED)
        elif not doc.fiscal_status:
            doc.fiscal_status = FiscalStatus.ISSUED

        _set_fiscal_issue_fields(
            doc=doc,
            mode=runtime_cfg.mode,
            reference=fiscal_issue.reference,
            evidence_id=fiscal_evidence.evidence_id,
            metadata=(fiscal_issue.metadata or {}),
        )
        doc.save(
            update_fields=[
                "fiscal_mode_resolved",
                "fiscal_status",
                "fiscal_reference",
                "fiscal_evidence_id",
                "fiscal_metadata_json",
            ]
        )

        if apply_inventory:
            from apps.kernels.inventarios.services import post_issue  # import local para evitar ciclos

            warehouse_id = request.data.get("warehouse_id")
            if not warehouse_id:
                raise BillingError("apply_inventory requires warehouse_id in request body")

            for ln in doc.lines.select_related("inventory_item").all():
                if ln.inventory_item_id:
                    post_issue(
                        request=request,
                        actor=actor,
                        warehouse_id=int(warehouse_id),
                        item_id=int(ln.inventory_item_id),
                        qty=ln.quantity,
                        allow_negative=False,
                        idempotency_key=f"bill:{doc.id}:ln:{ln.id}",
                        note=f"Auto-issue by billing doc {doc.id}",
                        source_module="BILLING",
                        source_type="DOC_ISSUE",
                        source_id=str(doc.id),
                    )

        after = {
            "status": doc.status,
            "number": doc.number,
            "issued_at": str(doc.issued_at or ""),
            "fiscal_status": doc.fiscal_status,
        }

        write_event(
            request=request,
            module="BILLING",
            event_type="BILLING_DOC_ISSUED",
            reason_code="BILLING_OK",
            actor_user=actor,
            subject_type="BILLING_DOC",
            subject_id=str(doc.id),
            before_snapshot=before,
            after_snapshot=after,
            metadata={
                "apply_inventory": bool(apply_inventory),
                "fiscal_adapter_mode": runtime_cfg.mode,
                "fiscal_adapter_code": fiscal_adapter.adapter_code,
                "fiscal_issue_status": fiscal_issue.status,
                "fiscal_reference": fiscal_issue.reference,
                "fiscal_evidence_id": fiscal_evidence.evidence_id,
            },
        )
        issued_outbox = publish_outbox_event(
            request=request,
            source_module="BILLING",
            event_type="DocumentIssued",
            payload={
                "doc_id": doc.id,
                "doc_type": doc.doc_type,
                "status": doc.status,
                "series": doc.series,
                "number": doc.number,
                "currency": doc.currency,
                "subtotal": str(doc.subtotal),
                "tax_total": str(doc.tax_total),
                "total": str(doc.total),
                "is_fiscal": bool(doc.is_fiscal),
                "apply_inventory": bool(apply_inventory),
                "fiscal_adapter_mode": runtime_cfg.mode,
                "fiscal_adapter_code": fiscal_adapter.adapter_code,
                "fiscal_issue_status": fiscal_issue.status,
                "fiscal_reference": fiscal_issue.reference,
                "fiscal_evidence_id": fiscal_evidence.evidence_id,
                "fiscal_status": doc.fiscal_status,
                **_source_payload(doc=doc),
            },
            actor_user=actor,
            company=company,
            branch=branch,
            correlation_id=correlation_id or "",
            causation_id=causation_id or "",
        )
        accounting_link = None
        try:
            from apps.kernels.accounting.services import (
                apply_accounting_link_to_outbox_event,
                link_operational_event_to_accounting,
            )

            accounting_link = link_operational_event_to_accounting(
                outbox_event=issued_outbox,
                actor_user=actor,
            )
            apply_accounting_link_to_outbox_event(outbox_event=issued_outbox, link=accounting_link)
            _apply_accounting_link_to_doc(
                doc=doc,
                status=accounting_link.status,
                error=accounting_link.error,
                economic_event_id=accounting_link.economic_event_id,
                journal_draft_id=accounting_link.journal_draft_id,
                journal_entry_id=accounting_link.journal_entry_id,
            )
        except (ImportError, AttributeError, IntegrationError, RuntimeError, ValueError) as exc:
            wrapped = IntegrationError(
                "Billing accounting link failed during issue flow.",
                code="BILLING_ACCOUNTING_LINK_ISSUE_FAILED",
                context={
                    "request_id": str(getattr(request, "request_id", "") or ""),
                    "company_id": company.id,
                    "branch_id": branch.id,
                    "event_id": str(getattr(issued_outbox, "event_id", "")),
                    "command_id": str(doc.id),
                    "doc_id": int(doc.id),
                },
            )
            logger.exception(
                "billing_accounting_link_issue_failed",
                extra={**wrapped.context, "error_code": wrapped.code},
            )
            _apply_accounting_link_to_doc(
                doc=doc,
                status=BillingDocument.AccountingStatus.DRAFT_EXCEPTION,
                error=f"{wrapped.code}:{exc}",
            )
        publish_outbox_event(
            request=request,
            source_module="BILLING",
            event_type="BILLING.FiscalDocumentIssued",
            payload={"doc_id": doc.id, **_fiscal_payload(doc=doc), **_source_payload(doc=doc)},
            actor_user=actor,
            company=company,
            branch=branch,
            correlation_id=correlation_id or "",
            causation_id=causation_id or "",
        )

        queued_job_id = None
        if runtime_cfg.mode == FiscalMode.B and runtime_cfg.print_required and bool(print_after_issue):
            job, _ = _create_or_reuse_print_job(
                request=request,
                actor=actor,
                doc=doc,
                idempotency_key=idempotency_key or f"issue-print:{doc.id}",
            )
            queued_job_id = job.id

        out = {"ok": True, "doc_id": doc.id, "number": doc.number}
        out.update(_fiscal_payload(doc=doc))
        out.update(
            {
                "accounting_status": doc.accounting_status,
                "accounting_error": doc.accounting_error,
                "journal_draft_id": doc.accounting_journal_draft_id,
                "journal_entry_id": doc.accounting_journal_entry_id,
            }
        )
        if queued_job_id is not None:
            out["print_job_id"] = queued_job_id
        return out


def queue_fiscal_print(
    *,
    request,
    actor,
    doc_id: int,
    idempotency_key: str = "",
) -> PrintQueueResult:
    company: OrgUnit = request.company
    branch: OrgUnit = request.branch
    with transaction.atomic():
        try:
            doc = BillingDocument.objects.select_for_update().get(id=doc_id, company=company, branch=branch)
        except BillingDocument.DoesNotExist as exc:
            raise BillingNotFoundError("documento no encontrado") from exc

        if doc.status != DocStatus.ISSUED:
            raise BillingError("only issued documents can be printed")
        if doc.fiscal_mode_resolved != FiscalMode.B:
            raise BillingError("document is not configured for fiscal mode B")
        if doc.fiscal_status == FiscalStatus.VOIDED:
            raise BillingError("voided document cannot be printed")

        job, created = _create_or_reuse_print_job(
            request=request,
            actor=actor,
            doc=doc,
            idempotency_key=idempotency_key,
        )
        return PrintQueueResult(
            doc_id=doc.id,
            job_id=job.id,
            status=job.status,
            created=created,
            fiscal_status=doc.fiscal_status,
        )


def mark_doc_contingency(
    *,
    request,
    actor,
    doc_id: int,
    reason: str,
) -> dict:
    company: OrgUnit = request.company
    branch: OrgUnit = request.branch

    with transaction.atomic():
        try:
            doc = BillingDocument.objects.select_for_update().get(id=doc_id, company=company, branch=branch)
        except BillingDocument.DoesNotExist as exc:
            raise BillingNotFoundError("documento no encontrado") from exc

        if doc.status != DocStatus.ISSUED:
            raise BillingError("only issued documents can move to contingency")
        if doc.fiscal_mode_resolved != FiscalMode.B:
            raise BillingError("document is not configured for fiscal mode B")
        if doc.fiscal_status == FiscalStatus.CONTINGENCY:
            out: dict[str, Any] = {"ok": True, "already_contingency": True, "doc_id": doc.id}
            out.update(_fiscal_payload(doc=doc))
            return out

        _set_fiscal_status(doc, target=FiscalStatus.CONTINGENCY)
        doc.contingency_reason = (reason or "CONTINGENCY")[:255]
        doc.contingency_at = timezone.now()
        doc.save(update_fields=["fiscal_status", "contingency_reason", "contingency_at"])

        fiscal_adapter = get_fiscal_adapter(doc=doc)
        fiscal_adapter.record_contingency(request=request, doc=doc, reason=doc.contingency_reason)

        write_event(
            request=request,
            module="BILLING",
            event_type="BILLING_DOC_CONTINGENCY_RECORDED",
            reason_code="BILLING_CONTINGENCY",
            actor_user=actor,
            subject_type="BILLING_DOC",
            subject_id=str(doc.id),
            metadata={"reason": doc.contingency_reason, **_fiscal_payload(doc=doc)},
        )
        publish_outbox_event(
            request=request,
            source_module="BILLING",
            event_type="BILLING.FiscalContingencyRecorded",
            payload={"doc_id": doc.id, "reason": doc.contingency_reason, **_fiscal_payload(doc=doc)},
            actor_user=actor,
            company=doc.company,
            branch=doc.branch,
        )
        out = {"ok": True, "doc_id": doc.id}
        out.update(_fiscal_payload(doc=doc))
        return out


def resolve_doc_contingency(
    *,
    request,
    actor,
    doc_id: int,
    action: str,
    idempotency_key: str = "",
    reason: str = "",
) -> dict:
    action = str(action or "").upper()
    if action not in ("RETRY_PRINT", "VOID"):
        raise BillingError("action must be RETRY_PRINT or VOID")

    if action == "RETRY_PRINT":
        queued = queue_fiscal_print(
            request=request,
            actor=actor,
            doc_id=doc_id,
            idempotency_key=idempotency_key or f"contingency-retry:{doc_id}",
        )
        return {
            "ok": True,
            "action": action,
            "doc_id": queued.doc_id,
            "job_id": queued.job_id,
            "job_status": queued.status,
            "fiscal_status": queued.fiscal_status,
        }

    return void_doc(
        request=request,
        actor=actor,
        doc_id=doc_id,
        reason=reason or "CONTINGENCY_VOID",
    )


def _process_print_job(
    *,
    job: FiscalPrintJob,
    actor=None,
    now=None,
) -> tuple[str, bool]:
    clock = now or timezone.now()
    doc = BillingDocument.objects.select_for_update().get(pk=job.doc_id)
    fiscal_adapter = get_fiscal_adapter(doc=doc)
    cfg = _resolve_config(company=doc.company, branch=doc.branch)
    max_attempts = max(1, int(cfg.contingency_max_attempts or 5))

    next_attempt = int(job.attempt_count) + 1
    doc.print_attempt_count = next_attempt
    job.attempt_count = next_attempt

    try:
        result = fiscal_adapter.print_document(request=None, doc=doc)
        _set_fiscal_status(doc, target=FiscalStatus.PRINTED)
        doc.printed_at = clock
        doc.last_print_error = ""
        _set_fiscal_issue_fields(
            doc=doc,
            mode=doc.fiscal_mode_resolved or cfg.mode,
            reference=result.reference,
            evidence_id="",
            metadata=result.metadata or {},
        )

        job.status = FiscalPrintJob.Status.PRINTED
        job.next_attempt_at = None
        job.last_error = ""
        job.save(update_fields=["status", "next_attempt_at", "last_error", "attempt_count", "updated_at"])

        doc.save(
            update_fields=[
                "fiscal_status",
                "fiscal_reference",
                "fiscal_metadata_json",
                "printed_at",
                "last_print_error",
                "print_attempt_count",
            ]
        )
        publish_outbox_event(
            source_module="BILLING",
            event_type="BILLING.FiscalPrinted",
            payload={"doc_id": doc.id, "job_id": job.id, **_fiscal_payload(doc=doc)},
            actor_user=actor,
            company=doc.company,
            branch=doc.branch,
        )
        return "PRINTED", False
    except (RuntimeError, ValueError, OSError, BillingError, IntegrationError) as exc:
        wrapped = IntegrationError(
            "Fiscal print job processing failed.",
            code="BILLING_FISCAL_PRINT_FAILED",
            context={
                "request_id": "",
                "company_id": doc.company_id,
                "branch_id": doc.branch_id,
                "event_id": "",
                "command_id": str(job.id),
                "doc_id": int(doc.id),
                "job_id": int(job.id),
            },
            retryable=True,
        )
        logger.warning(
            "billing_fiscal_print_retryable_error",
            extra={**wrapped.context, "error_code": wrapped.code},
        )
        error_text = (str(exc) or "print_error")[:255]
        doc.last_print_error = error_text
        is_contingency = next_attempt >= max_attempts

        if is_contingency:
            _set_fiscal_status(doc, target=FiscalStatus.CONTINGENCY)
            doc.contingency_at = clock
            doc.contingency_reason = "PRINT_RETRY_EXHAUSTED"
            job.status = FiscalPrintJob.Status.FAILED
            job.next_attempt_at = None
            job.last_error = error_text
            publish_outbox_event(
                source_module="BILLING",
                event_type="BILLING.FiscalContingencyRecorded",
                payload={
                    "doc_id": doc.id,
                    "job_id": job.id,
                    "reason": doc.contingency_reason,
                    **_fiscal_payload(doc=doc),
                },
                actor_user=actor,
                company=doc.company,
                branch=doc.branch,
            )
            result_status = "FAILED_CONTINGENCY"
        else:
            if doc.fiscal_status in (FiscalStatus.ISSUED, FiscalStatus.FAILED_PRINT):
                _set_fiscal_status(doc, target=FiscalStatus.FAILED_PRINT)
            backoff_min = min(2**next_attempt, 60)
            job.status = FiscalPrintJob.Status.RETRY
            job.next_attempt_at = clock + timedelta(minutes=backoff_min)
            job.last_error = error_text
            publish_outbox_event(
                source_module="BILLING",
                event_type="BILLING.FiscalPrintFailed",
                payload={
                    "doc_id": doc.id,
                    "job_id": job.id,
                    "attempt_count": next_attempt,
                    "next_attempt_at": job.next_attempt_at.isoformat() if job.next_attempt_at else "",
                    "error": error_text,
                    **_fiscal_payload(doc=doc),
                },
                actor_user=actor,
                company=doc.company,
                branch=doc.branch,
            )
            result_status = "RETRY"

        job.save(update_fields=["status", "next_attempt_at", "last_error", "attempt_count", "updated_at"])
        doc.save(
            update_fields=[
                "fiscal_status",
                "contingency_reason",
                "contingency_at",
                "last_print_error",
                "print_attempt_count",
            ]
        )
        return result_status, is_contingency


def process_fiscal_print_jobs(
    *,
    limit: int = 100,
    now=None,
    company_id: int | None = None,
    branch_id: int | None = None,
    actor=None,
) -> PrintProcessSummary:
    clock = now or timezone.now()
    qs = FiscalPrintJob.objects.filter(status__in=[FiscalPrintJob.Status.PENDING, FiscalPrintJob.Status.RETRY]).filter(
        Q(next_attempt_at__isnull=True) | Q(next_attempt_at__lte=clock)
    )
    if company_id is not None:
        qs = qs.filter(company_id=int(company_id))
    if branch_id is not None:
        qs = qs.filter(branch_id=int(branch_id))

    rows = list(qs.order_by("created_at", "id").values_list("id", flat=True)[: int(limit)])
    attempted = printed = retried = failed = contingency = 0
    for job_id in rows:
        attempted += 1
        with transaction.atomic():
            job = FiscalPrintJob.objects.select_for_update().select_related("doc").get(id=job_id)
            result_status, is_contingency = _process_print_job(job=job, actor=actor, now=clock)
            if result_status == "PRINTED":
                printed += 1
            elif result_status == "RETRY":
                retried += 1
            else:
                failed += 1
            if is_contingency:
                contingency += 1
    return PrintProcessSummary(
        attempted=attempted,
        printed=printed,
        retried=retried,
        failed=failed,
        contingency=contingency,
    )


def retry_fiscal_print_job(
    *,
    job_id: int,
    actor=None,
) -> FiscalPrintJob:
    with transaction.atomic():
        job = FiscalPrintJob.objects.select_for_update().select_related("doc").get(id=job_id)
        if job.status == FiscalPrintJob.Status.PRINTED:
            return job
        job.status = FiscalPrintJob.Status.PENDING
        job.next_attempt_at = None
        job.last_error = ""
        job.save(update_fields=["status", "next_attempt_at", "last_error", "updated_at"])
        return job


def void_doc(
    *,
    request,
    actor,
    doc_id: int,
    reason: str,
    correlation_id: str = "",
    causation_id: str = "",
) -> dict:
    company: OrgUnit = request.company
    branch: OrgUnit = request.branch

    with transaction.atomic():
        try:
            doc = BillingDocument.objects.select_for_update().get(id=doc_id, company=company, branch=branch)
        except BillingDocument.DoesNotExist as exc:
            raise BillingNotFoundError("documento no encontrado") from exc

        if doc.status == DocStatus.VOIDED:
            return {"ok": True, "already_voided": True}
        if doc.status == DocStatus.DRAFT:
            raise BillingError("cannot void a draft document")

        before = {
            "status": doc.status,
            "void_reason": doc.void_reason,
            "fiscal_status": doc.fiscal_status,
        }

        fiscal_adapter = get_fiscal_adapter(doc=doc)
        fiscal_void = fiscal_adapter.void_document(request=request, doc=doc, reason=reason or "VOID")

        if doc.fiscal_status:
            _set_fiscal_status(doc, target=FiscalStatus.VOIDED)

        doc.status = DocStatus.VOIDED
        doc.voided_at = timezone.now()
        doc.void_reason = reason or "VOID"
        if doc.fiscal_mode_resolved == FiscalMode.B:
            active_jobs = FiscalPrintJob.objects.filter(
                doc=doc,
                status__in=[FiscalPrintJob.Status.PENDING, FiscalPrintJob.Status.RETRY],
            )
            active_jobs.update(status=FiscalPrintJob.Status.FAILED, next_attempt_at=None, last_error="DOC_VOIDED")

        _set_fiscal_issue_fields(
            doc=doc,
            mode=doc.fiscal_mode_resolved or FiscalMode.NOOP,
            reference=fiscal_void.reference,
            evidence_id=doc.fiscal_evidence_id,
            metadata=(fiscal_void.metadata or {}),
        )
        doc.save(
            update_fields=[
                "status",
                "voided_at",
                "void_reason",
                "fiscal_status",
                "fiscal_reference",
                "fiscal_metadata_json",
            ]
        )

        after = {"status": doc.status, "void_reason": doc.void_reason, "fiscal_status": doc.fiscal_status}

        write_event(
            request=request,
            module="BILLING",
            event_type="BILLING_DOC_VOIDED",
            reason_code="BILLING_VOID",
            actor_user=actor,
            subject_type="BILLING_DOC",
            subject_id=str(doc.id),
            before_snapshot=before,
            after_snapshot=after,
            metadata={
                "fiscal_adapter_mode": getattr(fiscal_adapter, "mode", "UNKNOWN"),
                "fiscal_adapter_code": getattr(fiscal_adapter, "adapter_code", ""),
                "fiscal_void_status": fiscal_void.status,
                "fiscal_reference": fiscal_void.reference,
            },
        )
        voided_outbox = publish_outbox_event(
            request=request,
            source_module="BILLING",
            event_type="DocumentVoided",
            payload={
                "doc_id": doc.id,
                "doc_type": doc.doc_type,
                "status": doc.status,
                "series": doc.series,
                "number": doc.number,
                "void_reason": doc.void_reason,
                "fiscal_adapter_mode": getattr(fiscal_adapter, "mode", "UNKNOWN"),
                "fiscal_adapter_code": getattr(fiscal_adapter, "adapter_code", ""),
                "fiscal_void_status": fiscal_void.status,
                "fiscal_reference": fiscal_void.reference,
                "fiscal_status": doc.fiscal_status,
                **_source_payload(doc=doc),
            },
            actor_user=actor,
            company=company,
            branch=branch,
            correlation_id=correlation_id or "",
            causation_id=causation_id or "",
        )
        try:
            from apps.kernels.accounting.services import (
                apply_accounting_link_to_outbox_event,
                link_operational_event_to_accounting,
            )

            accounting_link = link_operational_event_to_accounting(
                outbox_event=voided_outbox,
                actor_user=actor,
            )
            apply_accounting_link_to_outbox_event(outbox_event=voided_outbox, link=accounting_link)
            _apply_accounting_link_to_doc(
                doc=doc,
                status=accounting_link.status,
                error=accounting_link.error,
                economic_event_id=accounting_link.economic_event_id,
                journal_draft_id=accounting_link.journal_draft_id,
                journal_entry_id=accounting_link.journal_entry_id,
            )
        except (ImportError, AttributeError, IntegrationError, RuntimeError, ValueError) as exc:
            wrapped = IntegrationError(
                "Billing accounting link failed during void flow.",
                code="BILLING_ACCOUNTING_LINK_VOID_FAILED",
                context={
                    "request_id": str(getattr(request, "request_id", "") or ""),
                    "company_id": company.id,
                    "branch_id": branch.id,
                    "event_id": str(getattr(voided_outbox, "event_id", "")),
                    "command_id": str(doc.id),
                    "doc_id": int(doc.id),
                },
            )
            logger.exception(
                "billing_accounting_link_void_failed",
                extra={**wrapped.context, "error_code": wrapped.code},
            )
            _apply_accounting_link_to_doc(
                doc=doc,
                status=BillingDocument.AccountingStatus.DRAFT_EXCEPTION,
                error=f"{wrapped.code}:{exc}",
            )
        return {
            "ok": True,
            "doc_id": doc.id,
            "fiscal_status": doc.fiscal_status,
            "accounting_status": doc.accounting_status,
            "accounting_error": doc.accounting_error,
            "journal_draft_id": doc.accounting_journal_draft_id,
            "journal_entry_id": doc.accounting_journal_entry_id,
        }


def get_or_update_branch_fiscal_config(
    *,
    company: OrgUnit,
    branch: OrgUnit,
    actor=None,
    data: dict | None = None,
):
    payload = data or {}
    with transaction.atomic():
        cfg, _ = BranchFiscalConfig.objects.select_for_update().get_or_create(
            company=company,
            branch=branch,
            defaults={
                "fiscal_mode": FiscalMode.NOOP,
                "adapter_code": "",
                "print_required": True,
                "strict_integrity": True,
                "contingency_max_attempts": 5,
                "is_active": True,
            },
        )

        changed = False
        if payload:
            mode = payload.get("fiscal_mode")
            if mode is not None and mode in FiscalMode.values and cfg.fiscal_mode != mode:
                cfg.fiscal_mode = mode
                changed = True
            if "adapter_code" in payload and cfg.adapter_code != str(payload.get("adapter_code") or ""):
                cfg.adapter_code = str(payload.get("adapter_code") or "")
                changed = True
            if "print_required" in payload and cfg.print_required != bool(payload.get("print_required")):
                cfg.print_required = bool(payload.get("print_required"))
                changed = True
            if "strict_integrity" in payload and cfg.strict_integrity != bool(payload.get("strict_integrity")):
                cfg.strict_integrity = bool(payload.get("strict_integrity"))
                changed = True
            if "contingency_max_attempts" in payload:
                next_attempts = max(1, int(payload.get("contingency_max_attempts") or 5))
                if cfg.contingency_max_attempts != next_attempts:
                    cfg.contingency_max_attempts = next_attempts
                    changed = True
            if "is_active" in payload and cfg.is_active != bool(payload.get("is_active")):
                cfg.is_active = bool(payload.get("is_active"))
                changed = True
            if changed:
                cfg.save()
                write_event(
                    request=None,
                    module="BILLING",
                    event_type="BILLING_BRANCH_FISCAL_CONFIG_UPDATED",
                    reason_code="BILLING_OK",
                    actor_user=actor,
                    subject_type="BRANCH",
                    subject_id=str(branch.id),
                    metadata={
                        "company_id": company.id,
                        "branch_id": branch.id,
                        "fiscal_mode": cfg.fiscal_mode,
                        "adapter_code": cfg.adapter_code,
                        "print_required": cfg.print_required,
                        "strict_integrity": cfg.strict_integrity,
                        "contingency_max_attempts": cfg.contingency_max_attempts,
                        "is_active": cfg.is_active,
                    },
                )
        return cfg


# Compat: mantener endpoint/tests existentes (/api/billing/invoices/)
def create_invoice(*, request, company, branch, actor_user, customer_name: str, total_amount):
    total_amount = _q_money(Decimal(str(total_amount)))

    res = create_draft(
        request=request,
        actor=actor_user,
        doc_type=DocType.INVOICE,
        series="A",
        currency="NIO",
        customer_name=customer_name,
        customer_ref="",
        is_fiscal=False,
        lines=[
            {
                "description": "Invoice total",
                "quantity": Decimal("1.0000"),
                "unit_price": total_amount,
                "tax_rate": Decimal("0.0000"),
            }
        ],
        idempotency_key="",
    )

    doc = BillingDocument.objects.get(id=res.doc_id)

    write_event(
        request=request,
        module="BILLING",
        event_type="BILLING_INVOICE_CREATED",
        reason_code="BILLING_OK",
        actor_user=actor_user,
        subject_type="INVOICE",
        subject_id=str(doc.id),
        metadata={
            "customer_name": customer_name,
            "total_amount": str(total_amount),
            "status": doc.status,
        },
    )

    return doc
