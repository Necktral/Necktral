import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.iam.models import OrgUnit, UserMembership

User = get_user_model()


@pytest.mark.django_db
def test_must_change_password_blocks_operational_endpoints():
    u = User.objects.create_user(username="admin", password="TempPass12345__", email="a@test.com")
    u.is_staff = True
    u.must_change_password = True
    u.save(update_fields=["is_staff", "must_change_password"])

    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    UserMembership.objects.create(user=u, org_unit=company, is_active=True)

    c = APIClient()
    login = c.post("/api/auth/login/", {"username": "admin", "password": "TempPass12345__"}, format="json")
    assert login.status_code == 200
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    me = c.get("/api/auth/me/")
    assert me.status_code == 200

    res = c.get("/api/metrics/", HTTP_X_COMPANY_ID=str(company.id))
    assert res.status_code == 403
