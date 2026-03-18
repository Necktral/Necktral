from __future__ import annotations

import uuid
from typing import ClassVar

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.iam.models import OrgUnit


class CloseRun(models.Model):
    class RunType(models.TextChoices):
        DAILY = "DAILY", "Daily"
        PERIODIC = "PERIODIC", "Periodic"

    class Status(models.TextChoices):
        CREATED = "CREATED", "Created"
        GATHERED = "GATHERED", "Gathered"
        VALIDATED = "VALIDATED", "Validated"
        PACKAGED = "PACKAGED", "Packaged"
        DELIVERED = "DELIVERED", "Delivered"
        REOPENED_EXCEPTION = "REOPENED_EXCEPTION", "Reopened exception"

    run_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    company = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="cec_close_runs_company")
    branch = models.ForeignKey(
        OrgUnit,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="cec_close_runs_branch",
    )

    run_type = models.CharField(max_length=16, choices=RunType.choices, default=RunType.DAILY)
    status = models.CharField(max_length=24, choices=Status.choices, default=Status.CREATED)

    started_at = models.DateTimeField(default=timezone.now, editable=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    window_start = models.DateTimeField(null=True, blank=True)
    window_end = models.DateTimeField(null=True, blank=True)

    input_manifest_hash = models.CharField(max_length=64, blank=True, default="")
    output_manifest_hash = models.CharField(max_length=64, blank=True, default="")
    consistency_score = models.PositiveSmallIntegerField(default=0)
    blocking_exceptions_count = models.PositiveIntegerField(default=0)
    summary_json = models.JSONField(default=dict)

    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cec_close_runs_created",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "cec"
        indexes = [
            models.Index(fields=["company", "branch", "run_type", "status", "started_at"]),
            models.Index(fields=["company", "branch", "window_start", "window_end"]),
        ]

    _ALLOWED_TRANSITIONS: ClassVar[dict[str, set[str]]] = {
        Status.CREATED: {Status.GATHERED, Status.REOPENED_EXCEPTION},
        Status.GATHERED: {Status.VALIDATED, Status.REOPENED_EXCEPTION},
        Status.VALIDATED: {Status.PACKAGED, Status.REOPENED_EXCEPTION},
        Status.PACKAGED: {Status.DELIVERED, Status.REOPENED_EXCEPTION},
        Status.DELIVERED: {Status.REOPENED_EXCEPTION},
        Status.REOPENED_EXCEPTION: {Status.GATHERED, Status.VALIDATED, Status.PACKAGED},
    }

    def can_transition_to(self, target_status: str) -> bool:
        if target_status == self.status:
            return True
        allowed = self._ALLOWED_TRANSITIONS.get(self.status, set())
        return target_status in allowed


class CECException(models.Model):
    class Severity(models.TextChoices):
        LOW = "LOW", "Low"
        MEDIUM = "MEDIUM", "Medium"
        HIGH = "HIGH", "High"
        CRITICAL = "CRITICAL", "Critical"

    class Status(models.TextChoices):
        OPEN = "OPEN", "Open"
        IN_PROGRESS = "IN_PROGRESS", "In progress"
        RESOLVED = "RESOLVED", "Resolved"
        CLOSED = "CLOSED", "Closed"

    exception_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    source_module = models.CharField(max_length=64)
    code = models.CharField(max_length=64)
    severity = models.CharField(max_length=12, choices=Severity.choices, default=Severity.MEDIUM)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.OPEN)

    company = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="cec_exceptions_company")
    branch = models.ForeignKey(
        OrgUnit,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="cec_exceptions_branch",
    )

    related_object_type = models.CharField(max_length=64, blank=True, default="")
    related_object_id = models.CharField(max_length=64, blank=True, default="")
    fingerprint = models.CharField(max_length=64, blank=True, default="", db_index=True)
    is_blocking = models.BooleanField(default=False)
    details_json = models.JSONField(default=dict)

    opened_at = models.DateTimeField(default=timezone.now, editable=False)
    assigned_to = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="cec_exceptions_assigned",
    )
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolution_note = models.TextField(blank=True, default="")

    close_run = models.ForeignKey(
        CloseRun,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="exceptions",
    )

    class Meta:
        app_label = "cec"
        indexes = [
            models.Index(fields=["status", "severity", "opened_at"]),
            models.Index(fields=["company", "branch", "status"]),
        ]


class EvidenceArtifact(models.Model):
    artifact_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    support_id = models.CharField(max_length=96, unique=True)
    sha256 = models.CharField(max_length=64)
    mime_type = models.CharField(max_length=64)
    storage_ref = models.CharField(max_length=255)
    metadata_json = models.JSONField(default=dict)

    close_run = models.ForeignKey(
        CloseRun,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="artifacts",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "cec"
        indexes = [
            models.Index(fields=["close_run", "created_at"]),
        ]
