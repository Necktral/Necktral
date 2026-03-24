from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
import hashlib
import json
from types import SimpleNamespace
from uuid import uuid4

from django.db import transaction
from django.db.utils import IntegrityError
from django.db.models import Q
from django.utils import timezone

from apps.modulos.audit.writer import write_event
from apps.modulos.integration.services import publish_outbox_event
from apps.modulos.payments.services import (
    capture_payment_intent,
    create_payment_intent,
    post_cash_movement,
    refund_payment_intent,
)
from apps.modulos.rbac.selectors import get_effective_permissions_for_scope
from apps.modulos.payments.models import CashMovement, CashSession
from kernels.facturacion.models import BillingDocument, DocType
from kernels.facturacion.services import create_draft, issue_doc, void_doc
from kernels.inventarios.models import InventoryItem, StockMovement, Warehouse
from kernels.inventarios.services import post_issue, post_receive

from .models import (
    RetailBranchConfig,
    RetailCommandExecution,
    RetailHold,
    RetailPaymentRecord,
    RetailReturn,
    RetailSale,
    RetailTerminal,
    RetailTicket,
    RetailTicketLine,
)

MONEY_Q = Decimal("0.01")
PRICE_Q = Decimal("0.000001")
QTY_Q = Decimal("0.0001")
COMPENSATION_MAX_ATTEMPTS = 5


class RetailDomainError(ValueError):
    def __init__(
        self,
        *,
        code: str,
        detail: str,
        status_code: int = 400,
        retryable: bool = False,
        correlation_id: str = "",
        causation_id: str = "",
        idempotency_replayed: bool = False,
    ):
        super().__init__(detail)
        self.code = str(code or "RETAIL_BAD_REQUEST")
        self.detail = str(detail or "Error en operación retail.")
        self.status_code = int(status_code)
        self.retryable = bool(retryable)
        self.correlation_id = str(correlation_id or "")
        self.causation_id = str(causation_id or "")
        self.idempotency_replayed = bool(idempotency_replayed)


def _q_money(value: Decimal) -> Decimal:
    return Decimal(value).quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _q_price(value: Decimal) -> Decimal:
    return Decimal(value).quantize(PRICE_Q, rounding=ROUND_HALF_UP)


