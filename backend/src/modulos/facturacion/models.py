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

    idempotency_key = models.CharField(max_length=96, blank=True, default="")

    issued_at = models.DateTimeField(null=True, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.CharField(max_length=255, blank=True, default="")

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["company", "branch", "created_at"]),
            models.Index(fields=["company", "branch", "doc_type", "status", "created_at"]),
            models.Index(fields=["company", "idempotency_key"]),
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
