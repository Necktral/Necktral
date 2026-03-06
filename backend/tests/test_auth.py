import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent

User = get_user_model()


@pytest.mark.django_db
def test_login_success_creates_contractual_audit_event():
    user = User.objects.create_user(username="u1", password="pass12345")

    client = APIClient()
    r = client.post("/api/auth/login/", {"username": "u1", "password": "pass12345"}, format="json")
    assert r.status_code == 200
    assert "access" in r.data and "refresh" in r.data

    ev = AuditEvent.objects.filter(event_type="AUTH_LOGIN_SUCCESS").latest("timestamp_server")
    assert ev.module == "AUTH"
    assert ev.schema_version == 1
    assert ev.actor_user == user
    assert ev.subject_type == "USER"
    assert ev.subject_id == str(user.id)
    assert ev.event_hash is not None and len(ev.event_hash) == 64
    assert ev.signature is not None and len(ev.signature) == 64


@pytest.mark.django_db
def test_login_failed_creates_contractual_audit_event():
    User.objects.create_user(username="u2", password="pass12345")

    client = APIClient()
    r = client.post("/api/auth/login/", {"username": "u2", "password": "bad"}, format="json")
    assert r.status_code == 401

    ev = AuditEvent.objects.filter(event_type="AUTH_LOGIN_FAILURE").latest("timestamp_server")
    assert ev.reason_code == "INVALID_CREDENTIALS"
    assert ev.subject_type == "USER"
    assert ev.subject_id == "u2"
    assert ev.event_hash is not None and len(ev.event_hash) == 64
    assert ev.signature is not None and len(ev.signature) == 64


@pytest.mark.django_db
def test_logout_requires_auth_and_creates_audit_event():
    user = User.objects.create_user(username="u3", password="pass12345")

    client = APIClient()
    r = client.post("/api/auth/login/", {"username": "u3", "password": "pass12345"}, format="json")
    assert r.status_code == 200
    refresh = r.data["refresh"]
    access = r.data["access"]

    # 1) sin Authorization -> 401 (bloqueado por IsAuthenticated)
    r2 = client.post("/api/auth/logout/", {"refresh": refresh}, format="json")
    assert r2.status_code == 401

    # 2) con Authorization -> 204 + audit AUTH_LOGOUT
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    r3 = client.post("/api/auth/logout/", {"refresh": refresh}, format="json")
    assert r3.status_code == 204

    ev = AuditEvent.objects.filter(event_type="AUTH_LOGOUT").latest("timestamp_server")
    assert ev.actor_user == user
    assert ev.subject_type == "USER"
    assert ev.subject_id == str(user.id)
    assert ev.event_hash is not None and len(ev.event_hash) == 64
    assert ev.signature is not None and len(ev.signature) == 64


@pytest.mark.django_db
def test_logout_is_idempotent_when_refresh_missing():
    user = User.objects.create_user(username="u4", email="u4@example.com", password="pass12345")

    client = APIClient()
    r = client.post("/api/auth/login/", {"username": "u4", "password": "pass12345"}, format="json")
    assert r.status_code == 200
    access = r.data["access"]

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    r2 = client.post("/api/auth/logout/", {}, format="json")
    assert r2.status_code == 204

    ev = AuditEvent.objects.filter(event_type="AUTH_LOGOUT_FAILURE").latest("timestamp_server")
    assert ev.actor_user == user
    assert ev.reason_code == "TOKEN_INVALID"
    assert ev.metadata.get("stage") == "logout"
    assert ev.metadata.get("detail") == "missing_refresh"


@pytest.mark.django_db
def test_logout_is_idempotent_when_refresh_invalid():
    user = User.objects.create_user(username="u5", email="u5@example.com", password="pass12345")

    client = APIClient()
    r = client.post("/api/auth/login/", {"username": "u5", "password": "pass12345"}, format="json")
    assert r.status_code == 200
    access = r.data["access"]

    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    r2 = client.post("/api/auth/logout/", {"refresh": "not-a-jwt"}, format="json")
    assert r2.status_code == 204

    ev = AuditEvent.objects.filter(event_type="AUTH_LOGOUT_FAILURE").latest("timestamp_server")
    assert ev.actor_user == user
    assert ev.reason_code == "TOKEN_INVALID"
    assert ev.metadata.get("stage") == "logout"
    assert ev.metadata.get("detail") == "invalid_refresh"


@pytest.mark.django_db
def test_logout_is_idempotent_when_refresh_belongs_to_another_user():
    u_a = User.objects.create_user(username="uA", email="uA@example.com", password="pass12345")
    u_b = User.objects.create_user(username="uB", email="uB@example.com", password="pass12345")

    client_a = APIClient()
    r_a = client_a.post("/api/auth/login/", {"username": "uA", "password": "pass12345"}, format="json")
    assert r_a.status_code == 200
    refresh_a = r_a.data["refresh"]

    client_b = APIClient()
    r_b = client_b.post("/api/auth/login/", {"username": "uB", "password": "pass12345"}, format="json")
    assert r_b.status_code == 200
    access_b = r_b.data["access"]

    client_b.credentials(HTTP_AUTHORIZATION=f"Bearer {access_b}")
    r2 = client_b.post("/api/auth/logout/", {"refresh": refresh_a}, format="json")
    assert r2.status_code == 403

    ev = AuditEvent.objects.filter(event_type="AUTH_LOGOUT_FAILURE").latest("timestamp_server")
    assert ev.actor_user == u_b
    assert ev.reason_code == "TOKEN_MISMATCH"
    assert ev.metadata.get("stage") == "logout"
    assert ev.metadata.get("detail") == "refresh_owner_mismatch"