def _q_qty(value: Decimal) -> Decimal:
    return Decimal(value).quantize(QTY_Q, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class CheckoutPreview:
    ok: bool
    blocking_errors: list[dict[str, str]]
    warnings: list[dict[str, str]]
    totals: dict[str, str]
    line_checks: list[dict[str, object]]
    config: RetailBranchConfig
    cash_session: CashSession | None
    warehouse: Warehouse | None


@dataclass(frozen=True)
class TicketMutationResult:
    ticket: RetailTicket
    line: RetailTicketLine | None = None


def _request_hash(payload: dict[str, object]) -> str:
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _start_command_execution(
    *,
    company,
    branch,
    action: str,
    idempotency_key: str,
    request_hash: str,
    correlation_id: str = "",
    causation_id: str = "",
) -> tuple[RetailCommandExecution, bool]:
    key = str(idempotency_key or "").strip()
    if not key:
        raise RetailDomainError(code="RETAIL_IDEMPOTENCY_KEY_REQUIRED", detail="idempotency_key requerido.", status_code=400)

    execution = (
        RetailCommandExecution.objects.select_for_update()
        .filter(company=company, action=action, idempotency_key=key)
        .first()
    )
    if execution is None:
        try:
            execution = RetailCommandExecution.objects.create(
                company=company,
                branch=branch,
                action=action,
                idempotency_key=key,
                request_hash=request_hash,
                status=RetailCommandExecution.Status.STARTED,
                correlation_id=str(correlation_id or ""),
                causation_id=str(causation_id or ""),
            )
            return execution, False
        except IntegrityError:
            execution = (
                RetailCommandExecution.objects.select_for_update()
                .filter(company=company, action=action, idempotency_key=key)
                .first()
            )
            if execution is None:
                raise

    if str(execution.request_hash or "") != str(request_hash or ""):
        raise RetailDomainError(
            code="IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD",
            detail="idempotency_key ya fue usado con payload diferente.",
            status_code=409,
            retryable=False,
            correlation_id=execution.correlation_id,
            causation_id=execution.causation_id,
        )

    if execution.status == RetailCommandExecution.Status.SUCCEEDED:
        return execution, True

    if execution.status == RetailCommandExecution.Status.FAILED:
        error_payload = dict(execution.error_json or {})
        raise RetailDomainError(
            code=str(error_payload.get("code") or "RETAIL_COMMAND_FAILED_REPLAY"),
            detail=str(error_payload.get("detail") or "Operación fallida previamente para esta idempotency_key."),
            status_code=int(error_payload.get("status_code") or 400),
            retryable=bool(error_payload.get("retryable", False)),
            correlation_id=str(error_payload.get("correlation_id") or execution.correlation_id or ""),
            causation_id=str(error_payload.get("causation_id") or execution.causation_id or ""),
            idempotency_replayed=True,
        )

    raise RetailDomainError(
        code="IDEMPOTENCY_KEY_IN_PROGRESS",
        detail="Ya existe una ejecución en progreso para esta idempotency_key.",
        status_code=409,
        retryable=True,
        correlation_id=execution.correlation_id,
        causation_id=execution.causation_id,
    )


def _mark_command_success(
    execution: RetailCommandExecution,
    *,
    response_json: dict[str, object],
    correlation_id: str = "",
    causation_id: str = "",
) -> None:
    execution.status = RetailCommandExecution.Status.SUCCEEDED
    execution.response_json = dict(response_json or {})
    execution.error_json = {}
    if correlation_id:
        execution.correlation_id = str(correlation_id)
    if causation_id:
        execution.causation_id = str(causation_id)
    execution.save(update_fields=["status", "response_json", "error_json", "correlation_id", "causation_id", "updated_at"])


def _mark_command_failure(
    execution: RetailCommandExecution,
    *,
    error: RetailDomainError,
) -> None:
    execution.status = RetailCommandExecution.Status.FAILED
    execution.error_json = {
        "code": error.code,
        "detail": error.detail,
        "status_code": int(error.status_code),
        "retryable": bool(error.retryable),
        "correlation_id": error.correlation_id,
        "causation_id": error.causation_id,
    }
    execution.response_json = {}
    execution.save(update_fields=["status", "error_json", "response_json", "updated_at"])


def _domain_error_from_exception(
    exc: Exception,
    *,
    fallback_code: str,
    fallback_detail: str,
    status_code: int = 400,
    retryable: bool = False,
    correlation_id: str = "",
    causation_id: str = "",
) -> RetailDomainError:
    if isinstance(exc, RetailDomainError):
        return exc
    return RetailDomainError(
        code=fallback_code,
        detail=str(exc) or fallback_detail,
        status_code=status_code,
        retryable=retryable,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )


def _request_scope(request):
    company = getattr(request, "company", None)
    branch = getattr(request, "branch", None)
    if company is None or branch is None:
        raise ValueError("X-Company-Id y X-Branch-Id requeridos")
    return company, branch


def _retail_request(*, company, branch, user=None):
    return SimpleNamespace(
        company=company,
        branch=branch,
        user=user,
        request_id=f"retail-comp-{uuid4().hex[:16]}",
        headers={},
        META={},
        path="/api/backend/retail/",
        method="POST",
        data={},
    )


def _publish_retail_event(
    *,
    request,
    event_type: str,
    data: dict,
    actor_user=None,
    correlation_id: str = "",
    causation_id: str = "",
):
    req = request
    return publish_outbox_event(
        request=req,
        source_module="RETAIL",
        event_type=event_type,
        payload=data,
        actor_user=actor_user,
        correlation_id=correlation_id or (getattr(req, "request_id", "") if req is not None else ""),
        causation_id=causation_id or correlation_id or "",
    )


def _actor_has_permission(*, actor, company, branch, permission_code: str) -> bool:
    if actor is None or not getattr(actor, "is_authenticated", False):
        return False
    perms = get_effective_permissions_for_scope(actor, company=company, branch=branch, include_global=True)
    return permission_code in perms or "*" in perms


def _get_branch_config(*, branch) -> RetailBranchConfig:
    warehouse = Warehouse.objects.filter(branch=branch, is_active=True).order_by("id").first()
    cfg, changed = RetailBranchConfig.objects.get_or_create(
        branch=branch,
        defaults={
            "series": "RTL",
            "default_warehouse": warehouse,
            "price_includes_tax": False,
            "hold_expiry_minutes": 120,
            "print_after_issue": False,
            "require_customer_for_fiscal": False,
            "allow_manual_reprice": False,
            "active": True,
        },
    )
    if not changed and cfg.default_warehouse_id is None and warehouse is not None:
        cfg.default_warehouse = warehouse
        cfg.save(update_fields=["default_warehouse", "updated_at"])
    return cfg


def _require_ticket_mutable(ticket: RetailTicket) -> None:
    if ticket.status in (RetailTicket.Status.CLOSED, RetailTicket.Status.VOIDED):
        raise ValueError("Ticket no permite edición en su estado actual.")


def _check_expected_version(ticket: RetailTicket, expected_version: int) -> None:
    if int(expected_version) != int(ticket.version):
        raise RetailDomainError(
            code="TICKET_VERSION_CONFLICT",
            detail="Versión de ticket desactualizada.",
            status_code=409,
            retryable=True,
            correlation_id=ticket.flow_correlation_id,
        )


def _expire_active_holds(*, ticket: RetailTicket) -> None:
    now = timezone.now()
    ticket.holds.filter(status=RetailHold.Status.ACTIVE, expires_at__lt=now).update(status=RetailHold.Status.EXPIRED)


def _active_hold(ticket: RetailTicket) -> RetailHold | None:
    _expire_active_holds(ticket=ticket)
    return ticket.holds.filter(status=RetailHold.Status.ACTIVE).order_by("-held_at", "-id").first()


def _ensure_no_active_hold(ticket: RetailTicket) -> None:
    hold = _active_hold(ticket)
    if hold is not None:
        raise ValueError("Ticket retenido; debe reanudarse antes de continuar.")


def _item_enabled_for_branch(*, item: InventoryItem, branch_id: int) -> bool:
    enabled_branch_ids = list(item.enabled_branch_ids or [])
    if enabled_branch_ids and int(branch_id) not in {int(v) for v in enabled_branch_ids}:
        return False
    if item.default_branch_id and int(item.default_branch_id) != int(branch_id) and enabled_branch_ids:
        return False
    return True


def _resolve_tax_rate(item: InventoryItem) -> Decimal:
    if item.tax_profile_id and getattr(item.tax_profile, "is_active", False):
        return Decimal(str(getattr(item.tax_profile, "rate", "0.0000") or "0.0000"))
    if item.tax_treatment in ("EXENTO", "EXONERADO"):
        return Decimal("0.0000")
    return Decimal("0.0000")


def _line_invoice_name(item: InventoryItem) -> str:
    return str(item.invoice_name or item.invoice_description or item.name or "")


def _build_line_snapshot(
    *,
    item: InventoryItem,
    qty: Decimal,
    unit_price: Decimal | None,
    discount_amount: Decimal | None,
    allow_manual_reprice: bool,
):
    if not item.is_active or item.status != "ACTIVO" or not item.sales_enabled or not item.visible_pos:
        raise ValueError("Item no disponible para POS.")
    qty_q = _q_qty(qty)
    if qty_q <= 0:
        raise ValueError("qty debe ser > 0.")
    if not item.allow_fraction:
        integral = qty_q.quantize(Decimal("1"))
        if qty_q != integral:
            raise ValueError("El item no permite fracciones.")
    if item.rounding_increment and Decimal(item.rounding_increment) > 0:
        remainder = qty_q % Decimal(item.rounding_increment)
        if remainder != 0:
            raise ValueError("qty no cumple el redondeo permitido del item.")
    resolved_price = _q_price(unit_price if unit_price is not None else Decimal(item.suggested_price or "0"))
    if not allow_manual_reprice and unit_price is not None and resolved_price != _q_price(Decimal(item.suggested_price or "0")):
        raise ValueError("Repricing manual no permitido por configuración.")
    if Decimal(item.min_sale_price or "0") and resolved_price < Decimal(item.min_sale_price):
        raise ValueError("Precio por debajo del mínimo permitido.")
    tax_rate = Decimal(_resolve_tax_rate(item))
    discount_q = _q_money(discount_amount or Decimal("0.00"))
    if discount_q > 0 and not allow_manual_reprice:
        raise ValueError("Descuento manual no permitido.")
    raw_subtotal = _q_money(qty_q * resolved_price)
    if discount_q < 0 or discount_q > raw_subtotal:
        raise ValueError("discount_amount inválido.")
    taxable_subtotal = _q_money(raw_subtotal - discount_q)
    line_tax = _q_money(taxable_subtotal * tax_rate)
    line_total = _q_money(taxable_subtotal + line_tax)
    return {
        "sku_snapshot": item.sku,
        "name_snapshot": item.name,
        "invoice_name_snapshot": _line_invoice_name(item),
        "uom_snapshot": item.uom_sale or item.uom,
        "tax_profile_snapshot": str(getattr(item.tax_profile, "code", "") or ""),
        "tax_rate_snapshot": tax_rate,
        "qty": qty_q,
        "unit_price": resolved_price,
        "discount_amount": discount_q,
        "line_subtotal": taxable_subtotal,
        "line_tax": line_tax,
        "line_total": line_total,
    }


def _recalculate_ticket(ticket: RetailTicket) -> None:
    rows = list(ticket.lines.order_by("position", "id"))
    subtotal = Decimal("0.00")
    tax_total = Decimal("0.00")
    discount_total = Decimal("0.00")
    total = Decimal("0.00")
    for row in rows:
        subtotal += Decimal(row.line_subtotal)
        tax_total += Decimal(row.line_tax)
        discount_total += Decimal(row.discount_amount)
        total += Decimal(row.line_total)
    ticket.subtotal = _q_money(subtotal)
    ticket.tax_total = _q_money(tax_total)
    ticket.discount_total = _q_money(discount_total)
    ticket.total = _q_money(total)
    ticket.status = RetailTicket.Status.OPEN if rows else RetailTicket.Status.DRAFT
    ticket.version = int(ticket.version) + 1
    ticket.save(update_fields=["subtotal", "tax_total", "discount_total", "total", "status", "version", "updated_at"])


def _sale_payload(sale: RetailSale) -> dict[str, object]:
    return {
        "sale_id": int(sale.id),
        "ticket_id": int(sale.ticket_id),
        "status": sale.status,
        "billing_doc_id": sale.billing_doc_id,
        "payment_id": str(getattr(sale.payment_intent, "payment_id", "") or ""),
        "cash_movement_id": sale.cash_movement_id,
        "inventory_movement_ids": list(sale.inventory_movement_ids or []),
        "flow_correlation_id": sale.flow_correlation_id,
        "accounting_status": sale.accounting_status,
    }


def _ticket_payload(ticket: RetailTicket) -> dict[str, object]:
    lines = [
        {
            "id": int(line.id),
            "source_line_id": int(line.source_line_id) if line.source_line_id else None,
            "position": int(line.position),
            "inventory_item_id": int(line.inventory_item_id) if line.inventory_item_id else None,
            "sku_snapshot": line.sku_snapshot,
            "name_snapshot": line.name_snapshot,
            "invoice_name_snapshot": line.invoice_name_snapshot,
            "uom_snapshot": line.uom_snapshot,
            "tax_profile_snapshot": line.tax_profile_snapshot,
            "tax_rate_snapshot": str(line.tax_rate_snapshot),
            "qty": str(line.qty),
            "unit_price": str(line.unit_price),
            "discount_amount": str(line.discount_amount),
            "line_subtotal": str(line.line_subtotal),
            "line_tax": str(line.line_tax),
            "line_total": str(line.line_total),
        }
        for line in ticket.lines.order_by("position", "id")
    ]
    return {
        "id": int(ticket.id),
        "ticket_kind": ticket.ticket_kind,
        "status": ticket.status,
        "payment_status": ticket.payment_status,
        "fulfillment_status": ticket.fulfillment_status,
        "compensation_status": ticket.compensation_status,
        "version": int(ticket.version),
        "terminal_id": int(ticket.terminal_id) if ticket.terminal_id else None,
        "terminal_code": str(getattr(ticket.terminal, "code", "") or ""),
        "cash_session_id": int(ticket.cash_session_id) if ticket.cash_session_id else None,
        "customer_name": ticket.customer_name,
        "customer_ref": ticket.customer_ref,
        "subtotal": str(ticket.subtotal),
        "tax_total": str(ticket.tax_total),
        "discount_total": str(ticket.discount_total),
        "total": str(ticket.total),
        "billing_doc_id": int(ticket.billing_doc_id) if ticket.billing_doc_id else None,
        "payment_intent_id": str(getattr(ticket.payment_intent, "payment_id", "") or ""),
        "flow_correlation_id": ticket.flow_correlation_id,
        "checkout_lock_token": ticket.checkout_lock_token,
        "compensation_attempts": int(ticket.compensation_attempts),
        "last_error": ticket.last_error,
        "closed_at": ticket.closed_at.isoformat() if ticket.closed_at else None,
        "created_at": ticket.created_at.isoformat(),
        "updated_at": ticket.updated_at.isoformat(),
        "lines": lines,
    }


@transaction.atomic
def open_ticket(
    *,
    request,
    actor,
    terminal_id: int | None = None,
    cash_session_id: int | None = None,
    customer_name: str = "",
    customer_ref: str = "",
    ticket_kind: str = RetailTicket.TicketKind.SALE,
) -> RetailTicket:
    company, branch = _request_scope(request)
    terminal = None
    if terminal_id is not None:
        terminal = RetailTerminal.objects.select_for_update().filter(id=int(terminal_id), branch=branch, is_active=True).first()
        if terminal is None:
            raise ValueError("terminal inválida")
    session = None
    if cash_session_id is not None:
        session = CashSession.objects.select_for_update().filter(
            id=int(cash_session_id),
            company=company,
            branch=branch,
        ).first()
        if session is None:
            raise ValueError("cash session inválida")
    ticket = RetailTicket.objects.create(
        company=company,
        branch=branch,
        terminal=terminal,
        cash_session=session,
        customer_name=str(customer_name or ""),
        customer_ref=str(customer_ref or ""),
        ticket_kind=str(ticket_kind or RetailTicket.TicketKind.SALE),
        created_by=actor,
    )
    write_event(
        request=request,
        module="RETAIL",
        event_type="RETAIL_TICKET_OPENED",
        reason_code="RETAIL_OK",
        actor_user=actor,
        subject_type="RETAIL_TICKET",
        subject_id=str(ticket.id),
        metadata={"ticket_kind": ticket.ticket_kind, "terminal_id": ticket.terminal_id or None},
    )
    _publish_retail_event(
        request=request,
        actor_user=actor,
        event_type="RetailTicketOpened",
        data={"ticket_id": ticket.id, "ticket_kind": ticket.ticket_kind, "status": ticket.status},
    )
    return ticket


@transaction.atomic
def add_line(
    *,
    request,
    actor,
    ticket_id: int,
    expected_version: int,
    item_id: int,
    qty: Decimal,
    unit_price: Decimal | None = None,
    discount_amount: Decimal | None = None,
) -> TicketMutationResult:
    _, branch = _request_scope(request)
    ticket = RetailTicket.objects.select_for_update().select_related("branch").get(id=int(ticket_id), branch=branch)
    _require_ticket_mutable(ticket)
    _ensure_no_active_hold(ticket)
    _check_expected_version(ticket, expected_version)
    cfg = _get_branch_config(branch=branch)
    item = InventoryItem.objects.select_related("tax_profile").get(id=int(item_id), company=ticket.company)
    if not _item_enabled_for_branch(item=item, branch_id=branch.id):
        raise ValueError("Item no habilitado para la sucursal.")
    can_manual_reprice = bool(cfg.allow_manual_reprice) and _actor_has_permission(
        actor=actor,
        company=ticket.company,
        branch=ticket.branch,
        permission_code="retail.ticket.reprice",
    )
    snapshot = _build_line_snapshot(
        item=item,
        qty=Decimal(qty),
        unit_price=Decimal(unit_price) if unit_price is not None else None,
        discount_amount=Decimal(discount_amount) if discount_amount is not None else None,
        allow_manual_reprice=can_manual_reprice,
    )
    line = RetailTicketLine.objects.create(
        ticket=ticket,
        inventory_item=item,
        position=int(ticket.lines.count()) + 1,
        **snapshot,
    )
    _recalculate_ticket(ticket)
    write_event(
        request=request,
        module="RETAIL",
        event_type="RETAIL_TICKET_UPDATED",
        reason_code="RETAIL_OK",
        actor_user=actor,
        subject_type="RETAIL_TICKET_LINE",
        subject_id=str(line.id),
        metadata={"ticket_id": ticket.id, "item_id": item.id, "qty": str(line.qty)},
    )
    _publish_retail_event(
        request=request,
        actor_user=actor,
        correlation_id=ticket.flow_correlation_id,
        event_type="RetailTicketLineAdded",
        data={"ticket_id": ticket.id, "line_id": line.id, "item_id": item.id, "qty": str(line.qty)},
    )
    ticket.refresh_from_db()
    return TicketMutationResult(ticket=ticket, line=line)


@transaction.atomic
def update_line(
    *,
    request,
    actor,
    ticket_id: int,
    line_id: int,
    expected_version: int,
    qty: Decimal | None = None,
    unit_price: Decimal | None = None,
    discount_amount: Decimal | None = None,
) -> TicketMutationResult:
    _, branch = _request_scope(request)
    ticket = RetailTicket.objects.select_for_update().get(id=int(ticket_id), branch=branch)
    _require_ticket_mutable(ticket)
    _ensure_no_active_hold(ticket)
    _check_expected_version(ticket, expected_version)
    cfg = _get_branch_config(branch=branch)
    line = RetailTicketLine.objects.select_for_update().get(id=int(line_id), ticket=ticket)
    item = line.inventory_item
    if item is None:
        raise ValueError("Línea sin item inventariable.")
    can_manual_reprice = bool(cfg.allow_manual_reprice) and _actor_has_permission(
        actor=actor,
        company=ticket.company,
        branch=ticket.branch,
        permission_code="retail.ticket.reprice",
    )
    snapshot = _build_line_snapshot(
        item=item,
        qty=Decimal(qty if qty is not None else line.qty),
        unit_price=Decimal(unit_price) if unit_price is not None else Decimal(line.unit_price),
        discount_amount=Decimal(discount_amount) if discount_amount is not None else Decimal(line.discount_amount),
        allow_manual_reprice=can_manual_reprice,
    )
    for key, value in snapshot.items():
        setattr(line, key, value)
    line.save()
    _recalculate_ticket(ticket)
    write_event(
        request=request,
        module="RETAIL",
        event_type="RETAIL_TICKET_UPDATED",
        reason_code="RETAIL_OK",
        actor_user=actor,
        subject_type="RETAIL_TICKET_LINE",
        subject_id=str(line.id),
        metadata={"ticket_id": ticket.id, "item_id": item.id, "qty": str(line.qty)},
    )
    _publish_retail_event(
        request=request,
        actor_user=actor,
        correlation_id=ticket.flow_correlation_id,
        event_type="RetailTicketRepriced",
        data={"ticket_id": ticket.id, "line_id": line.id, "item_id": item.id, "qty": str(line.qty)},
    )
    ticket.refresh_from_db()
    return TicketMutationResult(ticket=ticket, line=line)


@transaction.atomic
def remove_line(*, request, actor, ticket_id: int, line_id: int, expected_version: int) -> RetailTicket:
    _, branch = _request_scope(request)
    ticket = RetailTicket.objects.select_for_update().get(id=int(ticket_id), branch=branch)
    _require_ticket_mutable(ticket)
    _ensure_no_active_hold(ticket)
    _check_expected_version(ticket, expected_version)
    line = RetailTicketLine.objects.select_for_update().get(id=int(line_id), ticket=ticket)
    line.delete()
    for idx, row in enumerate(ticket.lines.order_by("position", "id"), start=1):
        if row.position != idx:
            row.position = idx
            row.save(update_fields=["position"])
    _recalculate_ticket(ticket)
    write_event(
        request=request,
        module="RETAIL",
        event_type="RETAIL_TICKET_UPDATED",
        reason_code="RETAIL_OK",
        actor_user=actor,
        subject_type="RETAIL_TICKET",
        subject_id=str(ticket.id),
        metadata={"removed_line_id": int(line_id)},
    )
    return ticket


@transaction.atomic
def hold_ticket(*, request, actor, ticket_id: int, expected_version: int, reason: str = "") -> RetailHold:
    _, branch = _request_scope(request)
    ticket = RetailTicket.objects.select_for_update().get(id=int(ticket_id), branch=branch)
    _require_ticket_mutable(ticket)
    _check_expected_version(ticket, expected_version)
    if ticket.lines.count() == 0:
        raise ValueError("No se puede retener un ticket vacío.")
    active = _active_hold(ticket)
    if active is not None:
        return active
    cfg = _get_branch_config(branch=branch)
    hold = RetailHold.objects.create(
        ticket=ticket,
        reason=str(reason or ""),
        held_by=actor,
        expires_at=timezone.now() + timedelta(minutes=max(1, int(cfg.hold_expiry_minutes))),
    )
    ticket.version = int(ticket.version) + 1
    ticket.save(update_fields=["version", "updated_at"])
    write_event(
        request=request,
        module="RETAIL",
        event_type="RETAIL_HOLD_CREATED",
        reason_code="RETAIL_OK",
        actor_user=actor,
        subject_type="RETAIL_HOLD",
        subject_id=str(hold.id),
        metadata={"ticket_id": ticket.id, "reason": hold.reason},
    )
    _publish_retail_event(
        request=request,
        actor_user=actor,
        correlation_id=ticket.flow_correlation_id,
        event_type="RetailHoldCreated",
        data={"ticket_id": ticket.id, "hold_id": hold.id, "reason": hold.reason},
    )
    return hold


@transaction.atomic
def resume_hold(*, request, actor, hold_id: int) -> RetailHold:
    _, branch = _request_scope(request)
    hold = RetailHold.objects.select_for_update().select_related("ticket").get(id=int(hold_id), ticket__branch=branch)
    _expire_active_holds(ticket=hold.ticket)
    if hold.status != RetailHold.Status.ACTIVE:
        return hold
    hold.status = RetailHold.Status.RESUMED
    hold.resumed_at = timezone.now()
    hold.save(update_fields=["status", "resumed_at"])
    hold.ticket.version = int(hold.ticket.version) + 1
    hold.ticket.save(update_fields=["version", "updated_at"])
    write_event(
        request=request,
        module="RETAIL",
        event_type="RETAIL_HOLD_RESUMED",
        reason_code="RETAIL_OK",
        actor_user=actor,
        subject_type="RETAIL_HOLD",
        subject_id=str(hold.id),
        metadata={"ticket_id": hold.ticket_id},
    )
    _publish_retail_event(
        request=request,
        actor_user=actor,
        correlation_id=hold.ticket.flow_correlation_id,
        event_type="RetailHoldResumed",
        data={"ticket_id": hold.ticket_id, "hold_id": hold.id},
    )
    return hold


def list_active_holds(*, request):
    _, branch = _request_scope(request)
    qs = RetailHold.objects.select_related("ticket__terminal").filter(ticket__branch=branch, status=RetailHold.Status.ACTIVE)
    now = timezone.now()
    qs = qs.filter(Q(expires_at__isnull=True) | Q(expires_at__gte=now)).order_by("-held_at", "-id")
    return list(qs)


def recent_tickets(*, request, limit: int = 20):
    _, branch = _request_scope(request)
    qs = RetailTicket.objects.select_related("terminal").filter(branch=branch).order_by("-created_at", "-id")
    return list(qs[: max(1, int(limit))])


def _build_preview(*, request, ticket: RetailTicket) -> CheckoutPreview:
    _, branch = _request_scope(request)
    cfg = _get_branch_config(branch=branch)
    blocking_errors: list[dict[str, str]] = []
    warnings: list[dict[str, str]] = []
    if not cfg.active:
        blocking_errors.append({"code": "RETAIL_CONFIG_INACTIVE", "detail": "Retail config inactiva."})
    if cfg.default_warehouse_id is None:
        blocking_errors.append({"code": "RETAIL_WAREHOUSE_REQUIRED", "detail": "Sucursal sin warehouse POS configurado."})
    active_session = None
    if ticket.cash_session_id:
        active_session = CashSession.objects.filter(id=ticket.cash_session_id, company=ticket.company, branch=ticket.branch).first()
    if active_session is None:
        active_session = CashSession.objects.filter(
            company=ticket.company,
            branch=ticket.branch,
            status=CashSession.Status.OPEN,
        ).order_by("-opened_at", "-id").first()
    if active_session is None:
        blocking_errors.append({"code": "RETAIL_CASH_SESSION_REQUIRED", "detail": "No hay CashSession OPEN."})
    elif active_session.status != CashSession.Status.OPEN:
        blocking_errors.append({"code": "RETAIL_CASH_SESSION_INVALID", "detail": "CashSession inválida para checkout."})

    if ticket.status not in (RetailTicket.Status.OPEN, RetailTicket.Status.DRAFT):
        blocking_errors.append({"code": "RETAIL_TICKET_STATE_INVALID", "detail": "Estado de ticket inválido para checkout."})
    if ticket.lines.count() == 0:
        blocking_errors.append({"code": "RETAIL_EMPTY_TICKET", "detail": "Ticket sin líneas."})
    if _active_hold(ticket) is not None:
        blocking_errors.append({"code": "RETAIL_TICKET_ON_HOLD", "detail": "Ticket retenido."})
    if ticket.ticket_kind != RetailTicket.TicketKind.SALE:
        blocking_errors.append({"code": "RETAIL_TICKET_KIND_INVALID", "detail": "Solo SALE usa checkout commit."})
    if cfg.require_customer_for_fiscal and ticket.customer_name.strip() == "":
        blocking_errors.append({"code": "RETAIL_CUSTOMER_REQUIRED", "detail": "Cliente requerido para documento fiscal."})

    warehouse = cfg.default_warehouse
    line_checks: list[dict[str, object]] = []
    if warehouse is not None:
        for line in ticket.lines.select_related("inventory_item").order_by("position", "id"):
            item = line.inventory_item
            line_payload: dict[str, object] = {
                "line_id": int(line.id),
                "item_id": int(item.id) if item is not None else None,
                "qty": str(line.qty),
                "controls_stock": bool(getattr(item, "controls_stock", False)),
                "ok": True,
            }
            if item is not None and bool(item.controls_stock) and item.item_type != "SERVICIO":
                bal = (
                    item.balances.filter(company=ticket.company, branch=ticket.branch, warehouse=warehouse)
                    .order_by("-updated_at", "-id")
                    .first()
                )
                qty_on_hand = Decimal(str(getattr(bal, "qty_on_hand", "0.0000") or "0.0000"))
                line_payload["qty_on_hand"] = str(qty_on_hand)
                if qty_on_hand < Decimal(line.qty):
                    line_payload["ok"] = False
                    line_payload["code"] = "INVENTORY_INSUFFICIENT_STOCK"
                    blocking_errors.append(
                        {
                            "code": "INVENTORY_INSUFFICIENT_STOCK",
                            "detail": f"Stock insuficiente para {line.sku_snapshot}.",
                        }
                    )
            line_checks.append(line_payload)

    return CheckoutPreview(
        ok=len(blocking_errors) == 0,
        blocking_errors=blocking_errors,
        warnings=warnings,
        totals={
            "subtotal": str(ticket.subtotal),
            "tax_total": str(ticket.tax_total),
            "discount_total": str(ticket.discount_total),
            "total": str(ticket.total),
        },
        line_checks=line_checks,
        config=cfg,
        cash_session=active_session,
        warehouse=warehouse,
    )


def preview_checkout(*, request, ticket_id: int) -> CheckoutPreview:
    _, branch = _request_scope(request)
    ticket = RetailTicket.objects.select_related("cash_session", "terminal").get(id=int(ticket_id), branch=branch)
    return _build_preview(request=request, ticket=ticket)


def _resolve_accounting_status(*, sale: RetailSale) -> str:
    statuses = []
    if sale.billing_doc_id:
        statuses.append(str(getattr(sale.billing_doc, "accounting_status", "") or ""))
    if sale.inventory_movement_ids:
        rows = StockMovement.objects.filter(id__in=list(sale.inventory_movement_ids or []))
        statuses.extend([str(row.accounting_status or "") for row in rows])
    non_empty = [value for value in statuses if value]
    if not non_empty:
        return ""
    if any(value == "DRAFT_EXCEPTION" for value in non_empty):
        return "DRAFT_EXCEPTION"
    if all(value == "POSTED" for value in non_empty):
        return "POSTED"
    if any(value == "PENDING_RULESET" for value in non_empty):
        return "PENDING_RULESET"
    return non_empty[0]


def _return_success_response(*, sale: RetailSale, payment_record: RetailPaymentRecord | None = None):
    billing = sale.billing_doc
    return {
        "ticket_id": int(sale.ticket_id),
        "sale_id": int(sale.id),
        "status": sale.status,
        "correlation_id": sale.flow_correlation_id,
        "billing": {
            "doc_id": int(billing.id) if billing is not None else None,
            "number": int(billing.number) if billing is not None else None,
            "status": str(getattr(billing, "status", "") or ""),
            "fiscal_status": str(getattr(billing, "fiscal_status", "") or ""),
            "fiscal_reference": str(getattr(billing, "fiscal_reference", "") or ""),
            "evidence_id": str(getattr(billing, "fiscal_evidence_id", "") or ""),
            "accounting_status": str(getattr(billing, "accounting_status", "") or ""),
        },
        "payment": {
            "payment_id": str(getattr(sale.payment_intent, "payment_id", "") or ""),
            "intent_status": str(getattr(sale.payment_intent, "status", "") or ""),
            "cash_movement_id": int(sale.cash_movement_id) if sale.cash_movement_id else None,
            "cash_received": str(getattr(payment_record, "cash_received", "0.00")),
            "change_due": str(getattr(payment_record, "change_due", "0.00")),
        },
        "inventory": {
            "movement_ids": list(sale.inventory_movement_ids or []),
            "fulfillment_status": sale.ticket.fulfillment_status,
            "reversal_movement_ids": list(sale.reversal_movement_ids or []),
        },
        "accounting": {
            "aggregate_status": sale.accounting_status,
            "billing_status": str(getattr(billing, "accounting_status", "") or ""),
            "inventory_statuses": list(
                StockMovement.objects.filter(id__in=list(sale.inventory_movement_ids or [])).values_list(
                    "accounting_status", flat=True
                )
            ),
        },
    }


def _reverse_checkout(
    *,
    request,
    sale: RetailSale,
    actor,
    reason: str,
    allow_retry: bool,
) -> RetailSale:
    req = request or _retail_request(company=sale.company, branch=sale.branch, user=actor)
    corr = sale.flow_correlation_id or f"retail-sale-{sale.id}-{uuid4().hex[:8]}"
    errors: list[str] = []
    reversal_ids = list(sale.reversal_movement_ids or [])

    if sale.cash_movement_id and sale.cash_session_id:
        try:
            if not RetailPaymentRecord.objects.filter(
                ticket_id=sale.ticket_id,
                kind=RetailPaymentRecord.Kind.SALE_REFUND,
                idempotency_key=f"retail:sale:{sale.id}:cash-refund",
            ).exists():
                refund_movement = post_cash_movement(
                    request=req,
                    actor=actor,
                    session_id=int(sale.cash_session_id),
                    movement_type=CashMovement.MovementType.REFUND,
                    amount=Decimal(sale.ticket.total),
                    reference=f"retail-sale-{sale.id}",
                    reason=reason,
                    correlation_id=corr,
                    causation_id=f"{corr}:compensation:cash-refund",
                )
                RetailPaymentRecord.objects.create(
                    ticket=sale.ticket,
                    payment_intent=sale.payment_intent,
                    cash_movement=refund_movement,
                    kind=RetailPaymentRecord.Kind.SALE_REFUND,
                    status=RetailPaymentRecord.Status.REFUNDED,
                    amount=Decimal(sale.ticket.total),
                    reason=reason,
                    idempotency_key=f"retail:sale:{sale.id}:cash-refund",
                )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"cash_refund:{exc}")
    elif sale.cash_movement_id and not sale.cash_session_id:
        errors.append("cash_refund:missing_cash_session")

    if sale.payment_intent_id:
        payment_intent = sale.payment_intent
        if payment_intent is None:
            errors.append("payment_refund:missing_payment_intent")
            payment_intent = None
        try:
            if payment_intent is not None:
                refund_payment_intent(
                    request=req,
                    actor=actor,
                    payment_id=str(payment_intent.payment_id),
                    amount=Decimal(sale.ticket.total),
                    idempotency_key=f"retail:sale:{sale.id}:payment-refund",
                    reason=reason,
                    correlation_id=corr,
                    causation_id=f"{corr}:compensation:payment-refund",
                )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"payment_refund:{exc}")

    if sale.billing_doc_id:
        try:
            void_doc(
                request=req,
                actor=actor,
                doc_id=int(sale.billing_doc_id),
                reason=reason or "VOID",
                correlation_id=corr,
                causation_id=f"{corr}:compensation:billing-void",
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"billing_void:{exc}")

    if sale.inventory_movement_ids:
        movements = StockMovement.objects.filter(id__in=list(sale.inventory_movement_ids or []))
        for movement in movements:
            existing = f"retail:sale:{sale.id}:reverse:{movement.id}"
            if StockMovement.objects.filter(company=sale.company, idempotency_key=existing).exists():
                prior = StockMovement.objects.filter(company=sale.company, idempotency_key=existing).first()
                if prior is not None and int(prior.id) not in reversal_ids:
                    reversal_ids.append(int(prior.id))
                continue
            try:
                qty = Decimal("0") - Decimal(movement.qty_delta)
                reversal = post_receive(
                    request=req,
                    actor=actor,
                    warehouse_id=int(movement.warehouse_id),
                    item_id=int(movement.item_id),
                    qty=qty,
                    unit_cost=Decimal(movement.unit_cost),
                    idempotency_key=existing,
                    note=f"Reverse retail sale {sale.id}",
                    source_module="RETAIL",
                    source_type="SALE_REVERSAL",
                    source_id=str(sale.id),
                    correlation_id=corr,
                    causation_id=f"{corr}:compensation:inventory-receive:{movement.id}",
                )
                reversal_ids.append(int(reversal.movement_id))
            except Exception as exc:  # noqa: BLE001
                errors.append(f"inventory_reverse:{movement.id}:{exc}")

    sale.reversal_movement_ids = reversal_ids
    sale.compensation_attempts = int(sale.compensation_attempts) + 1
    sale.compensation_last_error = "; ".join(errors)[:255]
    if errors:
        sale.status = (
            RetailSale.Status.COMPENSATING
            if allow_retry and sale.compensation_attempts < COMPENSATION_MAX_ATTEMPTS
            else RetailSale.Status.COMPENSATION_FAILED
        )
        sale.compensation_next_retry_at = (
            timezone.now() + timedelta(minutes=min(2 ** int(sale.compensation_attempts), 60))
            if sale.status == RetailSale.Status.COMPENSATING
            else None
        )
        sale.save(
            update_fields=[
                "reversal_movement_ids",
                "status",
                "compensation_attempts",
                "compensation_last_error",
                "compensation_next_retry_at",
                "updated_at",
            ]
        )
        sale.ticket.compensation_status = (
            RetailTicket.CompensationStatus.COMPENSATING
            if sale.status == RetailSale.Status.COMPENSATING
            else RetailTicket.CompensationStatus.FAILED
        )
        sale.ticket.last_error = sale.compensation_last_error
        sale.ticket.compensation_attempts = sale.compensation_attempts
        sale.ticket.save(update_fields=["compensation_status", "last_error", "compensation_attempts", "updated_at"])
        write_event(
            request=req,
            module="RETAIL",
            event_type="RETAIL_COMPENSATION_FAILED",
            reason_code="RETAIL_OK",
            actor_user=actor,
            subject_type="RETAIL_SALE",
            subject_id=str(sale.id),
            metadata={"error": sale.compensation_last_error, "attempts": sale.compensation_attempts},
        )
        _publish_retail_event(
            request=req,
            actor_user=actor,
            correlation_id=corr,
            event_type="RetailCompensationFailed",
            data={"sale_id": sale.id, "error": sale.compensation_last_error, "attempts": sale.compensation_attempts},
        )
        return sale

    sale.status = RetailSale.Status.VOIDED
    sale.voided_at = timezone.now()
    sale.compensation_next_retry_at = None
    sale.compensation_last_error = ""
    sale.save(
        update_fields=[
            "reversal_movement_ids",
            "status",
            "voided_at",
            "compensation_attempts",
            "compensation_last_error",
            "compensation_next_retry_at",
            "updated_at",
        ]
    )
    sale.ticket.status = RetailTicket.Status.VOIDED
    sale.ticket.payment_status = RetailTicket.PaymentStatus.REFUNDED
    sale.ticket.fulfillment_status = RetailTicket.FulfillmentStatus.REVERSED
    sale.ticket.compensation_status = RetailTicket.CompensationStatus.NONE
    sale.ticket.closed_at = sale.ticket.closed_at or timezone.now()
    sale.ticket.last_error = ""
    sale.ticket.compensation_attempts = sale.compensation_attempts
    sale.ticket.save(
        update_fields=[
            "status",
            "payment_status",
            "fulfillment_status",
            "compensation_status",
            "closed_at",
            "last_error",
            "compensation_attempts",
            "updated_at",
        ]
    )
    write_event(
        request=req,
        module="RETAIL",
        event_type="RETAIL_TICKET_VOIDED",
        reason_code="RETAIL_OK",
        actor_user=actor,
        subject_type="RETAIL_SALE",
        subject_id=str(sale.id),
        metadata={"ticket_id": sale.ticket_id, "reason": reason},
    )
    _publish_retail_event(
        request=req,
        actor_user=actor,
        correlation_id=corr,
        event_type="RetailSaleVoided",
        data={"sale_id": sale.id, "ticket_id": sale.ticket_id, "reason": reason},
    )
    return sale


