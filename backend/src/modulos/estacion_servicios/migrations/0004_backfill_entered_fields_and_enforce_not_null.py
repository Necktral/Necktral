from __future__ import annotations

from django.db import migrations, models
from django.db.models import F


def backfill_entered_fields(apps, schema_editor):
    FuelDispense = apps.get_model("estacion_servicios", "FuelDispense")

    # Volumen: si quedó nulo por data vieja, el histórico era litros implícitos.
    FuelDispense.objects.filter(volume_entered__isnull=True).update(volume_entered=F("liters"), volume_uom="LITER")

    # Precio: si quedó nulo, asumimos legacy (precio por litro).
    FuelDispense.objects.filter(unit_price_entered__isnull=True).update(
        unit_price_entered=F("unit_price"),
        unit_price_uom="PER_LITER",
    )

    # Normalización legacy (best-effort):
    FuelDispense.objects.filter(volume_uom="GALLON_US").update(volume_uom="GALLON")
    FuelDispense.objects.filter(unit_price_uom="PER_GALLON_US").update(unit_price_uom="PER_GALLON")


class Migration(migrations.Migration):
    dependencies = [
        ("estacion_servicios", "0003_price_uom_and_field_renames"),
    ]

    operations = [
        migrations.RunPython(backfill_entered_fields, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="fueldispense",
            name="volume_entered",
            field=models.DecimalField(max_digits=12, decimal_places=4),
        ),
        migrations.AlterField(
            model_name="fueldispense",
            name="unit_price_entered",
            field=models.DecimalField(max_digits=12, decimal_places=4),
        ),
    ]
