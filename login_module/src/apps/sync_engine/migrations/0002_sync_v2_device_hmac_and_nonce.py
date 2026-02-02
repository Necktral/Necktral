from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):
    dependencies = [
        ("sync_engine", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="device",
            name="public_key",
            field=models.BinaryField(blank=True, editable=False, max_length=64, null=True),
        ),
        migrations.AddField(
            model_name="device",
            name="hmac_secret_b64",
            field=models.CharField(blank=True, max_length=256, null=True),
        ),
        migrations.CreateModel(
            name="DeviceRequestNonce",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("nonce", models.CharField(max_length=128)),
                ("ts", models.BigIntegerField()),
                ("created_at", models.DateTimeField(default=django.utils.timezone.now)),
                (
                    "device",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="nonces",
                        to="sync_engine.device",
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["device", "created_at"], name="ix_drnonce_dev_ca_v2"),
                ],
            },
        ),
        migrations.AddConstraint(
            model_name="devicerequestnonce",
            constraint=models.UniqueConstraint(fields=("device", "nonce"), name="uniq_device_nonce_v2"),
        ),
    ]
