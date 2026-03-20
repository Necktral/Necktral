from __future__ import annotations

from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("estacion_servicios", "0006_fuel_uom_preference_unified"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AlterField(
            model_name="fueluompreference",
            name="user",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=models.CASCADE,
                related_name="fuel_uom_prefs_unified",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
    ]
