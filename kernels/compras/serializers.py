from __future__ import annotations

from rest_framework import serializers

from .models import PurchaseDocType


class PurchaseDocCreateSerializer(serializers.Serializer):
    doc_type = serializers.ChoiceField(choices=PurchaseDocType.choices)
    series = serializers.CharField(max_length=16, required=False, allow_blank=False, default="P")
    currency = serializers.CharField(max_length=8, required=False, allow_blank=False, default="NIO")
    supplier_name = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    supplier_ref = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    external_ref = serializers.CharField(max_length=96, required=False, allow_blank=True, default="")
    subtotal = serializers.DecimalField(max_digits=18, decimal_places=2)
    tax_total = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, default="0.00")
    total = serializers.DecimalField(max_digits=18, decimal_places=2)
    notes = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    metadata_json = serializers.JSONField(required=False, default=dict)
    idempotency_key = serializers.CharField(max_length=96, required=False, allow_blank=True, default="")

    def validate(self, attrs):
        if attrs["subtotal"] < 0 or attrs["tax_total"] < 0:
            raise serializers.ValidationError("subtotal/tax_total deben ser >= 0")
        if attrs["total"] < 0:
            raise serializers.ValidationError("total debe ser >= 0")
        if (attrs["subtotal"] + attrs["tax_total"]) != attrs["total"]:
            raise serializers.ValidationError("total debe ser subtotal + tax_total")
        return attrs


class PurchaseDocVoidSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True, default="VOID")
