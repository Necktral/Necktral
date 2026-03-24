from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.modulos.audit.writer import write_event
from apps.modulos.integration.services import publish_outbox_event

from .models import CashMovement, CashSession, PaymentIntent


def _branch_from_request(request):
    branch = getattr(request, "branch", None)
    if branch is None:
        raise ValueError("X-Branch-Id requerido")
    return branch


@dataclass(frozen=True)
class PaymentMutationResult:
    payment_id: str
    status: str
    amount: Decimal
    idempotent: bool
    refunded_total: Decimal = Decimal("0.00")


def _metadata_decimal(value) -> Decimal:
    try:
        return Decimal(str(value or "0.00"))
    except Exception:  # noqa: BLE001
        return Decimal("0.00")


def create_payment_intent(
    *,
    request,
    actor,
    amount: Decimal,
    currency: str = "NIO",
    idempotency_key: str = "",
    external_ref: str = "",
    provider: str = "",
    correlation_id: str = "",
    causation_id: str = "",
) -> tuple[PaymentIntent, bool]:
    company = request.company
    branch = _branch_from_request(request)
    with transaction.atomic():
        if idempotency_key:
            existing = PaymentIntent.objects.filter(company=company, idempotency_key=idempotency_key).first()
            if existing:
                return existing, True

        intent = PaymentIntent.objects.create(
            company=company,
            branch=branch,
            amount=amount,
            currency=currency or "NIO",
            idempotency_key=idempotency_key or "",
            external_ref=external_ref or "",
            provider=provider or "",
        )
        write_event(
            request=request,
            module="PAYMENTS",
            event_type="PAYMENT_INTENT_CREATED",
            reason_code="PAYMENTS_OK",
            actor_user=actor,
            subject_type="PAYMENT_INTENT",
            subject_id=str(intent.payment_id),
            metadata={
                "payment_id": str(intent.payment_id),
                "status": intent.status,
                "amount": str(intent.amount),
                "currency": intent.currency,
                "idempotency_key": intent.idempotency_key,
                "external_ref": intent.external_ref,
                "provider": intent.provider,
            },
        )
        publish_outbox_event(
            request=request,
            source_module="PAYMENTS",
            event_type="PaymentIntentCreated",
            payload={
                "payment_id": str(intent.payment_id),
                "amount": str(intent.amount),
                "currency": intent.currency,
                "status": intent.status,
                "idempotency_key": intent.idempotency_key,
            },
            actor_user=actor,
            company=company,
            branch=branch,
            correlation_id=correlation_id or "",
            causation_id=causation_id or "",
        )
        return intent, False


def open_cash_session(*, request, actor, opening_amount: Decimal = Decimal("0.00"), notes: str = "") -> CashSession:
    company = request.company
    branch = _branch_from_request(request)
    with transaction.atomic():
        existing = CashSession.objects.select_for_update().filter(
            company=company,
            branch=branch,
            status=CashSession.Status.OPEN,
        )
        if existing.exists():
            raise ValueError("Ya existe una cash session OPEN para esta sucursal.")

        session = CashSession.objects.create(
            company=company,
            branch=branch,
            opened_by=actor,
            status=CashSession.Status.OPEN,
            opening_amount=opening_amount,
            expected_amount=opening_amount,
            counted_amount=Decimal("0.00"),
            difference_amount=Decimal("0.00"),
            notes=notes or "",
        )
        write_event(
            request=request,
            module="PAYMENTS",
            event_type="CASH_SESSION_OPENED",
            reason_code="PAYMENTS_OK",
            actor_user=actor,
            subject_type="CASH_SESSION",
            subject_id=str(session.id),
            metadata={
                "session_id": session.id,
                "status": session.status,
                "opening_amount": str(session.opening_amount),
            },
        )
        publish_outbox_event(
            request=request,
            source_module="PAYMENTS",
            event_type="CashSessionOpened",
            payload={"session_id": session.id, "opening_amount": str(session.opening_amount)},
            actor_user=actor,
            company=company,
            branch=branch,
        )
        return session