@transaction.atomic
def commit_checkout(
    *,
    request,
    actor,
    ticket_id: int,
    expected_version: int,
    idempotency_key: str,
    cash_received: Decimal,
) -> dict:
    _, branch = _request_scope(request)
    normalized_idempotency_key = str(idempotency_key or "").strip()
    if not normalized_idempotency_key:
        raise RetailDomainError(code="RETAIL_IDEMPOTENCY_KEY_REQUIRED", detail="idempotency_key requerido.", status_code=400)
    ticket = RetailTicket.objects.select_for_update().get(id=int(ticket_id), branch=branch)

    command_request_hash = _request_hash(
        {
            "ticket_id": int(ticket_id),
            "expected_version": int(expected_version),
            "cash_received": str(cash_received),
        }
    )
    command, replayed = _start_command_execution(
        company=ticket.company,
        branch=ticket.branch,
        action=RetailCommandExecution.Action.CHECKOUT_COMMIT,
        idempotency_key=normalized_idempotency_key,
        request_hash=command_request_hash,
        correlation_id=ticket.flow_correlation_id,
        causation_id=f"retail:checkout:{ticket.id}",
    )
    if replayed:
        replay_payload = dict(command.response_json or {})
        replay_payload["idempotency_replayed"] = True
        return replay_payload

    sale = getattr(ticket, "sale", None)
    needs_compensation = False
    corr = ticket.flow_correlation_id or f"retail-ticket-{ticket.id}-{uuid4().hex[:12]}"
    try:
        if sale is not None and sale.status == RetailSale.Status.COMPLETED:
            payment_record = ticket.payment_records.filter(kind=RetailPaymentRecord.Kind.SALE_CAPTURE).order_by("-id").first()
            response = _return_success_response(sale=sale, payment_record=payment_record)
            response["idempotency_replayed"] = False
            _mark_command_success(command, response_json=response, correlation_id=sale.flow_correlation_id)
            return response

        if (
            ticket.checkout_lock_token
            and ticket.checkout_lock_token != normalized_idempotency_key
            and ticket.status not in (RetailTicket.Status.CLOSED, RetailTicket.Status.VOIDED)
        ):
            raise RetailDomainError(
                code="TICKET_CHECKOUT_IN_PROGRESS",
                detail="El ticket ya tiene un checkout en progreso con otra idempotency_key.",
                status_code=409,
                retryable=True,
                correlation_id=ticket.flow_correlation_id,
                causation_id=f"retail:checkout-lock:{ticket.id}",
            )

        _check_expected_version(ticket, expected_version)
        preview = _build_preview(request=request, ticket=ticket)
        if not preview.ok:
            raise RetailDomainError(
                code="RETAIL_CHECKOUT_PREVIEW_BLOCKED",
                detail="; ".join(item["detail"] for item in preview.blocking_errors),
                status_code=400,
                retryable=False,
                correlation_id=ticket.flow_correlation_id,
            )
        cash_session = preview.cash_session
        warehouse = preview.warehouse
        if cash_session is None or warehouse is None:
            raise RetailDomainError(
                code="RETAIL_CHECKOUT_PREVIEW_BLOCKED",
                detail="Configuración incompleta de caja o almacén para checkout.",
                status_code=400,
                retryable=False,
                correlation_id=ticket.flow_correlation_id,
            )
        if Decimal(cash_received) < Decimal(ticket.total):
            raise RetailDomainError(
                code="RETAIL_CASH_RECEIVED_INSUFFICIENT",
                detail="Efectivo recibido insuficiente.",
                status_code=400,
                retryable=False,
                correlation_id=ticket.flow_correlation_id,
            )

        ticket.flow_correlation_id = corr
        ticket.checkout_lock_token = normalized_idempotency_key
        ticket.payment_status = RetailTicket.PaymentStatus.INTENDED
        ticket.save(update_fields=["flow_correlation_id", "checkout_lock_token", "payment_status", "updated_at"])

        if sale is None:
            sale = RetailSale.objects.create(
                company=ticket.company,
                branch=ticket.branch,
                ticket=ticket,
                terminal=ticket.terminal,
                cash_session=cash_session,
                flow_correlation_id=corr,
                created_by=actor,
            )

        _publish_retail_event(
            request=request,
            actor_user=actor,
            correlation_id=corr,
            event_type="RetailCheckoutStarted",
            data={"ticket_id": ticket.id, "sale_id": sale.id, "total": str(ticket.total)},
        )
        write_event(
            request=request,
            module="RETAIL",
            event_type="RETAIL_CHECKOUT_STARTED",
            reason_code="RETAIL_OK",
            actor_user=actor,
            subject_type="RETAIL_SALE",
            subject_id=str(sale.id),
            metadata={"ticket_id": ticket.id, "idempotency_key": normalized_idempotency_key},
        )

        capture_record, _ = RetailPaymentRecord.objects.get_or_create(
            ticket=ticket,
            kind=RetailPaymentRecord.Kind.SALE_CAPTURE,
            idempotency_key=normalized_idempotency_key,
            defaults={
                "status": RetailPaymentRecord.Status.INTENDED,
                "amount": Decimal(ticket.total),
                "cash_received": _q_money(Decimal(cash_received)),
                "change_due": _q_money(Decimal(cash_received) - Decimal(ticket.total)),
            },
        )

        needs_compensation = True
        payment_intent, _ = create_payment_intent(
            request=request,
            actor=actor,
            amount=Decimal(ticket.total),
            currency="NIO",
            idempotency_key=f"retail:ticket:{ticket.id}:intent",
            external_ref=str(ticket.id),
            provider="CASH",
            correlation_id=corr,
            causation_id=f"{corr}:payment-intent",
        )
        ticket.payment_intent = payment_intent
        sale.payment_intent = payment_intent
        capture_record.payment_intent = payment_intent
        capture_record.save(update_fields=["payment_intent"])

        lines_payload = []
        movement_ids: list[int] = []
        for line in ticket.lines.select_related("inventory_item").order_by("position", "id"):
            lines_payload.append(
                {
                    "description": line.invoice_name_snapshot or line.name_snapshot,
                    "quantity": line.qty,
                    "unit_price": line.unit_price,
                    "tax_rate": line.tax_rate_snapshot,
                    "inventory_item_id": line.inventory_item_id,
                }
            )

        draft = create_draft(
            request=request,
            actor=actor,
            doc_type=DocType.INVOICE,
            series=preview.config.series or "RTL",
            currency="NIO",
            customer_name=ticket.customer_name,
            customer_ref=ticket.customer_ref,
            is_fiscal=False,
            lines=lines_payload,
            idempotency_key=f"retail:ticket:{ticket.id}:draft",
            source_module="RETAIL",
            source_type="SALE",
            source_id=str(sale.id),
            correlation_id=corr,
            causation_id=f"{corr}:billing-draft",
        )

        sale.save(update_fields=["payment_intent", "updated_at"])

        for line in ticket.lines.select_related("inventory_item").order_by("position", "id"):
            item = line.inventory_item
            if item is not None and item.controls_stock and item.item_type != "SERVICIO":
                movement = post_issue(
                    request=request,
                    actor=actor,
                    warehouse_id=int(warehouse.id),
                    item_id=int(item.id),
                    qty=Decimal(line.qty),
                    allow_negative=False,
                    idempotency_key=f"retail:sale:{sale.id}:issue:{line.id}",
                    note=f"Retail sale {sale.id}",
                    source_module="RETAIL",
                    source_type="SALE",
                    source_id=str(sale.id),
                    correlation_id=corr,
                    causation_id=f"{corr}:inventory-issue:{line.id}",
                )
                movement_ids.append(int(movement.movement_id))

        issued = issue_doc(
            request=request,
            actor=actor,
            doc_id=int(draft.doc_id),
            apply_inventory=False,
            print_after_issue=bool(preview.config.print_after_issue),
            idempotency_key=f"retail:ticket:{ticket.id}:issue",
            correlation_id=corr,
            causation_id=f"{corr}:billing-issue",
        )
        cash_movement = post_cash_movement(
            request=request,
            actor=actor,
            session_id=int(cash_session.id),
            movement_type=CashMovement.MovementType.INCOME,
            amount=Decimal(ticket.total),
            reference=f"retail-sale-{sale.id}",
            reason="SALE",
            correlation_id=corr,
            causation_id=f"{corr}:cash-income",
        )
        capture = capture_payment_intent(
            request=request,
            actor=actor,
            payment_id=str(payment_intent.payment_id),
            amount=Decimal(ticket.total),
            idempotency_key=f"retail:sale:{sale.id}:capture",
            correlation_id=corr,
            causation_id=f"{corr}:payment-capture",
        )
        payment_intent.refresh_from_db()

        billing_doc = BillingDocument.objects.get(id=int(draft.doc_id))
        ticket.billing_doc = billing_doc
        ticket.payment_intent = payment_intent
        ticket.status = RetailTicket.Status.CLOSED
        ticket.payment_status = RetailTicket.PaymentStatus.CAPTURED
        ticket.fulfillment_status = (
            RetailTicket.FulfillmentStatus.STOCK_APPLIED if movement_ids else RetailTicket.FulfillmentStatus.PENDING
        )
        ticket.closed_at = timezone.now()
        ticket.version = int(ticket.version) + 1
        ticket.compensation_status = RetailTicket.CompensationStatus.NONE
        ticket.last_error = ""
        ticket.cash_session = cash_session
        ticket.save(
            update_fields=[
                "billing_doc",
                "payment_intent",
                "status",
                "payment_status",
                "fulfillment_status",
                "closed_at",
                "version",
                "compensation_status",
                "last_error",
                "cash_session",
                "updated_at",
            ]
        )
        capture_record.cash_movement = cash_movement
        capture_record.status = RetailPaymentRecord.Status.CAPTURED
        capture_record.change_due = _q_money(Decimal(cash_received) - Decimal(ticket.total))
        capture_record.save(update_fields=["cash_movement", "status", "change_due"])

        sale.billing_doc = billing_doc
        sale.cash_movement = cash_movement
        sale.inventory_movement_ids = movement_ids
        sale.status = RetailSale.Status.COMPLETED
        sale.accounting_status = _resolve_accounting_status(sale=sale)
        sale.save(
            update_fields=[
                "billing_doc",
                "payment_intent",
                "cash_movement",
                "inventory_movement_ids",
                "status",
                "accounting_status",
                "updated_at",
            ]
        )
        _publish_retail_event(
            request=request,
            actor_user=actor,
            correlation_id=corr,
            event_type="RetailSaleCompleted",
            data={
                "sale_id": sale.id,
                "ticket_id": ticket.id,
                "billing_doc_id": billing_doc.id,
                "payment_id": str(payment_intent.payment_id),
                "cash_movement_id": cash_movement.id,
                "inventory_movement_ids": movement_ids,
                "billing_number": int(issued.get("number") or billing_doc.number),
                "accounting_status": sale.accounting_status,
            },
            causation_id=f"{corr}:sale-completed",
        )
        write_event(
            request=request,
            module="RETAIL",
            event_type="RETAIL_SALE_COMPLETED",
            reason_code="RETAIL_OK",
            actor_user=actor,
            subject_type="RETAIL_SALE",
            subject_id=str(sale.id),
            metadata={"ticket_id": ticket.id, "payment_status": capture.status, "billing_doc_id": billing_doc.id},
        )
        response = _return_success_response(sale=sale, payment_record=capture_record)
        response["idempotency_replayed"] = False
        _mark_command_success(command, response_json=response, correlation_id=corr, causation_id=f"{corr}:sale-completed")
        return response
    except Exception as exc:  # noqa: BLE001
        if needs_compensation and sale is not None:
            try:
                _reverse_checkout(request=request, sale=sale, actor=actor, reason=str(exc), allow_retry=True)
            except Exception:  # noqa: BLE001
                pass
        domain_exc = _domain_error_from_exception(
            exc,
            fallback_code="RETAIL_CHECKOUT_COMMIT_FAILED",
            fallback_detail="checkout failed",
            status_code=400,
            retryable=True,
            correlation_id=corr,
            causation_id=f"{corr}:checkout-failed",
        )
        _mark_command_failure(command, error=domain_exc)
        raise domain_exc from exc


