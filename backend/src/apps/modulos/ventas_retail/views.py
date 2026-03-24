from __future__ import annotations

from decimal import Decimal

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.pagination import get_limit_offset
from apps.modulos.common.permissions import rbac_permission
from apps.modulos.payments.models import CashSession
from kernels.inventarios.models import InventoryItem

from .models import RetailHold, RetailReturn, RetailSale, RetailTerminal, RetailTicket
from .serializers import (
    RetailCompensationRetryIn,
    RetailReturnCreateIn,
    TicketCheckoutCommitIn,
    TicketCheckoutPreviewIn,
    TicketCreateIn,
    TicketHoldIn,
    TicketLineCreateIn,
    TicketLineDeleteIn,
    TicketLinePatchIn,
    TicketVoidIn,
)
from .services import (
    RetailDomainError,
    _get_branch_config,
    _item_enabled_for_branch,
    _sale_payload,
    _ticket_payload,
    add_line,
    commit_checkout,
    create_return,
    hold_ticket,
    list_active_holds,
    open_ticket,
    preview_checkout,
    recent_tickets,
    remove_line,
    resume_hold,
    retry_compensation,
    update_line,
    void_sale,
)


def _serialize_cash_session(session: CashSession | None) -> dict | None:
    if session is None:
        return None
    return {
        "id": int(session.id),
        "status": session.status,
        "opening_amount": str(session.opening_amount),
        "expected_amount": str(session.expected_amount),
        "counted_amount": str(session.counted_amount),
        "difference_amount": str(session.difference_amount),
        "opened_at": session.opened_at.isoformat() if session.opened_at else None,
        "closed_at": session.closed_at.isoformat() if session.closed_at else None,
    }


def _serialize_terminal(terminal: RetailTerminal | None) -> dict | None:
    if terminal is None:
        return None
    return {
        "id": int(terminal.id),
        "code": terminal.code,
        "name": terminal.name,
        "device_ref": terminal.device_ref,
        "receipt_printer_ref": terminal.receipt_printer_ref,
        "is_active": bool(terminal.is_active),
    }


def _serialize_sale(sale: RetailSale) -> dict[str, object]:
    return {
        **_sale_payload(sale),
        "voided_at": sale.voided_at.isoformat() if sale.voided_at else None,
        "compensation_attempts": int(sale.compensation_attempts),
        "compensation_last_error": sale.compensation_last_error,
        "compensation_next_retry_at": (
            sale.compensation_next_retry_at.isoformat() if sale.compensation_next_retry_at else None
        ),
    }


def _serialize_hold(hold: RetailHold) -> dict[str, object]:
    return {
        "id": int(hold.id),
        "ticket_id": int(hold.ticket_id),
        "status": hold.status,
        "reason": hold.reason,
        "held_by_id": int(hold.held_by_id) if hold.held_by_id else None,
        "held_at": hold.held_at.isoformat() if hold.held_at else None,
        "resumed_at": hold.resumed_at.isoformat() if hold.resumed_at else None,
        "expires_at": hold.expires_at.isoformat() if hold.expires_at else None,
        "ticket": _ticket_payload(hold.ticket),
    }


def _serialize_return(return_record: RetailReturn) -> dict[str, object]:
    return {
        "id": int(return_record.id),
        "sale_id": int(return_record.original_sale_id),
        "ticket_id": int(return_record.return_ticket_id),
        "credit_note_doc_id": int(return_record.credit_note_doc_id) if return_record.credit_note_doc_id else None,
        "refund_payment_id": (
            str(getattr(return_record.refund_payment_intent, "payment_id", "") or "")
            if return_record.refund_payment_intent_id
            else ""
        ),
        "refund_cash_movement_id": (
            int(return_record.refund_cash_movement_id) if return_record.refund_cash_movement_id else None
        ),
        "inventory_movement_ids": list(return_record.inventory_movement_ids or []),
        "status": return_record.status,
        "reason": return_record.reason,
        "refund_amount": str(return_record.refund_amount),
        "flow_correlation_id": return_record.flow_correlation_id,
        "idempotency_key": return_record.idempotency_key,
        "created_at": return_record.created_at.isoformat() if return_record.created_at else None,
        "completed_at": return_record.completed_at.isoformat() if return_record.completed_at else None,
        "ticket": _ticket_payload(return_record.return_ticket),
    }


