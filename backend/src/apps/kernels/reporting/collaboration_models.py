"""
Collaborative features for reporting: annotations, comments, and sharing.
"""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

from apps.modulos.iam.models import OrgUnit

User = get_user_model()


class ReportAnnotation(models.Model):
    """
    User annotations on report data points or visualizations.

    Allows users to add notes, highlights, and comments to specific
    parts of a report for collaboration and knowledge sharing.
    """

    class AnnotationType(models.TextChoices):
        NOTE = "NOTE", "Note"
        HIGHLIGHT = "HIGHLIGHT", "Highlight"
        QUESTION = "QUESTION", "Question"
        INSIGHT = "INSIGHT", "Insight"
        ALERT = "ALERT", "Alert"

    # Identification
    id = models.BigAutoField(primary_key=True)
    annotation_type = models.CharField(
        max_length=20,
        choices=AnnotationType.choices,
        default=AnnotationType.NOTE,
    )

    # Scope
    company = models.ForeignKey(
        OrgUnit,
        on_delete=models.CASCADE,
        related_name="report_annotations",
        limit_choices_to={"unit_type": OrgUnit.UnitType.COMPANY},
    )
    branch = models.ForeignKey(
        OrgUnit,
        on_delete=models.CASCADE,
        related_name="branch_report_annotations",
        null=True,
        blank=True,
        limit_choices_to={"unit_type": OrgUnit.UnitType.BRANCH},
    )

    # Report context
    dataset_key = models.CharField(max_length=200, db_index=True)
    run_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    workspace_key = models.CharField(max_length=100, null=True, blank=True)

    # Annotation location (JSON path or coordinates)
    target_path = models.JSONField(
        default=dict,
        help_text="JSON path to the data point or visualization element",
    )

    # Content
    title = models.CharField(max_length=500, blank=True)
    content = models.TextField()
    metadata = models.JSONField(
        default=dict,
        help_text="Additional metadata (color, position, etc.)",
    )

    # Authorship
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="created_annotations",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Collaboration
    is_shared = models.BooleanField(default=False)
    is_resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="resolved_annotations",
    )

    class Meta:
        db_table = "reporting_annotation"
        indexes = [
            models.Index(fields=["company", "dataset_key", "created_at"]),
            models.Index(fields=["created_by", "is_shared"]),
            models.Index(fields=["is_resolved", "annotation_type"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.annotation_type}: {self.title or self.content[:50]}"

    def resolve(self, user: User) -> None:
        """Mark annotation as resolved"""
        self.is_resolved = True
        self.resolved_at = timezone.now()
        self.resolved_by = user
        self.save(update_fields=["is_resolved", "resolved_at", "resolved_by", "updated_at"])


class ReportComment(models.Model):
    """
    Comments on annotations for threaded discussions.
    """

    # Identification
    id = models.BigAutoField(primary_key=True)

    # Parent annotation
    annotation = models.ForeignKey(
        ReportAnnotation,
        on_delete=models.CASCADE,
        related_name="comments",
    )

    # Thread support
    parent_comment = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="replies",
    )

    # Content
    content = models.TextField()
    metadata = models.JSONField(default=dict)

    # Authorship
    created_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="report_comments",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Status
    is_edited = models.BooleanField(default=False)
    is_deleted = models.BooleanField(default=False)

    class Meta:
        db_table = "reporting_comment"
        indexes = [
            models.Index(fields=["annotation", "created_at"]),
            models.Index(fields=["parent_comment", "is_deleted"]),
        ]
        ordering = ["created_at"]

    def __str__(self):
        return f"Comment by {self.created_by} on {self.annotation}"


class ReportShare(models.Model):
    """
    Share reports/dashboards with specific users or teams.
    """

    class ShareType(models.TextChoices):
        VIEW_ONLY = "VIEW_ONLY", "View Only"
        CAN_COMMENT = "CAN_COMMENT", "Can Comment"
        CAN_EDIT = "CAN_EDIT", "Can Edit"

    # Identification
    id = models.BigAutoField(primary_key=True)

    # Scope
    company = models.ForeignKey(
        OrgUnit,
        on_delete=models.CASCADE,
        related_name="report_shares",
        limit_choices_to={"unit_type": OrgUnit.UnitType.COMPANY},
    )

    # Report/Dashboard context
    dataset_key = models.CharField(max_length=200, null=True, blank=True)
    workspace_key = models.CharField(max_length=100, null=True, blank=True)
    saved_view_id = models.BigIntegerField(null=True, blank=True)

    # Sharing details
    share_type = models.CharField(
        max_length=20,
        choices=ShareType.choices,
        default=ShareType.VIEW_ONLY,
    )

    # Recipients
    shared_with_user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="received_report_shares",
    )
    # Future: could add team/role sharing
    # shared_with_role = models.ForeignKey(Role, ...)

    # Share metadata
    share_url = models.CharField(max_length=500, blank=True)
    share_token = models.CharField(max_length=100, unique=True, null=True, blank=True)
    expires_at = models.DateTimeField(null=True, blank=True)

    # Authorship
    shared_by = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="shared_reports",
    )
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    # Status
    is_active = models.BooleanField(default=True, db_index=True)
    last_accessed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "reporting_share"
        indexes = [
            models.Index(fields=["company", "is_active"]),
            models.Index(fields=["shared_with_user", "is_active"]),
            models.Index(fields=["share_token"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"Share: {self.dataset_key or self.workspace_key} to {self.shared_with_user}"

    def is_expired(self) -> bool:
        """Check if share has expired"""
        if self.expires_at is None:
            return False
        return timezone.now() > self.expires_at


class DataQualityAlert(models.Model):
    """
    Data quality monitoring and alerting for datasets.
    """

    class Severity(models.TextChoices):
        INFO = "INFO", "Info"
        WARNING = "WARNING", "Warning"
        ERROR = "ERROR", "Error"
        CRITICAL = "CRITICAL", "Critical"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        ACKNOWLEDGED = "ACKNOWLEDGED", "Acknowledged"
        RESOLVED = "RESOLVED", "Resolved"
        IGNORED = "IGNORED", "Ignored"

    # Identification
    id = models.BigAutoField(primary_key=True)
    alert_code = models.CharField(max_length=100, db_index=True)

    # Scope
    company = models.ForeignKey(
        OrgUnit,
        on_delete=models.CASCADE,
        related_name="quality_alerts",
        limit_choices_to={"unit_type": OrgUnit.UnitType.COMPANY},
    )
    branch = models.ForeignKey(
        OrgUnit,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="branch_quality_alerts",
        limit_choices_to={"unit_type": OrgUnit.UnitType.BRANCH},
    )

    # Dataset context
    dataset_key = models.CharField(max_length=200, db_index=True)
    run_id = models.BigIntegerField(null=True, blank=True)

    # Alert details
    severity = models.CharField(
        max_length=20,
        choices=Severity.choices,
        default=Severity.WARNING,
        db_index=True,
    )
    title = models.CharField(max_length=500)
    description = models.TextField()
    details = models.JSONField(
        default=dict,
        help_text="Detailed quality metrics and failure info",
    )

    # Detection
    detected_at = models.DateTimeField(auto_now_add=True, db_index=True)
    detection_rule = models.CharField(max_length=200, blank=True)

    # Status
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        db_index=True,
    )
    acknowledged_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="acknowledged_alerts",
    )
    acknowledged_at = models.DateTimeField(null=True, blank=True)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "reporting_quality_alert"
        indexes = [
            models.Index(fields=["company", "status", "severity"]),
            models.Index(fields=["dataset_key", "detected_at"]),
            models.Index(fields=["status", "detected_at"]),
        ]
        ordering = ["-detected_at"]

    def __str__(self):
        return f"{self.severity}: {self.title} ({self.dataset_key})"

    def acknowledge(self, user: User) -> None:
        """Acknowledge the alert"""
        self.status = self.Status.ACKNOWLEDGED
        self.acknowledged_by = user
        self.acknowledged_at = timezone.now()
        self.save(update_fields=["status", "acknowledged_by", "acknowledged_at"])

    def resolve(self) -> None:
        """Mark alert as resolved"""
        self.status = self.Status.RESOLVED
        self.resolved_at = timezone.now()
        self.save(update_fields=["status", "resolved_at"])
