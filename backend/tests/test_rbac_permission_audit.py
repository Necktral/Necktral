import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.modulos.audit.models import AuditEvent
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


@pytest.mark.django_db
def test_403_creates_auth_access_denied_with_required_permission_and_scope():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C1", parent=holding)

    user = User.objects.create_user(username="u_no_perm", password="pass12345")
    # membresía para pasar el contexto
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)

    client = APIClient()
    login = client.post("/api/backend/auth/login/", {"username": "u_no_perm", "password": "pass12345"}, format="json")
    assert login.status_code == 200
    access = login.data.get("access") if isinstance(login.data, dict) else None
    if isinstance(access, str) and access.count(".") == 2:
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {access}"

    r = client.get("/api/rbac/demo/inventory-read/", HTTP_X_COMPANY_ID=str(company.id))
    assert r.status_code == 403

    ev = AuditEvent.objects.filter(
        event_type="AUTH_ACCESS_DENIED",
        path="/api/rbac/demo/inventory-read/",
        method="GET",
    ).latest("timestamp_server")

    assert ev.reason_code == "RBAC_FORBIDDEN"
    assert ev.metadata.get("required_permission") == "inventory.read"
    assert ev.metadata.get("required_scope", {}).get("company_id") == company.id
    assert ev.metadata.get("effective_scope", {}).get("company_id") == company.id


@pytest.mark.django_db
def test_200_when_user_has_scoped_permission():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C1", parent=holding)

    user = User.objects.create_user(username="u_yes_perm", password="pass12345")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)

    role = Role.objects.create(name="warehouse", is_active=True)
    perm = Permission.objects.create(code="inventory.read", is_active=True)
    RolePermission.objects.create(role=role, permission=perm)

    # scoped role assignment en company
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)

    client = APIClient()
    login = client.post("/api/backend/auth/login/", {"username": "u_yes_perm", "password": "pass12345"}, format="json")
    assert login.status_code == 200
    access = login.data.get("access") if isinstance(login.data, dict) else None
    if isinstance(access, str) and access.count(".") == 2:
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {access}"

    r = client.get("/api/rbac/demo/inventory-read/", HTTP_X_COMPANY_ID=str(company.id))
    assert r.status_code == 200
    assert r.data["ok"] is True
