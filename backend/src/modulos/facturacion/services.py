from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.audit.writer import write_event
from apps.iam.models import OrgUnit

from .models import BillingDocument, BillingLine, BillingSequence, DocStatus, DocType

MONEY_Q = Decimal("0.01")
QTY_Q = Decimal("0.0001")
PRICE_Q = Decimal("0.000001")
TAX_Q = Decimal("0.0001")


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


@dataclass(frozen=True)
class CreateResult:
    doc_id: int


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


DEFAULT_BILLING_SERIES = ("A", "FUEL")


def provision_billing_sequences_for_branch(*, request=None, company, branch, actor_user=None) -> dict:
    created = 0
    with transaction.atomic():
        for series in DEFAULT_BILLING_SERIES:
            for doc_type in (DocType.INVOICE, DocType.CREDIT_NOTE):
                obj, was_created = BillingSequence.objects.get_or_create(
                    company=company,
                    branch=branch,
                    doc_type=doc_type,
                    series=series,
                    defaults={"next_number": 1, "updated_at": timezone.now()},
                )
                if was_created:
                    created += 1

    if created:
        write_event(
            request=request,
            module="BILLING",
            event_type="BILLING_SEQUENCE_PROVISIONED",
            reason_code="BILLING_OK",
            actor_user=actor_user,
            subject_type="BRANCH",
            subject_id=str(branch.id),
            metadata={"created": created},
        )

    return {"created": created}


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
    idempotency_key: str = "",
) -> CreateResult:
    company: OrgUnit = request.company
    branch: OrgUnit = request.branch

    if doc_type not in (DocType.INVOICE, DocType.CREDIT_NOTE):
        raise BillingError("invalid doc_type")

    if not lines:
        raise BillingError("lines required")

    computed, subtotal, tax_total, total = _compute_lines_and_totals(lines_in=lines)

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
            subtotal=subtotal,
            tax_total=tax_total,
            total=total,
            is_fiscal=bool(is_fiscal),
            idempotency_key=idempotency_key or "",
            created_by=actor,
        )

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
                "subtotal": str(doc.subtotal),
                "tax_total": str(doc.tax_total),
                "total": str(doc.total),
                "is_fiscal": bool(doc.is_fiscal),
                "idempotency_key": idempotency_key,
            },
        )

        return CreateResult(doc.id)


def issue_doc(
    *,
    request,
    actor,
    doc_id: int,
    apply_inventory: bool = False,
) -> dict:
    company: OrgUnit = request.company
    branch: OrgUnit = request.branch

    with transaction.atomic():
        doc = BillingDocument.objects.select_for_update().get(id=doc_id, company=company, branch=branch)

        if doc.status == DocStatus.VOIDED:
            raise BillingError("cannot issue a voided document")
        if doc.status == DocStatus.ISSUED:
            return {"ok": True, "already_issued": True, "doc_id": doc.id, "number": doc.number}

        seq = BillingSequence.objects.select_for_update().filter(
            company=company,
            branch=branch,
            doc_type=doc.doc_type,
            series=doc.series,
        ).first()
        if not seq:
            try:
                seq, _ = BillingSequence.objects.get_or_create(
                    company=company,
                    branch=branch,
                    doc_type=doc.doc_type,
                    series=doc.series,
                    defaults={"next_number": 1, "updated_at": timezone.now()},
                )
            except IntegrityError:
                seq = BillingSequence.objects.get(
                    company=company,
                    branch=branch,
                    doc_type=doc.doc_type,
                    series=doc.series,
                )
            seq = BillingSequence.objects.select_for_update().get(pk=seq.pk)

        number = int(seq.next_number)
        seq.next_number = number + 1
        seq.updated_at = timezone.now()
        seq.save(update_fields=["next_number", "updated_at"])

        before = {"status": doc.status, "number": doc.number, "issued_at": str(doc.issued_at or "")}

        doc.number = number
        doc.status = DocStatus.ISSUED
        doc.issued_at = timezone.now()
        doc.save(update_fields=["number", "status", "issued_at"])

        if apply_inventory:
            from modulos.inventarios.services import post_issue  # import local para evitar ciclos

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

        after = {"status": doc.status, "number": doc.number, "issued_at": str(doc.issued_at or "")}

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
            metadata={"apply_inventory": bool(apply_inventory)},
        )

        return {"ok": True, "doc_id": doc.id, "number": doc.number}


def void_doc(
    *,
    request,
    actor,
    doc_id: int,
    reason: str,
) -> dict:
    company: OrgUnit = request.company
    branch: OrgUnit = request.branch

    with transaction.atomic():
        doc = BillingDocument.objects.select_for_update().get(id=doc_id, company=company, branch=branch)

        if doc.status == DocStatus.VOIDED:
            return {"ok": True, "already_voided": True}
        if doc.status == DocStatus.DRAFT:
            raise BillingError("cannot void a draft document")

        before = {"status": doc.status, "void_reason": doc.void_reason}

        doc.status = DocStatus.VOIDED
        doc.voided_at = timezone.now()
        doc.void_reason = reason or "VOID"
        doc.save(update_fields=["status", "voided_at", "void_reason"])

        after = {"status": doc.status, "void_reason": doc.void_reason}

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
        )

        return {"ok": True, "doc_id": doc.id}


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

    # Evento legacy requerido por tests actuales
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
