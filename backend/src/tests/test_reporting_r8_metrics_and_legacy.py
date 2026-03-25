from __future__ import annotations

import uuid

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _mk_org():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="Holding")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="Company", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="Branch", parent=company)
    return company, branch


def _mk_user(prefix: str = "r8"):
    username = f"{prefix}_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=username, email=f"{username}@test.local", password="pass12345")


def _client_with_perms(*, company: OrgUnit, branch: OrgUnit, perm_codes: list[str], is_staff: bool = False) -> APIClient:
    user = _mk_user("api")
    user.is_staff = bool(is_staff)
    user.save(update_fields=["is_staff"])
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)
    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perm_codes:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)

    client = APIClient()
    login = client.post("/api/auth/login/", {"username": user.username, "password": "pass12345"}, format="json")
    assert login.status_code == 200
    access = login.data.get("access") if isinstance(login.data, dict) else None
    if isinstance(access, str) and access:
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client


@pytest.mark.django_db
def test_metrics_endpoint_includes_reporting_and_dashboard_blocks():
    company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["report.dashboard.read"],
        is_staff=True,
    )
    response = client.get("/api/metrics/")
    assert response.status_code == 200
    assert "reporting" in response.data
    assert "dashboard" in response.data
    reporting = dict(response.data["reporting"] or {})
    dashboard = dict(response.data["dashboard"] or {})
    assert "failure_classes_last_window" in reporting
    assert "dataset_slo" in reporting
    assert "runs_by_consumer_type" in reporting
    assert "top_consumers" in reporting
    assert "workspace_redeem_rate" in dashboard
    assert "legacy_api_counts" in response.data


@pytest.mark.django_db
def test_accounting_reports_legacy_prefix_emits_deprecation_headers():
    company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["accounting.report.read"],
    )
    response = client.get("/api/accounting/reports/trial-balance/?year=2026&month=3")
    assert response.status_code == 200
    assert response.headers.get("Deprecation") == "true"
    assert response.headers.get("Sunset") == settings.REPORTING_LEGACY_ACCOUNTING_REPORTS_SUNSET
    assert response.headers.get("Link") == '</api/reporting/catalog/>; rel="successor-version"'
