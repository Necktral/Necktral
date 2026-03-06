from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import rbac_permission
from apps.iam.models import OrgUnit

from .models import InventoryItem, StockBalance, Warehouse
from .serializers import (
    InventoryItemOut,
    ItemCreateSerializer,
    MovementAdjustSerializer,
    MovementIssueSerializer,
    MovementReceiveSerializer,
    TransferSerializer,
    WarehouseCreateSerializer,
)
from .services import create_item, post_adjust, post_issue, post_receive, post_transfer


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

        item = create_item(
            request=request,
            company=company,
            actor_user=request.user,
            sku=v["sku"],
            name=v["name"],
            uom=v.get("uom") or "UNIT",
        )
        return Response(InventoryItemOut(item).data, status=status.HTTP_201_CREATED)


class ReceiveView(APIView):
    permission_classes = [rbac_permission("inventory.movement.receive")]

    def post(self, request):
        if not getattr(request, "branch", None):
            return Response({"detail": "X-Branch-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)
        s = MovementReceiveSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

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
        return Response(
            {"movement_id": r.movement_id, "qty_on_hand": str(r.qty_on_hand), "avg_cost": str(r.avg_cost)},
            status=status.HTTP_201_CREATED,
        )


class IssueView(APIView):
    permission_classes = [rbac_permission("inventory.movement.issue")]

    def post(self, request):
        if not getattr(request, "branch", None):
            return Response({"detail": "X-Branch-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)
        s = MovementIssueSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

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
        return Response(
            {"movement_id": r.movement_id, "qty_on_hand": str(r.qty_on_hand), "avg_cost": str(r.avg_cost)},
            status=status.HTTP_201_CREATED,
        )


class AdjustView(APIView):
    permission_classes = [rbac_permission("inventory.movement.adjust")]

    def post(self, request):
        if not getattr(request, "branch", None):
            return Response({"detail": "X-Branch-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)
        s = MovementAdjustSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        r = post_adjust(
            request=request,
            actor=request.user,
            warehouse_id=v["warehouse_id"],
            item_id=v["item_id"],
            new_qty_on_hand=v["new_qty_on_hand"],
            idempotency_key=v.get("idempotency_key", "") or "",
            note=v.get("note", "") or "",
        )
        return Response(
            {"movement_id": r.movement_id, "qty_on_hand": str(r.qty_on_hand), "avg_cost": str(r.avg_cost)},
            status=status.HTTP_201_CREATED,
        )


class TransferView(APIView):
    permission_classes = [rbac_permission("inventory.transfer.create")]

    def post(self, request):
        if not getattr(request, "branch", None):
            return Response({"detail": "X-Branch-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)
        s = TransferSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

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
