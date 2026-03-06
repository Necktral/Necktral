from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.db import migrations, models


MONEY_Q = Decimal("0.01")
VOL_Q = Decimal("0.0001")


def _money(x: Decimal) -> Decimal:
    return Decimal(x).quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _q4(x: Decimal) -> Decimal:
    return Decimal(x).quantize(VOL_Q, rounding=ROUND_HALF_UP)


def backfill_amounts(apps, schema_editor):
    FuelDispense = apps.get_model("estacion_servicios", "FuelDispense")

    # Backfill determinista:
    # - amount pasa a representar el monto entered (volume_entered * unit_price_entered).
    # - amount_canonical se calcula como liters * unit_price (unit_price ya es por litro).
    # - amount_delta = amount - amount_canonical.
    for d in FuelDispense.objects.all().iterator():
        volume_entered = _q4(d.volume_entered)
        unit_price_entered = _q4(d.unit_price_entered)
        liters = _q4(d.liters)
        unit_price_per_liter = _q4(d.unit_price)

        amount_entered = _money(volume_entered * unit_price_entered)
        amount_canonical = _money(liters * unit_price_per_liter)
        amount_delta = _money(amount_entered - amount_canonical)

        d.amount = amount_entered
        d.amount_canonical = amount_canonical
        d.amount_delta = amount_delta
        d.save(update_fields=["amount", "amount_canonical", "amount_delta"])


class Migration(migrations.Migration):
    dependencies = [
        ("estacion_servicios", "0004_backfill_entered_fields_and_enforce_not_null"),
    ]

    operations = [
        migrations.AddField(
            model_name="fueldispense",
            name="amount_canonical",
            field=models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00")),
        ),
        migrations.AddField(
            model_name="fueldispense",
            name="amount_delta",
            field=models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00")),
        ),
        migrations.RunPython(backfill_amounts, migrations.RunPython.noop),
    ]