def _preview_payload(preview) -> dict[str, object]:
    return {
        "ok": bool(preview.ok),
        "blocking_errors": list(preview.blocking_errors),
        "warnings": list(preview.warnings),
        "totals": dict(preview.totals),
        "line_checks": list(preview.line_checks),
        "cash_session": _serialize_cash_session(preview.cash_session),
        "warehouse": {
            "id": int(preview.warehouse.id),
            "code": preview.warehouse.code,
            "name": preview.warehouse.name,
        }
        if preview.warehouse is not None
        else None,
        "config": {
            "series": preview.config.series,
            "default_warehouse_id": int(preview.config.default_warehouse_id) if preview.config.default_warehouse_id else None,
            "price_includes_tax": bool(preview.config.price_includes_tax),
            "hold_expiry_minutes": int(preview.config.hold_expiry_minutes),
            "print_after_issue": bool(preview.config.print_after_issue),
            "require_customer_for_fiscal": bool(preview.config.require_customer_for_fiscal),
            "allow_manual_reprice": bool(preview.config.allow_manual_reprice),
            "active": bool(preview.config.active),
        },
    }


def _mutation_error_payload(*, request, exc: Exception) -> tuple[dict[str, object], int]:
    request_id = str(getattr(request, "request_id", "") or "")
    if isinstance(exc, RetailDomainError):
        return (
            {
                "code": exc.code,
                "detail": exc.detail,
                "retryable": bool(exc.retryable),
                "correlation_id": exc.correlation_id or request_id,
                "causation_id": exc.causation_id or "",
                "idempotency_replayed": bool(exc.idempotency_replayed),
            },
            int(exc.status_code),
        )
    return (
        {
            "code": "RETAIL_BAD_REQUEST",
            "detail": str(exc),
            "retryable": False,
            "correlation_id": request_id,
            "causation_id": "",
            "idempotency_replayed": False,
        },
        status.HTTP_400_BAD_REQUEST,
    )


class HealthView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"ok": True, "module": "retail"}, status=status.HTTP_200_OK)


class BootstrapView(APIView):
    permission_classes = [rbac_permission("retail.pos.use")]

    def get(self, request):
        branch = request.branch
        config = _get_branch_config(branch=branch)
        terminals = RetailTerminal.objects.filter(branch=branch, is_active=True).order_by("code", "id")
        active_cash_session = (
            CashSession.objects.filter(company=request.company, branch=branch, status=CashSession.Status.OPEN)
            .order_by("-opened_at", "-id")
            .first()
        )
        payload = {
            "branch_config": {
                "series": config.series,
                "default_warehouse_id": int(config.default_warehouse_id) if config.default_warehouse_id else None,
                "price_includes_tax": bool(config.price_includes_tax),
                "hold_expiry_minutes": int(config.hold_expiry_minutes),
                "print_after_issue": bool(config.print_after_issue),
                "require_customer_for_fiscal": bool(config.require_customer_for_fiscal),
                "allow_manual_reprice": bool(config.allow_manual_reprice),
                "active": bool(config.active),
            },
            "default_series": config.series,
            "default_warehouse": {
                "id": int(config.default_warehouse_id),
                "code": config.default_warehouse.code,
                "name": config.default_warehouse.name,
            }
            if config.default_warehouse_id
            else None,
            "terminals": [_serialize_terminal(row) for row in terminals],
            "active_cash_session": _serialize_cash_session(active_cash_session),
            "fiscal_mode": "BILLING",
            "shortcuts_enabled": True,
        }
        return Response(payload, status=status.HTTP_200_OK)


