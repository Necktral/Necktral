from __future__ import annotations

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [
        ("facturacion", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="billingdocument",
            name="contingency_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="billingdocument",
            name="contingency_reason",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="billingdocument",
            name="fiscal_evidence_id",
            field=models.CharField(blank=True, default="", max_length=96),
        ),
        migrations.AddField(
            model_name="billingdocument",
            name="fiscal_metadata_json",
            field=models.JSONField(default=dict),
        ),
        migrations.AddField(
            model_name="billingdocument",
            name="fiscal_mode_resolved",
            field=models.CharField(
                choices=[("NOOP", "Noop"), ("A", "Adapter A"), ("B", "Adapter B")],
                default="NOOP",
                max_length=8,
            ),
        ),
        migrations.AddField(
            model_name="billingdocument",
            name="fiscal_reference",
            field=models.CharField(blank=True, default="", max_length=96),
        ),
        migrations.AddField(
            model_name="billingdocument",
            name="fiscal_status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("NUMBER_RESERVED", "Number Reserved"),
                    ("ISSUED", "Issued"),
                    ("PRINTED", "Printed"),
                    ("FAILED_PRINT", "Failed Print"),
                    ("CONTINGENCY", "Contingency"),
                    ("VOIDED", "Voided"),
                ],
                default="",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="billingdocument",
            name="last_print_error",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="billingdocument",
            name="print_attempt_count",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="billingdocument",
            name="printed_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.CreateModel(
            name="BranchFiscalConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "fiscal_mode",
                    models.CharField(
                        choices=[("NOOP", "Noop"), ("A", "Adapter A"), ("B", "Adapter B")],
                        default="NOOP",
                        max_length=8,
                    ),
                ),
                ("adapter_code", models.CharField(blank=True, default="", max_length=32)),
                ("print_required", models.BooleanField(default=True)),
                ("strict_integrity", models.BooleanField(default=True)),
                ("contingency_max_attempts", models.PositiveSmallIntegerField(default=5)),
                ("is_active", models.BooleanField(default=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_at", models.DateTimeField(default=timezone.now)),
                (
                    "branch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="bill_fiscal_cfg_branch",
                        to="iam.orgunit",
                    ),
                ),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="bill_fiscal_cfg_company",
                        to="iam.orgunit",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="FiscalPrintJob",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "status",
                    models.CharField(
                        choices=[("PENDING", "Pending"), ("RETRY", "Retry"), ("PRINTED", "Printed"), ("FAILED", "Failed")],
                        default="PENDING",
                        max_length=16,
                    ),
                ),
                ("attempt_count", models.PositiveIntegerField(default=0)),
                ("next_attempt_at", models.DateTimeField(blank=True, null=True)),
                ("last_error", models.CharField(blank=True, default="", max_length=255)),
                ("idempotency_key", models.CharField(blank=True, default="", max_length=96)),
                ("created_at", models.DateTimeField(default=timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "branch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="bill_print_jobs_branch",
                        to="iam.orgunit",
                    ),
                ),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="bill_print_jobs_company",
                        to="iam.orgunit",
                    ),
                ),
                (
                    "doc",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="fiscal_print_jobs",
                        to="facturacion.billingdocument",
                    ),
                ),
                (
                    "requested_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="branchfiscalconfig",
            constraint=models.UniqueConstraint(
                fields=("company", "branch"),
                name="uniq_bill_fiscal_cfg_company_branch",
            ),
        ),
        migrations.AddConstraint(
            model_name="fiscalprintjob",
            constraint=models.UniqueConstraint(
                condition=~models.Q(idempotency_key=""),
                fields=("doc", "idempotency_key"),
                name="uniq_bill_print_job_doc_idempotency",
            ),
        ),
        migrations.AddIndex(
            model_name="branchfiscalconfig",
            index=models.Index(fields=["company", "branch", "is_active"], name="facturacion_company_ba6c83_idx"),
        ),
        migrations.AddIndex(
            model_name="billingdocument",
            index=models.Index(
                fields=["company", "branch", "fiscal_mode_resolved", "fiscal_status"],
                name="facturacion_company_99f3f6_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="fiscalprintjob",
            index=models.Index(fields=["status", "next_attempt_at", "created_at"], name="facturacion_status_55e93e_idx"),
        ),
        migrations.AddIndex(
            model_name="fiscalprintjob",
            index=models.Index(
                fields=["company", "branch", "status", "created_at"],
                name="facturacion_company_e8dd3b_idx",
            ),
        ),
    ]
