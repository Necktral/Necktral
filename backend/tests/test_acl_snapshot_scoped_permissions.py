import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.iam.models import OrgUnit, UserMembership
from apps.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


@pytest.mark.django_db
def test_acl_snapshot_permissions_are_per_company():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    c1 = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C1", parent=holding)
    c2 = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C2", parent=holding)

    user = User.objects.create_user(username="u_acl2", password="pass12345")
    UserMembership.objects.create(user=user, org_unit=c1, is_active=True)
    UserMembership.objects.create(user=user, org_unit=c2, is_active=True)

    role = Role.objects.create(name="warehouse", is_active=True)
    perm = Permission.objects.create(code="inventory.read", is_active=True)
    RolePermission.objects.create(role=role, permission=perm)

    # permiso solo en C1
    RoleAssignment.objects.create(user=user, role=role, org_unit=c1, is_active=True)

    client = APIClient()
    login = client.post("/api/auth/login/", {"username": "u_acl2", "password": "pass12345"}, format="json")
    assert login.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    r = client.get("/api/auth/me/acl/")
    assert r.status_code == 200

    companies = {c["company_name"]: c["permissions"] for c in r.data["companies"]}
    assert "C1" in companies and "C2" in companies
    assert "inventory.read" in companies["C1"]
    assert "inventory.read" not in companies["C2"]
