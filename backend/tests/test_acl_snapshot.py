import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.iam.models import AdminGrant, OrgUnit, UserMembership

User = get_user_model()


@pytest.mark.django_db
def test_acl_snapshot_lists_companies_and_branches_and_admin_caps():
    # Org: Holding -> Company -> Branches
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H1")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C1", parent=holding)
    b1 = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B1", parent=company)
    OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B2", parent=company)

    user = User.objects.create_user(username="u_acl", password="pass12345")

    # Membresía a una sucursal => acceso a la compañía y a esa sucursal
    UserMembership.objects.create(user=user, org_unit=b1, is_active=True)

    # Grant admin por empresa (RRHH)
    AdminGrant.objects.create(
        user=user,
        org_unit=company,
        capability=AdminGrant.Capability.MANAGE_USERS,
        applies_to_subtree=True,
        is_active=True,
    )

    client = APIClient()
    login = client.post("/api/auth/login/", {"username": "u_acl", "password": "pass12345"}, format="json")
    assert login.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    r = client.get("/api/auth/me/acl/")
    assert r.status_code == 200

    data = r.data
    assert "acl_version" in data
    assert len(data["companies"]) == 1
    assert data["companies"][0]["company_name"] == "C1"

    branches = data["companies"][0]["branches"]
    # solo B1 porque la membresía fue a B1
    assert any(x["branch_name"] == "B1" for x in branches)
    assert all(x["branch_name"] != "B2" for x in branches)

    caps = data["admin_caps_by_company"][str(company.id)]
    assert caps["MANAGE_USERS"] is True
