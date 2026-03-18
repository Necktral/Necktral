import pyotp
import pytest
from django.contrib.auth import get_user_model
from django.test import override_settings
from rest_framework.test import APIClient

User = get_user_model()

pytestmark = pytest.mark.django_db


def _mk_admin(username: str, password: str):
    user = User.objects.create_user(username=username, email=f"{username}@example.com", password=password)
    user.is_staff = True
    user.save(update_fields=["is_staff"])
    secret = pyotp.random_base32()
    user.totp_secret = secret
    user.totp_enabled = True
    user.save(update_fields=["totp_secret", "totp_enabled"])
    return user, pyotp.TOTP(secret)


def test_2fa_challenge_is_one_time_use():
    user, totp = _mk_admin("admin1", "pass12345ZZ")
    client = APIClient()

    login = client.post(
        "/api/backend/auth/login/",
        {"username": user.username, "password": "pass12345ZZ"},
        format="json",
    )
    assert login.status_code == 202
    challenge = login.data["challenge"]

    verify = client.post(
        "/api/backend/auth/2fa/verify/",
        {"challenge": challenge, "code": totp.now()},
        format="json",
    )
    assert verify.status_code == 200

    replay = client.post(
        "/api/backend/auth/2fa/verify/",
        {"challenge": challenge, "code": totp.now()},
        format="json",
    )
    assert replay.status_code == 400
    # Response is wrapped in error envelope
    error = replay.data.get("error", {})
    detail = error.get("details", {}).get("detail") or error.get("message")
    assert detail.startswith("Challenge")


def test_2fa_challenge_replay_with_wrong_user_agent_fails():
    user, totp = _mk_admin("admin2", "pass12345ZZ")
    client = APIClient()
    client.defaults["HTTP_USER_AGENT"] = "UA-A"

    login = client.post(
        "/api/backend/auth/login/",
        {"username": user.username, "password": "pass12345ZZ"},
        format="json",
    )
    assert login.status_code == 202
    challenge = login.data["challenge"]

    client.defaults["HTTP_USER_AGENT"] = "UA-B"
    verify = client.post(
        "/api/backend/auth/2fa/verify/",
        {"challenge": challenge, "code": totp.now()},
        format="json",
    )
    assert verify.status_code == 400
    # Response is wrapped in error envelope
    error = verify.data.get("error", {})
    detail = error.get("details", {}).get("detail") or error.get("message")
    assert detail.startswith("Challenge")


@pytest.mark.django_db
@override_settings(AUTH_TOKEN_TRANSPORT="cookie")
def test_2fa_replay_returns_400_with_auth_cookies_present():
    user, totp = _mk_admin("admin3", "pass12345ZZ")
    client = APIClient()
    client.defaults["HTTP_USER_AGENT"] = "UA-COOKIE-1"

    login = client.post(
        "/api/backend/auth/login/",
        {"username": user.username, "password": "pass12345ZZ"},
        format="json",
        HTTP_X_AUTH_TRANSPORT="cookie",
    )
    assert login.status_code == 202
    challenge = login.data["challenge"]

    verify = client.post(
        "/api/backend/auth/2fa/verify/",
        {"challenge": challenge, "code": totp.now()},
        format="json",
        HTTP_X_AUTH_TRANSPORT="cookie",
    )
    assert verify.status_code == 200
    assert "nt_access" in client.cookies
    assert "nt_refresh" in client.cookies

    replay = client.post(
        "/api/backend/auth/2fa/verify/",
        {"challenge": challenge, "code": totp.now()},
        format="json",
        HTTP_X_AUTH_TRANSPORT="cookie",
    )
    assert replay.status_code == 400
    error = replay.data.get("error", {})
    detail = error.get("details", {}).get("detail") or error.get("message")
    assert detail.startswith("Challenge")


@pytest.mark.django_db
@override_settings(AUTH_TOKEN_TRANSPORT="cookie")
def test_2fa_replay_returns_400_with_auth_cookies_and_different_ua():
    user, totp = _mk_admin("admin4", "pass12345ZZ")
    client = APIClient()
    client.defaults["HTTP_USER_AGENT"] = "UA-COOKIE-A"

    login = client.post(
        "/api/backend/auth/login/",
        {"username": user.username, "password": "pass12345ZZ"},
        format="json",
        HTTP_X_AUTH_TRANSPORT="cookie",
    )
    assert login.status_code == 202
    challenge = login.data["challenge"]

    verify = client.post(
        "/api/backend/auth/2fa/verify/",
        {"challenge": challenge, "code": totp.now()},
        format="json",
        HTTP_X_AUTH_TRANSPORT="cookie",
    )
    assert verify.status_code == 200

    client.defaults["HTTP_USER_AGENT"] = "UA-COOKIE-B"
    replay = client.post(
        "/api/backend/auth/2fa/verify/",
        {"challenge": challenge, "code": totp.now()},
        format="json",
        HTTP_X_AUTH_TRANSPORT="cookie",
    )
    assert replay.status_code == 400
    error = replay.data.get("error", {})
    detail = error.get("details", {}).get("detail") or error.get("message")
    assert detail.startswith("Challenge")
