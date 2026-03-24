from __future__ import annotations

import re

from rest_framework import serializers

from .models import (
    BarcodeType,
    CostingMethod,
    InventoryBrand,
    InventoryCategory,
    InventoryItem,
    InventoryTaxProfile,
    ItemStatus,
    ItemType,
    TaxTreatment,
    UoM,
    Warehouse,
)


_BARCODE_PATTERNS = {
    BarcodeType.EAN13: re.compile(r"^\d{13}$"),
    BarcodeType.UPCA: re.compile(r"^\d{12}$"),
    BarcodeType.CODE128: re.compile(r"^[A-Za-z0-9\-\.\$/\+%\s]{1,64}$"),
    BarcodeType.INTERNO: re.compile(r"^[A-Za-z0-9._\-]{3,64}$"),
}


class WarehouseCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    code = serializers.CharField(max_length=24, required=False, allow_blank=True)


class WarehousePatchSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120, required=False)
    code = serializers.CharField(max_length=24, required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Debe enviar al menos un campo para actualizar.")
        return attrs


class WarehouseListQuerySerializer(serializers.Serializer):
    q = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False, allow_null=True, default=None)
    branch_id = serializers.IntegerField(required=False, min_value=1)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=200, default=50)
    offset = serializers.IntegerField(required=False, min_value=0, default=0)


class InventoryLookupQuerySerializer(serializers.Serializer):
    q = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False, allow_null=True, default=None)
    parent_id = serializers.IntegerField(required=False, min_value=1)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=200, default=100)
    offset = serializers.IntegerField(required=False, min_value=0, default=0)


class BrandCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=80)


class CategoryCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=80)
    parent_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)


class TaxProfileCreateSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=32)
    name = serializers.CharField(max_length=120)
    tax_treatment = serializers.ChoiceField(choices=TaxTreatment.choices, default=TaxTreatment.GRAVADO)
    rate = serializers.DecimalField(max_digits=8, decimal_places=4, required=False, default="0.0000")

    def validate(self, attrs):
        tax_treatment = attrs.get("tax_treatment", TaxTreatment.GRAVADO)
        rate = attrs.get("rate")
        if tax_treatment in (TaxTreatment.EXENTO, TaxTreatment.EXONERADO):
            attrs["rate"] = "0.0000"
            return attrs
        if rate is None:
            attrs["rate"] = "0.0000"
        return attrs


