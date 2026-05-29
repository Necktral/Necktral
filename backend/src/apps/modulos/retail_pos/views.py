from __future__ import annotations

from decimal import Decimal

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.pagination import get_limit_offset, paginate_queryset
from apps.modulos.common.permissions import rbac_permission

from .models import PosSession, PosTicket
from .serializers import (
    PosEdgeChallengeCreateIn,
    PosEdgeHandshakeIn,
    PosPeripheralStatusUpsertIn,
    PosTicketCompensateRetryIn,
    PosSessionCloseIn,
    PosSessionOpenIn,
    PosTicketCheckoutIn,
    PosTicketOpenIn,
    PosTicketOut,
    PosTicketVoidIn,
)
from .services import (
    close_pos_session,
    checkout_ticket,
    get_peripheral_capabilities,
    get_current_pos_session,
    get_operational_cockpit,
    handshake_edge_connector,
    issue_edge_challenge,
    open_pos_session,
    open_ticket,
    retry_ticket_compensation,
    upsert_peripheral_status,
    void_ticket,
)


POS_ERROR_COMPENSATION_PENDING = "POS_COMPENSATION_PENDING"
POS_ERROR_SCHEMA_INVALID = "POS_SCHEMA_INVALID"
POS_ERROR_INVALID_SCOPE = "POS_INVALID_SCOPE"


def _error_payload(*, code: str, detail: str = "", **extra) -> dict:
    payload = {
        "detail": code,
        "error_code": code,
    }
    if detail:
        payload["error_message"] = detail
    payload.update(extra)
    return payload


def _scope_not_found_payload(*, entity: str) -> dict:
    return _error_payload(code=POS_ERROR_INVALID_SCOPE, detail=f"{entity} fuera de alcance", entity=entity)


def _ticket_to_dict(ticket: PosTicket) -> dict:
    ticket = (
        PosTicket.objects.select_related("session", "shift", "customer_party", "sale", "payment_intent", "cash_movement")
        .prefetch_related("lines")
        .get(id=ticket.id)
    )
    payment_intent = ticket.payment_intent
    customer_party = ticket.customer_party
    return {
        "id": int(ticket.id),
        "status": str(ticket.status),
        "session_id": int(ticket.session_id),
        "shift_id": int(ticket.shift_id),
        "external_ref": str(ticket.external_ref or ""),
        "correlation_id": str(ticket.correlation_id or ""),
        "sale_type": str(ticket.sale_type),
        "payment_method": str(ticket.payment_method),
        "total_amount": str(ticket.total_amount),
        "customer_name": str(ticket.customer_name or ""),
        "customer_ref": str(ticket.customer_ref or ""),
        "customer_party_id": int(ticket.customer_party_id) if ticket.customer_party_id else None,
        "customer_party_display_name": str(customer_party.display_name) if customer_party else "",
        "sale_id": int(ticket.sale_id) if ticket.sale_id else None,
        "payment_intent_id": str(payment_intent.payment_id) if payment_intent else "",
        "cash_movement_id": int(ticket.cash_movement_id) if ticket.cash_movement_id else None,
        "created_at": ticket.created_at,
        "updated_at": ticket.updated_at,
        "checkout_started_at": ticket.checkout_started_at,
        "paid_at": ticket.paid_at,
        "closed_at": ticket.closed_at,
        "voided_at": ticket.voided_at,
        "void_reason": str(ticket.void_reason or ""),
        "last_error": str(ticket.last_error or ""),
        "compensation_pending": bool(ticket.compensation_pending),
        "compensation_attempts": int(ticket.compensation_attempts),
        "compensation_last_error": str(ticket.compensation_last_error or ""),
        "compensation_next_retry_at": ticket.compensation_next_retry_at,
        "last_compensation_at": ticket.last_compensation_at,
        "lines": [
            {
                "id": int(line.id),
                "line_no": int(line.line_no),
                "line_type": str(line.line_type),
                "product": str(line.product),
                "volume": str(line.volume),
                "volume_uom": str(line.volume_uom),
                "unit_price_entered": str(line.unit_price_entered),
                "unit_price_uom": str(line.unit_price_uom),
                "amount_estimated": str(line.amount_estimated),
                "metadata": line.metadata or {},
            }
            for line in ticket.lines.order_by("line_no", "id")
        ],
    }


class HealthView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"ok": True, "module": "retail_pos"}, status=status.HTTP_200_OK)


