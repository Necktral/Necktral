from __future__ import annotations

import hashlib
import secrets
import uuid

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.iam.models import OrgUnit


class Device(models.Model):
    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        REVOKED = "REVOKED", "Revoked"
        QUARANTINED = "QUARANTINED", "Quarantined"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    company = models.ForeignKey(
        OrgUnit,
        on_delete=models.PROTECT,
        related_name="devices_company",
        limit_choices_to={"unit_type": OrgUnit.UnitType.COMPANY},
    )
    branch = models.ForeignKey(
        OrgUnit,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="devices_branch",
        limit_choices_to={"unit_type": OrgUnit.UnitType.BRANCH},
    )

    label = models.CharField(max_length=200, default="", blank=True)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)

    # Ed25519 public key: 32 bytes
    public_key = models.BinaryField(max_length=64, editable=False)

    min_app_version = models.CharField(max_length=32, default="", blank=True)
    meta = models.JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    revoked_at = models.DateTimeField(null=True, blank=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)

    # Opcional: secuencia monotónica por device (tolerante por defecto, pero útil para detectar huecos)
    last_accepted_sequence = models.BigIntegerField(default=0)

    enrolled_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="enrolled_devices",
    )

    class Meta:
        app_label = "sync_engine"
        indexes = [
            models.Index(fields=["company", "status"]),
            models.Index(fields=["branch", "status"]),
            models.Index(fields=["status", "last_seen_at"]),
        ]

    def clean(self):
        if self.branch_id is not None:
            if self.branch.parent_id != self.company_id:
                raise ValidationError("branch debe pertenecer a company (branch.parent == company).")

    def mark_seen(self) -> None:
        self.last_seen_at = timezone.now()
        self.save(update_fields=["last_seen_at"])

    def revoke(self) -> None:
        self.status = self.Status.REVOKED
        self.revoked_at = timezone.now()
        self.save(update_fields=["status", "revoked_at"])


class DeviceEnrollmentChallenge(models.Model):
    """
    Código de un solo uso (se guarda solo el hash).
    Flujo:
      - Usuario con permiso crea challenge y obtiene el code en texto/QR
      - Dispositivo envía code + public_key
      - Backend valida, crea Device y marca used_at/used_by_device
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    company = models.ForeignKey(
        OrgUnit,
        on_delete=models.PROTECT,
        related_name="device_enroll_challenges_company",
        limit_choices_to={"unit_type": OrgUnit.UnitType.COMPANY},
    )
    branch = models.ForeignKey(
        OrgUnit,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="device_enroll_challenges_branch",
        limit_choices_to={"unit_type": OrgUnit.UnitType.BRANCH},
    )

    enrollment_code_hash = models.CharField(max_length=64, unique=True)  # sha256 hex
    expires_at = models.DateTimeField()

    created_by_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_device_enroll_challenges",
    )

    used_at = models.DateTimeField(null=True, blank=True)
    used_by_device = models.ForeignKey(
        "Device",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="used_challenges",
    )

    label_hint = models.CharField(max_length=200, default="", blank=True)

    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "sync_engine"
        indexes = [
            models.Index(fields=["company", "expires_at"]),
            models.Index(fields=["used_at"]),
        ]

    def clean(self):
        if self.branch_id is not None:
            if self.branch.parent_id != self.company_id:
                raise ValidationError("branch debe pertenecer a company (branch.parent == company).")

    @staticmethod
    def generate_code() -> str:
        # Código corto, apto para QR o tipeo
        # 20 bytes => ~27 chars urlsafe
        return secrets.token_urlsafe(20)

    @staticmethod
    def sha256_hex(s: str) -> str:
        return hashlib.sha256(s.encode("utf-8")).hexdigest()

    def is_valid_now(self) -> bool:
        if self.used_at is not None:
            return False
        return timezone.now() <= self.expires_at


class AppliedCommand(models.Model):
    class ResultStatus(models.TextChoices):
        APPLIED = "APPLIED", "Applied"
        REJECTED = "REJECTED", "Rejected"
        DUPLICATE = "DUPLICATE", "Duplicate"

    command_id = models.UUIDField(primary_key=True, editable=False)
    device = models.ForeignKey(Device, on_delete=models.PROTECT, related_name="applied_commands")

    company = models.ForeignKey(
        OrgUnit,
        on_delete=models.PROTECT,
        related_name="applied_commands_company",
        limit_choices_to={"unit_type": OrgUnit.UnitType.COMPANY},
    )
    branch = models.ForeignKey(
        OrgUnit,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="applied_commands_branch",
        limit_choices_to={"unit_type": OrgUnit.UnitType.BRANCH},
    )

    command_type = models.CharField(max_length=64)
    occurred_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(default=timezone.now, editable=False)
    applied_at = models.DateTimeField(null=True, blank=True)

    sequence = models.BigIntegerField(null=True, blank=True)

    payload_hash = models.CharField(max_length=64)  # sha256 hex
    prev_hash = models.CharField(max_length=64, default="", blank=True)

    result_status = models.CharField(max_length=16, choices=ResultStatus.choices)
    result_ref = models.JSONField(default=dict, blank=True)  # refs (ticket_id, movement_id, ...)
    error = models.JSONField(default=dict, blank=True)  # motivo estructurado si rejected

    class Meta:
        app_label = "sync_engine"
        indexes = [
            models.Index(fields=["device", "received_at"]),
            models.Index(fields=["company", "received_at"]),
            models.Index(fields=["result_status", "received_at"]),
            models.Index(fields=["command_type"]),
        ]


class SyncReceipt(models.Model):
    batch_id = models.UUIDField(primary_key=True, editable=False)
    device = models.ForeignKey(Device, on_delete=models.PROTECT, related_name="sync_receipts")

    server_time = models.DateTimeField(default=timezone.now, editable=False)
    sent_at = models.DateTimeField(null=True, blank=True)

    received_count = models.PositiveIntegerField(default=0)
    applied_count = models.PositiveIntegerField(default=0)
    rejected_count = models.PositiveIntegerField(default=0)
    duplicate_count = models.PositiveIntegerField(default=0)

    errors_summary = models.JSONField(default=dict, blank=True)

    class Meta:
        app_label = "sync_engine"
        indexes = [
            models.Index(fields=["device", "server_time"]),
        ]
