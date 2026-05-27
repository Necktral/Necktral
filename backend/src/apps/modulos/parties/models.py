from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Q
from django.utils import timezone

from apps.modulos.iam.models import OrgUnit


def _trim(value: str | None) -> str:
    return (value or "").strip()


def _normalize_identifier(value: str | None) -> str:
    return _trim(value).upper()


class Party(models.Model):
    class PartyType(models.TextChoices):
        NATURAL = "NATURAL", "Natural"
        JURIDICAL = "JURIDICAL", "Juridical"
        INTERNAL = "INTERNAL", "Internal"

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Active"
        INACTIVE = "INACTIVE", "Inactive"
        BLOCKED = "BLOCKED", "Blocked"

    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="parties")
    party_type = models.CharField(max_length=16, choices=PartyType.choices)
    display_name = models.CharField(max_length=200)
    legal_name = models.CharField(max_length=255, blank=True, default="")
    tax_id = models.CharField(max_length=64, blank=True, default="")
    national_id = models.CharField(max_length=64, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=64, blank=True, default="")
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.ACTIVE)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "parties"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "tax_id"],
                condition=~Q(tax_id=""),
                name="uq_party_company_tax_id",
            ),
            models.UniqueConstraint(
                fields=["company", "national_id"],
                condition=~Q(national_id=""),
                name="uq_party_company_national_id",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "status", "display_name"], name="ix_party_company_status_name"),
            models.Index(fields=["company", "tax_id"], name="ix_party_company_tax_id"),
            models.Index(fields=["company", "national_id"], name="ix_party_company_nat_id"),
        ]

    def normalize(self) -> None:
        self.display_name = _trim(self.display_name)
        self.legal_name = _trim(self.legal_name)
        self.tax_id = _normalize_identifier(self.tax_id)
        self.national_id = _normalize_identifier(self.national_id)
        self.email = _trim(self.email).lower()
        self.phone = _trim(self.phone)

    def clean(self):
        super().clean()
        self.normalize()
        if not self.display_name:
            raise ValidationError({"display_name": "display_name es obligatorio."})
        if self.company_id and self.company.unit_type != OrgUnit.UnitType.COMPANY:
            raise ValidationError({"company": "Party.company debe ser OrgUnit de tipo COMPANY."})

    def full_clean(self, exclude=None, validate_unique=True, validate_constraints=True):
        self.normalize()
        return super().full_clean(
            exclude=exclude,
            validate_unique=validate_unique,
            validate_constraints=validate_constraints,
        )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return self.display_name


class PartyRole(models.Model):
    class Role(models.TextChoices):
        CUSTOMER = "CUSTOMER", "Customer"
        SUPPLIER = "SUPPLIER", "Supplier"
        EMPLOYEE = "EMPLOYEE", "Employee"
        PRODUCER = "PRODUCER", "Producer"
        DECLARANT = "DECLARANT", "Declarant"
        EXTERNAL_BUYER = "EXTERNAL_BUYER", "External buyer"

    party = models.ForeignKey(Party, on_delete=models.CASCADE, related_name="roles")
    role = models.CharField(max_length=32, choices=Role.choices)
    is_active = models.BooleanField(default=True)
    valid_from = models.DateTimeField(default=timezone.now)
    valid_to = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "parties"
        constraints = [
            models.UniqueConstraint(
                fields=["party", "role"],
                condition=Q(is_active=True),
                name="uq_party_role_active",
            ),
        ]
        indexes = [
            models.Index(fields=["party", "is_active"], name="ix_partyrole_party_active"),
            models.Index(fields=["party", "role", "is_active"], name="ix_partyrole_party_role_active"),
            models.Index(fields=["role", "is_active"], name="ix_partyrole_role_active"),
        ]

    def clean(self):
        super().clean()
        if self.valid_to and self.valid_from and self.valid_to < self.valid_from:
            raise ValidationError({"valid_to": "valid_to no puede ser anterior a valid_from."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.party_id}:{self.role}"