class PosSessionCurrentView(APIView):
    permission_classes = [rbac_permission("retail.pos.session.read")]

    def get(self, request):
        session = get_current_pos_session(company=request.company, branch=request.branch)
        if session is None:
            return Response({"session": None}, status=status.HTTP_200_OK)
        return Response(
            {
                "session": {
                    "id": int(session.id),
                    "status": str(session.status),
                    "cash_session_id": int(session.cash_session_id) if session.cash_session_id else None,
                    "opened_at": session.opened_at,
                    "opened_by": int(session.opened_by_id),
                    "opening_amount": str(session.opening_amount),
                    "note": str(session.note or ""),
                }
            },
            status=status.HTTP_200_OK,
        )


class PosSessionOpenView(APIView):
    permission_classes = [rbac_permission("retail.pos.session.open")]

    def post(self, request):
        ser = PosSessionOpenIn(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        result = open_pos_session(
            request=request,
            actor_user=request.user,
            opening_amount=Decimal(v.get("opening_amount") or "0.00"),
            note=v.get("note", "") or "",
        )
        body = {
            "id": int(result.session.id),
            "status": str(result.session.status),
            "cash_session_id": int(result.session.cash_session_id) if result.session.cash_session_id else None,
            "opening_amount": str(result.session.opening_amount),
            "opened_at": result.session.opened_at,
        }
        if result.duplicate:
            body["idempotency_status"] = "DUPLICATE_PROCESSED"
            return Response(body, status=status.HTTP_200_OK)
        return Response(body, status=status.HTTP_201_CREATED)


class PosSessionCloseView(APIView):
    permission_classes = [rbac_permission("retail.pos.session.close")]

    def post(self, request, session_id: int):
        ser = PosSessionCloseIn(data=request.data)
        ser.is_valid(raise_exception=True)
        session = PosSession.objects.filter(id=session_id, company=request.company, branch=request.branch).first()
        if session is None:
            return Response(_scope_not_found_payload(entity="session"), status=status.HTTP_404_NOT_FOUND)
        try:
            out = close_pos_session(
                request=request,
                actor_user=request.user,
                session=session,
                counted_amount=Decimal(ser.validated_data["counted_amount"]),
                note=ser.validated_data.get("note", "") or "",
            )
        except ValueError as exc:
            return Response(
                _error_payload(code=POS_ERROR_SCHEMA_INVALID, detail=str(exc)),
                status=status.HTTP_409_CONFLICT,
            )
        return Response(
            {
                "id": int(out.id),
                "status": str(out.status),
                "counted_amount": str(out.counted_amount),
                "difference_amount": str(out.difference_amount),
                "closed_at": out.closed_at,
            },
            status=status.HTTP_200_OK,
        )


class PosTicketListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [rbac_permission("retail.pos.ticket.read")()]
        return [rbac_permission("retail.pos.ticket.open")()]

    def get(self, request):
        qs = PosTicket.objects.filter(company=request.company, branch=request.branch).order_by("-created_at", "-id")
        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        results = [_ticket_to_dict(row) for row in rows]
        return Response(
            {
                "count": int(total),
                "limit": int(limit),
                "offset": int(offset),
                "results": results,
            },
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        ser = PosTicketOpenIn(data=request.data)
        ser.is_valid(raise_exception=True)

        session = get_current_pos_session(company=request.company, branch=request.branch)
        if session is None:
            return Response(
                _error_payload(code=POS_ERROR_SCHEMA_INVALID, detail="No hay sesión POS abierta."),
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            out = open_ticket(
                request=request,
                actor_user=request.user,
                session=session,
                shift_id=int(ser.validated_data["shift_id"]),
                idempotency_key=str(ser.validated_data.get("idempotency_key") or ""),
                external_ref=str(ser.validated_data.get("external_ref") or ""),
                customer_name=str(ser.validated_data.get("customer_name") or ""),
                customer_ref=str(ser.validated_data.get("customer_ref") or ""),
                customer_party_id=ser.validated_data.get("customer_party_id"),
                sale_type=str(ser.validated_data.get("sale_type")),
                payment_method=str(ser.validated_data.get("payment_method")),
            )
        except ValueError as exc:
            return Response(
                _error_payload(code=POS_ERROR_SCHEMA_INVALID, detail=str(exc)),
                status=status.HTTP_400_BAD_REQUEST,
            )
        payload = _ticket_to_dict(out.ticket)
        PosTicketOut(data=payload).is_valid(raise_exception=True)
        if out.duplicate:
            payload["idempotency_status"] = "DUPLICATE_PROCESSED"
            return Response(payload, status=status.HTTP_200_OK)
        return Response(payload, status=status.HTTP_201_CREATED)


class PosTicketCheckoutView(APIView):
    permission_classes = [rbac_permission("retail.pos.ticket.checkout")]

    def post(self, request, ticket_id: int):
        ser = PosTicketCheckoutIn(data=request.data)
        ser.is_valid(raise_exception=True)

        ticket = PosTicket.objects.filter(id=ticket_id, company=request.company, branch=request.branch).first()
        if ticket is None:
            return Response(_scope_not_found_payload(entity="ticket"), status=status.HTTP_404_NOT_FOUND)
        line_payload = ser.validated_data.get("line")
        try:
            out = checkout_ticket(
                request=request,
                actor_user=request.user,
                ticket=ticket,
                line_payload=dict(line_payload) if line_payload else None,
            )
        except ValueError as exc:
            return Response(
                _error_payload(code=POS_ERROR_SCHEMA_INVALID, detail=str(exc)),
                status=status.HTTP_409_CONFLICT,
            )
        if out.status != "CLOSED":
            return Response(
                _error_payload(
                    code=POS_ERROR_COMPENSATION_PENDING,
                    detail=str(out.last_error or ""),
                    ticket_status=str(out.status),
                    compensation_pending=bool(out.compensation_pending),
                    compensation_attempts=int(out.compensation_attempts),
                ),
                status=status.HTTP_409_CONFLICT,
            )

        payload = _ticket_to_dict(out)
        PosTicketOut(data=payload).is_valid(raise_exception=True)
        return Response(payload, status=status.HTTP_200_OK)


class PosTicketVoidView(APIView):
    permission_classes = [rbac_permission("retail.pos.ticket.void")]

    def post(self, request, ticket_id: int):
        ser = PosTicketVoidIn(data=request.data)
        ser.is_valid(raise_exception=True)

        ticket = PosTicket.objects.filter(id=ticket_id, company=request.company, branch=request.branch).first()
        if ticket is None:
            return Response(_scope_not_found_payload(entity="ticket"), status=status.HTTP_404_NOT_FOUND)
        try:
            out = void_ticket(
                request=request,
                actor_user=request.user,
                ticket=ticket,
                reason=str(ser.validated_data.get("reason") or "VOID"),
            )
        except ValueError as exc:
            return Response(
                _error_payload(code=POS_ERROR_SCHEMA_INVALID, detail=str(exc)),
                status=status.HTTP_409_CONFLICT,
            )
        payload = _ticket_to_dict(out)
        PosTicketOut(data=payload).is_valid(raise_exception=True)
        return Response(payload, status=status.HTTP_200_OK)


class PosTicketCompensationRetryView(APIView):
    permission_classes = [rbac_permission("retail.pos.ticket.checkout")]

    def post(self, request, ticket_id: int):
        ser = PosTicketCompensateRetryIn(data=request.data)
        ser.is_valid(raise_exception=True)

        ticket = PosTicket.objects.filter(id=ticket_id, company=request.company, branch=request.branch).first()
        if ticket is None:
            return Response(_scope_not_found_payload(entity="ticket"), status=status.HTTP_404_NOT_FOUND)
        try:
            out = retry_ticket_compensation(
                request=request,
                actor_user=request.user,
                ticket=ticket,
                reason=str(ser.validated_data.get("reason") or "MANUAL_RETRY"),
            )
        except ValueError as exc:
            return Response(
                _error_payload(code=POS_ERROR_SCHEMA_INVALID, detail=str(exc)),
                status=status.HTTP_409_CONFLICT,
            )
        if out.status != "CLOSED":
            return Response(
                _error_payload(
                    code=POS_ERROR_COMPENSATION_PENDING,
                    detail=str(out.last_error or ""),
                    ticket_status=str(out.status),
                    compensation_pending=bool(out.compensation_pending),
                    compensation_attempts=int(out.compensation_attempts),
                ),
                status=status.HTTP_409_CONFLICT,
            )

        payload = _ticket_to_dict(out)
        PosTicketOut(data=payload).is_valid(raise_exception=True)
        return Response(payload, status=status.HTTP_200_OK)


class PosPeripheralStatusView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [rbac_permission("retail.pos.peripherals.read")()]
        return [rbac_permission("retail.pos.peripherals.manage")()]

    def get(self, request):
        rows = (
            request.company.pos_peripherals_company.filter(branch=request.branch)
            .order_by("device_kind", "device_key")
            .values(
                "id",
                "connector_id",
                "connector_version",
                "device_key",
                "device_kind",
                "capability_level",
                "status",
                "last_seen_at",
                "edge_session_id",
                "metadata",
            )
        )
        results = [dict(row) for row in rows]
        return Response({"count": len(results), "results": results}, status=status.HTTP_200_OK)

    def post(self, request):
        ser = PosPeripheralStatusUpsertIn(data=request.data)
        ser.is_valid(raise_exception=True)
        row = upsert_peripheral_status(
            request=request,
            actor_user=request.user,
            payload=dict(ser.validated_data),
        )
        return Response(
            {
                "id": int(row.id),
                "device_key": row.device_key,
                "device_kind": row.device_kind,
                "status": row.status,
                "capability_level": row.capability_level,
                "last_seen_at": row.last_seen_at,
                "edge_session_id": int(row.edge_session_id) if row.edge_session_id else None,
            },
            status=status.HTTP_200_OK,
        )


def _edge_error_status(code: str) -> int:
    if code == "BAD_SIGNATURE":
        return status.HTTP_401_UNAUTHORIZED
    if code == "CHALLENGE_NOT_FOUND":
        return status.HTTP_404_NOT_FOUND
    if code in {"REPLAY_DETECTED", "CHALLENGE_EXPIRED", "CHALLENGE_CONNECTOR_MISMATCH"}:
        return status.HTTP_409_CONFLICT
    if code == "EDGE_SHARED_SECRET_NOT_CONFIGURED":
        return status.HTTP_503_SERVICE_UNAVAILABLE
    return status.HTTP_400_BAD_REQUEST


class PosPeripheralEdgeChallengeView(APIView):
    permission_classes = [rbac_permission("retail.pos.peripherals.manage")]

    def post(self, request):
        ser = PosEdgeChallengeCreateIn(data=request.data)
        ser.is_valid(raise_exception=True)
        v = ser.validated_data
        out = issue_edge_challenge(
            request=request,
            actor_user=request.user,
            connector_id=str(v["connector_id"]),
            connector_version=str(v.get("connector_version") or ""),
            metadata=dict(v.get("metadata") or {}),
        )
        challenge = out.challenge
        return Response(
            {
                "challenge_id": str(challenge.challenge_id),
                "nonce": str(challenge.nonce),
                "connector_id": str(challenge.connector_id),
                "connector_version": str(challenge.connector_version or ""),
                "issued_at": challenge.issued_at,
                "expires_at": challenge.expires_at,
            },
            status=status.HTTP_201_CREATED,
        )


class PosPeripheralEdgeHandshakeView(APIView):
    permission_classes = [rbac_permission("retail.pos.peripherals.manage")]

    def post(self, request):
        ser = PosEdgeHandshakeIn(data=request.data)
        ser.is_valid(raise_exception=True)
        try:
            out = handshake_edge_connector(
                request=request,
                actor_user=request.user,
                payload=dict(ser.validated_data),
            )
        except ValueError as exc:
            code = str(exc)
            return Response(
                {"detail": code, "error_code": code},
                status=_edge_error_status(code),
            )
        session = out.session
        return Response(
            {
                "session_id": int(session.id),
                "session_token": str(session.session_token),
                "connector_id": str(session.connector_id),
                "connector_version": str(session.connector_version or ""),
                "status": str(session.status),
                "issued_at": session.issued_at,
                "expires_at": session.expires_at,
                "devices_synced": int(out.devices_synced),
                "capability_registry": dict(session.capability_registry or {}),
            },
            status=status.HTTP_201_CREATED,
        )


class PosPeripheralCapabilitiesView(APIView):
    permission_classes = [rbac_permission("retail.pos.peripherals.read")]

    def get(self, request):
        out = get_peripheral_capabilities(company=request.company, branch=request.branch)
        return Response(out, status=status.HTTP_200_OK)


class PosOperationalCockpitView(APIView):
    permission_classes = [rbac_permission("retail.pos.ticket.read")]

    def get(self, request):
        data = get_operational_cockpit(company=request.company, branch=request.branch)
        return Response(data, status=status.HTTP_200_OK)
