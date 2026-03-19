from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("org", "0002_alter_branchprofile_id_alter_companyprofile_id"),
    ]

    operations = [
        migrations.AddField(
            model_name="branchprofile",
            name="fuel_default_volume_uom_gasoline",
            field=models.CharField(
                max_length=16,
                choices=[("LITER", "Litro"), ("GALLON", "Galón (US)")],
                default="LITER",
            ),
        ),
        migrations.AddField(
            model_name="branchprofile",
            name="fuel_default_volume_uom_diesel",
            field=models.CharField(
                max_length=16,
                choices=[("LITER", "Litro"), ("GALLON", "Galón (US)")],
                default="GALLON",
            ),
        ),
    ]
