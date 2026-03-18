from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone


class OrgUnit(models.Model):
    class UnitType(models.TextChoices):
        HOLDING = "HOLDING", "Holding"
        COMPANY = "COMPANY", "Company"
        BRANCH = "BRANCH", "Branch"

    unit_type = models.CharField(max_length=16, choices=UnitType.choices)
    name = models.CharField(max_length=200)
    code = models.CharField(max_length=64, blank=True, default="")
    parent = models.ForeignKey("self", null=True, blank=True, on_delete=models.PROTECT, related_name="children")
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "iam"
        indexes = [
            models.Index(fields=["unit_type", "is_active"]),
            models.Index(fields=["parent", "unit_type"]),
            models.Index(fields=["parent", "unit_type", "name"]),
        ]

    def clean(self):
        """
        Jerarquía fuerte:
          - HOLDING sin parent
          - COMPANY parent = HOLDING
          - BRANCH parent = COMPANY
        """
        if self.unit_type == self.UnitType.HOLDING:
            if self.parent_id is not None:
                raise ValidationError("HOLDING no puede tener parent.")
        elif self.unit_type == self.UnitType.COMPANY:
            if self.parent is None or self.parent.unit_type != self.UnitType.HOLDING:
                raise ValidationError("COMPANY requiere parent de tipo HOLDING.")
        elif self.unit_type == self.UnitType.BRANCH:
            if self.parent is None or self.parent.unit_type != self.UnitType.COMPANY:
                raise ValidationError("BRANCH requiere parent de tipo COMPANY.")

    def save(self, *args, **kwargs):
        is_new = self._state.adding

        # Bloqueo de “movimientos” de árbol en esta fase
        if not is_new and "update_fields" not in kwargs:
            old = OrgUnit.objects.filter(pk=self.pk).only("parent_id").first()
            if old and old.parent_id != self.parent_id:
                raise ValidationError("Cambiar parent no está habilitado en esta fase.")

        super().save(*args, **kwargs)

        if is_new:
            OrgClosure.create_for_new_node(self)

    def __str__(self) -> str:
        return f"{self.unit_type}:{self.name}"


class OrgClosure(models.Model):
    """
    Closure table: ancestor -> descendant con depth
    """

    ancestor = models.ForeignKey(OrgUnit, on_delete=models.CASCADE, related_name="closure_ancestor")
    descendant = models.ForeignKey(OrgUnit, on_delete=models.CASCADE, related_name="closure_descendant")
    depth = models.PositiveIntegerField()

    class Meta:
        app_label = "iam"
        constraints = [
            models.UniqueConstraint(fields=["ancestor", "descendant"], name="uq_orgclosure_ancestor_descendant"),
        ]
        indexes = [
            models.Index(fields=["ancestor", "depth"]),
            models.Index(fields=["descendant", "depth"]),
        ]

    @staticmethod
    def create_for_new_node(node: OrgUnit) -> None:
        """
        Inserta:
          - (node,node,0)
          - Para cada (a,parent,d): (a,node,d+1)
        """
        with transaction.atomic():
            OrgClosure.objects.create(ancestor=node, descendant=node, depth=0)

            if node.parent_id is None:
                return

            parent_paths = OrgClosure.objects.filter(descendant_id=node.parent_id).values("ancestor_id", "depth")
            OrgClosure.objects.bulk_create(
                [
                    OrgClosure(ancestor_id=row["ancestor_id"], descendant=node, depth=row["depth"] + 1)
                    for row in parent_paths
                ],
                ignore_conflicts=True,
            )


class UserMembership(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="memberships")
    org_unit = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="memberships")

    is_active = models.BooleanField(default=True)
    joined_at = models.DateTimeField(default=timezone.now, editable=False)
    left_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        app_label = "iam"
        constraints = [
            models.UniqueConstraint(fields=["user", "org_unit"], name="uq_membership_user_orgunit"),
        ]
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["org_unit", "is_active"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} -> {self.org_unit_id}"


