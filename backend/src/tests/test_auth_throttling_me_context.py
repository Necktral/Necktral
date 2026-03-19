import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test.utils import override_settings
from rest_framework.settings import api_settings
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.test import APIClient

from apps.modulos.iam.models import OrgUnit, UserMembership

User = get_user_model()


def _demo_pwd() -> str:
    return "Aa!9_Throttle_Zx7"


@pytest.mark.django_db
@override_settings(
    REST_FRAMEWORK={
        **settings.REST_FRAMEWORK,
        "DEFAULT_THROTTLE_CLASSES": (
            "rest_framework.throttling.AnonRateThrottle",
            "rest_framework.throttling.UserRateThrottle",
            "rest_framework.throttling.ScopedRateThrottle",
            "config.throttling.DeviceScopedRateThrottle",
        ),
        "DEFAULT_THROTTLE_RATES": {
            "anon": "1000/min",
            "user": "1000/min",
            "auth_login": "1000/min",
            "auth_sensitive": "1000/min",
            "me_read": "2/min",
            "me_acl_read": "2/min",
            "context_read": "2/min",
            "sync_batch": "1000/min",
            "admin_writes": "1000/min",
            "heavy_reads": "1000/min",
        },
    }
)
def test_me_and_context_throttling_scopes():
    api_settings.reload()
    SimpleRateThrottle.THROTTLE_RATES = api_settings.DEFAULT_THROTTLE_RATES
    pwd = _demo_pwd()
    user = User.objects.create_superuser(username="th_user", password=pwd)

    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="HOLDING", code="")
    company = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.COMPANY,
        name="ACME",
        code="",
        parent=holding,
    )
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)

    client = APIClient()
    login = client.post(
        "/api/backend/auth/login/",
        {"username": "th_user", "password": pwd},
        format="json",
    )
    assert login.status_code == 200

    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {login.data['access']}",
        HTTP_X_COMPANY_ID=str(company.id),
        HTTP_X_DEVICE_ID="device-1",
    )

    # /me (scope me_read)
    assert client.get("/api/backend/auth/me/").status_code == 200
    assert client.get("/api/backend/auth/me/").status_code == 200
    third = client.get("/api/backend/auth/me/")
    assert third.status_code == 429
    assert third.data.get("error", {}).get("code") == "RATE_LIMITED"

    # /me/acl (scope me_acl_read)
    assert client.get("/api/backend/auth/me/acl/").status_code == 200
    assert client.get("/api/backend/auth/me/acl/").status_code == 200
    third_acl = client.get("/api/backend/auth/me/acl/")
    assert third_acl.status_code == 429
    assert third_acl.data.get("error", {}).get("code") == "RATE_LIMITED"

    # /iam/context (scope context_read)
    assert client.get("/api/backend/iam/context/").status_code == 200
    assert client.get("/api/backend/iam/context/").status_code == 200
    third_ctx = client.get("/api/backend/iam/context/")
    assert third_ctx.status_code == 429
    assert third_ctx.data.get("error", {}).get("code") == "RATE_LIMITED"
