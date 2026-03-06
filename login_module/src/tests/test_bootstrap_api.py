import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APIClient

from apps.iam.models import OrgUnit

User = get_user_model()


@pytest.mark.django_db
def test_bootstrap_status_fresh_when_no_users():
    client = APIClient()
    r = client.get("/api/auth/bootstrap/status/")
    assert r.status_code == 200
    assert r.data["is_fresh"] is True


@pytest.mark.django_db
def test_bootstrap_init_creates_first_admin():
    client = APIClient()
    r = client.post(
        "/api/auth/bootstrap/init/",
        {"username": "root", "email": "root@test.com", "password": "Pass12345__Strong"},
        format="json",
    )
    assert r.status_code == 201
    u = User.objects.get(username="root")
    assert u.is_superuser is True
    assert u.is_staff is True
    assert u.must_change_password is False

    r2 = client.get("/api/auth/bootstrap/status/")
    assert r2.status_code == 200
    assert r2.data["is_fresh"] is False


@pytest.mark.django_db
@override_settings(INITIAL_SETUP_REQUIRE_TOKEN=True, INITIAL_SETUP_TOKEN="setup-secret")
def test_bootstrap_init_requires_setup_token_when_enabled():
    client = APIClient()
    r = client.post(
        "/api/auth/bootstrap/init/",
        {"username": "root", "email": "root@test.com", "password": "Pass12345__Strong"},
        format="json",
    )
    assert r.status_code == 401

    r2 = client.post(
        "/api/auth/bootstrap/init/",
        {"username": "root", "email": "root@test.com", "password": "Pass12345__Strong"},
        format="json",
        HTTP_X_SETUP_TOKEN="setup-secret",
    )
    assert r2.status_code == 201


@pytest.mark.django_db
def test_bootstrap_org_requires_auth_but_no_company_context_header():
    # 1) bootstrap init
    c = APIClient()
    c.post(
        "/api/auth/bootstrap/init/",
        {"username": "root", "email": "root2@test.com", "password": "Pass12345__Strong"},
        format="json",
    )

    # 2) login
    login = c.post("/api/auth/login/", {"username": "root", "password": "Pass12345__Strong"}, format="json")
    assert login.status_code == 200
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    # 3) bootstrap org (sin X-Company-Id)
    r = c.post(
        "/api/auth/bootstrap/org/",
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
    me = c.get("/api/auth/me/")
    assert me.status_code == 200
    assert me.data["is_setup_complete"] is True


@pytest.mark.django_db
def test_password_change_clears_must_change_password():
    u = User.objects.create_user(username="emp", password="TempPass12345__", email="emp@test.com")
    u.must_change_password = True
    u.save(update_fields=["must_change_password"])

    c = APIClient()
    login = c.post("/api/auth/login/", {"username": "emp", "password": "TempPass12345__"}, format="json")
    assert login.status_code == 200
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    r = c.post(
        "/api/auth/password/",
        {
            "old_password": "TempPass12345__",
            "new_password": "NewPass12345__Strong",
            "confirm_password": "NewPass12345__Strong",
        },
        format="json",
    )
    assert r.status_code == 200
    u.refresh_from_db()
    assert u.must_change_password is False

    # login with new password works
    c2 = APIClient()
    login2 = c2.post("/api/auth/login/", {"username": "emp", "password": "NewPass12345__Strong"}, format="json")
    assert login2.status_code == 200
