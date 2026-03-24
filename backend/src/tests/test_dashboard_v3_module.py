from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.modulos.audit.models import AuditEvent
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission
from apps.modulos.reports.registry import REPORT_SPECS

User = get_user_model()


DASHBOARD_BASE = "/api/backend/dashboard"


def _mk_org_tree(label: str) -> tuple[OrgUnit, OrgUnit, OrgUnit]:
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H-{label}", code=f"H-{label}")
    company = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.COMPANY,
        name=f"C-{label}",
        code=f"C-{label}",
        parent=holding,
    )
    branch = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.BRANCH,
        name=f"B-{label}",
        code=f"B-{label}",
        parent=company,
    )
    return holding, company, branch


def _mk_user(*, label: str, password: str = "Pass12345!"):
    return User.objects.create_user(username=f"user_{label}", email=f"{label}@test.com", password=password)


def _grant_local_permission(*, user, company: OrgUnit, branch: OrgUnit, permission_code: str) -> None:
    role = Role.objects.create(name=f"role-{uuid.uuid4().hex[:8]}", is_active=True)
    perm, _ = Permission.objects.get_or_create(
        code=permission_code,
        defaults={"description": permission_code, "is_active": True},
    )
    RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)


def _login_client(*, user, password: str, company: OrgUnit, branch: OrgUnit) -> APIClient:
    client = APIClient()
    resp = client.post("/api/backend/auth/login/", {"username": user.username, "password": password}, format="json")
    assert resp.status_code == 200
    access = resp.data.get("access")
    assert isinstance(access, str) and access
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {access}",
        HTTP_X_COMPANY_ID=str(company.id),
        HTTP_X_BRANCH_ID=str(branch.id),
    )
    return client


@pytest.mark.django_db
def test_dashboard_v3_catalog_workspace_query_and_drilldown_contracts():
    _, company, branch = _mk_org_tree("dash-v3")
    user = _mk_user(label="dash-v3")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    perms = [
        "dashboard.workspace.read",
        "dashboard.widget.read",
        "dashboard.drilldown.read",
        "dashboard.intercompany.read",
        "reports.audit.read",
        "reports.observability.read",
        "reports.trace.read",
        "reports.control.read",
        "reports.financial.read",
        "reports.security.read",
    ]
    for code in perms:
        _grant_local_permission(user=user, company=company, branch=branch, permission_code=code)

    client = _login_client(user=user, password="Pass12345!", company=company, branch=branch)

    catalog = client.get(f"{DASHBOARD_BASE}/catalog/")
    assert catalog.status_code == 200
    assert catalog.data["meta"]["contract_version"] == "3.0.0"
    assert catalog.data["meta"]["report_code"] == "DASHBOARD_V3_CATALOG"
    assert int(catalog.data["summary"]["workspace_count"]) >= 5

    workspace = client.get(f"{DASHBOARD_BASE}/workspaces/executive_cross_domain/")
    assert workspace.status_code == 200
    assert workspace.data["meta"]["report_code"] == "DASHBOARD_V3_WORKSPACE"
    assert workspace.data["summary"]["workspace_code"] == "executive_cross_domain"

    query = client.post(
        f"{DASHBOARD_BASE}/workspaces/executive_cross_domain/query/",
        {
            "widget_code": "exec_revenue_velocity",
            "filters": {"status": ["ISSUED"]},
            "group_by": ["domain"],
            "metrics": ["entity_count", "health_score"],
            "comparison": {"mode": "prev_period"},
            "drill_path": ["series"],
        },
        format="json",
    )
    assert query.status_code == 200
    assert query.data["meta"]["report_code"] == "DASHBOARD_V3_QUERY"
    assert query.data["summary"]["workspace_code"] == "executive_cross_domain"
    assert len(query.data["results"]["widgets"]) == 1
    first = query.data["results"]["widgets"][0]
    assert first["widget_code"] == "exec_revenue_velocity"
    assert first["report_code"] == "DOMAIN_FACTURACION_OVERVIEW_V1"

    drilldown = client.post(
        f"{DASHBOARD_BASE}/drilldown/",
        {
            "workspace_code": "executive_cross_domain",
            "widget_code": "exec_revenue_velocity",
            "drill_path": ["series", "doc_type"],
            "filters": {"status": ["ISSUED"]},
        },
        format="json",
    )
    assert drilldown.status_code == 200
    assert drilldown.data["meta"]["report_code"] == "DASHBOARD_V3_DRILLDOWN"
    assert drilldown.data["summary"]["widget_code"] == "exec_revenue_velocity"

    events = set(
        AuditEvent.objects.filter(module="DASHBOARD", partition_key=f"COMPANY:{company.id}").values_list("event_type", flat=True)
    )
    assert "DASHBOARD_WORKSPACE_VIEWED" in events
    assert "DASHBOARD_WIDGET_QUERIED" in events
    assert "DASHBOARD_DRILLDOWN_EXECUTED" in events


