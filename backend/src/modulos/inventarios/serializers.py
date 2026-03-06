from __future__ import annotations

from rest_framework import serializers

from .models import InventoryItem, UoM, Warehouse


class WarehouseCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    code = serializers.CharField(max_length=24, required=False, allow_blank=True)


class ItemCreateSerializer(serializers.Serializer):
    sku = serializers.CharField(max_length=64)
    name = serializers.CharField(max_length=160)
    uom = serializers.ChoiceField(choices=UoM.choices, required=False)


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


class WarehouseOut(serializers.ModelSerializer):
    class Meta:
        model = Warehouse
        fields = ["id", "name", "code", "is_active", "created_at"]


class InventoryItemOut(serializers.ModelSerializer):
    class Meta:
        model = InventoryItem
        fields = ["id", "sku", "name", "uom", "is_active", "created_at"]
