from __future__ import annotations

from rest_framework import serializers

from apps.modulos.common.tender import TENDER_PAYMENT_METHOD_CHOICES

from .models import BillingDocument, BranchFiscalConfig, DocStatus, DocType, FiscalMode


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
    customer_party_id = serializers.IntegerField(required=False, allow_null=True)
    is_fiscal = serializers.BooleanField(required=False, default=False)
    idempotency_key = serializers.CharField(max_length=96, required=False, allow_blank=True)
    payment_method = serializers.ChoiceField(
        choices=TENDER_PAYMENT_METHOD_CHOICES,
        required=False,
        allow_blank=True,
    )
    lines = LineInSerializer(many=True)

    def validate(self, attrs):
        customer_party_id = attrs.get("customer_party_id")
        if customer_party_id is not None and int(customer_party_id) <= 0:
            raise serializers.ValidationError("customer_party_id debe ser > 0")
        return attrs


class DocListQuerySerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=DocStatus.choices, required=False)
    doc_type = serializers.ChoiceField(choices=DocType.choices, required=False)
    q = serializers.CharField(max_length=160, required=False, allow_blank=True)
    date_from = serializers.DateField(required=False, input_formats=["%Y-%m-%d"])
    date_to = serializers.DateField(required=False, input_formats=["%Y-%m-%d"])
    ordering = serializers.ChoiceField(
        choices=["-created_at", "created_at", "-id", "id", "-total", "total"],
        required=False,
        default="-created_at",
    )


class DocIssueSerializer(serializers.Serializer):
    apply_inventory = serializers.BooleanField(required=False, default=False)
    warehouse_id = serializers.IntegerField(required=False)  # requerido si apply_inventory
    print_after_issue = serializers.BooleanField(required=False, default=False)
    idempotency_key = serializers.CharField(max_length=96, required=False, allow_blank=True)


class DocVoidSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True)


class DocPrintSerializer(serializers.Serializer):
    idempotency_key = serializers.CharField(max_length=96, required=False, allow_blank=True)


class DocContingencySerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


class DocContingencyResolveSerializer(serializers.Serializer):
    action = serializers.ChoiceField(choices=["RETRY_PRINT", "VOID"])
    idempotency_key = serializers.CharField(max_length=96, required=False, allow_blank=True)
    reason = serializers.CharField(max_length=255, required=False, allow_blank=True)


class BranchFiscalConfigOut(serializers.ModelSerializer):
    class Meta:
        model = BranchFiscalConfig
        fields = [
            "fiscal_mode",
            "adapter_code",
            "print_required",
            "strict_integrity",
            "contingency_max_attempts",
            "is_active",
            "updated_at",
            "created_at",
        ]


class BranchFiscalConfigUpdateIn(serializers.Serializer):
    fiscal_mode = serializers.ChoiceField(choices=FiscalMode.choices, required=False)
    adapter_code = serializers.CharField(max_length=32, required=False, allow_blank=True)
    print_required = serializers.BooleanField(required=False)
    strict_integrity = serializers.BooleanField(required=False)
    contingency_max_attempts = serializers.IntegerField(min_value=1, max_value=20, required=False)
    is_active = serializers.BooleanField(required=False)


class InvoiceCreateIn(serializers.Serializer):
    customer_name = serializers.CharField(max_length=255)
    total_amount = serializers.DecimalField(max_digits=14, decimal_places=2)


class InvoiceOut(serializers.ModelSerializer):
    total_amount = serializers.DecimalField(max_digits=18, decimal_places=2, source="total", read_only=True)

    class Meta:
        model = BillingDocument
        fields = ["id", "status", "customer_name", "total_amount", "created_at"]
