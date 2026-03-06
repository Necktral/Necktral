from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("estacion_servicios", "0007_alter_fueluompreference_user_related_name"),
        ("facturacion", "0001_initial"),
        ("inventarios", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="fuelsale",
            name="billing_doc",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.PROTECT,
                related_name="fuel_sales",
                to="facturacion.billingdocument",
            ),
        ),
        migrations.AddField(
            model_name="fuelsale",
            name="inventory_movement",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.PROTECT,
                related_name="fuel_sales",
                to="inventarios.stockmovement",
            ),
        ),
        migrations.AddField(
            model_name="fuelsale",
            name="inventory_reversal_movement",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.deletion.PROTECT,
                related_name="fuel_sales_reversals",
                to="inventarios.stockmovement",
            ),
        ),
    ]