class ItemCreateSerializer(serializers.Serializer):
    sku = serializers.CharField(max_length=64)
    name = serializers.CharField(max_length=160)
    uom = serializers.ChoiceField(choices=UoM.choices, required=False)

    item_type = serializers.ChoiceField(choices=ItemType.choices, required=False)
    status = serializers.ChoiceField(choices=ItemStatus.choices, required=False)
    short_name = serializers.CharField(max_length=80, required=False, allow_blank=True)
    invoice_name = serializers.CharField(max_length=160, required=False, allow_blank=True)
    description = serializers.CharField(max_length=500, required=False, allow_blank=True)

    brand_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    category_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    subcategory_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)

    barcode = serializers.CharField(max_length=64, required=False, allow_blank=True)
    barcode_type = serializers.ChoiceField(choices=BarcodeType.choices, required=False, allow_blank=True)
    alternate_code = serializers.CharField(max_length=64, required=False, allow_blank=True)
    search_tags = serializers.ListField(child=serializers.CharField(max_length=24), required=False)

    purchase_enabled = serializers.BooleanField(required=False)
    sales_enabled = serializers.BooleanField(required=False)
    controls_stock = serializers.BooleanField(required=False)
    transfer_enabled = serializers.BooleanField(required=False)
    allow_returns = serializers.BooleanField(required=False)

    uom_base = serializers.ChoiceField(choices=UoM.choices, required=False)
    uom_purchase = serializers.ChoiceField(choices=UoM.choices, required=False)
    uom_sale = serializers.ChoiceField(choices=UoM.choices, required=False)
    uom_conversions = serializers.ListField(child=serializers.DictField(), required=False)
    allow_fraction = serializers.BooleanField(required=False)
    min_qty = serializers.DecimalField(max_digits=18, decimal_places=4, required=False)
    rounding_increment = serializers.DecimalField(max_digits=18, decimal_places=4, required=False)

    enabled_branch_ids = serializers.ListField(child=serializers.IntegerField(min_value=1), required=False)
    default_branch_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    default_warehouse_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)

    min_stock = serializers.DecimalField(max_digits=18, decimal_places=4, required=False)
    max_stock = serializers.DecimalField(max_digits=18, decimal_places=4, required=False)
    reorder_point = serializers.DecimalField(max_digits=18, decimal_places=4, required=False)
    reorder_qty = serializers.DecimalField(max_digits=18, decimal_places=4, required=False)
    allow_negative_stock = serializers.BooleanField(required=False)
    reserve_enabled = serializers.BooleanField(required=False)
    internal_location = serializers.CharField(max_length=64, required=False, allow_blank=True)

    costing_method = serializers.ChoiceField(choices=CostingMethod.choices, required=False)
    initial_cost = serializers.DecimalField(max_digits=18, decimal_places=6, required=False)
    standard_cost = serializers.DecimalField(max_digits=18, decimal_places=6, required=False)
    currency = serializers.CharField(max_length=3, required=False)
    last_known_cost = serializers.DecimalField(max_digits=18, decimal_places=6, required=False)

    preferred_supplier_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    supplier_item_code = serializers.CharField(max_length=64, required=False, allow_blank=True)
    lead_time_days = serializers.IntegerField(required=False, allow_null=True, min_value=0, max_value=365)
    purchase_moq = serializers.DecimalField(max_digits=18, decimal_places=4, required=False)
    purchase_multiple = serializers.DecimalField(max_digits=18, decimal_places=4, required=False)

    suggested_price = serializers.DecimalField(max_digits=18, decimal_places=6, required=False)
    min_sale_price = serializers.DecimalField(max_digits=18, decimal_places=6, required=False)
    allow_discount = serializers.BooleanField(required=False)
    visible_pos = serializers.BooleanField(required=False)
    visible_quote = serializers.BooleanField(required=False)
    visible_invoice = serializers.BooleanField(required=False)

    tax_profile_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    tax_treatment = serializers.ChoiceField(choices=TaxTreatment.choices, required=False)
    invoice_description = serializers.CharField(max_length=160, required=False, allow_blank=True)

    use_lot = serializers.BooleanField(required=False)
    use_serial = serializers.BooleanField(required=False)
    use_expiry = serializers.BooleanField(required=False)
    shelf_life_days = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    quality_control_required = serializers.BooleanField(required=False)
    allow_return_to_stock = serializers.BooleanField(required=False)

    is_active = serializers.BooleanField(required=False)

    def validate_sku(self, value: str):
        normalized = value.strip().upper()
        if not re.match(r"^[A-Z0-9._-]{3,64}$", normalized):
            raise serializers.ValidationError("SKU inválido. Use A-Z 0-9 . _ - (3-64).")
        return normalized

    def validate_currency(self, value: str):
        normalized = value.strip().upper()
        if not re.match(r"^[A-Z]{3}$", normalized):
            raise serializers.ValidationError("Moneda inválida. Use formato ISO-4217 (3 letras).")
        return normalized

    def validate(self, attrs):
        barcode = str(attrs.get("barcode") or "").strip()
        barcode_type = str(attrs.get("barcode_type") or "").strip()

        if barcode:
            if not barcode_type:
                raise serializers.ValidationError({"barcode_type": "barcode_type requerido cuando barcode existe."})
            pattern = _BARCODE_PATTERNS.get(barcode_type)
            if pattern and not pattern.match(barcode):
                raise serializers.ValidationError({"barcode": f"Formato inválido para {barcode_type}."})
        elif barcode_type:
            raise serializers.ValidationError({"barcode": "barcode requerido cuando barcode_type existe."})

        search_tags = attrs.get("search_tags")
        if search_tags is not None:
            if len(search_tags) > 15:
                raise serializers.ValidationError({"search_tags": "Máximo 15 tags."})
            for tag in search_tags:
                if len(str(tag).strip()) < 2:
                    raise serializers.ValidationError({"search_tags": "Cada tag debe tener al menos 2 caracteres."})

        conversions = attrs.get("uom_conversions")
        if conversions is not None:
            seen_uom = set()
            for idx, row in enumerate(conversions):
                if not isinstance(row, dict):
                    raise serializers.ValidationError({"uom_conversions": f"Fila {idx + 1} inválida."})
                to_uom = str(row.get("to_uom") or "").upper()
                factor = row.get("factor")
                if to_uom not in UoM.values:
                    raise serializers.ValidationError({"uom_conversions": f"to_uom inválida en fila {idx + 1}."})
                if to_uom in seen_uom:
                    raise serializers.ValidationError({"uom_conversions": "No se permiten uom destino duplicadas."})
                seen_uom.add(to_uom)
                try:
                    numeric_factor = float(factor)
                except (TypeError, ValueError):
                    raise serializers.ValidationError({"uom_conversions": f"factor inválido en fila {idx + 1}."})
                if numeric_factor <= 0:
                    raise serializers.ValidationError({"uom_conversions": f"factor debe ser > 0 en fila {idx + 1}."})

        min_stock = attrs.get("min_stock")
        max_stock = attrs.get("max_stock")
        reorder_point = attrs.get("reorder_point")
        if min_stock is not None and min_stock < 0:
            raise serializers.ValidationError({"min_stock": "Debe ser >= 0."})
        if max_stock is not None and max_stock < 0:
            raise serializers.ValidationError({"max_stock": "Debe ser >= 0."})
        if min_stock is not None and max_stock is not None and max_stock < min_stock:
            raise serializers.ValidationError({"max_stock": "Debe ser >= min_stock."})
        if reorder_point is not None and reorder_point < 0:
            raise serializers.ValidationError({"reorder_point": "Debe ser >= 0."})
        if reorder_point is not None and max_stock is not None and max_stock > 0 and reorder_point > max_stock:
            raise serializers.ValidationError({"reorder_point": "Debe ser <= max_stock."})

        use_expiry = attrs.get("use_expiry")
        shelf_life_days = attrs.get("shelf_life_days")
        if use_expiry and not shelf_life_days:
            raise serializers.ValidationError({"shelf_life_days": "Requerido cuando use_expiry=true."})

        enabled_branch_ids = attrs.get("enabled_branch_ids")
        default_branch_id = attrs.get("default_branch_id")
        if enabled_branch_ids is not None and len(enabled_branch_ids) == 0:
            raise serializers.ValidationError({"enabled_branch_ids": "Debe incluir al menos una sucursal."})
        if default_branch_id and enabled_branch_ids is not None and default_branch_id not in enabled_branch_ids:
            raise serializers.ValidationError({"default_branch_id": "Debe pertenecer a enabled_branch_ids."})

        item_type = attrs.get("item_type")
        controls_stock = attrs.get("controls_stock")
        if item_type == ItemType.SERVICIO:
            attrs["controls_stock"] = False
            attrs["transfer_enabled"] = False
        if controls_stock is False:
            attrs["transfer_enabled"] = False

        min_sale_price = attrs.get("min_sale_price")
        suggested_price = attrs.get("suggested_price")
        if min_sale_price is not None and suggested_price is not None and min_sale_price > suggested_price:
            raise serializers.ValidationError({"min_sale_price": "Debe ser <= suggested_price."})

        return attrs


