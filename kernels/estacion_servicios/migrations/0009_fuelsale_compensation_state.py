from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("estacion_servicios", "0008_fuelsale_billing_and_inventory_links"),
    ]

    operations = [
        migrations.AlterField(
            model_name="fuelsale",
            name="status",
            field=models.CharField(
                choices=[
                    ("ACTIVE", "Activa"),
                    ("COMPENSATING", "Compensando"),
                    ("CANCELLED", "Anulada"),
                    ("COMPENSATION_FAILED", "Compensación fallida"),
                ],
                default="ACTIVE",
                max_length=24,
            ),
        ),
        migrations.AddField(
            model_name="fuelsale",
            name="compensation_attempts",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="fuelsale",
            name="compensation_last_error",
            field=models.CharField(blank=True, default="", max_length=255),
        ),
        migrations.AddField(
            model_name="fuelsale",
            name="compensation_next_retry_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="fuelsale",
            name="flow_correlation_id",
            field=models.CharField(blank=True, db_index=True, default="", max_length=96),
        ),
        migrations.AddField(
            model_name="fuelsale",
            name="last_compensation_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddIndex(
            model_name="fuelsale",
            index=models.Index(
                fields=["status", "compensation_next_retry_at", "created_at"],
                name="fuel_sale_comp_retry_idx",
            ),
        ),
    ]