class CatalogSearchView(APIView):
    permission_classes = [rbac_permission("retail.catalog.read")]

    def get(self, request):
        company = request.company
        branch = request.branch
        q = str(request.query_params.get("q") or "").strip()
        barcode = str(request.query_params.get("barcode") or "").strip()
        qs = InventoryItem.objects.select_related("tax_profile").filter(
            company=company,
            is_active=True,
            status="ACTIVO",
            sales_enabled=True,
            visible_pos=True,
        )
        if q:
            qs = qs.filter(
                Q(sku__icontains=q)
                | Q(name__icontains=q)
                | Q(invoice_name__icontains=q)
                | Q(invoice_description__icontains=q)
                | Q(barcode__icontains=q)
                | Q(alternate_code__icontains=q)
            )
        if barcode:
            qs = qs.filter(barcode=barcode)

        rows = [row for row in qs.order_by("sku", "id") if _item_enabled_for_branch(item=row, branch_id=int(branch.id))]
        limit, offset = get_limit_offset(request, default_limit=25, max_limit=100)
        total = len(rows)
        results = []
        for item in rows[offset : offset + limit]:
            tax_rate = Decimal(str(getattr(item.tax_profile, "rate", "0.0000") or "0.0000")) if item.tax_profile_id else Decimal("0.0000")
            results.append(
                {
                    "id": int(item.id),
                    "sku": item.sku,
                    "name": item.name,
                    "invoice_name": item.invoice_name,
                    "barcode": item.barcode,
                    "uom_sale": item.uom_sale or item.uom,
                    "item_type": item.item_type,
                    "controls_stock": bool(item.controls_stock),
                    "allow_fraction": bool(item.allow_fraction),
                    "rounding_increment": str(item.rounding_increment),
                    "suggested_price": str(item.suggested_price),
                    "min_sale_price": str(item.min_sale_price),
                    "allow_discount": bool(item.allow_discount),
                    "tax_treatment": item.tax_treatment,
                    "tax_rate": str(tax_rate),
                    "visible_pos": bool(item.visible_pos),
                }
            )
        return Response(
            {"count": total, "limit": limit, "offset": offset, "results": results},
            status=status.HTTP_200_OK,
        )


class TicketListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("retail.ticket.create")()]
        return [rbac_permission("retail.pos.use")()]

    def post(self, request):
        serializer = TicketCreateIn(data=request.data)
        serializer.is_valid(raise_exception=True)
        v = serializer.validated_data
        try:
            ticket = open_ticket(
                request=request,
                actor=request.user,
                terminal_id=v.get("terminal_id"),
                cash_session_id=v.get("cash_session_id"),
                customer_name=v.get("customer_name", "") or "",
                customer_ref=v.get("customer_ref", "") or "",
                ticket_kind=v.get("ticket_kind") or RetailTicket.TicketKind.SALE,
            )
        except Exception as exc:  # noqa: BLE001
            payload, code = _mutation_error_payload(request=request, exc=exc)
            return Response(payload, status=code)
        ticket = RetailTicket.objects.select_related("terminal", "cash_session", "payment_intent", "billing_doc").get(id=ticket.id)
        return Response(_ticket_payload(ticket), status=status.HTTP_201_CREATED)


class TicketDetailView(APIView):
    permission_classes = [rbac_permission("retail.pos.use")]

    def get(self, request, ticket_id: int):
        ticket = get_object_or_404(
            RetailTicket.objects.select_related("terminal", "cash_session", "payment_intent", "billing_doc"),
            id=int(ticket_id),
            branch=request.branch,
        )
        sale = RetailSale.objects.filter(ticket=ticket).first()
        active_hold = (
            RetailHold.objects.filter(ticket=ticket, status=RetailHold.Status.ACTIVE).order_by("-held_at", "-id").first()
        )
        return Response(
            {
                "ticket": _ticket_payload(ticket),
                "sale": _serialize_sale(sale) if sale is not None else None,
                "active_hold": _serialize_hold(active_hold) if active_hold is not None else None,
            },
            status=status.HTTP_200_OK,
        )


