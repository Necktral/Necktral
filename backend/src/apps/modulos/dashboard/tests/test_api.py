from __future__ import annotations

import uuid
from urllib.parse import unquote

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.kernels.reporting.models import ReportRun
from apps.modulos.dashboard.models import DashboardEmbedGrant
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _mk_org():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="Holding")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="Company", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="Branch", parent=company)
    return company, branch


def _mk_user(prefix: str = "dash"):
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
    login = client.post("/api/auth/login/", {"username": user.username, "password": "pass12345"}, format="json")
    assert login.status_code == 200
    access = login.data.get("access") if isinstance(login.data, dict) else None
    if isinstance(access, str) and access:
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client


@pytest.mark.django_db
def test_dashboard_embed_token_redeem_and_reporting_access():
    company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "report.dashboard.read",
            "report.dataset.read",
            "fuel.reports.view",
            "accounting.report.read",
        ],
    )

    ws = client.get("/api/backend/dashboard/workspaces/")
    assert ws.status_code == 200
    results = ws.data["results"]
    assert any(row["workspace_key"] == "operations" for row in results)

    issued = client.post(
        "/api/backend/dashboard/embed-token/",
        {"workspace_key": "operations"},
        format="json",
    )
    assert issued.status_code == 200
    bootstrap = str(issued.data["bootstrap_url"])
    assert bootstrap.startswith("/analytics/bootstrap?token=")
    token = unquote(bootstrap.split("token=", 1)[1])
    assert DashboardEmbedGrant.objects.count() == 1

    redeemed = client.post(
        "/api/backend/dashboard/embed-token/redeem/",
        {"token": token},
        format="json",
    )
    assert redeemed.status_code == 200
    reporting_token = str(redeemed.data["reporting_access_token"])
    assert reporting_token

    replay = client.post(
        "/api/backend/dashboard/embed-token/redeem/",
        {"token": token},
        format="json",
    )
    assert replay.status_code == 409

    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {reporting_token}")
    run = api.post(
        "/api/reporting/datasets/fuel.dispense_vs_sale.daily/run/",
        {"filters": {}},
        format="json",
    )
    assert run.status_code == 200
    assert run.data["dataset_key"] == "fuel.dispense_vs_sale.daily"
    assert "run_id" in run.data
    run_row = ReportRun.objects.filter(run_id=run.data["run_id"]).first()
    assert run_row is not None
    assert run_row.consumer_type == "DASHBOARD"
    assert run_row.consumer_ref == "workspace:operations"


@pytest.mark.django_db
def test_dashboard_embed_token_requires_compose_when_requested():
    company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "report.dashboard.read",
            "report.dataset.read",
            "fuel.reports.view",
            "accounting.report.read",
        ],
    )

    denied = client.post(
        "/api/backend/dashboard/embed-token/",
        {"workspace_key": "operations", "require_compose": True},
        format="json",
    )
    assert denied.status_code == 403
