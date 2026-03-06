from __future__ import annotations

from rest_framework import serializers

from .models import BillingDocument, DocType


class LineInSerializer(serializers.Serializer):
    description = serializers.CharField(max_length=200)
    quantity = serializers.DecimalField(max_digits=18, decimal_places=4)
    unit_price = serializers.DecimalField(max_digits=18, decimal_places=6)
    tax_rate = serializers.DecimalField(max_digits=8, decimal_places=4, required=False)
    inventory_item_id = serializers.IntegerField(required=False, allow_null=True)


class DocCreateSerializer(serializers.Serializer):
    doc_type = serializers.ChoiceField(choices=DocType.choices)
    series = serializers.CharField(max_length=16, required=False, allow_blank=True)
    currency = serializers.CharField(max_length=8, required=False, allow_blank=True)
    customer_name = serializers.CharField(max_length=160, required=False, allow_blank=True)
    customer_ref = serializers.CharField(max_length=64, required=False, allow_blank=True)
    is_fiscal = serializers.BooleanField(required=False, default=False)
    idempotency_key = serializers.CharField(max_length=96, required=False, allow_blank=True)
    lines = LineInSerializer(many=True)


class DocIssueSerializer(serializers.Serializer):
    apply_inventory = serializers.BooleanField(required=False, default=False)
    warehouse_id = serializers.IntegerField(required=False)  # requerido si apply_inventory


class DocVoidSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True)


class InvoiceCreateIn(serializers.Serializer):
    customer_name = serializers.CharField(max_length=255)
    total_amount = serializers.DecimalField(max_digits=14, decimal_places=2)


class InvoiceOut(serializers.ModelSerializer):
    total_amount = serializers.DecimalField(max_digits=18, decimal_places=2, source="total", read_only=True)

    class Meta:
        model = BillingDocument
        fields = ["id", "status", "customer_name", "total_amount", "created_at"]
