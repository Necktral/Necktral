import pytest
from django.contrib.auth import get_user_model
from django.test.utils import override_settings
from rest_framework.test import APIClient

User = get_user_model()


def _pwd() -> str:
    return "Aa!9_Csrf_Refresh_Zx7"


@pytest.mark.django_db
@override_settings(
    AUTH_TOKEN_TRANSPORT="cookie",
    AUTH_ALLOW_TRANSPORT_OVERRIDE=False,
)
def test_refresh_cookie_mode_requires_csrf_header():
    user = User.objects.create_user(username="csrf_user", password=_pwd())
    assert user is not None

    client = APIClient()
    login = client.post("/api/backend/auth/login/", {"username": "csrf_user", "password": _pwd()}, format="json")
    assert login.status_code == 200
    assert "nt_refresh" in client.cookies

    refresh = client.post("/api/backend/auth/refresh/", {}, format="json")
    assert refresh.status_code == 403
    body = refresh.json()
    assert body.get("error", {}).get("code") == "AUTH_CSRF_FAILED"


@pytest.mark.django_db
@override_settings(
    AUTH_TOKEN_TRANSPORT="cookie",
    AUTH_ALLOW_TRANSPORT_OVERRIDE=False,
)
def test_refresh_cookie_mode_with_csrf_header_succeeds():
    user = User.objects.create_user(username="csrf_user_ok", password=_pwd())
    assert user is not None

    client = APIClient()
    login = client.post("/api/backend/auth/login/", {"username": "csrf_user_ok", "password": _pwd()}, format="json")
    assert login.status_code == 200
    csrf = client.cookies.get("nt_csrf")
    assert csrf is not None

    refresh = client.post("/api/backend/auth/refresh/", {}, format="json", HTTP_X_CSRF_TOKEN=str(csrf.value))
    assert refresh.status_code == 200
