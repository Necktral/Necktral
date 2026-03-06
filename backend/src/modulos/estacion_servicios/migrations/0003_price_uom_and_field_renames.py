from __future__ import annotations

from decimal import Decimal

from django.db import migrations, models
from django.db.models import Case, DecimalField, ExpressionWrapper, F, Value, When


GALLON_US_TO_LITER = Decimal("3.785411784")


def forward_backfill_price_uom(apps, schema_editor):
    FuelDispense = apps.get_model("estacion_servicios", "FuelDispense")

    # 1) Normalizar valores antiguos: GALLON_US -> GALLON
    FuelDispense.objects.filter(volume_uom="GALLON_US").update(volume_uom="GALLON")

    # 2) Backfill de precio: el histórico existente interpretaba unit_price como "por unidad ingresada".
    #    Nuevo contrato: unit_price es canónico (por litro) y unit_price_entered/unit_price_uom conservan lo capturado.
    unit_price_per_liter_from_gallon = ExpressionWrapper(
        F("unit_price") / Value(GALLON_US_TO_LITER),
        output_field=DecimalField(max_digits=12, decimal_places=4),
    )

    FuelDispense.objects.all().update(
        unit_price_entered=F("unit_price"),
        unit_price_uom=Case(
            When(volume_uom="GALLON", then=Value("PER_GALLON")),
            default=Value("PER_LITER"),
            output_field=models.CharField(max_length=16),
        ),
        unit_price=Case(
            When(volume_uom="GALLON", then=unit_price_per_liter_from_gallon),
            default=F("unit_price"),
            output_field=DecimalField(max_digits=12, decimal_places=4),
        ),
    )


def reverse_backfill_price_uom(apps, schema_editor):
    FuelDispense = apps.get_model("estacion_servicios", "FuelDispense")

    # Reversión best-effort:
    # - Restauramos unit_price al precio "entered" si existe.
    # - Normalizamos volumen a GALLON_US si estaba en GALLON (para compat con histórico).
    FuelDispense.objects.filter(volume_uom="GALLON").update(volume_uom="GALLON_US")
    FuelDispense.objects.filter(unit_price_entered__isnull=False).update(unit_price=F("unit_price_entered"))


class Migration(migrations.Migration):
    dependencies = [
        ("estacion_servicios", "0002_uom_and_precision"),
    ]

    operations = [
        migrations.RenameField(
            model_name="fueldispense",
            old_name="uom_entered",
            new_name="volume_uom",
        ),
        migrations.AlterField(
            model_name="fueldispense",
            name="volume_entered",
            field=models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True),
        ),
        migrations.AlterField(
            model_name="fueldispense",
            name="volume_uom",
            field=models.CharField(
                max_length=16,
                choices=[("LITER", "Litro"), ("GALLON", "Galón (US)"), ("GALLON_US", "Galón (US)")],
                default="LITER",
            ),
        ),
        migrations.AddField(
            model_name="fueldispense",
            name="unit_price_entered",
            field=models.DecimalField(max_digits=12, decimal_places=4, null=True, blank=True),
        ),
        migrations.AddField(
            model_name="fueldispense",
            name="unit_price_uom",
            field=models.CharField(
                max_length=16,
                choices=[
                    ("PER_LITER", "Precio/Litro"),
                    ("PER_GALLON", "Precio/Galón (US)"),
                    ("PER_GALLON_US", "Precio/Galón (US)"),
                ],
                default="PER_LITER",
            ),
        ),
        migrations.RunPython(forward_backfill_price_uom, reverse_backfill_price_uom),
    ]
