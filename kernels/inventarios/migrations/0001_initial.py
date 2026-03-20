from __future__ import annotations

import django.db.models.deletion
from decimal import Decimal

from django.conf import settings
from django.db import migrations, models
from django.utils import timezone


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("iam", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="Warehouse",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=120)),
                ("code", models.CharField(blank=True, default="", max_length=24)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(default=timezone.now)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="inv_warehouses_company",
                        to="iam.orgunit",
                    ),
                ),
                (
                    "branch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="inv_warehouses_branch",
                        to="iam.orgunit",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="InventoryItem",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("sku", models.CharField(max_length=64)),
                ("name", models.CharField(max_length=160)),
                ("uom", models.CharField(choices=[("UNIT", "Unit"), ("LITER", "Liter")], default="UNIT", max_length=16)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(default=timezone.now)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="inv_items_company",
                        to="iam.orgunit",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="StockBalance",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("qty_on_hand", models.DecimalField(decimal_places=4, default=Decimal("0.0000"), max_digits=18)),
                ("avg_cost", models.DecimalField(decimal_places=6, default=Decimal("0.000000"), max_digits=18)),
                ("updated_at", models.DateTimeField(default=timezone.now)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="inv_bal_company",
                        to="iam.orgunit",
                    ),
                ),
                (
                    "branch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="inv_bal_branch",
                        to="iam.orgunit",
                    ),
                ),
                (
                    "warehouse",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="balances",
                        to="inventarios.warehouse",
                    ),
                ),
                (
                    "item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="balances",
                        to="inventarios.inventoryitem",
                    ),
                ),
            ],
        ),
        migrations.CreateModel(
            name="StockMovement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "movement_type",
                    models.CharField(
                        choices=[
                            ("RECEIVE", "Receive"),
                            ("ISSUE", "Issue"),
                            ("ADJUST", "Adjust"),
                            ("TRANSFER_OUT", "Transfer Out"),
                            ("TRANSFER_IN", "Transfer In"),
                        ],
                        max_length=16,
                    ),
                ),
                ("qty_delta", models.DecimalField(decimal_places=4, max_digits=18)),
                ("unit_cost", models.DecimalField(decimal_places=6, default=Decimal("0.000000"), max_digits=18)),
                ("total_cost", models.DecimalField(decimal_places=6, default=Decimal("0.000000"), max_digits=18)),
                ("source_module", models.CharField(blank=True, default="", max_length=32)),
                ("source_type", models.CharField(blank=True, default="", max_length=64)),
                ("source_id", models.CharField(blank=True, default="", max_length=64)),
                ("note", models.CharField(blank=True, default="", max_length=255)),
                ("idempotency_key", models.CharField(blank=True, default="", max_length=96)),
                ("created_at", models.DateTimeField(default=timezone.now)),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="inv_mov_company",
                        to="iam.orgunit",
                    ),
                ),
                (
                    "branch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="inv_mov_branch",
                        to="iam.orgunit",
                    ),
                ),
                (
                    "warehouse",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="movements",
                        to="inventarios.warehouse",
                    ),
                ),
                (
                    "item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="movements",
                        to="inventarios.inventoryitem",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
        ),
        migrations.AddConstraint(
            model_name="warehouse",
            constraint=models.UniqueConstraint(fields=("company", "branch", "code"), name="uniq_inv_wh_code_per_branch"),
        ),
        migrations.AddConstraint(
            model_name="inventoryitem",
            constraint=models.UniqueConstraint(fields=("company", "sku"), name="uniq_inv_sku_per_company"),
        ),
        migrations.AddConstraint(
            model_name="stockbalance",
            constraint=models.UniqueConstraint(
                fields=("company", "branch", "warehouse", "item"),
                name="uniq_inv_balance_per_scope",
            ),
        ),
        migrations.AddConstraint(
            model_name="stockmovement",
            constraint=models.UniqueConstraint(
                condition=~models.Q(idempotency_key=""),
                fields=("company", "idempotency_key"),
                name="uniq_inv_idempotency_per_company",
            ),
        ),
        migrations.AddIndex(
            model_name="warehouse",
            index=models.Index(
                fields=["company", "branch", "is_active", "name"],
                name="inventarios_company_branch_is_active_name_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="inventoryitem",
            index=models.Index(fields=["company", "is_active", "sku"], name="inventarios_company_is_active_sku_idx"),
        ),
    ]