@transaction.atomic
def void_sale(
    *,
    request,
    actor,
    ticket_id: int,
    expected_version: int,
    idempotency_key: str,
    reason: str = "",
) -> tuple[RetailSale, bool]:
    _, branch = _request_scope(request)
    normalized_idempotency_key = str(idempotency_key or "").strip()
    if not normalized_idempotency_key:
        raise RetailDomainError(code="RETAIL_IDEMPOTENCY_KEY_REQUIRED", detail="idempotency_key requerido.", status_code=400)
    ticket = RetailTicket.objects.select_for_update().get(id=int(ticket_id), branch=branch)
    command, replayed = _start_command_execution(
        company=ticket.company,
        branch=ticket.branch,
        action=RetailCommandExecution.Action.SALE_VOID,
        idempotency_key=normalized_idempotency_key,
        request_hash=_request_hash(
            {
                "ticket_id": int(ticket_id),
                "expected_version": int(expected_version),
                "reason": str(reason or ""),
            }
        ),
        correlation_id=ticket.flow_correlation_id,
        causation_id=f"retail:void:{ticket.id}",
    )
    if replayed:
        replay_sale_id = int((command.response_json or {}).get("sale_id") or 0)
        if replay_sale_id:
            replay_sale = RetailSale.objects.select_for_update().get(id=replay_sale_id, branch=branch)
            return replay_sale, True
        replay_sale = RetailSale.objects.select_for_update().get(ticket=ticket)
        return replay_sale, True

    try:
        _check_expected_version(ticket, expected_version)
        sale = RetailSale.objects.select_for_update().get(ticket=ticket)
        if sale.status == RetailSale.Status.VOIDED:
            _mark_command_success(
                command,
                response_json={"sale_id": int(sale.id), "status": sale.status},
                correlation_id=sale.flow_correlation_id,
            )
            return sale, False
        if sale.returns.filter(status=RetailReturn.Status.COMPLETED).exists():
            raise RetailDomainError(
                code="RETAIL_VOID_NOT_ALLOWED_WITH_RETURNS",
                detail="La venta ya tiene devoluciones registradas; use return en lugar de void.",
                status_code=400,
                retryable=False,
                correlation_id=sale.flow_correlation_id,
            )
        if sale.status not in (
            RetailSale.Status.COMPLETED,
            RetailSale.Status.COMPENSATING,
            RetailSale.Status.COMPENSATION_FAILED,
        ):
            raise RetailDomainError(
                code="RETAIL_VOID_STATE_INVALID",
                detail="Venta no permite anulación en su estado actual.",
                status_code=400,
                retryable=False,
                correlation_id=sale.flow_correlation_id,
            )
        sale = _reverse_checkout(request=request, sale=sale, actor=actor, reason=reason or "VOID", allow_retry=True)
        _mark_command_success(
            command,
            response_json={"sale_id": int(sale.id), "status": sale.status},
            correlation_id=sale.flow_correlation_id,
            causation_id=f"{sale.flow_correlation_id}:void-sale",
        )
        return sale, False
    except Exception as exc:  # noqa: BLE001
        domain_exc = _domain_error_from_exception(
            exc,
            fallback_code="RETAIL_VOID_FAILED",
            fallback_detail="No se pudo anular la venta.",
            status_code=400,
            retryable=True,
            correlation_id=ticket.flow_correlation_id,
            causation_id=f"retail:void:{ticket.id}",
        )
        _mark_command_failure(command, error=domain_exc)
        raise domain_exc from exc


