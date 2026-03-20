from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("facturacion", "0003_accounting_links"),
    ]

    operations = [
        migrations.AddField(
            model_name="billingdocument",
            name="source_id",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AddField(
            model_name="billingdocument",
            name="source_module",
            field=models.CharField(blank=True, default="", max_length=32),
        ),
        migrations.AddField(
            model_name="billingdocument",
            name="source_type",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
    ]
