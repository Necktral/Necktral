import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent

User = get_user_model()


@pytest.mark.django_db
def test_login_audits_request_id():
    User.objects.create_user(username="auditor", password="Pass12345__Strong")

    client = APIClient()
    login = client.post(
        "/api/auth/login/",
        {"username": "auditor", "password": "Pass12345__Strong"},
        format="json",
    )
    assert login.status_code == 200

    request_id = login.headers.get("X-Request-Id")
    assert request_id

    ev = (
        AuditEvent.objects.filter(event_type="AUTH_LOGIN_SUCCESS")
        .order_by("-timestamp_server")
        .first()
    )
    assert ev is not None
    assert ev.metadata.get("request_id") == request_id
