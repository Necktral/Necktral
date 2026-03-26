from __future__ import annotations

import pytest
from django.urls import get_resolver
from rest_framework.test import APIClient

from config.routing_policy import LEGACY_ROUTE_POLICIES


@pytest.mark.django_db
def test_billing_has_single_canonical_prefix_and_explicit_legacy_prefix():
    routes = [str(getattr(pattern.pattern, "_route", "")) for pattern in get_resolver().url_patterns]
    assert routes.count("api/billing/") == 1
    assert routes.count("api/legacy/billing/") == 1


@pytest.mark.django_db
def test_legacy_billing_health_emits_standard_deprecation_headers():
    response = APIClient().get("/api/legacy/billing/health-legacy/")
    policy = LEGACY_ROUTE_POLICIES["/api/legacy/billing/"]

    assert response.status_code == 200
    assert response.headers.get("Deprecation") == "true"
    assert response.headers.get("Sunset") == policy.resolve_sunset()
    assert response.headers.get("Link") == '</api/billing/>; rel="successor-version"'


@pytest.mark.django_db
def test_backend_fuel_alias_emits_standard_deprecation_headers():
    response = APIClient().get("/api/backend/fuel/health/")
    policy = LEGACY_ROUTE_POLICIES["/api/backend/fuel/"]

    assert response.status_code == 200
    assert response.headers.get("Deprecation") == "true"
    assert response.headers.get("Sunset") == policy.resolve_sunset()
    assert response.headers.get("Link") == '</api/fuel/>; rel="successor-version"'


@pytest.mark.django_db
def test_public_fuel_prefix_is_not_marked_as_legacy():
    response = APIClient().get("/api/fuel/health/")

    assert response.status_code == 200
    assert response.headers.get("Deprecation") is None
    assert response.headers.get("Sunset") is None
    assert response.headers.get("Link") is None
