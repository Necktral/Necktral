import pyotp
import pytest
from django.contrib.auth import get_user_model
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
        "/api/auth/login/",
        {"username": user.username, "password": "pass12345ZZ"},
        format="json",
    )
    assert login.status_code == 202
    challenge = login.data["challenge"]

    verify = client.post(
        "/api/auth/2fa/verify/",
        {"challenge": challenge, "code": totp.now()},
        format="json",
    )
    assert verify.status_code == 200

    replay = client.post(
        "/api/auth/2fa/verify/",
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
        "/api/auth/login/",
        {"username": user.username, "password": "pass12345ZZ"},
        format="json",
    )
    assert login.status_code == 202
    challenge = login.data["challenge"]

    client.defaults["HTTP_USER_AGENT"] = "UA-B"
    verify = client.post(
        "/api/auth/2fa/verify/",
        {"challenge": challenge, "code": totp.now()},
        format="json",
    )
    assert verify.status_code == 400
    # Response is wrapped in error envelope
    error = verify.data.get("error", {})
    detail = error.get("details", {}).get("detail") or error.get("message")
    assert detail.startswith("Challenge")
