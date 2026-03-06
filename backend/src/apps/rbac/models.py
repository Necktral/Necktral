from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from apps.iam.models import OrgUnit


# --- Asignación de roles por alcance (empresa/sucursal) ---
class RoleAssignment(models.Model):
    """
    Asignación de rol por alcance (scope):
      - org_unit: COMPANY o BRANCH
      - is_active: revocar sin borrar
      - origin: trazabilidad (MANUAL / POSITION / SYSTEM)
    """

    class Origin(models.TextChoices):
        MANUAL = "MANUAL", "Manual"
        POSITION = "POSITION", "Position automation"
        SYSTEM = "SYSTEM", "System bootstrap"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="role_assignments")
    role = models.ForeignKey("rbac.Role", on_delete=models.PROTECT, related_name="assignments")
    org_unit = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="role_assignments")

    origin = models.CharField(max_length=16, choices=Origin.choices, default=Origin.MANUAL)
    origin_ref = models.CharField(max_length=128, blank=True, default="")

    is_active = models.BooleanField(default=True)

    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="role_assignments_granted",
    )
    granted_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "rbac"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "role", "org_unit", "origin"],
                name="uq_roleassignment_user_role_orgunit_origin",
            ),
        ]
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["org_unit", "is_active"]),
            models.Index(fields=["role", "is_active"]),
            models.Index(fields=["origin", "is_active"]),
        ]

    def clean(self):
        if self.org_unit.unit_type not in (OrgUnit.UnitType.COMPANY, OrgUnit.UnitType.BRANCH):
            raise ValidationError("RoleAssignment.org_unit debe ser COMPANY o BRANCH.")

    def __str__(self) -> str:
        return f"{self.user_id} -> {self.role_id} @ {self.org_unit_id} ({self.origin})"


class Role(models.Model):
    class Meta:
        app_label = "rbac"
        indexes = [
            models.Index(fields=["is_active", "name"]),
        ]
    name = models.CharField(max_length=64, unique=True)
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.name


class Permission(models.Model):
    class Meta:
        app_label = "rbac"
        indexes = [
            models.Index(fields=["is_active", "code"]),
        ]
    code = models.CharField(max_length=128, unique=True)  # ejemplo: "inventory.read"
    description = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)

    def __str__(self) -> str:
        return self.code


class RolePermission(models.Model):
    role = models.ForeignKey(Role, on_delete=models.CASCADE)
    permission = models.ForeignKey(Permission, on_delete=models.CASCADE)

    class Meta:
        app_label = "rbac"
        unique_together = ("role", "permission")


class UserRole(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    role = models.ForeignKey(Role, on_delete=models.CASCADE)

    class Meta:
        app_label = "rbac"
        unique_together = ("user", "role")