class ItemPatchSerializer(ItemCreateSerializer):
    sku = serializers.CharField(max_length=64, required=False)
    name = serializers.CharField(max_length=160, required=False)

    def validate(self, attrs):
        if not attrs:
            raise serializers.ValidationError("Debe enviar al menos un campo para actualizar.")
        return super().validate(attrs)


class ItemListQuerySerializer(serializers.Serializer):
    q = serializers.CharField(required=False, allow_blank=True)
    sku_exact = serializers.CharField(required=False, allow_blank=True)
    barcode_exact = serializers.CharField(required=False, allow_blank=True)
    is_active = serializers.BooleanField(required=False, allow_null=True, default=None)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=200, default=50)
    offset = serializers.IntegerField(required=False, min_value=0, default=0)


class MovementReceiveSerializer(serializers.Serializer):
    warehouse_id = serializers.IntegerField()
    item_id = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=18, decimal_places=4)
    unit_cost = serializers.DecimalField(max_digits=18, decimal_places=6)
    idempotency_key = serializers.CharField(max_length=96, required=False, allow_blank=True)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True)


class MovementIssueSerializer(serializers.Serializer):
    warehouse_id = serializers.IntegerField()
    item_id = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=18, decimal_places=4)
    allow_negative = serializers.BooleanField(required=False, default=False)
    idempotency_key = serializers.CharField(max_length=96, required=False, allow_blank=True)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True)


class MovementAdjustSerializer(serializers.Serializer):
    warehouse_id = serializers.IntegerField()
    item_id = serializers.IntegerField()
    new_qty_on_hand = serializers.DecimalField(max_digits=18, decimal_places=4)
    idempotency_key = serializers.CharField(max_length=96, required=False, allow_blank=True)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True)


class TransferSerializer(serializers.Serializer):
    from_warehouse_id = serializers.IntegerField()
    to_warehouse_id = serializers.IntegerField()
    item_id = serializers.IntegerField()
    qty = serializers.DecimalField(max_digits=18, decimal_places=4)
    idempotency_key = serializers.CharField(max_length=96, required=False, allow_blank=True)
    note = serializers.CharField(max_length=255, required=False, allow_blank=True)


