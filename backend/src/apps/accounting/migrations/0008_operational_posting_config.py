import django.utils.timezone
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("iam", "0003_orgunit_parent_type_name_idx"),
        ("accounting", "0007_phase11_intercompany_advanced"),
    ]

    operations = [
        migrations.CreateModel(
            name="OperationalPostingConfig",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                (
                    "posting_mode",
                    models.CharField(
                        choices=[
                            ("DISABLED", "Disabled"),
                            ("ASYNC", "Async"),
                            ("SYNC", "Sync"),
                            ("HYBRID", "Hybrid"),
                        ],
                        default="HYBRID",
                        max_length=16,
                    ),
                ),
                ("enable_billing", models.BooleanField(default=True)),
                ("enable_inventory", models.BooleanField(default=True)),
                ("auto_post_on_write", models.BooleanField(default=False)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now, editable=False)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "branch",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="acc_operational_posting_branch",
                        to="iam.orgunit",
                    ),
                ),
                (
                    "company",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="acc_operational_posting_company",
                        to="iam.orgunit",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["company", "branch", "is_active"], name="accounting_o_company_a7bb16_idx"),
                    models.Index(fields=["company", "posting_mode", "is_active"], name="accounting_o_company_b290dc_idx"),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="operationalpostingconfig",
            constraint=models.UniqueConstraint(fields=("company", "branch"), name="uq_acc_operational_posting_scope"),
        ),
    ]
