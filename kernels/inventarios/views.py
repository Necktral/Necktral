from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.permissions import rbac_permission
from apps.modulos.iam.models import OrgUnit

from .models import InventoryItem, StockBalance, StockMovement, Warehouse
from .serializers import (
    InventoryItemOut,
    ItemCreateSerializer,
    LedgerQuerySerializer,
    MovementAdjustSerializer,
    MovementIssueSerializer,
    MovementReceiveSerializer,
    TransferSerializer,
    WarehouseCreateSerializer,
)
from .services import create_item, post_adjust, post_issue, post_receive, post_transfer


def _movement_post_response(result) -> dict:
    return {
        "movement_id": result.movement_id,
        "qty_on_hand": str(result.qty_on_hand),
        "avg_cost": str(result.avg_cost),
        "accounting_status": result.accounting_status,
        "accounting_error": result.accounting_error,
        "journal_draft_id": result.accounting_journal_draft_id,
        "journal_entry_id": result.accounting_journal_entry_id,
    }


class HealthView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"ok": True, "module": "inventory"}, status=status.HTTP_200_OK)


class WarehouseCreateView(APIView):
    permission_classes = [rbac_permission("inventory.warehouse.create")]

    def post(self, request):
        company: OrgUnit = request.company
        branch: OrgUnit | None = getattr(request, "branch", None)
        if not branch:
            return Response({"detail": "X-Branch-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)

        s = WarehouseCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        wh = Warehouse.objects.create(
            company=company,
            branch=branch,
            name=v["name"],
            code=v.get("code", "") or "",
            is_active=True,
        )
        return Response({"id": wh.id}, status=status.HTTP_201_CREATED)


class ItemCreateView(APIView):
    permission_classes = [rbac_permission("inventory.item.create")]

    def post(self, request):
        company: OrgUnit = request.company

        s = ItemCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        try:
            item = create_item(
                request=request,
                company=company,
                actor_user=request.user,
                sku=v["sku"],
                name=v["name"],
                uom=v.get("uom") or "UNIT",
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(InventoryItemOut(item).data, status=status.HTTP_201_CREATED)


class ReceiveView(APIView):
    permission_classes = [rbac_permission("inventory.movement.receive")]

    def post(self, request):
        if not getattr(request, "branch", None):
            return Response({"detail": "X-Branch-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)
        s = MovementReceiveSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        try:
            r = post_receive(
                request=request,
                actor=request.user,
                warehouse_id=v["warehouse_id"],
                item_id=v["item_id"],
                qty=v["qty"],
                unit_cost=v["unit_cost"],
                idempotency_key=v.get("idempotency_key", "") or "",
                note=v.get("note", "") or "",
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_movement_post_response(r), status=status.HTTP_201_CREATED)


class IssueView(APIView):
    permission_classes = [rbac_permission("inventory.movement.issue")]

    def post(self, request):
        if not getattr(request, "branch", None):
            return Response({"detail": "X-Branch-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)
        s = MovementIssueSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        try:
            r = post_issue(
                request=request,
                actor=request.user,
                warehouse_id=v["warehouse_id"],
                item_id=v["item_id"],
                qty=v["qty"],
                allow_negative=bool(v.get("allow_negative", False)),
                idempotency_key=v.get("idempotency_key", "") or "",
                note=v.get("note", "") or "",
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_movement_post_response(r), status=status.HTTP_201_CREATED)


class AdjustView(APIView):
    permission_classes = [rbac_permission("inventory.movement.adjust")]

    def post(self, request):
        if not getattr(request, "branch", None):
            return Response({"detail": "X-Branch-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)
        s = MovementAdjustSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        try:
            r = post_adjust(
                request=request,
                actor=request.user,
                warehouse_id=v["warehouse_id"],
                item_id=v["item_id"],
                new_qty_on_hand=v["new_qty_on_hand"],
                idempotency_key=v.get("idempotency_key", "") or "",
                note=v.get("note", "") or "",
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(_movement_post_response(r), status=status.HTTP_201_CREATED)


class TransferView(APIView):
    permission_classes = [rbac_permission("inventory.transfer.create")]

    def post(self, request):
        if not getattr(request, "branch", None):
            return Response({"detail": "X-Branch-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)
        s = TransferSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        try:
            out = post_transfer(
                request=request,
                actor=request.user,
                from_warehouse_id=v["from_warehouse_id"],
                to_warehouse_id=v["to_warehouse_id"],
                item_id=v["item_id"],
                qty=v["qty"],
                idempotency_key=v.get("idempotency_key", "") or "",
                note=v.get("note", "") or "",
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(out, status=status.HTTP_201_CREATED)


class BalanceView(APIView):
    permission_classes = [rbac_permission("inventory.balance.read")]

    def get(self, request):
        company: OrgUnit = request.company
        branch: OrgUnit | None = getattr(request, "branch", None)
        if not branch:
            return Response({"detail": "X-Branch-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)

        warehouse_id = request.query_params.get("warehouse_id")
        item_id = request.query_params.get("item_id")
        if not warehouse_id or not item_id:
            return Response({"detail": "warehouse_id and item_id are required"}, status=status.HTTP_400_BAD_REQUEST)

        wh = get_object_or_404(Warehouse, id=int(warehouse_id), company=company, branch=branch)
        item = get_object_or_404(InventoryItem, id=int(item_id), company=company)

        bal = StockBalance.objects.filter(company=company, branch=branch, warehouse=wh, item=item).first()
        if not bal:
            return Response({"qty_on_hand": "0.0000", "avg_cost": "0.000000"}, status=status.HTTP_200_OK)

        return Response({"qty_on_hand": str(bal.qty_on_hand), "avg_cost": str(bal.avg_cost)}, status=status.HTTP_200_OK)


class LedgerView(APIView):
    permission_classes = [rbac_permission("inventory.balance.read")]

    def get(self, request):
        company: OrgUnit = request.company
        branch: OrgUnit | None = getattr(request, "branch", None)
        if not branch:
            return Response({"detail": "X-Branch-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)

        serializer = LedgerQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        filters = serializer.validated_data

        page = int(filters.get("page", 1))
        page_size = min(int(filters.get("page_size", 50)), 100)
        offset = (page - 1) * page_size

        qs = StockMovement.objects.filter(company=company, branch=branch)

        warehouse_id = filters.get("warehouse_id")
        if warehouse_id is not None:
            qs = qs.filter(warehouse_id=int(warehouse_id))

        item_id = filters.get("item_id")
        if item_id is not None:
            qs = qs.filter(item_id=int(item_id))

        movement_type = (filters.get("movement_type") or "").strip().upper()
        if movement_type:
            valid_types = {choice[0] for choice in StockMovement._meta.get_field("movement_type").choices}
            if movement_type not in valid_types:
                return Response({"detail": "movement_type inválido"}, status=status.HTTP_400_BAD_REQUEST)
            qs = qs.filter(movement_type=movement_type)

        total = qs.count()
        rows = list(qs.order_by("-created_at", "-id")[offset : offset + page_size])

        items = [
            {
                "id": row.id,
                "created_at": row.created_at.isoformat(),
                "movement_type": row.movement_type,
                "warehouse_id": row.warehouse_id,
                "item_id": row.item_id,
                "qty_delta": str(row.qty_delta),
                "unit_cost": str(row.unit_cost),
                "total_cost": str(row.total_cost),
                "source_module": row.source_module,
                "source_type": row.source_type,
                "source_id": row.source_id,
                "note": row.note,
                "idempotency_key": row.idempotency_key,
                "accounting_status": row.accounting_status,
                "accounting_error": row.accounting_error,
                "journal_draft_id": row.accounting_journal_draft_id,
                "journal_entry_id": row.accounting_journal_entry_id,
            }
            for row in rows
        ]

        return Response(
            {
                "page": page,
                "page_size": page_size,
                "total": total,
                "has_next": (offset + page_size) < total,
                "has_prev": page > 1,
                "items": items,
            },
            status=status.HTTP_200_OK,
        )
