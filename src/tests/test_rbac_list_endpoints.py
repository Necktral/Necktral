import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.iam.models import OrgUnit, UserMembership
from apps.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _mk_org():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    return company


def _client_with_perms(company: OrgUnit, perm_codes: list[str]) -> APIClient:
    username = f"u_{uuid.uuid4().hex[:10]}"
    User.objects.create_user(username=username, password="pass12345")
    user = User.objects.get(username=username)

    UserMembership.objects.create(user=user, org_unit=company, is_active=True)

    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perm_codes:
        p, _ = Permission.objects.get_or_create(code=code, defaults={"description": "", "is_active": True})
        if not p.is_active:
            p.is_active = True
            p.save(update_fields=["is_active"])
        RolePermission.objects.get_or_create(role=role, permission=p)

    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)

    client = APIClient()
    login = client.post("/api/auth/login/", {"username": username, "password": "pass12345"}, format="json")
    assert login.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    return client


@pytest.mark.django_db
def test_rbac_roles_list_returns_roles():
    company = _mk_org()
    client = _client_with_perms(company, ["rbac.roles.read"])

    Role.objects.create(name="sales_rep", is_active=True)
    Role.objects.create(name="inactive_role", is_active=False)

    r = client.get("/api/rbac/roles/", HTTP_X_COMPANY_ID=str(company.id))
    assert r.status_code == 200
    names = [x["name"] for x in r.data["results"]]
    assert "sales_rep" in names
    assert "inactive_role" not in names

    r2 = client.get("/api/rbac/roles/?include_inactive=1", HTTP_X_COMPANY_ID=str(company.id))
    assert r2.status_code == 200
    names2 = [x["name"] for x in r2.data["results"]]
    assert "inactive_role" in names2


@pytest.mark.django_db
def test_rbac_permissions_list_returns_permissions():
    company = _mk_org()
    client = _client_with_perms(company, ["rbac.permissions.read"])

    Permission.objects.create(code="org.branch.create", description="", is_active=True)
    Permission.objects.create(code="x.inactive", description="", is_active=False)

    r = client.get("/api/rbac/permissions/", HTTP_X_COMPANY_ID=str(company.id))
    assert r.status_code == 200
    codes = [x["code"] for x in r.data["results"]]
    assert "org.branch.create" in codes
    assert "x.inactive" not in codes


@pytest.mark.django_db
def test_rbac_roles_list_denied_without_permission_audited():
    company = _mk_org()
    client = _client_with_perms(company, [])  # sin permisos RBAC

    r = client.get("/api/rbac/roles/", HTTP_X_COMPANY_ID=str(company.id))
    assert r.status_code == 403

    ev = AuditEvent.objects.filter(
        event_type="AUTH_ACCESS_DENIED",
        path="/api/rbac/roles/",
        method="GET",
    ).latest("timestamp_server")

    assert ev.reason_code == "POLICY_PERMISSION_DENIED"
    assert ev.metadata.get("required_permission") == "rbac.roles.read"
