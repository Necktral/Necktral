from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import logging

from django.db import transaction
from django.utils import timezone

from apps.modulos.common.domain_errors import IntegrationError
from apps.modulos.iam.models import OrgUnit
from apps.modulos.integration.services import publish_outbox_event

from .models import PurchaseDocument, PurchaseDocStatus, PurchaseDocType, PurchaseSequence


class ProcurementError(Exception):
    pass


class ProcurementNotFoundError(ProcurementError):
    pass


@dataclass(frozen=True)
class PurchaseCreateResult:
    doc_id: int


@dataclass(frozen=True)
class ProcurementAccountingResult:
    status: str
    error: str = ""
    journal_draft_id: int | None = None
    journal_entry_id: int | None = None


logger = logging.getLogger(__name__)


def _allocate_number(*, doc: PurchaseDocument) -> None:
    seq, _ = PurchaseSequence.objects.select_for_update().get_or_create(
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


def _set_doc_accounting(
    *,
    doc: PurchaseDocument,
    status: str,
    error: str = "",
    economic_event_id=None,
    journal_draft_id=None,
    journal_entry_id=None,
) -> None:
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


def _link_accounting_for_doc(*, doc: PurchaseDocument, outbox_event, actor=None) -> ProcurementAccountingResult:
    try:
        from apps.modulos.accounting.services import (
            apply_accounting_link_to_outbox_event,
            link_operational_event_to_accounting,
        )

        link = link_operational_event_to_accounting(outbox_event=outbox_event, actor_user=actor)
        apply_accounting_link_to_outbox_event(outbox_event=outbox_event, link=link)
        _set_doc_accounting(
            doc=doc,
            status=str(link.status or ""),
            error=str(link.error or ""),
            economic_event_id=link.economic_event_id,
            journal_draft_id=link.journal_draft_id,
            journal_entry_id=link.journal_entry_id,
        )
        return ProcurementAccountingResult(
            status=str(link.status or ""),
            error=str(link.error or ""),
            journal_draft_id=link.journal_draft_id,
            journal_entry_id=link.journal_entry_id,
        )
    except (ImportError, AttributeError, ValueError, RuntimeError, IntegrationError) as exc:
        wrapped = IntegrationError(
            "Procurement to accounting link failed.",
            code="PROCUREMENT_ACCOUNTING_LINK_FAILED",
            context={
                "request_id": str(getattr(outbox_event, "correlation_id", "") or ""),
                "company_id": int(doc.company_id),
                "branch_id": int(doc.branch_id),
                "event_id": str(getattr(outbox_event, "event_id", "")),
                "doc_id": int(doc.id),
            },
        )
        logger.exception(
            "procurement_accounting_link_failed",
            extra={
                **wrapped.context,
                "error_code": wrapped.code,
            },
        )
        _set_doc_accounting(
            doc=doc,
            status=PurchaseDocument.AccountingStatus.DRAFT_EXCEPTION,
            error=f"{wrapped.code}:{exc}",
        )
        return ProcurementAccountingResult(
            status=PurchaseDocument.AccountingStatus.DRAFT_EXCEPTION,
            error=f"{wrapped.code}:{exc}",
            journal_draft_id=doc.accounting_journal_draft_id,
            journal_entry_id=doc.accounting_journal_entry_id,
        )


def create_purchase_draft(
    *,
    request,
    actor,
    doc_type: str,
    series: str,
    currency: str,
    supplier_name: str,
    supplier_ref: str,
    external_ref: str,
    subtotal: Decimal,
    tax_total: Decimal,
    total: Decimal,
    notes: str = "",
    metadata_json: dict | None = None,
    idempotency_key: str = "",
) -> PurchaseCreateResult:
    company: OrgUnit = request.company
    branch: OrgUnit = request.branch

    if doc_type not in PurchaseDocType.values:
        raise ProcurementError("invalid doc_type")

    with transaction.atomic():
        if idempotency_key:
            existing = PurchaseDocument.objects.filter(company=company, idempotency_key=idempotency_key).first()
            if existing is not None:
                return PurchaseCreateResult(doc_id=int(existing.id))

        doc = PurchaseDocument.objects.create(
            company=company,
            branch=branch,
            doc_type=doc_type,
            status=PurchaseDocStatus.DRAFT,
            series=(series or "P").strip().upper(),
            number=0,
            currency=(currency or "NIO").strip().upper(),
            supplier_name=supplier_name or "",
            supplier_ref=supplier_ref or "",
            external_ref=external_ref or "",
            subtotal=Decimal(str(subtotal)),
            tax_total=Decimal(str(tax_total)),
            total=Decimal(str(total)),
            notes=notes or "",
            metadata_json=dict(metadata_json or {}),
            idempotency_key=idempotency_key or "",
            created_by=actor,
        )

        publish_outbox_event(
            request=request,
            source_module="PROCUREMENT",
            event_type="ProcurementDocumentDrafted",
            payload={
                "doc_id": int(doc.id),
                "doc_type": doc.doc_type,
                "status": doc.status,
                "series": doc.series,
                "currency": doc.currency,
                "subtotal": str(doc.subtotal),
                "tax_total": str(doc.tax_total),
                "total": str(doc.total),
                "supplier_ref": doc.supplier_ref,
                "external_ref": doc.external_ref,
                "idempotency_key": doc.idempotency_key,
            },
            actor_user=actor,
            company=company,
            branch=branch,
        )
        return PurchaseCreateResult(doc_id=int(doc.id))


def post_purchase_document(*, request, actor, doc_id: int) -> dict:
    company: OrgUnit = request.company
    branch: OrgUnit = request.branch

    with transaction.atomic():
        try:
            doc = PurchaseDocument.objects.select_for_update().get(id=int(doc_id), company=company, branch=branch)
        except PurchaseDocument.DoesNotExist as exc:
            raise ProcurementNotFoundError("documento de compra no encontrado") from exc

        if doc.status == PurchaseDocStatus.VOIDED:
            raise ProcurementError("cannot post a voided purchase document")
        if doc.status == PurchaseDocStatus.POSTED:
            return {
                "ok": True,
                "already_posted": True,
                "doc_id": int(doc.id),
                "number": int(doc.number),
                "accounting_status": str(doc.accounting_status or ""),
                "accounting_error": str(doc.accounting_error or ""),
                "journal_draft_id": doc.accounting_journal_draft_id,
                "journal_entry_id": doc.accounting_journal_entry_id,
            }

        _allocate_number(doc=doc)
        doc.status = PurchaseDocStatus.POSTED
        doc.posted_at = timezone.now()
        doc.save(update_fields=["number", "status", "posted_at"])

        outbox_event = publish_outbox_event(
            request=request,
            source_module="PROCUREMENT",
            event_type="ProcurementDocumentPosted",
            payload={
                "doc_id": int(doc.id),
                "doc_type": doc.doc_type,
                "status": doc.status,
                "series": doc.series,
                "number": int(doc.number),
                "currency": doc.currency,
                "subtotal": str(doc.subtotal),
                "tax_total": str(doc.tax_total),
                "total": str(doc.total),
                "supplier_ref": doc.supplier_ref,
                "external_ref": doc.external_ref,
            },
            actor_user=actor,
            company=company,
            branch=branch,
        )
        accounting = _link_accounting_for_doc(doc=doc, outbox_event=outbox_event, actor=actor)

        return {
            "ok": True,
            "doc_id": int(doc.id),
            "status": doc.status,
            "number": int(doc.number),
            "accounting_status": accounting.status,
            "accounting_error": accounting.error,
            "journal_draft_id": accounting.journal_draft_id,
            "journal_entry_id": accounting.journal_entry_id,
        }


def void_purchase_document(*, request, actor, doc_id: int, reason: str = "VOID") -> dict:
    company: OrgUnit = request.company
    branch: OrgUnit = request.branch

    with transaction.atomic():
        try:
            doc = PurchaseDocument.objects.select_for_update().get(id=int(doc_id), company=company, branch=branch)
        except PurchaseDocument.DoesNotExist as exc:
            raise ProcurementNotFoundError("documento de compra no encontrado") from exc

        if doc.status == PurchaseDocStatus.VOIDED:
            return {
                "ok": True,
                "already_voided": True,
                "doc_id": int(doc.id),
                "accounting_status": str(doc.accounting_status or ""),
                "accounting_error": str(doc.accounting_error or ""),
                "journal_draft_id": doc.accounting_journal_draft_id,
                "journal_entry_id": doc.accounting_journal_entry_id,
            }
        if doc.status == PurchaseDocStatus.DRAFT:
            raise ProcurementError("cannot void a draft purchase document")

        doc.status = PurchaseDocStatus.VOIDED
        doc.voided_at = timezone.now()
        doc.void_reason = (reason or "VOID")[:255]
        doc.save(update_fields=["status", "voided_at", "void_reason"])

        outbox_event = publish_outbox_event(
            request=request,
            source_module="PROCUREMENT",
            event_type="ProcurementDocumentVoided",
            payload={
                "doc_id": int(doc.id),
                "doc_type": doc.doc_type,
                "status": doc.status,
                "series": doc.series,
                "number": int(doc.number),
                "currency": doc.currency,
                "subtotal": str(doc.subtotal),
                "tax_total": str(doc.tax_total),
                "total": str(doc.total),
                "reason": doc.void_reason,
                "supplier_ref": doc.supplier_ref,
                "external_ref": doc.external_ref,
            },
            actor_user=actor,
            company=company,
            branch=branch,
        )
        accounting = _link_accounting_for_doc(doc=doc, outbox_event=outbox_event, actor=actor)

        return {
            "ok": True,
            "doc_id": int(doc.id),
            "status": doc.status,
            "accounting_status": accounting.status,
            "accounting_error": accounting.error,
            "journal_draft_id": accounting.journal_draft_id,
            "journal_entry_id": accounting.journal_entry_id,
        }
