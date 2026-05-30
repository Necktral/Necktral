"""
Portfolio Kernel Admin
"""
from django.contrib import admin
from django.utils.html import format_html

from .models import (
    Receivable,
    Payable,
    Credit,
    PaymentAllocation,
    InterestAccrual,
    PortfolioSettings,
)


@admin.register(Receivable)
class ReceivableAdmin(admin.ModelAdmin):
    list_display = [
        "obligation_id",
        "invoice_number",
        "party",
        "principal_amount",
        "outstanding_amount",
        "status",
        "aging_bucket",
        "due_date",
        "is_overdue",
    ]
    list_filter = ["status", "aging_bucket", "currency", "accounting_status", "created_at"]
    search_fields = ["invoice_number", "party__name", "notes"]
    readonly_fields = [
        "obligation_id",
        "allocated_amount",
        "days_overdue",
        "aging_bucket",
        "accounting_status",
        "created_at",
        "updated_at",
    ]
    fieldsets = (
        ("Identification", {
            "fields": ("obligation_id", "company", "branch", "party")
        }),
        ("Reference", {
            "fields": ("reference_type", "reference_id", "invoice_number", "invoice_date")
        }),
        ("Amounts", {
            "fields": (
                "currency",
                "principal_amount",
                "interest_amount",
                "fee_amount",
                "penalty_amount",
                "allocated_amount",
            )
        }),
        ("Dates", {
            "fields": ("issue_date", "due_date", "last_payment_date", "paid_date", "written_off_date")
        }),
        ("Status & Aging", {
            "fields": ("status", "days_overdue", "aging_bucket", "accounting_status")
        }),
        ("Credit Terms", {
            "fields": ("credit_limit", "credit_days")
        }),
        ("Collection", {
            "fields": ("risk_rating", "collection_priority", "collector_user")
        }),
        ("Metadata", {
            "fields": ("metadata_json", "notes"),
            "classes": ("collapse",)
        }),
        ("Audit", {
            "fields": ("created_by", "created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )

    def outstanding_amount(self, obj):
        return f"{obj.outstanding_amount} {obj.currency}"

    def is_overdue(self, obj):
        if obj.is_overdue:
            return format_html('<span style="color: red;">✗ Overdue</span>')
        return format_html('<span style="color: green;">✓ Current</span>')


@admin.register(Payable)
class PayableAdmin(admin.ModelAdmin):
    list_display = [
        "obligation_id",
        "supplier_invoice_number",
        "party",
        "principal_amount",
        "outstanding_amount",
        "status",
        "payment_priority",
        "due_date",
    ]
    list_filter = ["status", "payment_priority", "currency", "accounting_status", "created_at"]
    search_fields = ["supplier_invoice_number", "party__name", "notes"]
    readonly_fields = [
        "obligation_id",
        "allocated_amount",
        "days_overdue",
        "aging_bucket",
        "withholding_tax_amount",
        "accounting_status",
        "created_at",
        "updated_at",
    ]
    fieldsets = (
        ("Identification", {
            "fields": ("obligation_id", "company", "branch", "party")
        }),
        ("Reference", {
            "fields": ("reference_type", "reference_id", "supplier_invoice_number", "supplier_invoice_date")
        }),
        ("Amounts", {
            "fields": (
                "currency",
                "principal_amount",
                "interest_amount",
                "fee_amount",
                "penalty_amount",
                "allocated_amount",
            )
        }),
        ("Withholding", {
            "fields": ("withholding_tax_rate", "withholding_tax_amount")
        }),
        ("Early Payment Discount", {
            "fields": (
                "early_payment_discount_rate",
                "early_payment_discount_days",
                "early_payment_discount_date"
            )
        }),
        ("Dates", {
            "fields": ("issue_date", "due_date", "last_payment_date", "paid_date")
        }),
        ("Status & Priority", {
            "fields": ("status", "days_overdue", "aging_bucket", "payment_priority", "accounting_status")
        }),
        ("Approval", {
            "fields": ("approver_user", "approved_at")
        }),
        ("Metadata", {
            "fields": ("metadata_json", "notes"),
            "classes": ("collapse",)
        }),
        ("Audit", {
            "fields": ("created_by", "created_at", "updated_at"),
            "classes": ("collapse",)
        }),
    )

    def outstanding_amount(self, obj):
        return f"{obj.outstanding_amount} {obj.currency}"


@admin.register(Credit)
class CreditAdmin(admin.ModelAdmin):
    list_display = [
        "obligation_id",
        "contract_number",
        "credit_type",
        "borrower_party",
        "approved_amount",
        "disbursed_amount",
        "credit_status",
        "maturity_date",
    ]
    list_filter = ["credit_status", "credit_type", "currency", "created_at"]
    search_fields = ["contract_number", "borrower_party__name", "lender_party__name"]
    readonly_fields = [
        "obligation_id",
        "disbursed_amount",
        "allocated_amount",
        "days_overdue",
        "aging_bucket",
        "days_past_due",
        "accounting_status",
        "created_at",
        "updated_at",
    ]
    fieldsets = (
        ("Identification", {
            "fields": ("obligation_id", "company", "branch", "contract_number")
        }),
        ("Parties", {
            "fields": ("lender_party", "borrower_party", "guarantor_party")
        }),
        ("Credit Terms", {
            "fields": (
                "credit_type",
                "credit_status",
                "approved_amount",
                "disbursed_amount",
                "currency",
            )
        }),
        ("Interest", {
            "fields": (
                "interest_rate",
                "interest_calculation_method",
                "payment_frequency",
                "term_months",
                "grace_period_months",
            )
        }),
        ("Amounts", {
            "fields": (
                "principal_amount",
                "interest_amount",
                "fee_amount",
                "penalty_amount",
                "allocated_amount",
            )
        }),
        ("Dates", {
            "fields": (
                "approval_date",
                "disbursement_date",
                "first_payment_date",
                "maturity_date",
                "last_payment_date",
                "paid_date",
            )
        }),
        ("Late Payment", {
            "fields": ("late_payment_penalty_rate", "days_past_due", "days_overdue", "aging_bucket")
        }),
        ("Collateral", {
            "fields": ("collateral_type", "collateral_value", "collateral_description"),
            "classes": ("collapse",)
        }),
        ("Restructure", {
            "fields": ("restructured_from", "restructure_count"),
            "classes": ("collapse",)
        }),
        ("Metadata", {
            "fields": ("reference_type", "reference_id", "metadata_json", "notes"),
            "classes": ("collapse",)
        }),
        ("Audit", {
            "fields": ("created_by", "created_at", "updated_at", "accounting_status"),
            "classes": ("collapse",)
        }),
    )


@admin.register(PaymentAllocation)
class PaymentAllocationAdmin(admin.ModelAdmin):
    list_display = [
        "allocation_id",
        "payment_intent",
        "allocated_amount",
        "status",
        "allocation_date",
        "applied_at",
    ]
    list_filter = ["status", "allocation_date", "created_at"]
    readonly_fields = [
        "allocation_id",
        "applied_at",
        "reversed_at",
        "created_at",
    ]
    fieldsets = (
        ("Identification", {
            "fields": ("allocation_id", "company")
        }),
        ("Payment", {
            "fields": ("payment_intent", "status")
        }),
        ("Obligation", {
            "fields": ("obligation_content_type", "obligation_object_id")
        }),
        ("Amounts", {
            "fields": (
                "allocated_amount",
                "currency",
                "principal_applied",
                "interest_applied",
                "fee_applied",
                "penalty_applied",
            )
        }),
        ("Exchange", {
            "fields": ("exchange_rate",)
        }),
        ("Dates", {
            "fields": ("allocation_date", "applied_at", "reversed_at")
        }),
        ("Reversal", {
            "fields": ("reversal_reason",),
            "classes": ("collapse",)
        }),
        ("Audit", {
            "fields": ("created_by", "created_at"),
            "classes": ("collapse",)
        }),
    )


@admin.register(InterestAccrual)
class InterestAccrualAdmin(admin.ModelAdmin):
    list_display = [
        "accrual_id",
        "credit",
        "accrual_date",
        "accrued_interest",
        "is_capitalized",
    ]
    list_filter = ["is_capitalized", "accrual_date", "created_at"]
    readonly_fields = [
        "accrual_id",
        "capitalized_at",
        "created_at",
    ]
    fieldsets = (
        ("Identification", {
            "fields": ("accrual_id", "credit")
        }),
        ("Period", {
            "fields": ("accrual_date", "period_start", "period_end", "days_in_period")
        }),
        ("Calculation", {
            "fields": (
                "principal_balance",
                "interest_rate_applied",
                "accrued_interest",
                "calculation_method",
            )
        }),
        ("Capitalization", {
            "fields": ("is_capitalized", "capitalized_at")
        }),
        ("Metadata", {
            "fields": ("metadata_json",),
            "classes": ("collapse",)
        }),
        ("Audit", {
            "fields": ("calculated_by", "created_at"),
            "classes": ("collapse",)
        }),
    )


@admin.register(PortfolioSettings)
class PortfolioSettingsAdmin(admin.ModelAdmin):
    list_display = [
        "company",
        "auto_allocate_payments",
        "integration_mode",
        "gate_mode",
        "updated_at",
    ]
    readonly_fields = ["updated_at"]
    fieldsets = (
        ("Company", {
            "fields": ("company",)
        }),
        ("Aging", {
            "fields": ("aging_buckets_json",)
        }),
        ("Payment Allocation", {
            "fields": ("auto_allocate_payments", "allocation_strategy")
        }),
        ("Interest", {
            "fields": ("interest_accrual_frequency", "auto_capitalize_interest")
        }),
        ("Write-offs", {
            "fields": ("auto_writeoff_enabled", "auto_writeoff_days")
        }),
        ("Gates", {
            "fields": ("gate_mode",)
        }),
        ("Currency", {
            "fields": ("functional_currency", "auto_convert_currency")
        }),
        ("Integration", {
            "fields": ("sync_with_billing", "sync_with_procurement", "integration_mode")
        }),
        ("Additional Settings", {
            "fields": ("settings_json",),
            "classes": ("collapse",)
        }),
        ("Audit", {
            "fields": ("updated_by", "updated_at"),
            "classes": ("collapse",)
        }),
    )
