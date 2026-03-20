import pytest
from rest_framework.test import APIClient


def _demo_pwd(label: str) -> str:
    return f"Aa!9_{label}_Zx7"


@pytest.mark.django_db
def test_bootstrap_canonical_endpoints_e2e():
    client = APIClient()

    status_resp = client.get("/api/backend/iam/bootstrap/status/")
    assert status_resp.status_code == 200
    assert status_resp.data["is_fresh"] is True

    root_pwd = _demo_pwd("canonical")
    init_resp = client.post(
        "/api/backend/iam/bootstrap/init-admin/",
        {"username": "root", "email": "root@test.com", "password": root_pwd},
        format="json",
    )
    assert init_resp.status_code == 201

    login_resp = client.post("/api/backend/auth/login/", {"username": "root", "password": root_pwd}, format="json")
    assert login_resp.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login_resp.data['access']}")

    org_resp = client.post(
        "/api/backend/org/bootstrap/organization/",
        {
            "holding_name": "HOLDING",
            "company_name": "ACME",
            "company_tax_id": "J-123",
            "branch_name": "ACME-1",
            "branch_address": "Main street",
        },
        format="json",
    )
    assert org_resp.status_code == 200
    assert "company_id" in org_resp.data

    me = client.get("/api/backend/auth/me/")
    assert me.status_code == 200
    assert me.data["is_setup_complete"] is True


@pytest.mark.django_db
def test_bootstrap_legacy_wrapper_has_deprecation_headers():
    client = APIClient()
    resp = client.get("/api/auth/bootstrap/status/")
    assert resp.status_code == 200
    assert resp.headers.get("Deprecation") == "true"
    assert "Mon, 18 May 2026" in (resp.headers.get("Sunset") or "")
    assert "/api/backend/iam/bootstrap/status/" in (resp.headers.get("Link") or "")


@pytest.mark.django_db
def test_legacy_iam_alias_has_deprecation_headers():
    client = APIClient()
    resp = client.get("/api/iam/bootstrap/status/")
    assert resp.status_code == 200
    assert resp.headers.get("Deprecation") == "true"
    assert "Mon, 18 May 2026" in (resp.headers.get("Sunset") or "")