def capture_payment_intent(
    *,
    request,
    actor,
    payment_id: str,
    amount: Decimal | None = None,
    idempotency_key: str = "",
    provider_txn_id: str = "",
    correlation_id: str = "",
    causation_id: str = "",
) -> PaymentMutationResult:
    company = request.company
    branch = _branch_from_request(request)

    with transaction.atomic():
        intent = get_object_or_404(
            PaymentIntent.objects.select_for_update(),
            company=company,
            branch=branch,
            payment_id=payment_id,
        )
        normalized_key = str(idempotency_key or "").strip()
        requested_amount = Decimal(str(amount if amount is not None else intent.amount))
        if requested_amount <= 0:
            raise ValueError("capture amount debe ser > 0.")
        if requested_amount > intent.amount:
            raise ValueError("capture amount no puede exceder el amount del intent.")

        metadata = dict(intent.metadata or {})
        if normalized_key and metadata.get("capture_idempotency_key") == normalized_key:
            captured_amount = _metadata_decimal(metadata.get("captured_amount", intent.amount))
            return PaymentMutationResult(
                payment_id=str(intent.payment_id),
                status=intent.status,
                amount=captured_amount,
                idempotent=True,
                refunded_total=_metadata_decimal(metadata.get("refunded_total")),
            )
        if intent.status == PaymentIntent.Status.CAPTURED:
            captured_amount = _metadata_decimal(metadata.get("captured_amount", intent.amount))
            return PaymentMutationResult(
                payment_id=str(intent.payment_id),
                status=intent.status,
                amount=captured_amount,
                idempotent=True,
                refunded_total=_metadata_decimal(metadata.get("refunded_total")),
            )
        if intent.status in (PaymentIntent.Status.REFUNDED, PaymentIntent.Status.FAILED):
            raise ValueError("Intent no permite captura en su estado actual.")

        intent.status = PaymentIntent.Status.CAPTURED
        intent.captured_at = timezone.now()
        if provider_txn_id:
            intent.provider_txn_id = str(provider_txn_id)
        metadata["captured_amount"] = str(requested_amount)
        if normalized_key:
            metadata["capture_idempotency_key"] = normalized_key
        intent.metadata = metadata
        intent.save(update_fields=["status", "captured_at", "provider_txn_id", "metadata", "updated_at"])

        write_event(
            request=request,
            module="PAYMENTS",
            event_type="PAYMENT_CAPTURED",
            reason_code="PAYMENTS_OK",
            actor_user=actor,
            subject_type="PAYMENT_INTENT",
            subject_id=str(intent.payment_id),
            metadata={
                "payment_id": str(intent.payment_id),
                "amount": str(requested_amount),
                "currency": intent.currency,
                "idempotency_key": normalized_key,
                "provider": intent.provider,
                "provider_txn_id": intent.provider_txn_id,
            },
        )
        publish_outbox_event(
            request=request,
            source_module="PAYMENTS",
            event_type="PaymentCaptured",
            payload={
                "payment_id": str(intent.payment_id),
                "amount": str(requested_amount),
                "currency": intent.currency,
                "status": intent.status,
                "idempotency_key": normalized_key,
                "provider": intent.provider,
                "provider_txn_id": intent.provider_txn_id,
            },
            actor_user=actor,
            company=company,
            branch=branch,
            correlation_id=correlation_id or "",
            causation_id=causation_id or "",
        )
        return PaymentMutationResult(
            payment_id=str(intent.payment_id),
            status=intent.status,
            amount=requested_amount,
            idempotent=False,
            refunded_total=_metadata_decimal(metadata.get("refunded_total")),
        )


def post_cash_movement(
    *,
    request,
    actor,
    session_id: int,
    movement_type: str,
    amount: Decimal,
    reference: str = "",
    reason: str = "",
    correlation_id: str = "",
    causation_id: str = "",
) -> CashMovement:
    company = request.company
    branch = _branch_from_request(request)

    with transaction.atomic():
        session = get_object_or_404(CashSession.objects.select_for_update(), id=session_id, company=company, branch=branch)
        if session.status not in (CashSession.Status.OPEN, CashSession.Status.COUNT_PENDING):
            raise ValueError("Cash session no permite movimientos en su estado actual.")

        mov = CashMovement.objects.create(
            session=session,
            movement_type=movement_type,
            amount=amount,
            reference=reference or "",
            reason=reason or "",
            created_by=actor,
        )

        sign = Decimal("1")
        if movement_type in (CashMovement.MovementType.EXPENSE, CashMovement.MovementType.REFUND):
            sign = Decimal("-1")
        session.expected_amount = Decimal(session.expected_amount) + (Decimal(amount) * sign)
        session.save(update_fields=["expected_amount"])
        write_event(
            request=request,
            module="PAYMENTS",
            event_type="CASH_MOVEMENT_POSTED",
            reason_code="PAYMENTS_OK",
            actor_user=actor,
            subject_type="CASH_MOVEMENT",
            subject_id=str(mov.id),
            metadata={
                "session_id": session.id,
                "movement_id": mov.id,
                "movement_type": mov.movement_type,
                "amount": str(mov.amount),
                "reference": mov.reference,
            },
        )

        publish_outbox_event(
            request=request,
            source_module="PAYMENTS",
            event_type="CashMovementPosted",
            payload={
                "session_id": session.id,
                "movement_id": mov.id,
                "movement_type": mov.movement_type,
                "amount": str(mov.amount),
                "reference": mov.reference,
            },
            actor_user=actor,
            company=company,
            branch=branch,
            correlation_id=correlation_id or "",
            causation_id=causation_id or "",
        )
        return mov


