from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import uuid
from django.utils import timezone


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0005_user_totp_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="TwoFactorChallenge",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        primary_key=True,
                        default=uuid.uuid4,
                        editable=False,
                        serialize=False,
                    ),
                ),
                ("created_at", models.DateTimeField(default=timezone.now, editable=False)),
                ("expires_at", models.DateTimeField()),
                ("used_at", models.DateTimeField(null=True, blank=True)),
                ("ip_address", models.GenericIPAddressField(null=True, blank=True)),
                ("user_agent_hash", models.CharField(max_length=64, blank=True, default="")),
                (
                    "user",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="two_factor_challenges",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "indexes": [
                    models.Index(fields=["user", "expires_at"], name="accounts_two_user_expires_idx"),
                    models.Index(fields=["used_at"], name="accounts_two_used_idx"),
                ],
            },
        ),
    ]
