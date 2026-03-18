from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.iam.models import OrgUnit


class OutboxEvent(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SENT = "SENT", "Sent"
        FAILED = "FAILED", "Failed"

    event_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    source_module = models.CharField(max_length=64)
    event_type = models.CharField(max_length=128)
    schema_version = models.PositiveSmallIntegerField(default=1)

    company = models.ForeignKey(
        OrgUnit,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="outbox_events_company",
    )
    branch = models.ForeignKey(
        OrgUnit,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="outbox_events_branch",
    )
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="outbox_events_actor",
    )

    device_id = models.CharField(max_length=96, blank=True, default="")
    correlation_id = models.CharField(max_length=96, blank=True, default="")
    causation_id = models.CharField(max_length=96, blank=True, default="")
    payload = models.JSONField(default=dict)

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.PENDING)
    attempt_count = models.PositiveIntegerField(default=0)
    last_error = models.CharField(max_length=255, blank=True, default="")

    occurred_at = models.DateTimeField(default=timezone.now)
    published_at = models.DateTimeField(null=True, blank=True)
    next_attempt_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "integration"
        indexes = [
            models.Index(fields=["status", "occurred_at"]),
            models.Index(fields=["status", "next_attempt_at"]),
            models.Index(fields=["source_module", "event_type", "occurred_at"]),
        ]


class InboxEvent(models.Model):
    class Status(models.TextChoices):
        RECEIVED = "RECEIVED", "Received"
        PROCESSED = "PROCESSED", "Processed"
        FAILED = "FAILED", "Failed"

    event_id = models.UUIDField()
    consumer = models.CharField(max_length=64)

    source_module = models.CharField(max_length=64, blank=True, default="")
    event_type = models.CharField(max_length=128)
    schema_version = models.PositiveSmallIntegerField(default=1)
    payload = models.JSONField(default=dict)

    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RECEIVED)
    last_error = models.CharField(max_length=255, blank=True, default="")

    received_at = models.DateTimeField(default=timezone.now, editable=False)
    processed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "integration"
        constraints = [
            models.UniqueConstraint(fields=["event_id", "consumer"], name="uq_inbox_event_consumer"),
        ]
        indexes = [
            models.Index(fields=["consumer", "status", "received_at"]),
        ]
