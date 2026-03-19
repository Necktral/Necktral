from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class AuditChainHead(models.Model):
    """
    Cabezal de cadena para encadenamiento consistente (prev_event_hash).
    Usamos una sola fila (id=1) y la bloqueamos con SELECT FOR UPDATE
    al escribir eventos, para evitar carreras en entornos concurrentes.
    """
    class Meta:
        app_label = "audit"
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    last_event_hash = models.CharField(max_length=64, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)


class AuditChainHeadV2(models.Model):
    """
    Cabezal de cadena particionado para reducir contención del lock.
    partition_key ejemplo:
            - SYSTEM
            - COMPANY:123
    """
    class Meta:
        app_label = "audit"
    partition_key = models.CharField(max_length=64, primary_key=True)
    last_event_hash = models.CharField(max_length=64, blank=True, default="")
    updated_at = models.DateTimeField(auto_now=True)


class AuditEvent(models.Model):
    """
    EAU v1 (mínimo contractual):
      - Identidad: event_id, schema_version, module
      - Semántica: event_type (AUTH_*), reason_code, subject_type/subject_id
      - Contexto: actor_user, device_id, ip_server_seen, offline_mode, user_agent, path, method, metadata
      - Integridad: prev_event_hash, event_hash, signature (HMAC sobre event_hash)
    """

    # Identidad
    event_id = models.UUIDField(default=uuid.uuid4, editable=False, unique=True)
    schema_version = models.PositiveSmallIntegerField(default=1)
    module = models.CharField(max_length=32, default="AUTH")

    # Semántica
    event_type = models.CharField(max_length=64)
    reason_code = models.CharField(max_length=64, blank=True, default="")

    subject_type = models.CharField(max_length=32, blank=True, default="")
    subject_id = models.CharField(max_length=128, blank=True, default="")

    # Contexto / actor
    partition_key = models.CharField(max_length=64, default="", blank=True, db_index=True)
    timestamp_server = models.DateTimeField()
    actor_user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    device_id = models.CharField(max_length=64, blank=True, default="")
    ip_server_seen = models.GenericIPAddressField(null=True, blank=True)
    offline_mode = models.BooleanField(default=False)
    user_agent = models.TextField(blank=True, default="")
    path = models.CharField(max_length=256, blank=True, default="")
    method = models.CharField(max_length=16, blank=True, default="")

    # Snapshots (cuando aplique)
    before_snapshot = models.JSONField(default=dict, blank=True)
    after_snapshot = models.JSONField(default=dict, blank=True)

    # Metadata
    metadata = models.JSONField(default=dict, blank=True)

    # Integridad (permitimos null por migración; nuevos eventos siempre tendrán valor)
    prev_event_hash = models.CharField(max_length=64, blank=True, default="")
    event_hash = models.CharField(max_length=64, null=True, blank=True)
    signature = models.CharField(max_length=64, null=True, blank=True)
    signature_key_id = models.CharField(max_length=32, blank=True, default="")

    class Meta:
        app_label = "audit"
        indexes = [
            models.Index(fields=["timestamp_server"]),
            models.Index(fields=["module", "event_type"]),
            models.Index(fields=["actor_user", "timestamp_server"]),
            models.Index(fields=["subject_type", "subject_id"]),
            models.Index(fields=["partition_key", "-timestamp_server"], name="audit_pk_ts_idx"),
            models.Index(fields=["partition_key", "event_type", "-timestamp_server"], name="audit_pk_type_ts_idx"),
            models.Index(fields=["partition_key", "reason_code", "-timestamp_server"], name="audit_pk_reason_ts_idx"),
        ]

    def __str__(self) -> str:
        return f"{self.timestamp_server} {self.module} {self.event_type}"
