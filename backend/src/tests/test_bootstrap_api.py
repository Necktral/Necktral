import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.iam.models import OrgUnit

User = get_user_model()


def _demo_pwd(label: str) -> str:
    return f"Aa!9_{label}_Zx7"


@pytest.mark.django_db
def test_bootstrap_status_fresh_when_no_users():
    client = APIClient()
    r = client.get("/api/backend/auth/bootstrap/status/")
    assert r.status_code == 200
    assert r.data["is_fresh"] is True


@pytest.mark.django_db
def test_bootstrap_init_creates_first_admin():
    client = APIClient()
    root_pwd = _demo_pwd("root")
    r = client.post(
        "/api/backend/auth/bootstrap/init/",
        {"username": "root", "email": "root@test.com", "password": root_pwd},
        format="json",
    )
    assert r.status_code == 201
    u = User.objects.get(username="root")
    assert u.is_superuser is True
    assert u.is_staff is True
    assert u.must_change_password is False

    r2 = client.get("/api/backend/auth/bootstrap/status/")
    assert r2.status_code == 200
    assert r2.data["is_fresh"] is False


@pytest.mark.django_db
def test_bootstrap_org_requires_auth_but_no_company_context_header():
    # 1) bootstrap init
    c = APIClient()
    root_pwd = _demo_pwd("root2")
    c.post(
        "/api/backend/auth/bootstrap/init/",
        {"username": "root", "email": "root2@test.com", "password": root_pwd},
        format="json",
    )

    # 2) login
    login = c.post("/api/backend/auth/login/", {"username": "root", "password": root_pwd}, format="json")
    assert login.status_code == 200
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    # 3) bootstrap org (sin X-Company-Id)
    r = c.post(
        "/api/backend/auth/bootstrap/org/",
        {
            "holding_name": "HOLDING",
            "company_name": "ACME",
            "company_tax_id": "J-123",
            "branch_name": "ACME-1",
            "branch_address": "Main street",
        },
        format="json",
    )
    assert r.status_code == 200
    assert OrgUnit.objects.filter(unit_type=OrgUnit.UnitType.HOLDING).exists()
    assert OrgUnit.objects.filter(unit_type=OrgUnit.UnitType.COMPANY).exists()
    assert OrgUnit.objects.filter(unit_type=OrgUnit.UnitType.BRANCH).exists()

    # 4) /me refleja setup complete
    me = c.get("/api/backend/auth/me/")
    assert me.status_code == 200
    assert me.data["is_setup_complete"] is True


@pytest.mark.django_db
def test_password_change_clears_must_change_password():
    temp_pwd = _demo_pwd("temp")
    new_pwd = _demo_pwd("new")
    u = User.objects.create_user(username="emp", password=temp_pwd, email="emp@test.com")
    u.must_change_password = True
    u.save(update_fields=["must_change_password"])

    c = APIClient()
    login = c.post("/api/backend/auth/login/", {"username": "emp", "password": temp_pwd}, format="json")
    assert login.status_code == 200
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    r = c.post(
        "/api/backend/auth/password/",
        {
            "old_password": temp_pwd,
            "new_password": new_pwd,
            "confirm_password": new_pwd,
        },
        format="json",
    )
    assert r.status_code == 200
    u.refresh_from_db()
    assert u.must_change_password is False

    # login with new password works
    c2 = APIClient()
    login2 = c2.post("/api/backend/auth/login/", {"username": "emp", "password": new_pwd}, format="json")
    assert login2.status_code == 200
