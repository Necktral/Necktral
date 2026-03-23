from __future__ import annotations

from django.test import override_settings
from rest_framework.test import APIClient


@override_settings(
    SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
    SECURE_HSTS_SECONDS=3600,
    SECURE_HSTS_INCLUDE_SUBDOMAINS=True,
    SECURE_SSL_REDIRECT=False,
)
def test_hsts_is_emitted_when_forwarded_proto_is_https():
    client = APIClient()
    response = client.get("/api/backend/billing/health/", HTTP_X_FORWARDED_PROTO="https")
    assert response.status_code == 200
    sts = response.headers.get("Strict-Transport-Security") or ""
    assert "max-age=3600" in sts
    assert "includeSubDomains" in sts


@override_settings(
    SECURE_PROXY_SSL_HEADER=("HTTP_X_FORWARDED_PROTO", "https"),
    SECURE_HSTS_SECONDS=3600,
    SECURE_HSTS_INCLUDE_SUBDOMAINS=True,
    SECURE_SSL_REDIRECT=False,
)
def test_hsts_is_not_emitted_without_secure_forwarded_proto():
    client = APIClient()
    response = client.get("/api/backend/billing/health/")
    assert response.status_code == 200
    assert (response.headers.get("Strict-Transport-Security") or "") == ""


def test_csp_header_is_emitted_by_django_without_unsafe_inline():
    client = APIClient()
    response = client.get("/api/backend/billing/health/")
    assert response.status_code == 200
    csp = response.headers.get("Content-Security-Policy") or ""
    assert csp
    assert "default-src 'self'" in csp
    assert "'unsafe-inline'" not in csp
