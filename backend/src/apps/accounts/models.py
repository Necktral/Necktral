import uuid

from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.db import models
from django.utils import timezone


class User(AbstractUser):
    # AbstractUser.email es str (no nullable). Mantener compatibilidad de tipos.
    email = models.EmailField(unique=True, blank=True)

    # Flujo onboarding:
    # - empleado creado por admin: entra con contraseña provisional y el sistema obliga a cambiarla
    must_change_password = models.BooleanField(default=False)

    # Compatibilidad con esquemas existentes (algunas BD tienen esta columna NOT NULL)
    is_setup_complete = models.BooleanField(default=False)

    # 2FA (TOTP)
    totp_secret = models.CharField(max_length=64, blank=True, default="")
    totp_enabled = models.BooleanField(default=False)
    totp_confirmed_at = models.DateTimeField(null=True, blank=True)


class RefreshTokenSession(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="refresh_sessions",
    )
    jti = models.CharField(max_length=64, unique=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    expires_at = models.DateTimeField()
    last_used_at = models.DateTimeField(null=True, blank=True)
    revoked_at = models.DateTimeField(null=True, blank=True)
    replaced_by_jti = models.CharField(max_length=64, blank=True, default="")
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.CharField(max_length=256, blank=True, default="")

    class Meta:
        app_label = "accounts"
        indexes = [
            models.Index(fields=["user", "revoked_at"]),
            models.Index(fields=["expires_at"]),
        ]


class TwoFactorChallenge(models.Model):
    """One-time challenge para 2FA (anti-replay)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="two_factor_challenges",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent_hash = models.CharField(max_length=64, blank=True, default="")

    class Meta:
        app_label = "accounts"
        indexes = [
            models.Index(fields=["user", "expires_at"]),
            models.Index(fields=["used_at"]),
        ]
