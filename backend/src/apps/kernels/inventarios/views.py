from __future__ import annotations

from django.db.models import Q
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.permissions import rbac_permission
from apps.modulos.iam.models import OrgUnit

from .models import InventoryItem, StockBalance, StockMovement, Warehouse
from .serializers import (
    InventoryItemsQuerySerializer,
    InventoryMovementOut,
    InventoryMovementsQuerySerializer,
    InventoryItemOut,
    ItemCreateSerializer,
    MovementAdjustSerializer,
    MovementIssueSerializer,
    MovementReceiveSerializer,
    TransferSerializer,
    WarehouseCreateSerializer,
    WarehouseOut,
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
    def get_permissions(self):
        if self.request.method == "GET":
            return [rbac_permission("inventory.balance.read")()]
        return [rbac_permission("inventory.warehouse.create")()]

    def get(self, request):
        company: OrgUnit = request.company
        branch: OrgUnit | None = getattr(request, "branch", None)
        if not branch:
            return Response({"detail": "X-Branch-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)

        rows = Warehouse.objects.filter(company=company, branch=branch, is_active=True).order_by("name", "id")
        return Response(WarehouseOut(rows, many=True).data, status=status.HTTP_200_OK)

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
    def get_permissions(self):
        if self.request.method == "GET":
            return [rbac_permission("inventory.item.read")()]
        return [rbac_permission("inventory.item.create")()]

    def get(self, request):
        company: OrgUnit = request.company
        query = InventoryItemsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data

        rows = InventoryItem.objects.filter(company=company, is_active=True)
        q = str(params.get("q") or "").strip()
        if q:
            rows = rows.filter(Q(sku__icontains=q) | Q(name__icontains=q))

        limit = min(int(params.get("limit") or 20), 50)
        rows = rows.order_by("name", "id")[:limit]
        return Response(InventoryItemOut(rows, many=True).data, status=status.HTTP_200_OK)

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


class MovementsHistoryView(APIView):
    permission_classes = [rbac_permission("inventory.balance.read")]

    def get(self, request):
        company: OrgUnit = request.company
        branch: OrgUnit | None = getattr(request, "branch", None)
        if not branch:
            return Response({"detail": "X-Branch-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)

        query = InventoryMovementsQuerySerializer(data=request.query_params)
        query.is_valid(raise_exception=True)
        params = query.validated_data

        wh = get_object_or_404(
            Warehouse,
            id=int(params["warehouse_id"]),
            company=company,
            branch=branch,
            is_active=True,
        )
        item = get_object_or_404(InventoryItem, id=int(params["item_id"]), company=company, is_active=True)
        limit = min(int(params.get("limit") or 20), 50)

        rows = (
            StockMovement.objects.filter(company=company, branch=branch, warehouse=wh, item=item)
            .order_by("-created_at", "-id")[:limit]
        )
        return Response(InventoryMovementOut(rows, many=True).data, status=status.HTTP_200_OK)


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