@transaction.atomic
def retry_compensation(*, request, actor, sale_id: int, idempotency_key: str, reason: str = "") -> tuple[RetailSale, bool]:
    _, branch = _request_scope(request)
    normalized_idempotency_key = str(idempotency_key or "").strip()
    if not normalized_idempotency_key:
        raise RetailDomainError(code="RETAIL_IDEMPOTENCY_KEY_REQUIRED", detail="idempotency_key requerido.", status_code=400)
    sale = RetailSale.objects.select_for_update().get(id=int(sale_id), branch=branch)
    command, replayed = _start_command_execution(
        company=sale.company,
        branch=sale.branch,
        action=RetailCommandExecution.Action.COMPENSATION_RETRY,
        idempotency_key=normalized_idempotency_key,
        request_hash=_request_hash({"sale_id": int(sale_id), "reason": str(reason or "")}),
        correlation_id=sale.flow_correlation_id,
        causation_id=f"retail:comp-retry:{sale.id}",
    )
    if replayed:
        replay_sale_id = int((command.response_json or {}).get("sale_id") or sale.id)
        replay_sale = RetailSale.objects.select_for_update().get(id=replay_sale_id, branch=branch)
        return replay_sale, True

    try:
        if sale.status == RetailSale.Status.VOIDED:
            _mark_command_success(
                command,
                response_json={"sale_id": int(sale.id), "status": sale.status},
                correlation_id=sale.flow_correlation_id,
            )
            return sale, False
        if sale.status not in (RetailSale.Status.COMPENSATING, RetailSale.Status.COMPENSATION_FAILED):
            raise RetailDomainError(
                code="RETAIL_COMPENSATION_STATE_INVALID",
                detail="Venta no está en estado reintentable.",
                status_code=400,
                retryable=False,
                correlation_id=sale.flow_correlation_id,
            )
        write_event(
            request=request,
            module="RETAIL",
            event_type="RETAIL_COMPENSATION_RETRIED",
            reason_code="RETAIL_OK",
            actor_user=actor,
            subject_type="RETAIL_SALE",
            subject_id=str(sale.id),
            metadata={
                "reason": str(reason or ""),
                "attempt": int(sale.compensation_attempts) + 1,
                "idempotency_key": normalized_idempotency_key,
            },
        )
        _publish_retail_event(
            request=request,
            actor_user=actor,
            correlation_id=sale.flow_correlation_id,
            event_type="RetailCompensationRetried",
            data={"sale_id": sale.id, "reason": str(reason or "")},
        )
        sale = _reverse_checkout(
            request=request,
            sale=sale,
            actor=actor,
            reason=reason or sale.compensation_last_error,
            allow_retry=True,
        )
        _mark_command_success(
            command,
            response_json={"sale_id": int(sale.id), "status": sale.status},
            correlation_id=sale.flow_correlation_id,
            causation_id=f"{sale.flow_correlation_id}:compensation-retried",
        )
        return sale, False
    except Exception as exc:  # noqa: BLE001
        domain_exc = _domain_error_from_exception(
            exc,
            fallback_code="RETAIL_COMPENSATION_RETRY_FAILED",
            fallback_detail="No se pudo reintentar la compensación.",
            status_code=400,
            retryable=True,
            correlation_id=sale.flow_correlation_id,
            causation_id=f"retail:comp-retry:{sale.id}",
        )
        _mark_command_failure(command, error=domain_exc)
        raise domain_exc from exc


