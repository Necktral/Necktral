from __future__ import annotations

from decimal import Decimal

from django.db import migrations, models
from django.db.models import F


def backfill_entered_fields(apps, schema_editor):
    FuelDispense = apps.get_model("estacion_servicios", "FuelDispense")
    # En el histórico existente, todo era “liters” (entrada implícita en litros)
    FuelDispense.objects.all().update(volume_entered=F("liters"), uom_entered="LITER")


class Migration(migrations.Migration):
    dependencies = [
        ("estacion_servicios", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="fueldispense",
            name="liters",
            field=models.DecimalField(max_digits=12, decimal_places=4),
        ),
        migrations.AlterField(
            model_name="fueldispense",
            name="meter_reading",
            field=models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True),
        ),
        migrations.AddField(
            model_name="fueldispense",
            name="volume_entered",
            field=models.DecimalField(max_digits=12, decimal_places=4, default=Decimal("0.0000")),
        ),
        migrations.AddField(
            model_name="fueldispense",
            name="uom_entered",
            field=models.CharField(
                max_length=16,
                choices=[("LITER", "Litro"), ("GALLON_US", "Galón (US)")],
                default="LITER",
            ),
        ),
        migrations.RunPython(backfill_entered_fields, migrations.RunPython.noop),
    ]