class TicketLineView(APIView):
    def get_permissions(self):
        if self.request.method == "DELETE":
            return [rbac_permission("retail.ticket.update")()]
        return [rbac_permission("retail.ticket.update")()]

    def post(self, request, ticket_id: int):
        serializer = TicketLineCreateIn(data=request.data)
        serializer.is_valid(raise_exception=True)
        v = serializer.validated_data
        try:
            result = add_line(
                request=request,
                actor=request.user,
                ticket_id=ticket_id,
                expected_version=v["expected_version"],
                item_id=v["item_id"],
                qty=v["qty"],
                unit_price=v.get("unit_price"),
                discount_amount=v.get("discount_amount"),
            )
        except Exception as exc:  # noqa: BLE001
            payload, code = _mutation_error_payload(request=request, exc=exc)
            return Response(payload, status=code)
        return Response(_ticket_payload(result.ticket), status=status.HTTP_201_CREATED)

    def patch(self, request, ticket_id: int, line_id: int):
        serializer = TicketLinePatchIn(data=request.data)
        serializer.is_valid(raise_exception=True)
        v = serializer.validated_data
        try:
            result = update_line(
                request=request,
                actor=request.user,
                ticket_id=ticket_id,
                line_id=line_id,
                expected_version=v["expected_version"],
                qty=v.get("qty"),
                unit_price=v.get("unit_price"),
                discount_amount=v.get("discount_amount"),
            )
        except Exception as exc:  # noqa: BLE001
            payload, code = _mutation_error_payload(request=request, exc=exc)
            return Response(payload, status=code)
        return Response(_ticket_payload(result.ticket), status=status.HTTP_200_OK)

    def delete(self, request, ticket_id: int, line_id: int):
        serializer = TicketLineDeleteIn(data=request.data or request.query_params)
        serializer.is_valid(raise_exception=True)
        try:
            ticket = remove_line(
                request=request,
                actor=request.user,
                ticket_id=ticket_id,
                line_id=line_id,
                expected_version=serializer.validated_data["expected_version"],
            )
        except Exception as exc:  # noqa: BLE001
            payload, code = _mutation_error_payload(request=request, exc=exc)
            return Response(payload, status=code)
        ticket = RetailTicket.objects.select_related("terminal", "cash_session", "payment_intent", "billing_doc").get(id=ticket.id)
        return Response(_ticket_payload(ticket), status=status.HTTP_200_OK)