def _credit_note_lines_from_return(*, original_sale: RetailSale, original_ticket: RetailTicket, line_quantities: dict[int, Decimal]):
    payload = []
    inventory_rows: list[tuple[RetailTicketLine, Decimal]] = []
    prior_returned: dict[int, Decimal] = {}
    for source_line_id, qty in RetailTicketLine.objects.filter(
        ticket__return_record__original_sale=original_sale,
        ticket__return_record__status=RetailReturn.Status.COMPLETED,
        source_line_id__isnull=False,
    ).values_list("source_line_id", "qty"):
        if source_line_id is None:
            continue
        key = int(source_line_id)
        prior_returned[key] = prior_returned.get(key, Decimal("0.0000")) + Decimal(qty)
    for line in original_ticket.lines.select_related("inventory_item").order_by("position", "id"):
        if int(line.id) not in line_quantities:
            continue
        qty = _q_qty(line_quantities[int(line.id)])
        if qty <= 0 or qty + prior_returned.get(int(line.id), Decimal("0.0000")) > Decimal(line.qty):
            raise ValueError("Cantidad de devolución inválida.")
        if line.inventory_item_id and not bool(getattr(line.inventory_item, "allow_returns", True)):
            raise ValueError(f"El item {line.sku_snapshot} no permite devolución.")
        payload.append(
            {
                "description": line.invoice_name_snapshot or line.name_snapshot,
                "quantity": qty,
                "unit_price": line.unit_price,
                "tax_rate": line.tax_rate_snapshot,
                "inventory_item_id": line.inventory_item_id,
            }
        )
        inventory_rows.append((line, qty))
    if not payload:
        raise ValueError("return sin líneas.")
    return payload, inventory_rows


