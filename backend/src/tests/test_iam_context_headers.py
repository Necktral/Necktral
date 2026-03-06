import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.iam.models import OrgUnit, UserMembership

User = get_user_model()


@pytest.mark.django_db
def test_iam_context_requires_company_header():
    user = User.objects.create_user(username="ctx_user", password="Pass12345__Strong")

    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="HOLDING", code="")
    company = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.COMPANY,
        name="ACME",
        code="",
        parent=holding,
    )
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)

    client = APIClient()
    login = client.post(
        "/api/auth/login/",
        {"username": "ctx_user", "password": "Pass12345__Strong"},
        format="json",
    )
    assert login.status_code == 200

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    res = client.get("/api/iam/context/")
    assert res.status_code == 400
    assert res.data.get("error", {}).get("code") == "BAD_REQUEST"


@pytest.mark.django_db
def test_iam_context_with_company_header():
    user = User.objects.create_user(username="ctx_user_ok", password="Pass12345__Strong")

    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="HOLDING", code="")
    company = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.COMPANY,
        name="ACME",
        code="",
        parent=holding,
    )
    branch = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.BRANCH,
        name="ACME-1",
        code="",
        parent=company,
    )
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)

    client = APIClient()
    login = client.post(
        "/api/auth/login/",
        {"username": "ctx_user_ok", "password": "Pass12345__Strong"},
        format="json",
    )
    assert login.status_code == 200

    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {login.data['access']}",
        HTTP_X_COMPANY_ID=str(company.id),
        HTTP_X_BRANCH_ID=str(branch.id),
    )
    res = client.get("/api/iam/context/")
    assert res.status_code == 200
    assert res.data.get("company_id") == company.id
    assert res.data.get("branch_id") == branch.id
    assert res.headers.get("X-Request-Id")
