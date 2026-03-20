from __future__ import annotations

from decimal import Decimal

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("iam", "0003_orgunit_parent_type_name_idx"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="PurchaseDocument",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("doc_type", models.CharField(choices=[("GOODS_RECEIPT", "Goods Receipt"), ("SUPPLIER_INVOICE", "Supplier Invoice"), ("SUPPLIER_CREDIT_NOTE", "Supplier Credit Note"), ("SUPPLIER_PAYMENT", "Supplier Payment"), ("ADJUSTMENT", "Adjustment")], max_length=32)),
                ("status", models.CharField(choices=[("DRAFT", "Draft"), ("POSTED", "Posted"), ("VOIDED", "Voided")], default="DRAFT", max_length=16)),
                ("series", models.CharField(default="P", max_length=16)),
                ("number", models.IntegerField(default=0)),
                ("currency", models.CharField(default="NIO", max_length=8)),
                ("supplier_name", models.CharField(blank=True, default="", max_length=160)),
                ("supplier_ref", models.CharField(blank=True, default="", max_length=64)),
                ("external_ref", models.CharField(blank=True, default="", max_length=96)),
                ("subtotal", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=18)),
                ("tax_total", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=18)),
                ("total", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=18)),
                ("notes", models.CharField(blank=True, default="", max_length=255)),
                ("metadata_json", models.JSONField(default=dict)),
                ("idempotency_key", models.CharField(blank=True, default="", max_length=96)),
                ("posted_at", models.DateTimeField(blank=True, null=True)),
                ("voided_at", models.DateTimeField(blank=True, null=True)),
                ("void_reason", models.CharField(blank=True, default="", max_length=255)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("branch", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="proc_docs_branch", to="iam.orgunit")),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="proc_docs_company", to="iam.orgunit")),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "indexes": [
                    models.Index(fields=["company", "branch", "created_at"], name="ix_proc_doc_c_b_ca"),
                    models.Index(fields=["company", "branch", "doc_type", "status", "created_at"], name="ix_proc_doc_scope"),
                    models.Index(fields=["company", "idempotency_key"], name="ix_proc_doc_idem"),
                ],
            },
        ),
        migrations.CreateModel(
            name="PurchaseSequence",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("doc_type", models.CharField(choices=[("GOODS_RECEIPT", "Goods Receipt"), ("SUPPLIER_INVOICE", "Supplier Invoice"), ("SUPPLIER_CREDIT_NOTE", "Supplier Credit Note"), ("SUPPLIER_PAYMENT", "Supplier Payment"), ("ADJUSTMENT", "Adjustment")], max_length=32)),
                ("series", models.CharField(default="P", max_length=16)),
                ("next_number", models.IntegerField(default=1)),
                ("updated_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("branch", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="proc_seq_branch", to="iam.orgunit")),
                ("company", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="proc_seq_company", to="iam.orgunit")),
            ],
        ),
        migrations.AddConstraint(
            model_name="purchasedocument",
            constraint=models.UniqueConstraint(condition=models.Q(("idempotency_key__gt", "")), fields=("company", "idempotency_key"), name="uniq_proc_idem_per_company"),
        ),
        migrations.AddConstraint(
            model_name="purchasedocument",
            constraint=models.UniqueConstraint(fields=("company", "branch", "doc_type", "series", "number"), name="uniq_proc_number"),
        ),
        migrations.AddConstraint(
            model_name="purchasesequence",
            constraint=models.UniqueConstraint(fields=("company", "branch", "doc_type", "series"), name="uniq_proc_seq"),
        ),
    ]