@transaction.atomic
def create_return(
    *,
    request,
    actor,
    sale_id: int,
    reason: str,
    lines: list[dict[str, object]],
    idempotency_key: str,
) -> tuple[RetailReturn, bool]:
    _, branch = _request_scope(request)
    normalized_idempotency_key = str(idempotency_key or "").strip()
    if not normalized_idempotency_key:
        raise RetailDomainError(code="RETAIL_IDEMPOTENCY_KEY_REQUIRED", detail="idempotency_key requerido.", status_code=400)
    sale = RetailSale.objects.select_for_update().get(id=int(sale_id), branch=branch)
    line_quantities: dict[int, Decimal] = {}
    normalized_lines: list[dict[str, str]] = []
    for row in lines:
        if not isinstance(row, dict):
            raise RetailDomainError(
                code="RETAIL_RETURN_LINES_INVALID",
                detail="Formato inválido de líneas de devolución.",
                status_code=400,
                retryable=False,
                correlation_id=sale.flow_correlation_id,
            )
        raw_line_id = row.get("line_id")
        raw_qty = row.get("qty")
        if raw_line_id is None or raw_qty is None:
            raise RetailDomainError(
                code="RETAIL_RETURN_LINES_INVALID",
                detail="Cada línea requiere line_id y qty.",
                status_code=400,
                retryable=False,
                correlation_id=sale.flow_correlation_id,
            )
        try:
            line_id = int(str(raw_line_id))
            qty = Decimal(str(raw_qty))
        except Exception as exc:  # noqa: BLE001
            raise RetailDomainError(
                code="RETAIL_RETURN_LINES_INVALID",
                detail="line_id/qty inválidos en devolución.",
                status_code=400,
                retryable=False,
                correlation_id=sale.flow_correlation_id,
            ) from exc
        if line_id in line_quantities:
            raise RetailDomainError(
                code="RETAIL_RETURN_LINES_DUPLICATED",
                detail="No se permiten line_id repetidos en devolución.",
                status_code=400,
                retryable=False,
                correlation_id=sale.flow_correlation_id,
            )
        line_quantities[line_id] = qty
        normalized_lines.append({"line_id": str(line_id), "qty": str(qty)})
    normalized_lines = sorted(
        normalized_lines,
        key=lambda row: (int(row["line_id"]), row["qty"]),
    )
    command, replayed = _start_command_execution(
        company=sale.company,
        branch=sale.branch,
        action=RetailCommandExecution.Action.RETURN_CREATE,
        idempotency_key=normalized_idempotency_key,
        request_hash=_request_hash({"sale_id": int(sale_id), "reason": str(reason or ""), "lines": normalized_lines}),
        correlation_id=sale.flow_correlation_id,
        causation_id=f"retail:return:{sale.id}",
    )
    if replayed:
        replay_return_id = int((command.response_json or {}).get("return_id") or 0)
        if replay_return_id:
            replay_result = RetailReturn.objects.select_for_update().get(id=replay_return_id, branch=branch)
            return replay_result, True
        replay_result = RetailReturn.objects.select_for_update().get(company=sale.company, idempotency_key=normalized_idempotency_key)
        return replay_result, True

    corr = f"retail-return-{sale.id}-{uuid4().hex[:10]}"
    try:
        if sale.status != RetailSale.Status.COMPLETED:
            raise RetailDomainError(
                code="RETAIL_RETURN_STATE_INVALID",
                detail="Solo ventas COMPLETED permiten devolución.",
                status_code=400,
                retryable=False,
                correlation_id=sale.flow_correlation_id,
            )
        if sale.payment_intent_id is None:
            raise RetailDomainError(
                code="RETAIL_RETURN_PAYMENT_INTENT_REQUIRED",
                detail="La venta no tiene PaymentIntent para procesar devolución.",
                status_code=400,
                retryable=False,
                correlation_id=sale.flow_correlation_id,
            )

        branch_cfg = _get_branch_config(branch=branch)
        if branch_cfg.default_warehouse_id is None:
            raise RetailDomainError(
                code="RETAIL_WAREHOUSE_REQUIRED",
                detail="Sucursal sin warehouse POS configurado.",
                status_code=400,
                retryable=False,
                correlation_id=sale.flow_correlation_id,
            )
        active_session = (
            CashSession.objects.select_for_update()
            .filter(company=sale.company, branch=sale.branch, status=CashSession.Status.OPEN)
            .order_by("-opened_at", "-id")
            .first()
        )
        if active_session is None:
            raise RetailDomainError(
                code="RETAIL_CASH_SESSION_REQUIRED",
                detail="No hay CashSession OPEN para procesar devolución.",
                status_code=400,
                retryable=False,
                correlation_id=sale.flow_correlation_id,
            )

        original_ticket = sale.ticket
        credit_lines, inventory_rows = _credit_note_lines_from_return(
            original_sale=sale,
            original_ticket=original_ticket,
            line_quantities=line_quantities,
        )

        return_ticket = RetailTicket.objects.create(
            company=sale.company,
            branch=sale.branch,
            terminal=sale.terminal,
            cash_session=active_session,
            ticket_kind=RetailTicket.TicketKind.RETURN,
            flow_correlation_id=corr,
            customer_name=original_ticket.customer_name,
            customer_ref=original_ticket.customer_ref,
            created_by=actor,
        )
        for position, (source_line, qty) in enumerate(inventory_rows, start=1):
            line_subtotal = _q_money(Decimal(source_line.unit_price) * qty)
            line_tax = _q_money(line_subtotal * Decimal(source_line.tax_rate_snapshot))
            snapshot = {
                "source_line_id": int(source_line.id),
                "sku_snapshot": source_line.sku_snapshot,
                "name_snapshot": source_line.name_snapshot,
                "invoice_name_snapshot": source_line.invoice_name_snapshot,
                "uom_snapshot": source_line.uom_snapshot,
                "tax_profile_snapshot": source_line.tax_profile_snapshot,
                "tax_rate_snapshot": source_line.tax_rate_snapshot,
                "qty": qty,
                "unit_price": source_line.unit_price,
                "discount_amount": Decimal("0.00"),
                "line_subtotal": line_subtotal,
                "line_tax": line_tax,
                "line_total": _q_money(line_subtotal + line_tax),
            }
            RetailTicketLine.objects.create(
                ticket=return_ticket,
                inventory_item=source_line.inventory_item,
                position=position,
                **snapshot,
            )
        _recalculate_ticket(return_ticket)
        refund_amount = Decimal(return_ticket.total)
        return_ticket.status = RetailTicket.Status.CLOSED
        return_ticket.payment_status = RetailTicket.PaymentStatus.REFUNDED
        return_ticket.fulfillment_status = RetailTicket.FulfillmentStatus.STOCK_APPLIED
        return_ticket.closed_at = timezone.now()
        return_ticket.save(
            update_fields=["status", "payment_status", "fulfillment_status", "closed_at", "updated_at"]
        )

        draft = create_draft(
            request=request,
            actor=actor,
            doc_type=DocType.CREDIT_NOTE,
            series=branch_cfg.series or "RTL",
            currency="NIO",
            customer_name=return_ticket.customer_name,
            customer_ref=return_ticket.customer_ref,
            is_fiscal=False,
            lines=credit_lines,
            idempotency_key=f"retail:return:{sale.id}:{normalized_idempotency_key}:draft",
            source_module="RETAIL",
            source_type="RETURN",
            source_id=str(sale.id),
            correlation_id=corr,
            causation_id=f"{corr}:credit-draft",
        )
        issue_doc(
            request=request,
            actor=actor,
            doc_id=int(draft.doc_id),
            apply_inventory=False,
            correlation_id=corr,
            causation_id=f"{corr}:credit-issue",
        )
        credit_doc = BillingDocument.objects.get(id=int(draft.doc_id))

        movement_ids: list[int] = []
        for line, qty in inventory_rows:
            if line.inventory_item_id and getattr(line.inventory_item, "controls_stock", False):
                movement = post_receive(
                    request=request,
                    actor=actor,
                    warehouse_id=int(branch_cfg.default_warehouse_id),
                    item_id=int(line.inventory_item_id),
                    qty=qty,
                    unit_cost=Decimal(line.inventory_item.last_known_cost or "0.000000"),
                    idempotency_key=f"retail:return:{sale.id}:{normalized_idempotency_key}:receive:{line.id}",
                    note=f"Retail return {sale.id}",
                    source_module="RETAIL",
                    source_type="RETURN",
                    source_id=str(sale.id),
                    correlation_id=corr,
                    causation_id=f"{corr}:inventory-receive:{line.id}",
                )
                movement_ids.append(int(movement.movement_id))

        payment_intent = sale.payment_intent
        if payment_intent is None:
            raise RetailDomainError(
                code="RETAIL_RETURN_PAYMENT_INTENT_REQUIRED",
                detail="La venta no tiene PaymentIntent para procesar devolución.",
                status_code=400,
                retryable=False,
                correlation_id=sale.flow_correlation_id,
            )

        refund_payment_intent(
            request=request,
            actor=actor,
            payment_id=str(payment_intent.payment_id),
            amount=refund_amount,
            idempotency_key=f"retail:return:{sale.id}:{normalized_idempotency_key}:refund",
            reason=reason or "RETURN",
            correlation_id=corr,
            causation_id=f"{corr}:payment-refund",
        )
        refund_cash = post_cash_movement(
            request=request,
            actor=actor,
            session_id=int(active_session.id),
            movement_type=CashMovement.MovementType.REFUND,
            amount=refund_amount,
            reference=f"retail-return-{sale.id}",
            reason=reason or "RETURN",
            correlation_id=corr,
            causation_id=f"{corr}:cash-refund",
        )
        RetailPaymentRecord.objects.create(
            ticket=return_ticket,
            payment_intent=payment_intent,
            cash_movement=refund_cash,
            kind=RetailPaymentRecord.Kind.SALE_REFUND,
            status=RetailPaymentRecord.Status.REFUNDED,
            amount=refund_amount,
            reason=reason or "RETURN",
            idempotency_key=f"retail:return:{sale.id}:{normalized_idempotency_key}:cash",
        )

        result = RetailReturn.objects.create(
            company=sale.company,
            branch=sale.branch,
            original_sale=sale,
            return_ticket=return_ticket,
            credit_note_doc=credit_doc,
            refund_payment_intent=payment_intent,
            refund_cash_movement=refund_cash,
            inventory_movement_ids=movement_ids,
            flow_correlation_id=corr,
            idempotency_key=normalized_idempotency_key,
            status=RetailReturn.Status.COMPLETED,
            reason=str(reason or ""),
            refund_amount=refund_amount,
            created_by=actor,
            completed_at=timezone.now(),
        )
        write_event(
            request=request,
            module="RETAIL",
            event_type="RETAIL_RETURN_COMPLETED",
            reason_code="RETAIL_OK",
            actor_user=actor,
            subject_type="RETAIL_RETURN",
            subject_id=str(result.id),
            metadata={"sale_id": sale.id, "credit_note_doc_id": credit_doc.id, "refund_amount": str(refund_amount)},
        )
        _publish_retail_event(
            request=request,
            actor_user=actor,
            correlation_id=corr,
            event_type="RetailReturnCompleted",
            data={
                "return_id": result.id,
                "sale_id": sale.id,
                "ticket_id": return_ticket.id,
                "credit_note_doc_id": credit_doc.id,
                "refund_amount": str(refund_amount),
                "inventory_movement_ids": movement_ids,
            },
        )
        _mark_command_success(
            command,
            response_json={"return_id": int(result.id), "status": result.status},
            correlation_id=corr,
            causation_id=f"{corr}:return-completed",
        )
        return result, False
    except Exception as exc:  # noqa: BLE001
        domain_exc = _domain_error_from_exception(
            exc,
            fallback_code="RETAIL_RETURN_FAILED",
            fallback_detail="No se pudo completar la devolución.",
            status_code=400,
            retryable=True,
            correlation_id=corr,
            causation_id=f"retail:return:{sale.id}",
        )
        _mark_command_failure(command, error=domain_exc)
        raise domain_exc from exc


