from __future__ import annotations

from typing import Any

from django.db import IntegrityError
from django.db.models import Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.permissions import rbac_permission
from apps.modulos.iam.models import OrgUnit

from .models import (
    InventoryBrand,
    InventoryCategory,
    InventoryItem,
    InventoryTaxProfile,
    StockBalance,
    StockMovement,
    Warehouse,
)
from .serializers import (
    BalanceListQuerySerializer,
    BrandCreateSerializer,
    BrandOut,
    CategoryCreateSerializer,
    CategoryOut,
    InventoryCommandBatchIn,
    InventoryLookupQuerySerializer,
    InventoryItemOut,
    ItemCreateSerializer,
    ItemListQuerySerializer,
    ItemPatchSerializer,
    LedgerQuerySerializer,
    MovementAdjustSerializer,
    MovementIssueSerializer,
    MovementReceiveSerializer,
    TaxProfileCreateSerializer,
    TaxProfileOut,
    TransferSerializer,
    WarehouseCreateSerializer,
    WarehouseListQuerySerializer,
    WarehouseOut,
    WarehousePatchSerializer,
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


def _require_branch(request) -> OrgUnit | None:
    return getattr(request, "branch", None)


def _inventory_error_code(exc: Exception) -> str:
    msg = str(exc).lower()
    if "stock insuficiente" in msg:
        return "INVENTORY_INSUFFICIENT_STOCK"
    if "x-branch-id requerido" in msg:
        return "INVENTORY_INVALID_SCOPE"
    if "warehouse inválido" in msg:
        return "INVENTORY_INVALID_WAREHOUSE"
    if "item inválido" in msg:
        return "INVENTORY_INVALID_ITEM"
    if "from_warehouse_id" in msg and "to_warehouse_id" in msg:
        return "INVENTORY_SCHEMA_INVALID"
    if "qty debe ser" in msg or "unit_cost" in msg:
        return "INVENTORY_SCHEMA_INVALID"
    return "INVENTORY_VALIDATION_ERROR"


def _normalize_command_type(value: str) -> str:
    normalized = str(value or "").strip().upper()
    return {
        "INVENTORY_MOVEMENT_RECEIVE": "INVENTORY.MOVEMENT.RECEIVE",
        "INVENTORY.MOVEMENT.RECEIVE": "INVENTORY.MOVEMENT.RECEIVE",
        "INVENTORY_MOVEMENT_ISSUE": "INVENTORY.MOVEMENT.ISSUE",
        "INVENTORY.MOVEMENT.ISSUE": "INVENTORY.MOVEMENT.ISSUE",
        "INVENTORY_MOVEMENT_ADJUST": "INVENTORY.MOVEMENT.ADJUST",
        "INVENTORY.MOVEMENT.ADJUST": "INVENTORY.MOVEMENT.ADJUST",
        "INVENTORY_TRANSFER": "INVENTORY.TRANSFER",
        "INVENTORY.TRANSFER": "INVENTORY.TRANSFER",
        "INVENTORY_ITEM_CREATE": "INVENTORY.ITEM.CREATE",
        "INVENTORY.ITEM.CREATE": "INVENTORY.ITEM.CREATE",
        "INVENTORY_WAREHOUSE_CREATE": "INVENTORY.WAREHOUSE.CREATE",
        "INVENTORY.WAREHOUSE.CREATE": "INVENTORY.WAREHOUSE.CREATE",
    }.get(normalized, normalized)


def _paginate(*, limit: int, offset: int, total: int, rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "count": total,
        "limit": limit,
        "offset": offset,
        "has_next": (offset + limit) < total,
        "has_prev": offset > 0,
        "results": rows,
    }


def _resolve_lookup_refs(*, company: OrgUnit, payload: dict[str, Any]) -> dict[str, Any]:
    refs: dict[str, Any] = {}

    brand_id = payload.pop("brand_id", None)
    if brand_id is not None:
        refs["brand"] = get_object_or_404(InventoryBrand, id=int(brand_id), company=company)

    category_id = payload.pop("category_id", None)
    if category_id is not None:
        refs["category"] = get_object_or_404(InventoryCategory, id=int(category_id), company=company)

    subcategory_id = payload.pop("subcategory_id", None)
    if subcategory_id is not None:
        subcategory = get_object_or_404(InventoryCategory, id=int(subcategory_id), company=company)
        if refs.get("category") and subcategory.parent_id != refs["category"].id:
            raise ValueError("subcategory_id debe pertenecer a category_id.")
        refs["subcategory"] = subcategory

    tax_profile_id = payload.pop("tax_profile_id", None)
    if tax_profile_id is not None:
        refs["tax_profile"] = get_object_or_404(InventoryTaxProfile, id=int(tax_profile_id), company=company)

    default_branch_id = payload.pop("default_branch_id", None)
    if default_branch_id is not None:
        branch = get_object_or_404(
            OrgUnit,
            id=int(default_branch_id),
            unit_type=OrgUnit.UnitType.BRANCH,
            parent=company,
            is_active=True,
        )
        refs["default_branch"] = branch

    default_warehouse_id = payload.pop("default_warehouse_id", None)
    if default_warehouse_id is not None:
        wh = get_object_or_404(Warehouse, id=int(default_warehouse_id), company=company)
        if refs.get("default_branch") and wh.branch_id != refs["default_branch"].id:
            raise ValueError("default_warehouse_id debe pertenecer a default_branch_id.")
        refs["default_warehouse"] = wh

    return refs


def _extract_item_fields(validated: dict[str, Any]) -> dict[str, Any]:
    payload = dict(validated)
    sku = str(payload.pop("sku")).strip().upper() if "sku" in payload else ""
    name = str(payload.pop("name")).strip() if "name" in payload else ""
    legacy_uom = str(payload.pop("uom", "") or "").strip().upper() if "uom" in payload else ""
    if legacy_uom and "uom_base" not in payload:
        payload["uom_base"] = legacy_uom
    selected_uom = payload.get("uom_base") or legacy_uom
    if selected_uom:
        payload["uom"] = selected_uom
    return {"sku": sku, "name": name, "uom": selected_uom or None, "payload": payload}


class HealthView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"ok": True, "module": "inventory"}, status=status.HTTP_200_OK)


class WarehouseListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [rbac_permission("inventory.balance.read")()]
        return [rbac_permission("inventory.warehouse.create")()]

    def get(self, request):
        company: OrgUnit = request.company
        serializer = WarehouseListQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        filters = serializer.validated_data

        qs = Warehouse.objects.filter(company=company)

        branch_id = filters.get("branch_id")
        if branch_id:
            qs = qs.filter(branch_id=int(branch_id))
        else:
            branch = _require_branch(request)
            if branch:
                qs = qs.filter(branch=branch)

        q = str(filters.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(code__icontains=q))

        is_active = filters.get("is_active")
        if is_active is not None:
            qs = qs.filter(is_active=bool(is_active))

        total = qs.count()
        limit = int(filters.get("limit", 50))
        offset = int(filters.get("offset", 0))
        rows = [WarehouseOut(row).data for row in qs.order_by("name", "id")[offset : offset + limit]]
        return Response(_paginate(limit=limit, offset=offset, total=total, rows=rows), status=status.HTTP_200_OK)

    def post(self, request):
        company: OrgUnit = request.company
        branch = _require_branch(request)
        if not branch:
            return Response({"detail": "X-Branch-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)

        s = WarehouseCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = s.validated_data

        try:
            wh = Warehouse.objects.create(
                company=company,
                branch=branch,
                name=v["name"],
                code=v.get("code", "") or "",
                is_active=True,
            )
        except IntegrityError:
            return Response(
                {"detail": "Código de almacén duplicado.", "code": "INVENTORY_DUPLICATE_WAREHOUSE_CODE"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response({"id": wh.id}, status=status.HTTP_201_CREATED)


class WarehouseDetailView(APIView):
    permission_classes = [rbac_permission("inventory.warehouse.create")]

    def patch(self, request, warehouse_id: int):
        company: OrgUnit = request.company
        branch = _require_branch(request)
        if not branch:
            return Response({"detail": "X-Branch-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)

        wh = get_object_or_404(Warehouse, id=int(warehouse_id), company=company, branch=branch)
        s = WarehousePatchSerializer(data=request.data)
        s.is_valid(raise_exception=True)

        for field, value in s.validated_data.items():
            setattr(wh, field, value)

        try:
            wh.save(update_fields=list(s.validated_data.keys()))
        except IntegrityError:
            return Response(
                {"detail": "Código de almacén duplicado.", "code": "INVENTORY_DUPLICATE_WAREHOUSE_CODE"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(WarehouseOut(wh).data, status=status.HTTP_200_OK)


class ItemListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [rbac_permission("inventory.item.read")()]
        return [rbac_permission("inventory.item.create")()]

    def get(self, request):
        company: OrgUnit = request.company

        serializer = ItemListQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        filters = serializer.validated_data

        qs = InventoryItem.objects.filter(company=company)

        q = str(filters.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(sku__icontains=q))

        sku_exact = str(filters.get("sku_exact") or "").strip().upper()
        if sku_exact:
            qs = qs.filter(sku=sku_exact)

        barcode_exact = str(filters.get("barcode_exact") or "").strip()
        if barcode_exact:
            qs = qs.filter(barcode=barcode_exact)

        is_active = filters.get("is_active")
        if is_active is not None:
            qs = qs.filter(is_active=bool(is_active))

        total = qs.count()
        limit = int(filters.get("limit", 50))
        offset = int(filters.get("offset", 0))
        rows = [InventoryItemOut(row).data for row in qs.order_by("sku", "id")[offset : offset + limit]]
        return Response(_paginate(limit=limit, offset=offset, total=total, rows=rows), status=status.HTTP_200_OK)

    def post(self, request):
        company: OrgUnit = request.company

        s = ItemCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        v = dict(s.validated_data)

        extracted = _extract_item_fields(v)
        try:
            lookup_refs = _resolve_lookup_refs(company=company, payload=extracted["payload"])
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        payload = extracted["payload"]
        payload.update(lookup_refs)

        sku = extracted["sku"]
        name = extracted["name"]
        uom = extracted["uom"] or "UNIT"

        barcode = str(payload.get("barcode") or "").strip()
        if barcode and InventoryItem.objects.filter(company=company, barcode=barcode).exists():
            return Response(
                {"detail": "Barcode duplicado.", "code": "INVENTORY_DUPLICATE_BARCODE"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            item = create_item(
                request=request,
                company=company,
                actor_user=request.user,
                sku=sku,
                name=name,
                uom=uom,
                extra_fields=payload,
            )
        except IntegrityError:
            return Response(
                {"detail": "SKU duplicado.", "code": "INVENTORY_DUPLICATE_SKU"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(InventoryItemOut(item).data, status=status.HTTP_201_CREATED)


class ItemDetailView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [rbac_permission("inventory.item.read")()]
        return [rbac_permission("inventory.item.update")()]

    def get(self, request, item_id: int):
        company: OrgUnit = request.company
        item = get_object_or_404(InventoryItem, id=int(item_id), company=company)
        return Response(InventoryItemOut(item).data, status=status.HTTP_200_OK)

    def patch(self, request, item_id: int):
        company: OrgUnit = request.company
        item = get_object_or_404(InventoryItem, id=int(item_id), company=company)

        s = ItemPatchSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        payload = dict(s.validated_data)
        extracted = _extract_item_fields(payload)
        try:
            lookup_refs = _resolve_lookup_refs(company=company, payload=extracted["payload"])
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        patch_data = extracted["payload"]
        patch_data.update(lookup_refs)

        if extracted["sku"]:
            patch_data["sku"] = extracted["sku"]
        if extracted["name"]:
            patch_data["name"] = extracted["name"]
        if extracted["uom"]:
            patch_data["uom"] = extracted["uom"]

        barcode = str(patch_data.get("barcode") or "").strip()
        if barcode and InventoryItem.objects.filter(company=company, barcode=barcode).exclude(id=item.id).exists():
            return Response(
                {"detail": "Barcode duplicado.", "code": "INVENTORY_DUPLICATE_BARCODE"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        for field, value in patch_data.items():
            setattr(item, field, value)
        item.version = int(item.version) + 1

        try:
            update_fields = list(patch_data.keys()) + ["version", "updated_at"]
            item.updated_at = timezone.now()
            item.save(update_fields=update_fields)
        except IntegrityError:
            return Response(
                {"detail": "SKU duplicado.", "code": "INVENTORY_DUPLICATE_SKU"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(InventoryItemOut(item).data, status=status.HTTP_200_OK)


class UomLookupView(APIView):
    permission_classes = [rbac_permission("inventory.item.read")]

    def get(self, request):
        rows = [{"code": code, "label": label} for code, label in InventoryItem._meta.get_field("uom").choices]
        return Response({"results": rows}, status=status.HTTP_200_OK)


class BrandLookupView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [rbac_permission("inventory.item.read")()]
        return [rbac_permission("inventory.item.create")()]

    def get(self, request):
        company: OrgUnit = request.company
        s = InventoryLookupQuerySerializer(data=request.query_params)
        s.is_valid(raise_exception=True)
        f = s.validated_data

        qs = InventoryBrand.objects.filter(company=company)
        q = str(f.get("q") or "").strip()
        if q:
            qs = qs.filter(name__icontains=q)
        is_active = f.get("is_active")
        if is_active is not None:
            qs = qs.filter(is_active=bool(is_active))
        total = qs.count()
        limit = int(f.get("limit", 100))
        offset = int(f.get("offset", 0))
        rows = [BrandOut(row).data for row in qs.order_by("name", "id")[offset : offset + limit]]
        return Response(_paginate(limit=limit, offset=offset, total=total, rows=rows), status=status.HTTP_200_OK)

    def post(self, request):
        company: OrgUnit = request.company
        s = BrandCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            brand = InventoryBrand.objects.create(company=company, name=str(s.validated_data["name"]).strip())
        except IntegrityError:
            return Response(
                {"detail": "Marca duplicada.", "code": "INVENTORY_DUPLICATE_BRAND"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(BrandOut(brand).data, status=status.HTTP_201_CREATED)


class CategoryLookupView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [rbac_permission("inventory.item.read")()]
        return [rbac_permission("inventory.item.create")()]

    def get(self, request):
        company: OrgUnit = request.company
        s = InventoryLookupQuerySerializer(data=request.query_params)
        s.is_valid(raise_exception=True)
        f = s.validated_data

        qs = InventoryCategory.objects.filter(company=company)
        q = str(f.get("q") or "").strip()
        if q:
            qs = qs.filter(name__icontains=q)
        parent_id = f.get("parent_id")
        if parent_id:
            qs = qs.filter(parent_id=int(parent_id))
        is_active = f.get("is_active")
        if is_active is not None:
            qs = qs.filter(is_active=bool(is_active))
        total = qs.count()
        limit = int(f.get("limit", 100))
        offset = int(f.get("offset", 0))
        rows = [CategoryOut(row).data for row in qs.order_by("name", "id")[offset : offset + limit]]
        return Response(_paginate(limit=limit, offset=offset, total=total, rows=rows), status=status.HTTP_200_OK)

    def post(self, request):
        company: OrgUnit = request.company
        s = CategoryCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        parent = None
        parent_id = s.validated_data.get("parent_id")
        if parent_id:
            parent = get_object_or_404(InventoryCategory, id=int(parent_id), company=company)
        try:
            cat = InventoryCategory.objects.create(
                company=company,
                parent=parent,
                name=str(s.validated_data["name"]).strip(),
            )
        except IntegrityError:
            return Response(
                {"detail": "Categoría duplicada.", "code": "INVENTORY_DUPLICATE_CATEGORY"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(CategoryOut(cat).data, status=status.HTTP_201_CREATED)


class TaxProfileLookupView(APIView):
    def get_permissions(self):
        if self.request.method == "GET":
            return [rbac_permission("inventory.item.read")()]
        return [rbac_permission("inventory.item.create")()]

    def get(self, request):
        company: OrgUnit = request.company
        s = InventoryLookupQuerySerializer(data=request.query_params)
        s.is_valid(raise_exception=True)
        f = s.validated_data

        qs = InventoryTaxProfile.objects.filter(company=company)
        q = str(f.get("q") or "").strip()
        if q:
            qs = qs.filter(Q(code__icontains=q) | Q(name__icontains=q))
        is_active = f.get("is_active")
        if is_active is not None:
            qs = qs.filter(is_active=bool(is_active))
        total = qs.count()
        limit = int(f.get("limit", 100))
        offset = int(f.get("offset", 0))
        rows = [TaxProfileOut(row).data for row in qs.order_by("code", "id")[offset : offset + limit]]
        return Response(_paginate(limit=limit, offset=offset, total=total, rows=rows), status=status.HTTP_200_OK)

    def post(self, request):
        company: OrgUnit = request.company
        s = TaxProfileCreateSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        try:
            profile = InventoryTaxProfile.objects.create(
                company=company,
                code=str(s.validated_data["code"]).strip().upper(),
                name=str(s.validated_data["name"]).strip(),
                tax_treatment=s.validated_data["tax_treatment"],
            )
        except IntegrityError:
            return Response(
                {"detail": "Código fiscal duplicado.", "code": "INVENTORY_DUPLICATE_TAX_PROFILE"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return Response(TaxProfileOut(profile).data, status=status.HTTP_201_CREATED)


class ReceiveView(APIView):
    permission_classes = [rbac_permission("inventory.movement.receive")]

    def post(self, request):
        if not _require_branch(request):
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
        if not _require_branch(request):
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
        if not _require_branch(request):
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
        if not _require_branch(request):
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
        branch = _require_branch(request)
        if not branch:
            return Response({"detail": "X-Branch-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)

        warehouse_id = request.query_params.get("warehouse_id")
        item_id = request.query_params.get("item_id")

        # Compat mode: consulta puntual existente
        if warehouse_id and item_id:
            wh = get_object_or_404(Warehouse, id=int(warehouse_id), company=company, branch=branch)
            item = get_object_or_404(InventoryItem, id=int(item_id), company=company)

            bal = StockBalance.objects.filter(company=company, branch=branch, warehouse=wh, item=item).first()
            if not bal:
                return Response({"qty_on_hand": "0.0000", "avg_cost": "0.000000"}, status=status.HTTP_200_OK)

            return Response({"qty_on_hand": str(bal.qty_on_hand), "avg_cost": str(bal.avg_cost)}, status=status.HTTP_200_OK)

        # Modo listado paginado
        serializer = BalanceListQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        filters = serializer.validated_data

        qs = StockBalance.objects.select_related("warehouse", "item").filter(company=company, branch=branch)

        if filters.get("warehouse_id") is not None:
            qs = qs.filter(warehouse_id=int(filters["warehouse_id"]))

        if filters.get("item_id") is not None:
            qs = qs.filter(item_id=int(filters["item_id"]))

        q = str(filters.get("q") or "").strip()
        if q:
            qs = qs.filter(
                Q(item__sku__icontains=q)
                | Q(item__name__icontains=q)
                | Q(warehouse__name__icontains=q)
                | Q(warehouse__code__icontains=q)
            )

        total = qs.count()
        limit = int(filters.get("limit", 50))
        offset = int(filters.get("offset", 0))
        rows = [
            {
                "id": row.id,
                "warehouse_id": row.warehouse_id,
                "warehouse_name": row.warehouse.name,
                "warehouse_code": row.warehouse.code,
                "item_id": row.item_id,
                "item_sku": row.item.sku,
                "item_name": row.item.name,
                "qty_on_hand": str(row.qty_on_hand),
                "avg_cost": str(row.avg_cost),
                "updated_at": row.updated_at.isoformat() if row.updated_at else None,
            }
            for row in qs.order_by("warehouse__name", "item__sku", "id")[offset : offset + limit]
        ]

        return Response(_paginate(limit=limit, offset=offset, total=total, rows=rows), status=status.HTTP_200_OK)


class LedgerView(APIView):
    permission_classes = [rbac_permission("inventory.balance.read")]

    def get(self, request):
        company: OrgUnit = request.company
        branch = _require_branch(request)
        if not branch:
            return Response({"detail": "X-Branch-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)

        serializer = LedgerQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        filters = serializer.validated_data

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

        source_module = str(filters.get("source_module") or "").strip()
        if source_module:
            qs = qs.filter(source_module__iexact=source_module)

        source_type = str(filters.get("source_type") or "").strip()
        if source_type:
            qs = qs.filter(source_type__iexact=source_type)

        source_id = str(filters.get("source_id") or "").strip()
        if source_id:
            qs = qs.filter(source_id=source_id)

        accounting_status = str(filters.get("accounting_status") or "").strip().upper()
        if accounting_status:
            qs = qs.filter(accounting_status=accounting_status)

        date_from = filters.get("date_from")
        if date_from is not None:
            qs = qs.filter(created_at__gte=date_from)

        date_to = filters.get("date_to")
        if date_to is not None:
            qs = qs.filter(created_at__lte=date_to)

        total = qs.count()

        if "limit" in filters:
            limit = int(filters.get("limit") or 50)
            offset = int(filters.get("offset") or 0)
        else:
            page = int(filters.get("page", 1))
            page_size = min(int(filters.get("page_size", 50)), 100)
            limit = page_size
            offset = (page - 1) * page_size

        rows = list(qs.order_by("-created_at", "-id")[offset : offset + limit])

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

        page = (offset // limit) + 1
        return Response(
            {
                "page": page,
                "page_size": limit,
                "total": total,
                "has_next": (offset + limit) < total,
                "has_prev": page > 1,
                "items": items,
                # Contrato aditivo para UI moderna
                "count": total,
                "limit": limit,
                "offset": offset,
                "results": items,
            },
            status=status.HTTP_200_OK,
        )


class InventoryCommandBatchView(APIView):
    permission_classes = [rbac_permission("inventory.movement.post")]

    def post(self, request):
        company: OrgUnit = request.company
        branch = _require_branch(request)
        if not branch:
            return Response({"detail": "X-Branch-Id requerido"}, status=status.HTTP_400_BAD_REQUEST)

        serializer = InventoryCommandBatchIn(data=request.data)
        serializer.is_valid(raise_exception=True)

        applied = 0
        duplicate = 0
        rejected = 0
        out: list[dict[str, Any]] = []

        for command in serializer.validated_data["commands"]:
            command_id = str(command["command_id"])
            cmd_type = _normalize_command_type(command["type"])
            payload = dict(command.get("payload") or {})

            raw_idempotency = str(payload.get("idempotency_key") or "").strip()
            idempotency_key = raw_idempotency or command_id

            try:
                if cmd_type == "INVENTORY.MOVEMENT.RECEIVE":
                    existing = StockMovement.objects.filter(company=company, idempotency_key=idempotency_key).first()
                    if existing:
                        duplicate += 1
                        out.append(
                            {
                                "command_id": command_id,
                                "status": "DUPLICATE",
                                "refs": {"movement_id": existing.id},
                            }
                        )
                        continue

                    result = post_receive(
                        request=request,
                        actor=request.user,
                        warehouse_id=int(payload["warehouse_id"]),
                        item_id=int(payload["item_id"]),
                        qty=payload["qty"],
                        unit_cost=payload.get("unit_cost", "0"),
                        idempotency_key=idempotency_key,
                        note=str(payload.get("note") or ""),
                    )
                    applied += 1
                    out.append(
                        {
                            "command_id": command_id,
                            "status": "APPLIED",
                            "refs": {
                                "movement_id": result.movement_id,
                                "qty_on_hand": str(result.qty_on_hand),
                                "avg_cost": str(result.avg_cost),
                            },
                        }
                    )
                    continue

                if cmd_type == "INVENTORY.MOVEMENT.ISSUE":
                    existing = StockMovement.objects.filter(company=company, idempotency_key=idempotency_key).first()
                    if existing:
                        duplicate += 1
                        out.append(
                            {
                                "command_id": command_id,
                                "status": "DUPLICATE",
                                "refs": {"movement_id": existing.id},
                            }
                        )
                        continue

                    result = post_issue(
                        request=request,
                        actor=request.user,
                        warehouse_id=int(payload["warehouse_id"]),
                        item_id=int(payload["item_id"]),
                        qty=payload["qty"],
                        allow_negative=bool(payload.get("allow_negative", False)),
                        idempotency_key=idempotency_key,
                        note=str(payload.get("note") or ""),
                    )
                    applied += 1
                    out.append(
                        {
                            "command_id": command_id,
                            "status": "APPLIED",
                            "refs": {
                                "movement_id": result.movement_id,
                                "qty_on_hand": str(result.qty_on_hand),
                                "avg_cost": str(result.avg_cost),
                            },
                        }
                    )
                    continue

                if cmd_type == "INVENTORY.MOVEMENT.ADJUST":
                    existing = StockMovement.objects.filter(company=company, idempotency_key=idempotency_key).first()
                    if existing:
                        duplicate += 1
                        out.append(
                            {
                                "command_id": command_id,
                                "status": "DUPLICATE",
                                "refs": {"movement_id": existing.id},
                            }
                        )
                        continue

                    result = post_adjust(
                        request=request,
                        actor=request.user,
                        warehouse_id=int(payload["warehouse_id"]),
                        item_id=int(payload["item_id"]),
                        new_qty_on_hand=payload["new_qty_on_hand"],
                        idempotency_key=idempotency_key,
                        note=str(payload.get("note") or ""),
                    )
                    applied += 1
                    out.append(
                        {
                            "command_id": command_id,
                            "status": "APPLIED",
                            "refs": {
                                "movement_id": result.movement_id,
                                "qty_on_hand": str(result.qty_on_hand),
                                "avg_cost": str(result.avg_cost),
                            },
                        }
                    )
                    continue

                if cmd_type == "INVENTORY.TRANSFER":
                    existing = StockMovement.objects.filter(company=company, idempotency_key=idempotency_key).first()
                    if existing:
                        duplicate += 1
                        out.append(
                            {
                                "command_id": command_id,
                                "status": "DUPLICATE",
                                "refs": {"transfer_out_movement_id": existing.id},
                            }
                        )
                        continue

                    result = post_transfer(
                        request=request,
                        actor=request.user,
                        from_warehouse_id=int(payload["from_warehouse_id"]),
                        to_warehouse_id=int(payload["to_warehouse_id"]),
                        item_id=int(payload["item_id"]),
                        qty=payload["qty"],
                        idempotency_key=idempotency_key,
                        note=str(payload.get("note") or ""),
                    )
                    applied += 1
                    out.append(
                        {
                            "command_id": command_id,
                            "status": "APPLIED",
                            "refs": {
                                "transfer_out_movement_id": result.get("out_movement_id"),
                                "transfer_in_movement_id": result.get("in_movement_id"),
                            },
                        }
                    )
                    continue

                if cmd_type == "INVENTORY.ITEM.CREATE":
                    item = create_item(
                        request=request,
                        company=company,
                        actor_user=request.user,
                        sku=str(payload["sku"]),
                        name=str(payload["name"]),
                        uom=str(payload.get("uom") or "UNIT"),
                    )
                    applied += 1
                    out.append(
                        {
                            "command_id": command_id,
                            "status": "APPLIED",
                            "refs": {"item_id": item.id, "sku": item.sku},
                        }
                    )
                    continue

                if cmd_type == "INVENTORY.WAREHOUSE.CREATE":
                    wh = Warehouse.objects.create(
                        company=company,
                        branch=branch,
                        name=str(payload["name"]),
                        code=str(payload.get("code") or ""),
                        is_active=True,
                    )
                    applied += 1
                    out.append(
                        {
                            "command_id": command_id,
                            "status": "APPLIED",
                            "refs": {"warehouse_id": wh.id, "code": wh.code},
                        }
                    )
                    continue

                rejected += 1
                out.append(
                    {
                        "command_id": command_id,
                        "status": "REJECTED",
                        "error_code": "INVENTORY_COMMAND_UNSUPPORTED",
                        "error_detail": f"Tipo de comando no soportado: {cmd_type}",
                    }
                )
            except (ValueError, IntegrityError, KeyError, TypeError) as exc:
                rejected += 1
                error_code = "INVENTORY_VALIDATION_ERROR"
                if isinstance(exc, IntegrityError):
                    error_code = "INVENTORY_CONSTRAINT_VIOLATION"
                elif isinstance(exc, (ValueError, KeyError, TypeError)):
                    error_code = _inventory_error_code(exc)

                out.append(
                    {
                        "command_id": command_id,
                        "status": "REJECTED",
                        "error_code": error_code,
                        "error_detail": str(exc),
                    }
                )

        return Response(
            {
                "results": out,
                "summary": {
                    "total": len(out),
                    "applied": applied,
                    "duplicate": duplicate,
                    "rejected": rejected,
                },
            },
            status=status.HTTP_200_OK,
        )
