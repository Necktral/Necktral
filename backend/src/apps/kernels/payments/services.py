from __future__ import annotations

from decimal import Decimal
from typing import Any, Protocol, cast
from uuid import UUID, uuid4

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpRequest
from django.utils import timezone

from apps.modulos.audit.writer import write_event
from apps.modulos.common.tender import TENDER_PAYMENT_METHOD_VALUES, TenderPaymentMethod
from apps.modulos.iam.models import OrgUnit
from apps.modulos.integration.models import OutboxEvent
from apps.modulos.integration.services import publish_outbox_event

from .models import CashMovement, CashSession, PaymentIntent


class PaymentsDomainError(ValueError):
    """Error de dominio base para el módulo de pagos."""


class PaymentsNotFoundError(PaymentsDomainError):
    """Entidad no encontrada dentro del scope de pagos."""


class PaymentsInvalidStateError(PaymentsDomainError):
    """Transición inválida de estado."""


class PaymentsConflictError(PaymentsDomainError):
    """Conflicto de concurrencia o unicidad de negocio."""


class PaymentsValidationError(PaymentsDomainError):
    """Error de validación de entrada de dominio."""


class ActorPrincipal(Protocol):
    id: Any


def _normalize_payment_method(payment_method: str) -> str:
    normalized = str(payment_method or "").strip().upper()
    if normalized and normalized not in TENDER_PAYMENT_METHOD_VALUES:
        raise PaymentsValidationError("payment_method inválido.")
    return normalized


def _coerce_actor_for_fk(*, actor: ActorPrincipal, field_name: str) -> Any:
    actor_id = getattr(actor, "id", None)
    if actor_id is None:
        raise PaymentsValidationError(f"{field_name} requiere actor con id no nulo.")
    return cast(Any, actor)


def _branch_from_request(request: HttpRequest) -> OrgUnit:
    branch = getattr(request, "branch", None)
    if branch is None:
        raise PaymentsValidationError("X-Branch-Id requerido")
    if not isinstance(branch, OrgUnit):
        raise PaymentsValidationError("X-Branch-Id inválido")
    return branch


def _scope_from_request(request: HttpRequest) -> tuple[OrgUnit, OrgUnit]:
    company = getattr(request, "company", None)
    if company is None:
        raise PaymentsValidationError("X-Company-Id requerido")
    if not isinstance(company, OrgUnit):
        raise PaymentsValidationError("X-Company-Id inválido")
    branch = _branch_from_request(request)
    return company, branch


def _dt_iso(value) -> str:
    return value.isoformat() if value else ""


def _capture_reversal_metadata(intent: PaymentIntent) -> dict[str, Any]:
    metadata = intent.metadata if isinstance(intent.metadata, dict) else {}
    reversal = metadata.get("capture_reversal")
    return reversal if isinstance(reversal, dict) else {}


def _find_payment_captured_event(*, intent: PaymentIntent, company: OrgUnit, branch: OrgUnit) -> OutboxEvent | None:
    return (
        OutboxEvent.objects.filter(
            source_module="PAYMENTS",
            event_type="PaymentCaptured",
            company=company,
            branch=branch,
            payload__data__payment_id=str(intent.payment_id),
        )
        .order_by("-occurred_at", "-id")
        .first()
    )


def create_payment_intent_for_scope(
    *,
    company: OrgUnit,
    branch: OrgUnit,
    actor: ActorPrincipal,
    request: HttpRequest | None = None,
    amount: Decimal,
    currency: str = "NIO",
    idempotency_key: str = "",
    external_ref: str = "",
    provider: str = "",
    payment_method: str = "",
) -> tuple[PaymentIntent, bool]:
    normalized_payment_method = _normalize_payment_method(payment_method)
    with transaction.atomic():
        if idempotency_key:
            existing = PaymentIntent.objects.filter(company=company, idempotency_key=idempotency_key).first()
            if existing is not None:
                return existing, True

        try:
            intent = PaymentIntent.objects.create(
                company=company,
                branch=branch,
                amount=amount,
                currency=currency or "NIO",
                idempotency_key=idempotency_key or "",
                external_ref=external_ref or "",
                provider=provider or "",
                payment_method=normalized_payment_method,
            )
        except IntegrityError:
            # Race condition: concurrent request created it between our check and insert
            if idempotency_key:
                existing = PaymentIntent.objects.filter(company=company, idempotency_key=idempotency_key).first()
                if existing is not None:
                    return existing, True
            raise PaymentsConflictError("Conflicto de unicidad al crear payment intent.")

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
                "payment_method": intent.payment_method,
            },
            actor_user=actor,
            company=company,
            branch=branch,
        )
        return intent, False


