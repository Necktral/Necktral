from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("estacion_servicios", "0011_fuelsale_idempotency"),
        ("parties", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="fuelsale",
            name="customer_party",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="fuel_sales",
                to="parties.party",
            ),
        ),
        migrations.AddIndex(
            model_name="fuelsale",
            index=models.Index(
                fields=["company", "customer_party"],
                name="ix_fuel_sale_co_cust_party",
            ),
        ),
    ]
