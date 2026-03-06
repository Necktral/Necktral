from __future__ import annotations

from django.db import migrations, models
import django.db.models.deletion
from decimal import Decimal
from django.utils import timezone


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("iam", "0001_initial"),
        ("inventarios", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="BillingSequence",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("doc_type", models.CharField(choices=[("INVOICE", "Invoice"), ("CREDIT_NOTE", "Credit Note")], max_length=16)),
                ("series", models.CharField(default="A", max_length=16)),
                ("next_number", models.IntegerField(default=1)),
                ("updated_at", models.DateTimeField(default=timezone.now)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="bill_seq_company", to="iam.orgunit")),
                ("branch", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="bill_seq_branch", to="iam.orgunit")),
            ],
        ),
        migrations.CreateModel(
            name="BillingDocument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("doc_type", models.CharField(choices=[("INVOICE", "Invoice"), ("CREDIT_NOTE", "Credit Note")], max_length=16)),
                ("status", models.CharField(choices=[("DRAFT", "Draft"), ("ISSUED", "Issued"), ("VOIDED", "Voided")], default="DRAFT", max_length=16)),
                ("series", models.CharField(default="A", max_length=16)),
                ("number", models.IntegerField(default=0)),
                ("currency", models.CharField(default="NIO", max_length=8)),
                ("customer_name", models.CharField(blank=True, default="", max_length=160)),
                ("customer_ref", models.CharField(blank=True, default="", max_length=64)),
                ("subtotal", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=18)),
                ("tax_total", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=18)),
                ("total", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=18)),
                ("is_fiscal", models.BooleanField(default=False)),
                ("idempotency_key", models.CharField(blank=True, default="", max_length=96)),
                ("issued_at", models.DateTimeField(blank=True, null=True)),
                ("voided_at", models.DateTimeField(blank=True, null=True)),
                ("void_reason", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(default=timezone.now)),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="bill_docs_company", to="iam.orgunit")),
                ("branch", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="bill_docs_branch", to="iam.orgunit")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to="accounts.user")),
            ],
        ),
        migrations.CreateModel(
            name="BillingLine",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("description", models.CharField(max_length=200)),
                ("quantity", models.DecimalField(decimal_places=4, default=Decimal("1.0000"), max_digits=18)),
                ("unit_price", models.DecimalField(decimal_places=6, default=Decimal("0.000000"), max_digits=18)),
                ("tax_rate", models.DecimalField(decimal_places=4, default=Decimal("0.0000"), max_digits=8)),
                ("line_subtotal", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=18)),
                ("line_tax", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=18)),
                ("line_total", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=18)),
                ("doc", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="lines", to="facturacion.billingdocument")),
                ("inventory_item", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="billing_lines", to="inventarios.inventoryitem")),
            ],
        ),
        migrations.AddConstraint(
            model_name="billingsequence",
            constraint=models.UniqueConstraint(fields=("company", "branch", "doc_type", "series"), name="uniq_bill_seq"),
        ),
        migrations.AddConstraint(
            model_name="billingdocument",
            constraint=models.UniqueConstraint(condition=~models.Q(idempotency_key=""), fields=("company", "idempotency_key"), name="uniq_bill_idempotency_per_company"),
        ),
        migrations.AddConstraint(
            model_name="billingdocument",
            constraint=models.UniqueConstraint(fields=("company", "branch", "doc_type", "series", "number"), name="uniq_bill_number"),
        ),
    ]
