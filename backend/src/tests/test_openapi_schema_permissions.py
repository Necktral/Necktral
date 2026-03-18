from __future__ import annotations

from django.test import override_settings
import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_openapi_schema_requires_auth_when_anon_disabled():
    client = APIClient()
    with override_settings(OPENAPI_ALLOW_ANON=False):
        resp = client.get("/api/schema/")
    assert resp.status_code in (401, 403)


@pytest.mark.django_db
def test_openapi_schema_allows_anon_when_enabled():
    client = APIClient()
    with override_settings(OPENAPI_ALLOW_ANON=True):
        resp = client.get("/api/schema/")
    assert resp.status_code == 200