def refund_payment_intent(
    *,
    request,
    actor,
    payment_id: str,
    amount: Decimal | None = None,
    idempotency_key: str = "",
    reason: str = "",
    correlation_id: str = "",
    causation_id: str = "",
) -> PaymentMutationResult:
    company = request.company
    branch = _branch_from_request(request)

    with transaction.atomic():
        intent = get_object_or_404(
            PaymentIntent.objects.select_for_update(),
            company=company,
            branch=branch,
            payment_id=payment_id,
        )
        normalized_key = str(idempotency_key or "").strip()
        metadata = dict(intent.metadata or {})
        refund_events = list(metadata.get("refund_events") or [])
        if normalized_key:
            for event in refund_events:
                if event.get("idempotency_key") == normalized_key:
                    refunded_total = _metadata_decimal(metadata.get("refunded_total"))
                    return PaymentMutationResult(
                        payment_id=str(intent.payment_id),
                        status=intent.status,
                        amount=_metadata_decimal(event.get("amount")),
                        idempotent=True,
                        refunded_total=refunded_total,
                    )

        if intent.status not in (PaymentIntent.Status.CAPTURED, PaymentIntent.Status.REFUNDED):
            raise ValueError("Intent no permite refund en su estado actual.")

        capture_amount = _metadata_decimal(metadata.get("captured_amount", intent.amount))
        refunded_total = _metadata_decimal(metadata.get("refunded_total"))
        remaining = capture_amount - refunded_total
        refund_amount = Decimal(str(amount if amount is not None else remaining))
        if refund_amount <= 0:
            raise ValueError("refund amount debe ser > 0.")
        if refund_amount > remaining:
            raise ValueError("refund amount excede el saldo capturado pendiente.")

        refunded_total = refunded_total + refund_amount
        metadata["refunded_total"] = str(refunded_total)
        refund_event = {
            "amount": str(refund_amount),
            "reason": str(reason or ""),
            "processed_at": timezone.now().isoformat(),
            "idempotency_key": normalized_key,
        }
        refund_events.append(refund_event)
        metadata["refund_events"] = refund_events
        intent.metadata = metadata
        if refunded_total >= capture_amount:
            intent.status = PaymentIntent.Status.REFUNDED
            intent.refunded_at = timezone.now()
        intent.save(update_fields=["status", "refunded_at", "metadata", "updated_at"])

        write_event(
            request=request,
            module="PAYMENTS",
            event_type="PAYMENT_REFUNDED",
            reason_code="PAYMENTS_OK",
            actor_user=actor,
            subject_type="PAYMENT_INTENT",
            subject_id=str(intent.payment_id),
            metadata={
                "payment_id": str(intent.payment_id),
                "amount": str(refund_amount),
                "currency": intent.currency,
                "reason": str(reason or ""),
                "idempotency_key": normalized_key,
                "refunded_total": str(refunded_total),
            },
        )
        publish_outbox_event(
            request=request,
            source_module="PAYMENTS",
            event_type="RefundProcessed",
            payload={
                "payment_id": str(intent.payment_id),
                "amount": str(refund_amount),
                "currency": intent.currency,
                "reason": str(reason or ""),
                "status": intent.status,
                "idempotency_key": normalized_key,
                "refunded_total": str(refunded_total),
            },
            actor_user=actor,
            company=company,
            branch=branch,
            correlation_id=correlation_id or "",
            causation_id=causation_id or "",
        )
        return PaymentMutationResult(
            payment_id=str(intent.payment_id),
            status=intent.status,
            amount=refund_amount,
            idempotent=False,
            refunded_total=refunded_total,
        )


def close_cash_session(*, request, actor, session_id: int, counted_amount: Decimal, notes: str = "") -> CashSession:
    company = request.company
    branch = _branch_from_request(request)

    with transaction.atomic():
        session = get_object_or_404(CashSession.objects.select_for_update(), id=session_id, company=company, branch=branch)
        if session.status == CashSession.Status.CLOSED:
            return session
        if session.status not in (
            CashSession.Status.OPEN,
            CashSession.Status.COUNT_PENDING,
            CashSession.Status.REVIEW_PENDING,
        ):
            raise ValueError("Estado de cash session inválido para cierre.")

        session.status = CashSession.Status.CLOSED
        session.closed_by = actor
        session.closed_at = timezone.now()
        session.counted_amount = counted_amount
        session.difference_amount = Decimal(counted_amount) - Decimal(session.expected_amount)
        if notes:
            session.notes = notes
        try:
            session.clean()
        except ValidationError as exc:
            raise ValueError(str(exc)) from exc
        session.save(
            update_fields=[
                "status",
                "closed_by",
                "closed_at",
                "counted_amount",
                "difference_amount",
                "notes",
            ]
        )
        write_event(
            request=request,
            module="PAYMENTS",
            event_type="CASH_SESSION_CLOSED",
            reason_code="PAYMENTS_OK",
            actor_user=actor,
            subject_type="CASH_SESSION",
            subject_id=str(session.id),
            metadata={
                "session_id": session.id,
                "status": session.status,
                "expected_amount": str(session.expected_amount),
                "counted_amount": str(session.counted_amount),
                "difference_amount": str(session.difference_amount),
            },
        )

        publish_outbox_event(
            request=request,
            source_module="PAYMENTS",
            event_type="CashSessionClosed",
            payload={
                "session_id": session.id,
                "expected_amount": str(session.expected_amount),
                "counted_amount": str(session.counted_amount),
                "difference_amount": str(session.difference_amount),
            },
            actor_user=actor,
            company=company,
            branch=branch,
        )
        return session