@pytest.mark.django_db
def test_dashboard_v3_intercompany_requires_permission():
    _, company_a, branch_a = _mk_org_tree("dash-a")
    _, company_b, branch_b = _mk_org_tree("dash-b")

    user = _mk_user(label="dash-interco")
    for org in (company_a, branch_a, company_b, branch_b):
        UserMembership.objects.create(user=user, org_unit=org, is_active=True)

    perms = [
        "dashboard.workspace.read",
        "dashboard.widget.read",
        "reports.audit.read",
        "reports.observability.read",
        "reports.trace.read",
        "reports.control.read",
        "reports.financial.read",
        "reports.security.read",
    ]
    for code in perms:
        _grant_local_permission(user=user, company=company_a, branch=branch_a, permission_code=code)
        _grant_local_permission(user=user, company=company_b, branch=branch_b, permission_code=code)

    client = _login_client(user=user, password="Pass12345!", company=company_a, branch=branch_a)
    denied = client.post(
        f"{DASHBOARD_BASE}/workspaces/executive_cross_domain/query/",
        {
            "widget_code": "exec_revenue_velocity",
            "company_ids": [company_a.id, company_b.id],
        },
        format="json",
    )
    assert denied.status_code == 403
    assert denied.data["error"]["code"] == "REPORT_FORBIDDEN"


@pytest.mark.django_db
def test_domain_report_specs_cover_all_modules_and_kernels():
    domains = [
        "ACCOUNTS",
        "IAM",
        "ORG",
        "HR",
        "RBAC",
        "AUDIT",
        "INTEGRATION",
        "SYNC_ENGINE",
        "SYNC",
        "ACCOUNTING",
        "PAYMENTS",
        "CEC",
        "REPORTS",
        "AUTH_KERNEL",
        "FACTURACION",
        "INVENTARIOS",
        "COMPRAS",
        "ESTACION_SERVICIOS",
    ]
    for domain in domains:
        assert f"DOMAIN_{domain}_OVERVIEW_V1" in REPORT_SPECS
        assert f"DOMAIN_{domain}_ALERTS_V1" in REPORT_SPECS

    critical_domains = ["ACCOUNTING", "FACTURACION", "INVENTARIOS", "ESTACION_SERVICIOS", "COMPRAS", "PAYMENTS", "CEC"]
    for domain in critical_domains:
        assert f"DOMAIN_{domain}_OVERVIEW_V1" in REPORT_SPECS
        assert f"DOMAIN_{domain}_ALERTS_V1" in REPORT_SPECS


@pytest.mark.django_db
def test_dashboard_kernel_permissions_and_embed_token_contract():
    _, company, branch = _mk_org_tree("dash-kernel")
    user = _mk_user(label="dash-kernel")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    perms = [
        "report.dashboard.read",
        "report.dataset.read",
        "dashboard.drilldown.read",
        "reports.audit.read",
        "reports.observability.read",
        "reports.trace.read",
        "reports.control.read",
        "reports.financial.read",
        "reports.security.read",
    ]
    for code in perms:
        _grant_local_permission(user=user, company=company, branch=branch, permission_code=code)

    client = _login_client(user=user, password="Pass12345!", company=company, branch=branch)

    catalog = client.get(f"{DASHBOARD_BASE}/catalog/")
    assert catalog.status_code == 200
    codes = {row["workspace_code"] for row in catalog.data["results"]}
    assert "executive_v1" in codes
    assert "operations_fuel_accounting_v1" in codes

    query = client.post(
        f"{DASHBOARD_BASE}/workspaces/executive_v1/query/",
        {"widget_code": "exec_margin_watch"},
        format="json",
    )
    assert query.status_code == 200
    assert query.data["summary"]["workspace_code"] == "executive_v1"

    embed = client.post(
        f"{DASHBOARD_BASE}/embed-token/",
        {"workspace_code": "executive_v1", "ttl_seconds": 300},
        format="json",
    )
    assert embed.status_code == 200
    assert embed.data["meta"]["report_code"] == "DASHBOARD_EMBED_TOKEN"
    assert embed.data["results"]["workspace_code"] == "executive_v1"
    assert embed.data["results"]["token"]
    assert int(embed.data["results"]["ttl_seconds"]) == 300
