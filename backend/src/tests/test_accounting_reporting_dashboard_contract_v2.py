from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _mk_org() -> tuple[OrgUnit, OrgUnit]:
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


def _mk_user(prefix: str = "acct"):
    username = f"{prefix}_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=username, email=f"{username}@test.local", password="pass12345")


def _client_with_perms(*, company: OrgUnit, branch: OrgUnit, perm_codes: list[str]) -> APIClient:
    user = _mk_user("api")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)
    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perm_codes:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)

    client = APIClient()
    resp = client.post("/api/backend/auth/login/", {"username": user.username, "password": "pass12345"}, format="json")
    assert resp.status_code == 200
    access = resp.data.get("access") if isinstance(resp.data, dict) else None
    if isinstance(access, str) and access:
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {access}"
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client


@pytest.mark.django_db
def test_accounting_reports_canonical_v2_and_legacy_parity_headers():
    company, branch = _mk_org()
    dt = timezone.localdate()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["accounting.report.read"],
    )

    canonical = client.get(f"/api/backend/accounting/reports/trial-balance/?year={dt.year}&month={dt.month}")
    assert canonical.status_code == 200
    assert canonical.data["meta"]["contract_version"] == "2.0.0"
    assert canonical.data["meta"]["report_code"] == "TRIAL_BALANCE"
    assert "summary" in canonical.data
    assert "results" in canonical.data
    assert "pagination" in canonical.data

    legacy = client.get(f"/api/accounting/reports/trial-balance/?year={dt.year}&month={dt.month}")
    assert legacy.status_code == 200
    assert "count" in legacy.data
    assert "results" in legacy.data
    assert legacy.headers.get("Deprecation") == "true"
    assert legacy.headers.get("Sunset") == "Mon, 18 May 2026 00:00:00 GMT"
    assert legacy.headers.get("Link") == '</api/backend/accounting/>; rel="successor-version"'
    assert int(legacy.data["count"]) == int(canonical.data["pagination"]["count"])


@pytest.mark.django_db
def test_accounting_dashboard_canonical_and_legacy_alias_with_deprecation():
    company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["accounting.dashboard.read"],
    )

    canonical = client.get("/api/backend/accounting/dashboard/executive-summary/")
    assert canonical.status_code == 200
    assert canonical.data["meta"]["contract_version"] == "2.0.0"
    assert canonical.data["meta"]["report_code"] == "DASHBOARD_EXECUTIVE_SUMMARY"
    assert "summary" in canonical.data
    assert "results" in canonical.data
    assert "pagination" in canonical.data

    legacy = client.get("/api/accounting/dashboard/executive-summary/")
    assert legacy.status_code == 200
    assert legacy.headers.get("Deprecation") == "true"
    assert legacy.headers.get("Sunset") == "Mon, 18 May 2026 00:00:00 GMT"
    assert legacy.headers.get("Link") == '</api/backend/accounting/>; rel="successor-version"'
    assert legacy.data["meta"]["report_code"] == "DASHBOARD_EXECUTIVE_SUMMARY"