class TicketHoldView(APIView):
    permission_classes = [rbac_permission("retail.ticket.hold")]

    def post(self, request, ticket_id: int):
        serializer = TicketHoldIn(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            hold = hold_ticket(
                request=request,
                actor=request.user,
                ticket_id=ticket_id,
                expected_version=serializer.validated_data["expected_version"],
                reason=serializer.validated_data.get("reason", "") or "",
            )
        except Exception as exc:  # noqa: BLE001
            payload, code = _mutation_error_payload(request=request, exc=exc)
            return Response(payload, status=code)
        hold = RetailHold.objects.select_related("ticket__terminal", "ticket__cash_session").get(id=hold.id)
        return Response(_serialize_hold(hold), status=status.HTTP_201_CREATED)


class HoldResumeView(APIView):
    permission_classes = [rbac_permission("retail.ticket.hold")]

    def post(self, request, hold_id: int):
        try:
            hold = resume_hold(request=request, actor=request.user, hold_id=hold_id)
        except Exception as exc:  # noqa: BLE001
            payload, code = _mutation_error_payload(request=request, exc=exc)
            return Response(payload, status=code)
        hold = RetailHold.objects.select_related("ticket__terminal", "ticket__cash_session").get(id=hold.id)
        return Response(_serialize_hold(hold), status=status.HTTP_200_OK)


class HoldActiveListView(APIView):
    permission_classes = [rbac_permission("retail.pos.use")]

    def get(self, request):
        holds = list_active_holds(request=request)
        limit, offset = get_limit_offset(request, default_limit=20, max_limit=100)
        total = len(holds)
        rows = holds[offset : offset + limit]
        return Response(
            {"count": total, "limit": limit, "offset": offset, "results": [_serialize_hold(row) for row in rows]},
            status=status.HTTP_200_OK,
        )


class TicketRecentListView(APIView):
    permission_classes = [rbac_permission("retail.pos.use")]

    def get(self, request):
        limit, offset = get_limit_offset(request, default_limit=20, max_limit=100)
        rows = recent_tickets(request=request, limit=offset + limit)
        results = [_ticket_payload(ticket) for ticket in rows[offset : offset + limit]]
        return Response(
            {"count": len(rows), "limit": limit, "offset": offset, "results": results},
            status=status.HTTP_200_OK,
        )


class TicketCheckoutPreviewView(APIView):
    permission_classes = [rbac_permission("retail.ticket.checkout")]

    def post(self, request, ticket_id: int):
        serializer = TicketCheckoutPreviewIn(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            preview = preview_checkout(request=request, ticket_id=ticket_id)
        except Exception as exc:  # noqa: BLE001
            payload, code = _mutation_error_payload(request=request, exc=exc)
            return Response(payload, status=code)
        return Response(_preview_payload(preview), status=status.HTTP_200_OK)


class TicketCheckoutCommitView(APIView):
    permission_classes = [rbac_permission("retail.ticket.checkout")]

    def post(self, request, ticket_id: int):
        serializer = TicketCheckoutCommitIn(data=request.data)
        serializer.is_valid(raise_exception=True)
        v = serializer.validated_data
        try:
            result = commit_checkout(
                request=request,
                actor=request.user,
                ticket_id=ticket_id,
                expected_version=v["expected_version"],
                idempotency_key=v["idempotency_key"],
                cash_received=v["cash_received"],
            )
        except Exception as exc:  # noqa: BLE001
            payload, code = _mutation_error_payload(request=request, exc=exc)
            return Response(payload, status=code)
        return Response(result, status=status.HTTP_200_OK)


class TicketVoidView(APIView):
    permission_classes = [rbac_permission("retail.ticket.void")]

    def post(self, request, ticket_id: int):
        serializer = TicketVoidIn(data=request.data)
        serializer.is_valid(raise_exception=True)
        v = serializer.validated_data
        try:
            sale, replayed = void_sale(
                request=request,
                actor=request.user,
                ticket_id=ticket_id,
                expected_version=v["expected_version"],
                idempotency_key=v["idempotency_key"],
                reason=v.get("reason", "") or "",
            )
        except Exception as exc:  # noqa: BLE001
            payload, code = _mutation_error_payload(request=request, exc=exc)
            return Response(payload, status=code)
        sale = RetailSale.objects.select_related("ticket", "billing_doc", "payment_intent", "cash_movement").get(id=sale.id)
        payload = _serialize_sale(sale)
        payload["idempotency_replayed"] = bool(replayed)
        return Response(payload, status=status.HTTP_200_OK)


class RetailReturnListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("retail.return.create")()]
        return [rbac_permission("retail.sale.read")()]

    def post(self, request):
        serializer = RetailReturnCreateIn(data=request.data)
        serializer.is_valid(raise_exception=True)
        v = serializer.validated_data
        try:
            result, replayed = create_return(
                request=request,
                actor=request.user,
                sale_id=v["sale_id"],
                reason=v.get("reason", "") or "",
                idempotency_key=v["idempotency_key"],
                lines=v["lines"],
            )
        except Exception as exc:  # noqa: BLE001
            payload, code = _mutation_error_payload(request=request, exc=exc)
            return Response(payload, status=code)
        result = RetailReturn.objects.select_related(
            "original_sale",
            "return_ticket__terminal",
            "return_ticket__cash_session",
            "refund_payment_intent",
            "refund_cash_movement",
        ).get(id=result.id)
        payload = _serialize_return(result)
        payload["idempotency_replayed"] = bool(replayed)
        return Response(payload, status=status.HTTP_201_CREATED)


class RetailReturnDetailView(APIView):
    permission_classes = [rbac_permission("retail.sale.read")]

    def get(self, request, return_id: int):
        result = get_object_or_404(
            RetailReturn.objects.select_related(
                "original_sale",
                "return_ticket__terminal",
                "return_ticket__cash_session",
                "refund_payment_intent",
                "refund_cash_movement",
            ),
            id=int(return_id),
            branch=request.branch,
        )
        return Response(_serialize_return(result), status=status.HTTP_200_OK)


class CompensationRetryView(APIView):
    permission_classes = [rbac_permission("retail.compensation.retry")]

    def post(self, request, sale_id: int):
        serializer = RetailCompensationRetryIn(data=request.data)
        serializer.is_valid(raise_exception=True)
        v = serializer.validated_data
        try:
            sale, replayed = retry_compensation(
                request=request,
                actor=request.user,
                sale_id=sale_id,
                idempotency_key=v["idempotency_key"],
                reason=v.get("reason", "") or "",
            )
        except Exception as exc:  # noqa: BLE001
            payload, code = _mutation_error_payload(request=request, exc=exc)
            return Response(payload, status=code)
        sale = RetailSale.objects.select_related("ticket", "billing_doc", "payment_intent", "cash_movement").get(id=sale.id)
        payload = _serialize_sale(sale)
        payload["idempotency_replayed"] = bool(replayed)
        return Response(payload, status=status.HTTP_200_OK)
