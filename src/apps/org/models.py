from __future__ import annotations

from django.db import models
from django.utils import timezone

from apps.iam.models import OrgUnit

class CompanyProfile(models.Model):
    """
    Tabla separada para datos de empresa.
    Canon de jerarquía sigue siendo OrgUnit (COMPANY).
    """
    company = models.OneToOneField(OrgUnit, on_delete=models.CASCADE, related_name="company_profile")
    legal_name = models.CharField(max_length=255, blank=True, default="")
    tax_id = models.CharField(max_length=64, blank=True, default="")
    address = models.TextField(blank=True, default="")
    phone = models.CharField(max_length=64, blank=True, default="")
    email = models.EmailField(blank=True, default="")

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.company.unit_type != OrgUnit.UnitType.COMPANY:
            raise ValueError("CompanyProfile.company debe ser OrgUnit de tipo COMPANY.")

class BranchProfile(models.Model):
    """
    Tabla separada para datos de sucursal.
    Canon de jerarquía sigue siendo OrgUnit (BRANCH).
    """
    branch = models.OneToOneField(OrgUnit, on_delete=models.CASCADE, related_name="branch_profile")
    address = models.TextField(blank=True, default="")
    phone = models.CharField(max_length=64, blank=True, default="")
    email = models.EmailField(blank=True, default="")

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    def clean(self):
        if self.branch.unit_type != OrgUnit.UnitType.BRANCH:
            raise ValueError("BranchProfile.branch debe ser OrgUnit de tipo BRANCH.")
