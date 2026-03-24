from __future__ import annotations

from rest_framework import serializers

from .models import RetailTicket


class TicketCreateIn(serializers.Serializer):
    terminal_id = serializers.IntegerField(required=False)
    cash_session_id = serializers.IntegerField(required=False)
    customer_name = serializers.CharField(required=False, allow_blank=True, max_length=200)
    customer_ref = serializers.CharField(required=False, allow_blank=True, max_length=96)
    ticket_kind = serializers.ChoiceField(choices=RetailTicket.TicketKind.choices, required=False)


class TicketLineCreateIn(serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=1)
    item_id = serializers.IntegerField(min_value=1)
    qty = serializers.DecimalField(max_digits=18, decimal_places=4)
    unit_price = serializers.DecimalField(max_digits=18, decimal_places=6, required=False)
    discount_amount = serializers.DecimalField(max_digits=18, decimal_places=2, required=False)


class TicketLinePatchIn(serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=1)
    qty = serializers.DecimalField(max_digits=18, decimal_places=4, required=False)
    unit_price = serializers.DecimalField(max_digits=18, decimal_places=6, required=False)
    discount_amount = serializers.DecimalField(max_digits=18, decimal_places=2, required=False)


class TicketLineDeleteIn(serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=1)


class TicketHoldIn(serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)


class TicketCheckoutPreviewIn(serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=1, required=False)


class TicketCheckoutCommitIn(serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=1)
    idempotency_key = serializers.CharField(max_length=96)
    cash_received = serializers.DecimalField(max_digits=18, decimal_places=2)


class TicketVoidIn(serializers.Serializer):
    expected_version = serializers.IntegerField(min_value=1)
    idempotency_key = serializers.CharField(max_length=96)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)


class RetailReturnLineIn(serializers.Serializer):
    line_id = serializers.IntegerField(min_value=1)
    qty = serializers.DecimalField(max_digits=18, decimal_places=4)


class RetailReturnCreateIn(serializers.Serializer):
    sale_id = serializers.IntegerField(min_value=1)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)
    idempotency_key = serializers.CharField(max_length=96)
    lines = RetailReturnLineIn(many=True, allow_empty=False)


class RetailCompensationRetryIn(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=96)
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)
