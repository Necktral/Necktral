import pytest
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent


@pytest.mark.django_db
def test_401_not_authenticated_creates_auth_access_denied_event():
    client = APIClient()

    r = client.get("/api/auth/me/")
    assert r.status_code == 401

    ev = AuditEvent.objects.filter(event_type="AUTH_ACCESS_DENIED").latest("timestamp_server")
    assert ev.module == "AUTH"
    assert ev.schema_version == 1
    assert ev.reason_code == "POLICY_SCOPE_DENIED"
    assert ev.path == "/api/auth/me/"
    assert ev.method == "GET"
    assert ev.event_hash is not None and len(ev.event_hash) == 64
    assert ev.signature is not None and len(ev.signature) == 64
