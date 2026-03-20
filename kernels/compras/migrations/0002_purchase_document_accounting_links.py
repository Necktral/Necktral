from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounting", "0008_operational_posting_config"),
        ("compras", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchasedocument",
            name="accounting_economic_event",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="procurement_documents",
                to="accounting.economicevent",
            ),
        ),
        migrations.AddField(
            model_name="purchasedocument",
            name="accounting_error",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="purchasedocument",
            name="accounting_journal_draft",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="procurement_documents",
                to="accounting.journaldraft",
            ),
        ),
        migrations.AddField(
            model_name="purchasedocument",
            name="accounting_journal_entry",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="procurement_documents",
                to="accounting.journalentry",
            ),
        ),
        migrations.AddField(
            model_name="purchasedocument",
            name="accounting_status",
            field=models.CharField(
                blank=True,
                choices=[
                    ("DISABLED", "Disabled"),
                    ("UNSUPPORTED", "Unsupported"),
                    ("PENDING_RULESET", "Pending ruleset"),
                    ("PENDING_RULE", "Pending rule"),
                    ("DRAFT_EXCEPTION", "Draft exception"),
                    ("DRAFT_VALIDATED", "Draft validated"),
                    ("POSTED", "Posted"),
                ],
                default="",
                max_length=24,
            ),
        ),
        migrations.AddIndex(
            model_name="purchasedocument",
            index=models.Index(
                fields=["company", "branch", "accounting_status", "created_at"],
                name="ix_proc_doc_acc_st",
            ),
        ),
    ]
