from __future__ import annotations

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.conf import settings
from django.db import models
from django.utils import timezone


class PurchaseDocType(models.TextChoices):
    GOODS_RECEIPT = "GOODS_RECEIPT", "Goods Receipt"
    SUPPLIER_INVOICE = "SUPPLIER_INVOICE", "Supplier Invoice"
    SUPPLIER_CREDIT_NOTE = "SUPPLIER_CREDIT_NOTE", "Supplier Credit Note"
    SUPPLIER_PAYMENT = "SUPPLIER_PAYMENT", "Supplier Payment"
    ADJUSTMENT = "ADJUSTMENT", "Adjustment"


class PurchaseDocStatus(models.TextChoices):
    DRAFT = "DRAFT", "Draft"
    POSTED = "POSTED", "Posted"
    VOIDED = "VOIDED", "Voided"


class PurchaseSequence(models.Model):
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="proc_seq_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="proc_seq_branch")
    doc_type = models.CharField(max_length=32, choices=PurchaseDocType.choices)
    series = models.CharField(max_length=16, default="P")
    next_number = models.IntegerField(default=1)
    updated_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "branch", "doc_type", "series"], name="uniq_proc_seq"),
        ]


class PurchaseDocument(models.Model):
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="proc_docs_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="proc_docs_branch")

    doc_type = models.CharField(max_length=32, choices=PurchaseDocType.choices)
    status = models.CharField(max_length=16, choices=PurchaseDocStatus.choices, default=PurchaseDocStatus.DRAFT)

    series = models.CharField(max_length=16, default="P")
    number = models.IntegerField(default=0)

    currency = models.CharField(max_length=8, default="NIO")
    supplier_name = models.CharField(max_length=160, blank=True, default="")
    supplier_ref = models.CharField(max_length=64, blank=True, default="")
    external_ref = models.CharField(max_length=96, blank=True, default="")
    supplier_party = models.ForeignKey(
        "parties.Party",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="purchase_documents",
    )

    subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    tax_total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))
    total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0.00"))

    notes = models.CharField(max_length=255, blank=True, default="")
    metadata_json = models.JSONField(default=dict)

    idempotency_key = models.CharField(max_length=96, blank=True, default="")
    posted_at = models.DateTimeField(null=True, blank=True)
    voided_at = models.DateTimeField(null=True, blank=True)
    void_reason = models.CharField(max_length=255, blank=True, default="")

    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [
            models.Index(fields=["company", "branch", "created_at"], name="ix_proc_doc_c_b_ca"),
            models.Index(fields=["company", "branch", "doc_type", "status", "created_at"], name="ix_proc_doc_scope"),
            models.Index(fields=["company", "idempotency_key"], name="ix_proc_doc_idem"),
            models.Index(fields=["company", "supplier_party"], name="ix_proc_doc_co_supp_party"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["company", "idempotency_key"],
                condition=models.Q(idempotency_key__gt=""),
                name="uniq_proc_idem_per_company",
            ),
            models.UniqueConstraint(
                fields=["company", "branch", "doc_type", "series", "number"],
                name="uniq_proc_number",
            ),
        ]

    def clean(self):
        super().clean()
        if self.supplier_party_id and self.company_id and self.supplier_party.company_id != self.company_id:
            raise ValidationError({"supplier_party": "supplier_party debe pertenecer a PurchaseDocument.company."})
