from __future__ import annotations

from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


def backfill_from_org_prefs(apps, schema_editor):
    FuelUoMPreference = apps.get_model("estacion_servicios", "FuelUoMPreference")
    OrgUnit = apps.get_model("iam", "OrgUnit")
    BranchProfile = apps.get_model("org", "BranchProfile")
    UserFuelUoMPreference = apps.get_model("org", "UserFuelUoMPreference")

    # Backfill defaults por sucursal desde BranchProfile: creamos 2 filas (GASOLINE/DIESEL).
    for bp in BranchProfile.objects.select_related("branch").all().iterator():
        branch = bp.branch
        if branch.unit_type != OrgUnit.UnitType.BRANCH:
            continue
        company_id = branch.parent_id
        if not company_id:
            continue

        # Gasoline
        v = bp.fuel_default_volume_uom_gasoline
        p = "PER_GALLON" if v == "GALLON" else "PER_LITER"
        FuelUoMPreference.objects.update_or_create(
            company_id=company_id,
            branch_id=branch.id,
            user_id=None,
            product="GASOLINE",
            defaults={
                "default_volume_uom": v,
                "default_price_uom": p,
                "updated_at": timezone.now(),
                "updated_by_id": None,
            },
        )

        # Diesel
        v = bp.fuel_default_volume_uom_diesel
        p = "PER_GALLON" if v == "GALLON" else "PER_LITER"
        FuelUoMPreference.objects.update_or_create(
            company_id=company_id,
            branch_id=branch.id,
            user_id=None,
            product="DIESEL",
            defaults={
                "default_volume_uom": v,
                "default_price_uom": p,
                "updated_at": timezone.now(),
                "updated_by_id": None,
            },
        )

    # Backfill overrides por usuario desde UserFuelUoMPreference: creamos filas por producto cuando exista valor.
    for up in UserFuelUoMPreference.objects.select_related("branch").all().iterator():
        branch = up.branch
        if branch.unit_type != OrgUnit.UnitType.BRANCH:
            continue
        company_id = branch.parent_id
        if not company_id:
            continue

        if up.gasoline_volume_uom:
            v = up.gasoline_volume_uom
            p = "PER_GALLON" if v == "GALLON" else "PER_LITER"
            FuelUoMPreference.objects.update_or_create(
                company_id=company_id,
                branch_id=branch.id,
                user_id=up.user_id,
                product="GASOLINE",
                defaults={
                    "default_volume_uom": v,
                    "default_price_uom": p,
                    "updated_at": timezone.now(),
                    "updated_by_id": None,
                },
            )

        if up.diesel_volume_uom:
            v = up.diesel_volume_uom
            p = "PER_GALLON" if v == "GALLON" else "PER_LITER"
            FuelUoMPreference.objects.update_or_create(
                company_id=company_id,
                branch_id=branch.id,
                user_id=up.user_id,
                product="DIESEL",
                defaults={
                    "default_volume_uom": v,
                    "default_price_uom": p,
                    "updated_at": timezone.now(),
                    "updated_by_id": None,
                },
            )


class Migration(migrations.Migration):
    dependencies = [
        ("estacion_servicios", "0005_amounts_dual_entered_and_canonical"),
        ("iam", "0002_initial"),
        ("org", "0004_user_fuel_uom_preference"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="FuelUoMPreference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("product", models.CharField(blank=True, default="", max_length=16)),
                ("default_volume_uom", models.CharField(choices=[("LITER", "Litro"), ("GALLON", "Galón (US)"), ("GALLON_US", "Galón (US)")], max_length=16)),
                ("default_price_uom", models.CharField(choices=[("PER_LITER", "Precio/Litro"), ("PER_GALLON", "Precio/Galón (US)"), ("PER_GALLON_US", "Precio/Galón (US)")], max_length=16)),
                ("updated_at", models.DateTimeField(default=timezone.now)),
                ("branch", models.ForeignKey(on_delete=models.PROTECT, related_name="fuel_uom_prefs_branch", to="iam.orgunit")),
                ("company", models.ForeignKey(on_delete=models.PROTECT, related_name="fuel_uom_prefs_company", to="iam.orgunit")),
                ("updated_by", models.ForeignKey(blank=True, null=True, on_delete=models.SET_NULL, related_name="fuel_uom_prefs_updated", to=settings.AUTH_USER_MODEL)),
                ("user", models.ForeignKey(blank=True, null=True, on_delete=models.CASCADE, related_name="fuel_uom_prefs", to=settings.AUTH_USER_MODEL)),
            ],
        ),
        migrations.AddIndex(
            model_name="fueluompreference",
            index=models.Index(fields=["company", "branch", "user", "product"], name="idx_fuel_uom_pref_scope"),
        ),
        migrations.AddIndex(
            model_name="fueluompreference",
            index=models.Index(fields=["company", "branch", "product"], name="idx_fuel_uom_pref_branch_prod"),
        ),
        migrations.AddConstraint(
            model_name="fueluompreference",
            constraint=models.UniqueConstraint(condition=models.Q(("user__isnull", True)), fields=("company", "branch", "product"), name="uq_fuel_uom_pref_branch_product"),
        ),
        migrations.AddConstraint(
            model_name="fueluompreference",
            constraint=models.UniqueConstraint(condition=models.Q(("user__isnull", False)), fields=("company", "branch", "user", "product"), name="uq_fuel_uom_pref_user_branch_product"),
        ),
        migrations.RunPython(backfill_from_org_prefs, migrations.RunPython.noop),
    ]
