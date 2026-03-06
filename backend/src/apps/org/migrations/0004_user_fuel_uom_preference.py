from __future__ import annotations

from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [
        ("org", "0003_branchprofile_fuel_uom_defaults"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("iam", "0002_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="UserFuelUoMPreference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("gasoline_volume_uom", models.CharField(blank=True, choices=[("LITER", "Litro"), ("GALLON", "Galón (US)")], max_length=16, null=True)),
                ("diesel_volume_uom", models.CharField(blank=True, choices=[("LITER", "Litro"), ("GALLON", "Galón (US)")], max_length=16, null=True)),
                ("created_at", models.DateTimeField(default=timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("branch", models.ForeignKey(on_delete=models.CASCADE, related_name="fuel_uom_prefs", to="iam.orgunit")),
                ("user", models.ForeignKey(on_delete=models.CASCADE, related_name="fuel_uom_prefs", to=settings.AUTH_USER_MODEL)),
            ],
            options={"app_label": "org"},
        ),
        migrations.AddConstraint(
            model_name="userfueluompreference",
            constraint=models.UniqueConstraint(fields=("user", "branch"), name="uq_user_fuel_uom_pref_user_branch"),
        ),
        migrations.AddIndex(
            model_name="userfueluompreference",
            index=models.Index(fields=["user", "branch"], name="idx_userfueluompref_user_branch"),
        ),
        migrations.AddIndex(
            model_name="userfueluompreference",
            index=models.Index(fields=["branch"], name="idx_userfueluompref_branch"),
        ),
    ]