def create_payment_intent(
    *,
    request: HttpRequest,
    actor: ActorPrincipal,
    amount: Decimal,
    currency: str = "NIO",
    idempotency_key: str = "",
    external_ref: str = "",
    provider: str = "",
    payment_method: str = "",
) -> tuple[PaymentIntent, bool]:
    company, branch = _scope_from_request(request)
    return create_payment_intent_for_scope(
        company=company,
        branch=branch,
        actor=actor,
        request=request,
        amount=amount,
        currency=currency,
        idempotency_key=idempotency_key,
        external_ref=external_ref,
        provider=provider,
        payment_method=payment_method,
    )


def capture_payment_intent_for_scope(
    *,
    company: OrgUnit,
    branch: OrgUnit,
    actor: ActorPrincipal,
    payment_id: str | UUID,
    request: HttpRequest | None = None,
    provider_txn_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> PaymentIntent:
    with transaction.atomic():
        intent = (
            PaymentIntent.objects.select_for_update()
            .filter(
                payment_id=payment_id,
                company=company,
                branch=branch,
            )
            .first()
        )
        if intent is None:
            raise PaymentsNotFoundError("Payment intent no encontrado.")
        if intent.status == PaymentIntent.Status.CAPTURED:
            return intent
        if intent.status in (PaymentIntent.Status.FAILED, PaymentIntent.Status.REFUNDED):
            raise PaymentsInvalidStateError("Payment intent no se puede capturar en su estado actual.")

        intent.status = PaymentIntent.Status.CAPTURED
        intent.captured_at = timezone.now()
        intent.updated_at = timezone.now()
        if provider_txn_id:
            intent.provider_txn_id = provider_txn_id
        if metadata:
            merged = dict(intent.metadata or {})
            merged.update(dict(metadata))
            intent.metadata = merged
        intent.save(update_fields=["status", "captured_at", "provider_txn_id", "metadata", "updated_at"])

        publish_outbox_event(
            request=request,
            source_module="PAYMENTS",
            event_type="PaymentCaptured",
            payload={
                "payment_id": str(intent.payment_id),
                "amount": str(intent.amount),
                "currency": intent.currency,
                "status": intent.status,
                "provider_txn_id": intent.provider_txn_id,
                "payment_method": intent.payment_method,
            },
            actor_user=actor,
            company=company,
            branch=branch,
        )
        return intent


def capture_payment_intent(
    *,
    request: HttpRequest,
    actor: ActorPrincipal,
    payment_id: str | UUID,
    provider_txn_id: str = "",
    metadata: dict[str, Any] | None = None,
) -> PaymentIntent:
    company, branch = _scope_from_request(request)
    return capture_payment_intent_for_scope(
        company=company,
        branch=branch,
        actor=actor,
        request=request,
        payment_id=payment_id,
        provider_txn_id=provider_txn_id,
        metadata=metadata,
    )


def reverse_captured_payment_intent_for_scope(
    *,
    company: OrgUnit,
    branch: OrgUnit,
    actor: ActorPrincipal,
    payment_id: str | UUID,
    request: HttpRequest | None = None,
    idempotency_key: str,
    reason: str = "",
) -> tuple[PaymentIntent, bool]:
    idempotency_key = str(idempotency_key or "").strip()
    reason = str(reason or "").strip()
    if not idempotency_key:
        raise PaymentsValidationError("idempotency_key requerido.")
    if len(reason) > 255:
        raise PaymentsValidationError("reason demasiado largo.")

    with transaction.atomic():
        intent = (
            PaymentIntent.objects.select_for_update()
            .filter(
                payment_id=payment_id,
                company=company,
                branch=branch,
            )
            .first()
        )
        if intent is None:
            raise PaymentsNotFoundError("Payment intent no encontrado.")

        if intent.status == PaymentIntent.Status.REFUNDED:
            reversal = _capture_reversal_metadata(intent)
            if str(reversal.get("idempotency_key") or "") == idempotency_key:
                if str(reversal.get("reason") or "") != reason:
                    raise PaymentsConflictError("Idempotency key reutilizada con payload distinto.")
                return intent, True
            if reversal:
                raise PaymentsConflictError("Payment intent ya fue reversado con otra idempotency_key.")
            raise PaymentsInvalidStateError("Payment intent no se puede reversar en su estado actual.")

        if intent.status != PaymentIntent.Status.CAPTURED:
            raise PaymentsInvalidStateError("Payment intent no se puede reversar en su estado actual.")

        if intent.payment_method != TenderPaymentMethod.TRANSFER:
            raise PaymentsInvalidStateError("Payment intent solo permite reversa CAP-05A para TRANSFER.")

        captured_event = _find_payment_captured_event(intent=intent, company=company, branch=branch)
        if captured_event is None:
            raise PaymentsConflictError("PaymentCaptured original requerido para reversa.")

        now = timezone.now()
        previous_status = intent.status
        reversal_id = str(uuid4())
        metadata = dict(intent.metadata) if isinstance(intent.metadata, dict) else {}
        metadata["capture_reversal"] = {
            "idempotency_key": idempotency_key,
            "reason": reason,
            "reversal_id": reversal_id,
            "reverses_event_type": "PaymentCaptured",
            "reverses_outbox_event_id": str(captured_event.event_id),
            "reversed_at": now.isoformat(),
        }

        intent.status = PaymentIntent.Status.REFUNDED
        intent.refunded_at = now
        intent.updated_at = now
        intent.metadata = metadata
        intent.save(update_fields=["status", "refunded_at", "metadata", "updated_at"])

        publish_outbox_event(
            request=request,
            source_module="PAYMENTS",
            event_type="PaymentCaptureReversed",
            payload={
                "payment_id": str(intent.payment_id),
                "amount": str(intent.amount),
                "currency": intent.currency,
                "payment_method": intent.payment_method,
                "provider_txn_id": intent.provider_txn_id,
                "previous_status": previous_status,
                "status": intent.status,
                "captured_at": _dt_iso(intent.captured_at),
                "refunded_at": _dt_iso(intent.refunded_at),
                "idempotency_key": idempotency_key,
                "reason": reason,
                "reversal_id": reversal_id,
                "reverses_event_type": "PaymentCaptured",
                "reverses_outbox_event_id": str(captured_event.event_id),
            },
            actor_user=actor,
            company=company,
            branch=branch,
            correlation_id=str(captured_event.correlation_id or ""),
            causation_id=str(captured_event.event_id),
        )
        return intent, False


def reverse_captured_payment_intent(
    *,
    request: HttpRequest,
    actor: ActorPrincipal,
    payment_id: str | UUID,
    idempotency_key: str,
    reason: str = "",
) -> tuple[PaymentIntent, bool]:
    company, branch = _scope_from_request(request)
    return reverse_captured_payment_intent_for_scope(
        company=company,
        branch=branch,
        actor=actor,
        request=request,
        payment_id=payment_id,
        idempotency_key=idempotency_key,
        reason=reason,
    )


def open_cash_session_for_scope(
    *,
    company: OrgUnit,
    branch: OrgUnit,
    actor: ActorPrincipal,
    request: HttpRequest | None = None,
    opening_amount: Decimal = Decimal("0.00"),
    notes: str = "",
) -> CashSession:
    with transaction.atomic():
        actor_fk = _coerce_actor_for_fk(actor=actor, field_name="opened_by")
        existing = CashSession.objects.select_for_update().filter(
            company=company,
            branch=branch,
            status=CashSession.Status.OPEN,
        )
        if existing.exists():
            raise PaymentsConflictError("Ya existe una cash session OPEN para esta sucursal.")

        session = CashSession.objects.create(
            company=company,
            branch=branch,
            opened_by=actor_fk,
            status=CashSession.Status.OPEN,
            opening_amount=opening_amount,
            expected_amount=opening_amount,
            counted_amount=Decimal("0.00"),
            difference_amount=Decimal("0.00"),
            notes=notes or "",
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


def open_cash_session(
    *,
    request: HttpRequest,
    actor: ActorPrincipal,
    opening_amount: Decimal = Decimal("0.00"),
    notes: str = "",
) -> CashSession:
    company, branch = _scope_from_request(request)
    return open_cash_session_for_scope(
        company=company,
        branch=branch,
        actor=actor,
        request=request,
        opening_amount=opening_amount,
        notes=notes,
    )


def _cash_movement_payload_matches(
    *,
    movement: CashMovement,
    movement_type: str,
    amount: Decimal,
    reference: str,
    reason: str,
) -> bool:
    return (
        movement.movement_type == movement_type
        and Decimal(movement.amount) == Decimal(amount)
        and (movement.reference or "") == (reference or "")
        and (movement.reason or "") == (reason or "")
    )


def _idempotent_cash_movement_or_conflict(
    *,
    movement: CashMovement,
    movement_type: str,
    amount: Decimal,
    reference: str,
    reason: str,
) -> CashMovement:
    if not _cash_movement_payload_matches(
        movement=movement,
        movement_type=movement_type,
        amount=amount,
        reference=reference,
        reason=reason,
    ):
        raise PaymentsConflictError("Idempotency key reutilizada con payload distinto.")
    return movement


def _write_cash_movement_audit_event(
    *,
    request: HttpRequest | None,
    actor: ActorPrincipal,
    mov: CashMovement,
    idempotency_key: str,
) -> None:
    write_event(
        request=request,
        module="PAYMENTS",
        event_type="PAYMENTS_CASH_MOVEMENT_POSTED",
        reason_code="OK",
        actor_user=actor,
        subject_type="CASH_MOVEMENT",
        subject_id=str(mov.id),
        metadata={
            "session_id": str(mov.session_id),
            "movement_id": str(mov.id),
            "movement_type": mov.movement_type,
            "amount": str(mov.amount),
            "reference": mov.reference,
            "reason": mov.reason,
            "idempotency_key": idempotency_key,
        },
    )


def post_cash_movement_for_scope(
    *,
    company: OrgUnit,
    branch: OrgUnit,
    actor: ActorPrincipal,
    session_id: int,
    movement_type: str,
    amount: Decimal,
    request: HttpRequest | None = None,
    reference: str = "",
    reason: str = "",
    idempotency_key: str = "",
) -> tuple[CashMovement, bool]:
    reference = reference or ""
    reason = reason or ""
    idempotency_key = (idempotency_key or "").strip()
    with transaction.atomic():
        actor_fk = _coerce_actor_for_fk(actor=actor, field_name="created_by")
        session = (
            CashSession.objects.select_for_update()
            .filter(id=session_id, company=company, branch=branch)
            .first()
        )
        if session is None:
            raise PaymentsNotFoundError("Cash session no encontrada.")
        if session.status not in (CashSession.Status.OPEN, CashSession.Status.COUNT_PENDING):
            raise PaymentsInvalidStateError("Cash session no permite movimientos en su estado actual.")

        if idempotency_key:
            existing = (
                CashMovement.objects.select_for_update()
                .filter(session=session, idempotency_key=idempotency_key)
                .first()
            )
            if existing is not None:
                return (
                    _idempotent_cash_movement_or_conflict(
                        movement=existing,
                        movement_type=movement_type,
                        amount=amount,
                        reference=reference,
                        reason=reason,
                    ),
                    True,
                )

        try:
            with transaction.atomic():
                mov = CashMovement.objects.create(
                    session=session,
                    movement_type=movement_type,
                    amount=amount,
                    reference=reference,
                    reason=reason,
                    idempotency_key=idempotency_key,
                    created_by=actor_fk,
                )
        except IntegrityError:
            if not idempotency_key:
                raise
            existing = (
                CashMovement.objects.select_for_update()
                .filter(session=session, idempotency_key=idempotency_key)
                .first()
            )
            if existing is None:
                raise
            return (
                _idempotent_cash_movement_or_conflict(
                    movement=existing,
                    movement_type=movement_type,
                    amount=amount,
                    reference=reference,
                    reason=reason,
                ),
                True,
            )

        sign = Decimal("1")
        if movement_type in (CashMovement.MovementType.EXPENSE, CashMovement.MovementType.REFUND):
            sign = Decimal("-1")
        session.expected_amount = Decimal(session.expected_amount) + (Decimal(amount) * sign)
        session.save(update_fields=["expected_amount"])

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
        )
        _write_cash_movement_audit_event(
            request=request,
            actor=actor,
            mov=mov,
            idempotency_key=idempotency_key,
        )
        return mov, False


def post_cash_movement(
    *,
    request: HttpRequest,
    actor: ActorPrincipal,
    session_id: int,
    movement_type: str,
    amount: Decimal,
    reference: str = "",
    reason: str = "",
    idempotency_key: str = "",
) -> CashMovement:
    company, branch = _scope_from_request(request)
    mov, _idempotent = post_cash_movement_for_scope(
        company=company,
        branch=branch,
        actor=actor,
        session_id=session_id,
        movement_type=movement_type,
        amount=amount,
        request=request,
        reference=reference,
        reason=reason,
        idempotency_key=idempotency_key,
    )
    return mov


def post_cash_movement_with_status(
    *,
    request: HttpRequest,
    actor: ActorPrincipal,
    session_id: int,
    movement_type: str,
    amount: Decimal,
    reference: str = "",
    reason: str = "",
    idempotency_key: str = "",
) -> tuple[CashMovement, bool]:
    company, branch = _scope_from_request(request)
    return post_cash_movement_for_scope(
        company=company,
        branch=branch,
        actor=actor,
        session_id=session_id,
        movement_type=movement_type,
        amount=amount,
        request=request,
        reference=reference,
        reason=reason,
        idempotency_key=idempotency_key,
    )


def close_cash_session_for_scope(
    *,
    company: OrgUnit,
    branch: OrgUnit,
    actor: ActorPrincipal,
    session_id: int,
    counted_amount: Decimal,
    request: HttpRequest | None = None,
    notes: str = "",
) -> CashSession:
    with transaction.atomic():
        actor_fk = _coerce_actor_for_fk(actor=actor, field_name="closed_by")
        session = (
            CashSession.objects.select_for_update()
            .filter(id=session_id, company=company, branch=branch)
            .first()
        )
        if session is None:
            raise PaymentsNotFoundError("Cash session no encontrada.")
        if session.status == CashSession.Status.CLOSED:
            return session
        if session.status not in (
            CashSession.Status.OPEN,
            CashSession.Status.COUNT_PENDING,
            CashSession.Status.REVIEW_PENDING,
        ):
            raise PaymentsInvalidStateError("Estado de cash session inválido para cierre.")

        session.status = CashSession.Status.CLOSED
        session.closed_by = actor_fk
        session.closed_at = timezone.now()
        session.counted_amount = counted_amount
        session.difference_amount = Decimal(counted_amount) - Decimal(session.expected_amount)
        if notes:
            session.notes = notes
        try:
            session.clean()
        except ValidationError as exc:
            raise PaymentsValidationError(str(exc)) from exc
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


def close_cash_session(
    *,
    request: HttpRequest,
    actor: ActorPrincipal,
    session_id: int,
    counted_amount: Decimal,
    notes: str = "",
) -> CashSession:
    company, branch = _scope_from_request(request)
    return close_cash_session_for_scope(
        company=company,
        branch=branch,
        actor=actor,
        session_id=session_id,
        counted_amount=counted_amount,
        request=request,
        notes=notes,
    )
