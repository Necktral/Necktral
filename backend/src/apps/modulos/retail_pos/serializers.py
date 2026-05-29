from __future__ import annotations

from decimal import Decimal
from typing import Any

from rest_framework import serializers

from apps.modulos.estacion_servicios.models import FuelPaymentMethod, FuelPriceUOM, FuelProduct, FuelSaleType, FuelVolumeUOM

from .models import PeripheralCapability, PeripheralKind, PeripheralStatus, PosTicketLine, PosTicketStatus


class PosSessionOpenIn(serializers.Serializer):
    opening_amount = serializers.DecimalField(max_digits=18, decimal_places=2, required=False, default=Decimal("0.00"))
    note = serializers.CharField(required=False, allow_blank=True, default="")


class PosSessionCloseIn(serializers.Serializer):
    counted_amount = serializers.DecimalField(max_digits=18, decimal_places=2)
    note = serializers.CharField(required=False, allow_blank=True, default="")


class PosTicketOpenIn(serializers.Serializer):
    shift_id = serializers.IntegerField()
    idempotency_key = serializers.CharField(required=False, allow_blank=True, default="")
    external_ref = serializers.CharField(required=False, allow_blank=True, default="")
    customer_name = serializers.CharField(required=False, allow_blank=True, default="")
    customer_ref = serializers.CharField(required=False, allow_blank=True, default="")
    customer_party_id = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    sale_type = serializers.ChoiceField(choices=FuelSaleType.choices, required=False, default=FuelSaleType.PUBLIC)
    payment_method = serializers.ChoiceField(choices=FuelPaymentMethod.choices, required=False, default=FuelPaymentMethod.CASH)


class PosTicketLineIn(serializers.Serializer):
    product = serializers.ChoiceField(choices=FuelProduct.choices)
    volume = serializers.DecimalField(max_digits=12, decimal_places=4)
    volume_uom = serializers.ChoiceField(choices=FuelVolumeUOM.choices, required=False, default=FuelVolumeUOM.LITER)
    unit_price_entered = serializers.DecimalField(max_digits=12, decimal_places=4)
    unit_price_uom = serializers.ChoiceField(choices=FuelPriceUOM.choices, required=False, default=FuelPriceUOM.PER_LITER)
    metadata = serializers.DictField(required=False, default=dict)


class PosTicketCheckoutIn(serializers.Serializer):
    line = PosTicketLineIn(required=False)


class PosTicketVoidIn(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="VOID")


class PosTicketCompensateRetryIn(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="MANUAL_RETRY")


class PosPeripheralStatusUpsertIn(serializers.Serializer):
    connector_id = serializers.CharField(max_length=96)
    connector_version = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    device_key = serializers.CharField(max_length=96)
    device_kind = serializers.ChoiceField(choices=PeripheralKind.choices)
    capability_level = serializers.ChoiceField(
        choices=PeripheralCapability.choices,
        required=False,
        default=PeripheralCapability.EXPERIMENTAL,
    )
    status = serializers.ChoiceField(choices=PeripheralStatus.choices, required=False, default=PeripheralStatus.ONLINE)
    metadata = serializers.DictField(required=False, default=dict)


class PosEdgeChallengeCreateIn(serializers.Serializer):
    connector_id = serializers.CharField(max_length=96)
    connector_version = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    metadata = serializers.DictField(required=False, default=dict)


class PosEdgeHandshakeDeviceIn(serializers.Serializer):
    device_key = serializers.CharField(max_length=96)
    device_kind = serializers.ChoiceField(choices=PeripheralKind.choices)
    capability_level = serializers.ChoiceField(
        choices=PeripheralCapability.choices,
        required=False,
        default=PeripheralCapability.EXPERIMENTAL,
    )
    status = serializers.ChoiceField(choices=PeripheralStatus.choices, required=False, default=PeripheralStatus.ONLINE)
    metadata = serializers.DictField(required=False, default=dict)


class PosEdgeHandshakeIn(serializers.Serializer):
    challenge_id = serializers.UUIDField()
    connector_id = serializers.CharField(max_length=96)
    connector_version = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    signature = serializers.CharField(max_length=256)
    capability_registry = serializers.DictField(required=False, default=dict)
    devices = PosEdgeHandshakeDeviceIn(many=True, required=False, default=list)
    metadata = serializers.DictField(required=False, default=dict)

    def validate_capability_registry(self, value: dict[str, Any]) -> dict[str, Any]:
        normalized: dict[str, Any] = {}
        for key, raw in (value or {}).items():
            device_kind = str(key or "").strip().upper()
            if not device_kind:
                continue
            capability = str(raw or "").strip().lower()
            if capability not in PeripheralCapability.values:
                raise serializers.ValidationError(f"capability inválida para {device_kind}")
            normalized[device_kind] = capability
        return normalized


class PosTicketLineOut(serializers.ModelSerializer):
    class Meta:
        model = PosTicketLine
        fields = [
            "id",
            "line_no",
            "line_type",
            "product",
            "volume",
            "volume_uom",
            "unit_price_entered",
            "unit_price_uom",
            "amount_estimated",
            "metadata",
        ]


class PosTicketOut(serializers.Serializer):
    id = serializers.IntegerField()
    status = serializers.ChoiceField(choices=PosTicketStatus.choices)
    session_id = serializers.IntegerField()
    shift_id = serializers.IntegerField()
    external_ref = serializers.CharField(allow_blank=True)
    correlation_id = serializers.CharField(allow_blank=True)
    sale_type = serializers.CharField()
    payment_method = serializers.CharField()
    total_amount = serializers.CharField()
    customer_name = serializers.CharField(allow_blank=True)
    customer_ref = serializers.CharField(allow_blank=True)
    customer_party_id = serializers.IntegerField(allow_null=True)
    customer_party_display_name = serializers.CharField(allow_blank=True)
    sale_id = serializers.IntegerField(allow_null=True)
    payment_intent_id = serializers.CharField(allow_blank=True)
    cash_movement_id = serializers.IntegerField(allow_null=True)
    created_at = serializers.DateTimeField()
    updated_at = serializers.DateTimeField()
    checkout_started_at = serializers.DateTimeField(allow_null=True)
    paid_at = serializers.DateTimeField(allow_null=True)
    closed_at = serializers.DateTimeField(allow_null=True)
    voided_at = serializers.DateTimeField(allow_null=True)
    void_reason = serializers.CharField(allow_blank=True)
    last_error = serializers.CharField(allow_blank=True)
    compensation_pending = serializers.BooleanField()
    compensation_attempts = serializers.IntegerField()
    compensation_last_error = serializers.CharField(allow_blank=True)
    compensation_next_retry_at = serializers.DateTimeField(allow_null=True)
    last_compensation_at = serializers.DateTimeField(allow_null=True)
    lines = PosTicketLineOut(many=True)
