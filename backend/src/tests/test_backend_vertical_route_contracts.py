from __future__ import annotations

from rest_framework.test import APIClient


def test_backend_vertical_canonical_health_endpoints_are_available():
    client = APIClient()

    checks = [
        ("/api/backend/billing/health/", "billing"),
        ("/api/backend/inventory/health/", "inventory"),
        ("/api/backend/procurement/health/", "procurement"),
        ("/api/backend/fuel/health/", "fuel"),
        ("/api/backend/retail/health/", "retail"),
    ]

    for path, module in checks:
        response = client.get(path)
        assert response.status_code == 200
        assert response.data.get("module") == module


def test_vertical_legacy_aliases_emit_deprecation_headers():
    client = APIClient()

    checks = [
        ("/api/billing/health/", "/api/backend/billing/"),
        ("/api/inventory/health/", "/api/backend/inventory/"),
        ("/api/procurement/health/", "/api/backend/procurement/"),
        ("/api/fuel/health/", "/api/backend/fuel/"),
        ("/api/retail/health/", "/api/backend/retail/"),
    ]

    for path, successor in checks:
        response = client.get(path)
        assert response.status_code == 200
        assert response.headers.get("Deprecation") == "true"
        assert "Mon, 18 May 2026" in (response.headers.get("Sunset") or "")
        assert successor in (response.headers.get("Link") or "")
