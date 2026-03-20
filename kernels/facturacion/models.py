from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class DocType(models.TextChoices):
    INVOICE = "INVOICE", "Invoice"
    CREDIT_NOTE = "CREDIT_NOTE", "Credit Note"


class DocStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    ISSUED = "ISSUED", "Issued"
    VOIDED = "VOIDED", "Voided"


class FiscalMode(models.TextChoices):
    NOOP = "NOOP", "Noop"
    A = "A", "Adapter A"
    B = "B", "Adapter B"


class FiscalStatus(models.TextChoices):
    NUMBER_RESERVED = "NUMBER_RESERVED", "Number Reserved"
    ISSUED = "ISSUED", "Issued"
    PRINTED = "PRINTED", "Printed"
    FAILED_PRINT = "FAILED_PRINT", "Failed Print"
    CONTINGENCY = "CONTINGENCY", "Contingency"
    VOIDED = "VOIDED", "Voided"


class BillingSequence(models.Model):
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="bill_seq_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="bill_seq_branch")
    doc_type = models.CharField(max_length=16, choices=DocType.choices)
    series = models.CharField(max_length=16, default="A")
    next_number = models.IntegerField(default=1)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "branch", "doc_type", "series"], name="uniq_bill_seq"),
        ]


class BillingDocument(models.Model):
    class AccountingStatus(models.TextChoices):
        DISABLED = "DISABLED", "Disabled"
        UNSUPPORTED = "UNSUPPORTED", "Unsupported"
        PENDING_RULESET = "PENDING_RULESET", "Pending ruleset"
        PENDING_RULE = "PENDING_RULE", "Pending rule"
        DRAFT_EXCEPTION = "DRAFT_EXCEPTION", "Draft exception"
        DRAFT_VALIDATED = "DRAFT_VALIDATED", "Draft validated"
        POSTED = "POSTED", "Posted"

    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="bill_docs_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="bill_docs_branch")

    doc_type = models.CharField(max_length=16, choices=DocType.choices)
    status = models.CharField(max_length=16, choices=DocStatus.choices, default=DocStatus.DRAFT)

    series = models.CharField(max_length=16, default="A")
    number = models.IntegerField(default=0)  # asignado al emitir

    currency = models.CharField(max_length=8, default="NIO")
    customer_name = models.CharField(max_length=160, blank=True, default="")
    customer_ref = models.CharField(max_length=64, blank=True, default="")

    subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    tax_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    is_fiscal = models.BooleanField(default=False)
    fiscal_mode_resolved = models.CharField(max_length=8, choices=FiscalMode.choices, default=FiscalMode.NOOP)
    fiscal_status = models.CharField(max_length=24, choices=FiscalStatus.choices, blank=True, default="")
    fiscal_reference = models.CharField(max_length=96, blank=True, default="")
    fiscal_evidence_id = models.CharField(max_length=96, blank=True, default="")
    print_attempt_count = models.PositiveIntegerField(default=0)
    last_print_error = models.CharField(max_length=255, blank=True, default="")
    contingency_reason = models.CharField(max_length=255, blank=True, default="")
    contingency_at = models.DateTimeField(null=True, blank=True)
    printed_at = models.DateTimeField(null=True, blank=True)
    fiscal_metadata_json = models.JSONField(default=dict)

    idempotency_key = models.CharField(max_length=96, blank=True, default="")
    source_module = models.CharField(max_length=32, blank=True, default="")
    source_type = models.CharField(max_length=64, blank=True, default="")
    source_id = models.CharField(max_length=64, blank=True, default="")

    issued_at = models.DateTimeField(null=True, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.CharField(max_length=255, blank=True, default="")

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(default=timezone.now)

    accounting_status = models.CharField(
        max_length=24,
        choices=AccountingStatus.choices,
        blank=True,
        default="",
    )
    accounting_error = models.CharField(max_length=255, blank=True, default="")
    accounting_economic_event = models.ForeignKey(
        "accounting.EconomicEvent",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="billing_documents",
    )
    accounting_journal_draft = models.ForeignKey(
        "accounting.JournalDraft",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="billing_documents",
    )
    accounting_journal_entry = models.ForeignKey(
        "accounting.JournalEntry",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="billing_documents",
    )

    class Meta:
        indexes = [
            models.Index(fields=["company", "branch", "created_at"]),
            models.Index(fields=["company", "branch", "doc_type", "status", "created_at"]),
            models.Index(fields=["company", "idempotency_key"]),
            models.Index(fields=["company", "branch", "fiscal_mode_resolved", "fiscal_status"]),
            models.Index(fields=["company", "branch", "accounting_status", "created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uniq_bill_idempotency_per_company",
            ),
            models.UniqueConstraint(fields=["company", "branch", "doc_type", "series", "number"], name="uniq_bill_number"),
        ]


class BillingLine(models.Model):
    doc = models.ForeignKey(BillingDocument, on_delete=models.CASCADE, related_name="lines")

    description = models.CharField(max_length=200)
    quantity = models.DecimalField(max_digits=18, decimal_places=4, default=Decimal("1.0000"))
    unit_price = models.DecimalField(max_digits=18, decimal_places=6, default=Decimal("0.000000"))
    tax_rate = models.DecimalField(max_digits=8, decimal_places=4, default=Decimal("0.0000"))  # 0.1500 = 15%

    line_subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    line_tax = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    line_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    inventory_item = models.ForeignKey(
        "inventarios.InventoryItem",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="billing_lines",
    )

    class Meta:
        indexes = [
            models.Index(fields=["doc"]),
        ]


class BranchFiscalConfig(models.Model):
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="bill_fiscal_cfg_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="bill_fiscal_cfg_branch")
    fiscal_mode = models.CharField(max_length=8, choices=FiscalMode.choices, default=FiscalMode.NOOP)
    adapter_code = models.CharField(max_length=32, blank=True, default="")
    print_required = models.BooleanField(default=True)
    strict_integrity = models.BooleanField(default=True)
    contingency_max_attempts = models.PositiveSmallIntegerField(default=5)
    is_active = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "branch"], name="uniq_bill_fiscal_cfg_company_branch"),
        ]
        indexes = [
            models.Index(fields=["company", "branch", "is_active"]),
        ]


class FiscalPrintJob(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        RETRY = "RETRY", "Retry"
        PRINTED = "PRINTED", "Printed"
        FAILED = "FAILED", "Failed"

    doc = models.ForeignKey(BillingDocument, on_delete=models.CASCADE, related_name="fiscal_print_jobs")
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="bill_print_jobs_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="bill_print_jobs_branch")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    attempt_count = models.PositiveIntegerField(default=0)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    last_error = models.CharField(max_length=255, blank=True, default="")
    idempotency_key = models.CharField(max_length=96, blank=True, default="")
    requested_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        indexes = [
            models.Index(fields=["status", "next_attempt_at", "created_at"]),
            models.Index(fields=["company", "branch", "status", "created_at"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["doc", "idempotency_key"],
                condition=~models.Q(idempotency_key=""),
                name="uniq_bill_print_job_doc_idempotency",
            ),
        ]
