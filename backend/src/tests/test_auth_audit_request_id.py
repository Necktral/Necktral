import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.modulos.audit.models import AuditEvent

User = get_user_model()


def _demo_pwd() -> str:
    return "Aa!9_Audit_Zx7"


@pytest.mark.django_db
def test_login_audits_request_id():
    pwd = _demo_pwd()
    User.objects.create_user(username="auditor", password=pwd)

    client = APIClient()
    login = client.post(
        "/api/backend/auth/login/",
        {"username": "auditor", "password": pwd},
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
