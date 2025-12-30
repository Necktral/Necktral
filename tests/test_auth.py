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