class LedgerQuerySerializer(serializers.Serializer):
    warehouse_id = serializers.IntegerField(required=False, min_value=1)
    item_id = serializers.IntegerField(required=False, min_value=1)
    movement_type = serializers.CharField(max_length=16, required=False, allow_blank=True)
    source_module = serializers.CharField(max_length=32, required=False, allow_blank=True)
    source_type = serializers.CharField(max_length=64, required=False, allow_blank=True)
    source_id = serializers.CharField(max_length=64, required=False, allow_blank=True)
    accounting_status = serializers.CharField(max_length=24, required=False, allow_blank=True)
    date_from = serializers.DateTimeField(required=False)
    date_to = serializers.DateTimeField(required=False)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=200)
    offset = serializers.IntegerField(required=False, min_value=0, default=0)
    page = serializers.IntegerField(required=False, min_value=1, default=1)
    page_size = serializers.IntegerField(required=False, min_value=1, max_value=200, default=50)

    def validate(self, attrs):
        date_from = attrs.get("date_from")
        date_to = attrs.get("date_to")
        if date_from and date_to and date_from > date_to:
            raise serializers.ValidationError({"date_to": "Debe ser mayor o igual a date_from"})
        return attrs


class BalanceListQuerySerializer(serializers.Serializer):
    warehouse_id = serializers.IntegerField(required=False, min_value=1)
    item_id = serializers.IntegerField(required=False, min_value=1)
    q = serializers.CharField(required=False, allow_blank=True)
    limit = serializers.IntegerField(required=False, min_value=1, max_value=200, default=50)
    offset = serializers.IntegerField(required=False, min_value=0, default=0)


class InventoryCommandIn(serializers.Serializer):
    command_id = serializers.UUIDField()
    type = serializers.CharField(max_length=64)
    payload = serializers.DictField(child=serializers.JSONField(), required=False, default=dict)


class InventoryCommandBatchIn(serializers.Serializer):
    commands = InventoryCommandIn(many=True)

    def validate_commands(self, commands):
        if not commands:
            raise serializers.ValidationError("Debe incluir al menos un comando.")
        if len(commands) > 200:
            raise serializers.ValidationError("Se permiten hasta 200 comandos por lote.")
        return commands


class WarehouseOut(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = ["id", "name", "code", "is_active", "created_at", "branch_id"]


class BrandOut(serializers.ModelSerializer):
    class Meta:
        model = InventoryBrand
        fields = ["id", "name", "is_active"]


class CategoryOut(serializers.ModelSerializer):
    class Meta:
        model = InventoryCategory
        fields = ["id", "name", "parent_id", "is_active"]


class TaxProfileOut(serializers.ModelSerializer):
    class Meta:
        model = InventoryTaxProfile
        fields = ["id", "code", "name", "tax_treatment", "rate", "is_active"]


class InventoryItemOut(serializers.ModelSerializer):
    brand_name = serializers.SerializerMethodField()
    category_name = serializers.SerializerMethodField()
    subcategory_name = serializers.SerializerMethodField()
    tax_profile_name = serializers.SerializerMethodField()

    class Meta:
        model = InventoryItem
        fields = [
            "id",
            "sku",
            "name",
            "uom",
            "item_type",
            "status",
            "short_name",
            "invoice_name",
            "description",
            "brand_id",
            "brand_name",
            "category_id",
            "category_name",
            "subcategory_id",
            "subcategory_name",
            "barcode",
            "barcode_type",
            "alternate_code",
            "search_tags",
            "purchase_enabled",
            "sales_enabled",
            "controls_stock",
            "transfer_enabled",
            "allow_returns",
            "uom_base",
            "uom_purchase",
            "uom_sale",
            "uom_conversions",
            "allow_fraction",
            "min_qty",
            "rounding_increment",
            "enabled_branch_ids",
            "default_branch_id",
            "default_warehouse_id",
            "min_stock",
            "max_stock",
            "reorder_point",
            "reorder_qty",
            "allow_negative_stock",
            "reserve_enabled",
            "internal_location",
            "costing_method",
            "initial_cost",
            "standard_cost",
            "currency",
            "last_known_cost",
            "preferred_supplier_id",
            "supplier_item_code",
            "lead_time_days",
            "purchase_moq",
            "purchase_multiple",
            "suggested_price",
            "min_sale_price",
            "allow_discount",
            "visible_pos",
            "visible_quote",
            "visible_invoice",
            "tax_profile_id",
            "tax_profile_name",
            "tax_treatment",
            "invoice_description",
            "use_lot",
            "use_serial",
            "use_expiry",
            "shelf_life_days",
            "quality_control_required",
            "allow_return_to_stock",
            "is_active",
            "version",
            "created_at",
            "updated_at",
        ]

    def get_brand_name(self, obj: InventoryItem) -> str:
        return str(getattr(obj.brand, "name", "") or "")

    def get_category_name(self, obj: InventoryItem) -> str:
        return str(getattr(obj.category, "name", "") or "")

    def get_subcategory_name(self, obj: InventoryItem) -> str:
        return str(getattr(obj.subcategory, "name", "") or "")

    def get_tax_profile_name(self, obj: InventoryItem) -> str:
        return str(getattr(obj.tax_profile, "name", "") or "")
