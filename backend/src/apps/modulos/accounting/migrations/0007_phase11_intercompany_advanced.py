from __future__ import annotations

import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("iam", "0002_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("accounting", "0006_phase7b_performance_indexes"),
    ]

    operations = [
        migrations.CreateModel(
            name="IntercompanyDisputeReason",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=64)),
                ("version", models.PositiveIntegerField(default=1)),
                ("title", models.CharField(max_length=128)),
                ("description", models.CharField(blank=True, default="", max_length=255)),
                (
                    "severity",
                    models.CharField(
                        choices=[("LOW", "Low"), ("MEDIUM", "Medium"), ("HIGH", "High"), ("CRITICAL", "Critical")],
                        default="HIGH",
                        max_length=16,
                    ),
                ),
                ("requires_evidence", models.BooleanField(default=True)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="acc_intercompany_dispute_reasons",
                        to="iam.orgunit",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["company", "code", "is_active"], name="accounting_i_company_2e3dca_idx"),
                    models.Index(fields=["company", "is_active", "updated_at"], name="accounting_i_company_3cf75c_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="IntercompanyDisputeCase",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("case_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("OPEN", "Open"),
                            ("UNDER_REVIEW", "Under review"),
                            ("APPROVED", "Approved"),
                            ("REJECTED", "Rejected"),
                            ("SETTLED", "Settled"),
                            ("CANCELLED", "Cancelled"),
                        ],
                        default="OPEN",
                        max_length=16,
                    ),
                ),
                ("summary", models.CharField(blank=True, default="", max_length=255)),
                ("resolution_note", models.CharField(blank=True, default="", max_length=255)),
                ("details_json", models.JSONField(default=dict)),
                ("opened_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("reviewed_at", models.DateTimeField(blank=True, null=True)),
                ("settled_at", models.DateTimeField(blank=True, null=True)),
                ("closed_at", models.DateTimeField(blank=True, null=True)),
                ("sla_due_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "opened_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="acc_intercompany_disputes_opened",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "reason",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="dispute_cases",
                        to="accounting.intercompanydisputereason",
                    ),
                ),
                (
                    "reviewed_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="acc_intercompany_disputes_reviewed",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "settled_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="acc_intercompany_disputes_settled",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "transaction",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="dispute_cases",
                        to="accounting.intercompanytransaction",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["transaction", "status", "updated_at"], name="accounting_i_transac_952957_idx"),
                    models.Index(fields=["status", "sla_due_at"], name="accounting_i_status_4cf38d_idx"),
                    models.Index(fields=["reason", "status"], name="accounting_i_reason__a2ded0_idx"),
                ],
            },
        ),
        migrations.CreateModel(
            name="IntercompanyDisputeEvidence",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("evidence_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("reference", models.CharField(max_length=255)),
                ("evidence_hash", models.CharField(max_length=64)),
                ("mime_type", models.CharField(blank=True, default="", max_length=128)),
                ("note", models.CharField(blank=True, default="", max_length=255)),
                ("metadata_json", models.JSONField(default=dict)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="acc_intercompany_dispute_evidences_created",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "dispute_case",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="evidences",
                        to="accounting.intercompanydisputecase",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["dispute_case", "created_at"], name="accounting_i_dispute_3b72d5_idx"),
                    models.Index(fields=["evidence_hash"], name="accounting_i_evidenc_6f533e_idx"),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="intercompanydisputecase",
            constraint=models.UniqueConstraint(
                condition=models.Q(status__in=["OPEN", "UNDER_REVIEW", "APPROVED"]),
                fields=("transaction",),
                name="uq_acc_ic_dispute_case_active_per_tx",
            ),
        ),
        migrations.AddConstraint(
            model_name="intercompanydisputeevidence",
            constraint=models.UniqueConstraint(
                fields=("dispute_case", "evidence_hash"),
                name="uq_acc_ic_dispute_evidence_case_hash",
            ),
        ),
        migrations.AddConstraint(
            model_name="intercompanydisputereason",
            constraint=models.UniqueConstraint(
                fields=("company", "code", "version"),
                name="uq_acc_ic_dispute_reason_company_code_version",
            ),
        ),
    ]
