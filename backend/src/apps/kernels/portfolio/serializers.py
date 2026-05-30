"""
Portfolio Kernel Serializers
"""
from rest_framework import serializers

from .models import (
    Receivable,
    Payable,
    Credit,
    PaymentAllocation,
    InterestAccrual,
    PortfolioSettings,
)


class ReceivableSerializer(serializers.ModelSerializer):
    """Serializer for Receivable (CxC)"""

    total_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    outstanding_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    is_overdue = serializers.BooleanField(read_only=True)

    class Meta:
        model = Receivable
        fields = [
            "id",
            "obligation_id",
            "company",
            "branch",
            "party",
            "reference_type",
            "reference_id",
            "status",
            "currency",
            "principal_amount",
            "interest_amount",
            "fee_amount",
            "penalty_amount",
            "allocated_amount",
            "total_amount",
            "outstanding_amount",
            "issue_date",
            "due_date",
            "last_payment_date",
            "paid_date",
            "days_overdue",
            "aging_bucket",
            "is_overdue",
            "invoice_number",
            "invoice_date",
            "credit_limit",
            "credit_days",
            "risk_rating",
            "collection_priority",
            "collector_user",
            "accounting_status",
            "metadata_json",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "obligation_id",
            "allocated_amount",
            "days_overdue",
            "aging_bucket",
            "accounting_status",
            "created_at",
            "updated_at",
        ]


class PayableSerializer(serializers.ModelSerializer):
    """Serializer for Payable (CxP)"""

    total_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    outstanding_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    net_payable_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    discount_available = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)

    class Meta:
        model = Payable
        fields = [
            "id",
            "obligation_id",
            "company",
            "branch",
            "party",
            "reference_type",
            "reference_id",
            "status",
            "currency",
            "principal_amount",
            "interest_amount",
            "fee_amount",
            "penalty_amount",
            "allocated_amount",
            "total_amount",
            "outstanding_amount",
            "net_payable_amount",
            "issue_date",
            "due_date",
            "last_payment_date",
            "paid_date",
            "days_overdue",
            "aging_bucket",
            "supplier_invoice_number",
            "supplier_invoice_date",
            "early_payment_discount_rate",
            "early_payment_discount_days",
            "early_payment_discount_date",
            "discount_available",
            "withholding_tax_rate",
            "withholding_tax_amount",
            "payment_priority",
            "approver_user",
            "approved_at",
            "accounting_status",
            "metadata_json",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "obligation_id",
            "allocated_amount",
            "days_overdue",
            "aging_bucket",
            "accounting_status",
            "created_at",
            "updated_at",
        ]


class CreditSerializer(serializers.ModelSerializer):
    """Serializer for Credit"""

    total_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    outstanding_amount = serializers.DecimalField(max_digits=18, decimal_places=2, read_only=True)
    loan_to_value_ratio = serializers.DecimalField(max_digits=5, decimal_places=2, read_only=True, allow_null=True)

    class Meta:
        model = Credit
        fields = [
            "id",
            "obligation_id",
            "company",
            "branch",
            "credit_type",
            "credit_status",
            "lender_party",
            "borrower_party",
            "guarantor_party",
            "approved_amount",
            "disbursed_amount",
            "currency",
            "principal_amount",
            "interest_amount",
            "allocated_amount",
            "total_amount",
            "outstanding_amount",
            "interest_rate",
            "interest_calculation_method",
            "payment_frequency",
            "term_months",
            "grace_period_months",
            "approval_date",
            "disbursement_date",
            "first_payment_date",
            "maturity_date",
            "due_date",
            "late_payment_penalty_rate",
            "days_past_due",
            "collateral_type",
            "collateral_value",
            "loan_to_value_ratio",
            "collateral_description",
            "restructured_from",
            "restructure_count",
            "contract_number",
            "contract_document_ref",
            "accounting_status",
            "metadata_json",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "id",
            "obligation_id",
            "disbursed_amount",
            "allocated_amount",
            "accounting_status",
            "created_at",
            "updated_at",
        ]


class PaymentAllocationSerializer(serializers.ModelSerializer):
    """Serializer for Payment Allocation"""

    class Meta:
        model = PaymentAllocation
        fields = [
            "id",
            "allocation_id",
            "company",
            "payment_intent",
            "obligation_content_type",
            "obligation_object_id",
            "status",
            "allocated_amount",
            "currency",
            "principal_applied",
            "interest_applied",
            "fee_applied",
            "penalty_applied",
            "exchange_rate",
            "allocation_date",
            "applied_at",
            "reversed_at",
            "reversal_reason",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "allocation_id",
            "applied_at",
            "created_at",
        ]


class InterestAccrualSerializer(serializers.ModelSerializer):
    """Serializer for Interest Accrual"""

    class Meta:
        model = InterestAccrual
        fields = [
            "id",
            "accrual_id",
            "credit",
            "accrual_date",
            "period_start",
            "period_end",
            "days_in_period",
            "principal_balance",
            "interest_rate_applied",
            "accrued_interest",
            "is_capitalized",
            "capitalized_at",
            "calculation_method",
            "metadata_json",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "accrual_id",
            "created_at",
        ]


class PortfolioSettingsSerializer(serializers.ModelSerializer):
    """Serializer for Portfolio Settings"""

    class Meta:
        model = PortfolioSettings
        fields = [
            "company",
            "aging_buckets_json",
            "auto_allocate_payments",
            "allocation_strategy",
            "interest_accrual_frequency",
            "auto_capitalize_interest",
            "auto_writeoff_enabled",
            "auto_writeoff_days",
            "gate_mode",
            "functional_currency",
            "auto_convert_currency",
            "sync_with_billing",
            "sync_with_procurement",
            "integration_mode",
            "settings_json",
            "updated_at",
        ]
        read_only_fields = ["updated_at"]
