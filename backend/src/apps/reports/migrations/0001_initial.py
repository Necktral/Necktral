# Generated manually (minimal, contract-first).

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("iam", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ReportDefinition",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("report_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("code", models.SlugField(max_length=64)),
                ("name", models.CharField(default="", max_length=160)),
                ("description", models.CharField(blank=True, default="", max_length=500)),
                ("schema_version", models.PositiveIntegerField(default=1)),
                ("contract_version", models.PositiveIntegerField(default=1)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "company",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="report_definitions", to="iam.orgunit"),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["company", "code"], name="ix_report_def_code"),
                ],
            },
        ),
        migrations.CreateModel(
            name="ReportRun",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("run_id", models.UUIDField(default=uuid.uuid4, editable=False, unique=True)),
                ("branch_id", models.IntegerField(blank=True, null=True)),
                ("status", models.CharField(choices=[("RUNNING", "RUNNING"), ("SUCCEEDED", "SUCCEEDED"), ("FAILED", "FAILED")], default="RUNNING", max_length=16)),
                ("request_id", models.CharField(blank=True, default="", max_length=64)),
                ("parameters", models.JSONField(blank=True, default=dict)),
                ("result", models.JSONField(blank=True, default=dict)),
                ("error", models.CharField(blank=True, default="", max_length=500)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                (
                    "actor_user",
                    models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="report_runs", to=settings.AUTH_USER_MODEL),
                ),
                (
                    "company",
                    models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="report_runs", to="iam.orgunit"),
                ),
                (
                    "definition",
                    models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="runs", to="reports.reportdefinition"),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["company", "started_at", "id"], name="ix_report_run_time"),
                    models.Index(fields=["company", "definition", "started_at"], name="ix_report_run_def_time"),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="reportdefinition",
            constraint=models.UniqueConstraint(fields=("company", "code"), name="uniq_report_def_per_company"),
        ),
    ]