def run_retail_compensation_cycle(
    *,
    company=None,
    branch=None,
    limit: int = 100,
    include_failed: bool = False,
    actor_user=None,
    now=None,
):
    clock = now or timezone.now()
    due_filter = Q(status=RetailSale.Status.COMPENSATING) & (
        Q(compensation_next_retry_at__isnull=True) | Q(compensation_next_retry_at__lte=clock)
    )
    if include_failed:
        due_filter = due_filter | Q(status=RetailSale.Status.COMPENSATION_FAILED)
    qs = RetailSale.objects.filter(due_filter)
    if company is not None:
        qs = qs.filter(company=company)
    if branch is not None:
        qs = qs.filter(branch=branch)
    sale_ids = list(qs.order_by("compensation_next_retry_at", "id").values_list("id", flat=True)[: max(1, int(limit))])
    attempted = succeeded = failed = still_pending = 0
    errors: list[dict[str, str]] = []
    for sale_id in sale_ids:
        attempted += 1
        try:
            with transaction.atomic():
                sale = RetailSale.objects.select_for_update().get(id=int(sale_id))
                updated = _reverse_checkout(
                    request=None,
                    sale=sale,
                    actor=actor_user,
                    reason=sale.compensation_last_error or "RETRY",
                    allow_retry=True,
                )
                if updated.status == RetailSale.Status.VOIDED:
                    succeeded += 1
                elif updated.status == RetailSale.Status.COMPENSATING:
                    still_pending += 1
                else:
                    failed += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            errors.append({"sale_id": str(sale_id), "error": str(exc)})
    return {
        "attempted": attempted,
        "succeeded": succeeded,
        "failed": failed,
        "still_pending": still_pending,
        "errors": errors,
    }
