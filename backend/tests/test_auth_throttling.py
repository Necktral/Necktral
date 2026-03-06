from __future__ import annotations

import uuid

import pytest
from django.conf import settings
from django.test import override_settings
from rest_framework.settings import api_settings
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.test import APIClient

from apps.accounts.models import User


@pytest.mark.django_db
def test_login_throttling_enveloped():
    user = User.objects.create_user(username=f"u_{uuid.uuid4().hex[:8]}", password="pass12345")

    override = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": {
            **settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_RATES", {}),
            "auth_login": "1/min",
        },
    }

    with override_settings(REST_FRAMEWORK=override):
        api_settings.reload()
        SimpleRateThrottle.THROTTLE_RATES = api_settings.DEFAULT_THROTTLE_RATES
        try:
            client = APIClient()

            r1 = client.post("/api/auth/login/", {"username": user.username, "password": "pass12345"}, format="json")
            assert r1.status_code == 200

            r2 = client.post("/api/auth/login/", {"username": user.username, "password": "pass12345"}, format="json")
            assert r2.status_code == 429
            payload = r2.json()
            assert payload["error"]["code"] == "RATE_LIMITED"
            assert payload["error"]["http_status"] == 429
            assert payload["error"]["retryable"] is True
            assert r2["X-Request-Id"] == payload["error"]["request_id"]
        finally:
            api_settings.reload()
            SimpleRateThrottle.THROTTLE_RATES = api_settings.DEFAULT_THROTTLE_RATES


@pytest.mark.django_db
def test_refresh_throttling_enveloped():
    user = User.objects.create_user(username=f"u_{uuid.uuid4().hex[:8]}", password="pass12345")

    override = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": {
            **settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_RATES", {}),
            "auth_refresh": "1/min",
        },
    }

    with override_settings(REST_FRAMEWORK=override):
        api_settings.reload()
        SimpleRateThrottle.THROTTLE_RATES = api_settings.DEFAULT_THROTTLE_RATES
        try:
            client = APIClient()
            client.credentials(HTTP_X_DEVICE_ID="device-rt-1")
            login = client.post("/api/auth/login/", {"username": user.username, "password": "pass12345"}, format="json")
            assert login.status_code == 200

            refresh = login.data.get("refresh")
            assert refresh

            r1 = client.post("/api/auth/refresh/", {"refresh": refresh}, format="json")
            assert r1.status_code == 200

            refresh2 = r1.data.get("refresh") or refresh
            r2 = client.post("/api/auth/refresh/", {"refresh": refresh2}, format="json")
            assert r2.status_code == 429
            payload = r2.json()
            assert payload["error"]["code"] == "RATE_LIMITED"
            assert payload["error"]["http_status"] == 429
            assert payload["error"]["retryable"] is True
        finally:
            api_settings.reload()
            SimpleRateThrottle.THROTTLE_RATES = api_settings.DEFAULT_THROTTLE_RATES


@pytest.mark.django_db
def test_logout_throttling_enveloped():
    user = User.objects.create_user(username=f"u_{uuid.uuid4().hex[:8]}", password="pass12345")

    override = {
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_RATES": {
            **settings.REST_FRAMEWORK.get("DEFAULT_THROTTLE_RATES", {}),
            "auth_logout": "1/min",
        },
    }

    with override_settings(REST_FRAMEWORK=override):
        api_settings.reload()
        SimpleRateThrottle.THROTTLE_RATES = api_settings.DEFAULT_THROTTLE_RATES
        try:
            client = APIClient()
            login = client.post("/api/auth/login/", {"username": user.username, "password": "pass12345"}, format="json")
            assert login.status_code == 200

            access = login.data.get("access")
            refresh = login.data.get("refresh")
            assert access
            assert refresh

            client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

            r1 = client.post("/api/auth/logout/", {"refresh": refresh}, format="json")
            assert r1.status_code == 204

            r2 = client.post("/api/auth/logout/", {"refresh": refresh}, format="json")
            assert r2.status_code == 429
            payload = r2.json()
            assert payload["error"]["code"] == "RATE_LIMITED"
            assert payload["error"]["http_status"] == 429
            assert payload["error"]["retryable"] is True
        finally:
            api_settings.reload()
            SimpleRateThrottle.THROTTLE_RATES = api_settings.DEFAULT_THROTTLE_RATES
