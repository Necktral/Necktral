from __future__ import annotations

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.modulos.iam.models import OrgUnit
from apps.modulos.rbac.models import Role


class JobPosition(models.Model):
    company = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="job_positions")
    code = models.CharField(max_length=64, blank=True, default="")
    name = models.CharField(max_length=200)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "hr"
        constraints = [
            models.UniqueConstraint(fields=["company", "name"], name="uq_position_company_name"),
        ]
        indexes = [
            models.Index(fields=["company", "is_active"]),
        ]


class PositionRoleMap(models.Model):
    """
    Mapeo Puesto -> Role (automatización controlada).
    """

    class ScopeMode(models.TextChoices):
        COMPANY = "COMPANY", "Company"
        BRANCH = "BRANCH", "Branch"

    position = models.ForeignKey(JobPosition, on_delete=models.CASCADE, related_name="role_maps")
    role = models.ForeignKey(Role, on_delete=models.PROTECT, related_name="position_maps")
    scope_mode = models.CharField(max_length=16, choices=ScopeMode.choices, default=ScopeMode.BRANCH)
    is_active = models.BooleanField(default=True)

    class Meta:
        app_label = "hr"
        constraints = [
            models.UniqueConstraint(fields=["position", "role", "scope_mode"], name="uq_position_role_scope"),
        ]


class Employee(models.Model):
    company = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="employees")
    employee_code = models.CharField(max_length=64, blank=True, default="")
    first_name = models.CharField(max_length=120)
    last_name = models.CharField(max_length=120, blank=True, default="")
    phone = models.CharField(max_length=64, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    linked_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="employee_links",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "hr"
        indexes = [
            models.Index(fields=["company", "is_active"]),
            models.Index(fields=["linked_user"]),
        ]


class EmploymentAssignment(models.Model):
    employee = models.ForeignKey(Employee, on_delete=models.CASCADE, related_name="assignments")
    position = models.ForeignKey(JobPosition, on_delete=models.PROTECT, related_name="assignments")
    branch = models.ForeignKey(
        OrgUnit, null=True, blank=True, on_delete=models.PROTECT, related_name="employment_assignments"
    )
    is_active = models.BooleanField(default=True)
    started_at = models.DateTimeField(default=timezone.now, editable=False)
    ended_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="employment_assignments_created",
    )

    class Meta:
        app_label = "hr"
        indexes = [
            models.Index(fields=["employee", "is_active"]),
            models.Index(fields=["employee", "is_active", "started_at"]),
            models.Index(fields=["position", "is_active"]),
            models.Index(fields=["branch", "is_active"]),
        ]