class AdminGrant(models.Model):
    class Capability(models.TextChoices):
        MANAGE_USERS = "MANAGE_USERS", "Manage users"
        MANAGE_ROLE_ASSIGNMENTS = "MANAGE_ROLE_ASSIGNMENTS", "Manage role assignments"
        VIEW_REPORTS = "VIEW_REPORTS", "View reports"
        VIEW_AUDIT = "VIEW_AUDIT", "View audit"

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="admin_grants")
    org_unit = models.ForeignKey(OrgUnit, on_delete=models.PROTECT, related_name="admin_grants")

    capability = models.CharField(max_length=64, choices=Capability.choices)
    applies_to_subtree = models.BooleanField(default=True)
    is_active = models.BooleanField(default=True)

    granted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="admin_grants_given",
    )
    granted_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        app_label = "iam"
        constraints = [
            models.UniqueConstraint(fields=["user", "org_unit", "capability"], name="uq_admingrant_user_org_cap"),
        ]
        indexes = [
            models.Index(fields=["user", "is_active"]),
            models.Index(fields=["org_unit", "capability"]),
        ]

    def __str__(self) -> str:
        return f"{self.user_id} {self.capability} @ {self.org_unit_id}"


class CompanyLink(models.Model):
    class LinkType(models.TextChoices):
        HOLDING = "HOLDING", "Holding"
        ALLIANCE = "ALLIANCE", "Alliance"
        FRANCHISE = "FRANCHISE", "Franchise"
        SUPPLIER = "SUPPLIER", "Supplier"
        CORPORATE_CLIENT = "CORPORATE_CLIENT", "Corporate client"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"

    from_company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="outgoing_company_links")
    to_company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="incoming_company_links")

    link_type = models.CharField(max_length=32, choices=LinkType.choices, default=LinkType.ALLIANCE)
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    is_active = models.BooleanField(default=True)

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "iam"
        constraints = [
            models.UniqueConstraint(fields=["from_company", "to_company"], name="uq_companylink_from_to"),
        ]
        indexes = [
            models.Index(fields=["from_company", "status", "is_active"]),
            models.Index(fields=["to_company", "status", "is_active"]),
        ]

    def clean(self):
        if self.from_company_id and self.to_company_id and self.from_company_id == self.to_company_id:
            raise ValidationError("CompanyLink no permite from_company == to_company.")

        if self.from_company_id and self.from_company.unit_type != OrgUnit.UnitType.COMPANY:
            raise ValidationError("from_company debe ser COMPANY.")
        if self.to_company_id and self.to_company.unit_type != OrgUnit.UnitType.COMPANY:
            raise ValidationError("to_company debe ser COMPANY.")

    def __str__(self) -> str:
        return f"{self.from_company_id} -> {self.to_company_id} ({self.status})"


class LinkGrant(models.Model):
    class AccessMode(models.TextChoices):
        READ = "READ", "Read"
        WRITE = "WRITE", "Write"

    link = models.ForeignKey(CompanyLink, on_delete=models.CASCADE, related_name="grants")
    permission = models.ForeignKey("rbac.Permission", on_delete=models.PROTECT, related_name="intercompany_grants")

    access_mode = models.CharField(max_length=8, choices=AccessMode.choices, default=AccessMode.READ)

    scope_org_unit = models.ForeignKey(
        "iam.OrgUnit",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="intercompany_grant_scopes",
        help_text="NULL => toda from_company; no-NULL => BRANCH de from_company.",
    )

    is_active = models.BooleanField(default=True)
    valid_from = models.DateTimeField(null=True, blank=True)
    valid_to = models.DateTimeField(null=True, blank=True)

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "iam"
        constraints = [
            models.UniqueConstraint(
                fields=["link", "permission", "access_mode", "scope_org_unit"],
                name="uq_linkgrant_link_perm_mode_scope",
            ),
        ]
        indexes = [
            models.Index(fields=["is_active", "access_mode"]),
            models.Index(fields=["permission", "access_mode"]),
            models.Index(fields=["scope_org_unit"]),
        ]

    def clean(self):
        if self.scope_org_unit_id is None:
            return

        if self.scope_org_unit.unit_type != OrgUnit.UnitType.BRANCH:
            raise ValidationError("scope_org_unit debe ser BRANCH.")
        if self.scope_org_unit.parent_id != self.link.from_company_id:
            raise ValidationError("scope_org_unit debe pertenecer a from_company del link.")

    def __str__(self) -> str:
        return f"Grant {self.permission_id} {self.access_mode} on link {self.link_id}"
