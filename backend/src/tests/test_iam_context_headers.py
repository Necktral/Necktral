import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.iam.models import OrgUnit, UserMembership

User = get_user_model()


def _demo_pwd(label: str) -> str:
    return f"Aa!9_{label}_Ctx7"


@pytest.mark.django_db
def test_iam_context_requires_company_header():
    pwd = _demo_pwd("req")
    user = User.objects.create_user(username="ctx_user", password=pwd)

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
        "/api/backend/auth/login/",
        {"username": "ctx_user", "password": pwd},
        format="json",
    )
    assert login.status_code == 200

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    res = client.get("/api/backend/iam/context/")
    assert res.status_code == 400
    assert res.data.get("error", {}).get("code") == "BAD_REQUEST"


@pytest.mark.django_db
def test_iam_context_with_company_header():
    pwd = _demo_pwd("ok")
    user = User.objects.create_user(username="ctx_user_ok", password=pwd)

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
        "/api/backend/auth/login/",
        {"username": "ctx_user_ok", "password": pwd},
        format="json",
    )
    assert login.status_code == 200

    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {login.data['access']}",
        HTTP_X_COMPANY_ID=str(company.id),
        HTTP_X_BRANCH_ID=str(branch.id),
    )
    res = client.get("/api/backend/iam/context/")
    assert res.status_code == 200
    assert res.data.get("company_id") == company.id
    assert res.data.get("branch_id") == branch.id
    assert res.headers.get("X-Request-Id")
