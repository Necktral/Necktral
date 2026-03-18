from __future__ import annotations

import uuid

from django.db import models
from django.utils import timezone


class DeviceEnrollment(models.Model):
    """
    Representa un dispositivo autorizado (tablet/celular/PC) para enviar lotes.
    En v0.1 usamos secreto HMAC por dispositivo.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    device_name = models.CharField(max_length=120, blank=True, default="")
    secret_b64 = models.CharField(max_length=256)  # base64 del secreto (HMAC key)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(default=timezone.now)
    revoked_at = models.DateTimeField(null=True, blank=True)

    def revoke(self) -> None:
        self.is_active = False
        self.revoked_at = timezone.now()
        self.save(update_fields=["is_active", "revoked_at"])


class DeviceRequestNonce(models.Model):
    """
    Anti-replay: nonce único por dispositivo en una ventana temporal.
    Limpieza: un cron/management command puede borrar viejos.
    """

    device = models.ForeignKey(
        DeviceEnrollment,
        on_delete=models.CASCADE,
        related_name="nonces",
    )
    nonce = models.CharField(max_length=128)
    ts = models.BigIntegerField()  # unix seconds
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["device", "nonce"], name="uniq_device_nonce"),
        ]
        indexes = [
            models.Index(fields=["device", "created_at"], name="ix_drnonce_dev_ca"),
        ]


class AppliedCommand(models.Model):
    """
    Idempotencia: (device, command_id) único. Cachea resultado.
    """

    device = models.ForeignKey(
        DeviceEnrollment,
        on_delete=models.CASCADE,
        related_name="applied_commands",
    )
    command_id = models.UUIDField()
    command_type = models.CharField(max_length=64)
    request_hash = models.CharField(max_length=64)  # sha256 hex del payload del comando
    status = models.CharField(max_length=32)  # OK | ERROR
    response_json = models.JSONField()
    applied_at = models.DateTimeField(default=timezone.now)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["device", "command_id"], name="uniq_device_command"),
        ]
        indexes = [
            models.Index(fields=["device", "applied_at"], name="ix_apcmd_dev_at"),
            models.Index(fields=["command_type", "applied_at"], name="ix_apcmd_type_at"),
        ]
