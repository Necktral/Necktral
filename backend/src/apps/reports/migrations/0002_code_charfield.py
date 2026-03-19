# Generated manually (contract: allow dotted report codes).

from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("reports", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="reportdefinition",
            name="code",
            field=models.CharField(max_length=64),
        ),
    ]

