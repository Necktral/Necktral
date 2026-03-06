import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.iam.models import OrgUnit, UserMembership

User = get_user_model()


@pytest.mark.django_db
def test_context_requires_company_header_and_denies_without_membership():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    c1 = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C1", parent=holding)
    c2 = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C2", parent=holding)
    b1 = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B1", parent=c1)

    user = User.objects.create_user(username="u_ctx", password="pass12345")
    UserMembership.objects.create(user=user, org_unit=b1, is_active=True)  # acceso solo a C1/B1

    client = APIClient()
    login = client.post("/api/auth/login/", {"username": "u_ctx", "password": "pass12345"}, format="json")
    assert login.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    # Falta header -> 400
    r = client.get("/api/iam/context/")
    assert r.status_code == 400

    # Company no accesible -> 403 + audit con required_scope
    r2 = client.get("/api/iam/context/", HTTP_X_COMPANY_ID=str(c2.id))
    assert r2.status_code == 403

    ev = AuditEvent.objects.filter(event_type="AUTH_ACCESS_DENIED", path="/api/iam/context/").latest("timestamp_server")
    assert ev.reason_code == "SCOPE_FORBIDDEN"
    assert ev.metadata.get("required_scope", {}).get("company_id") == c2.id


@pytest.mark.django_db
def test_context_allows_branch_membership_with_headers():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    c1 = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C1", parent=holding)
    b1 = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B1", parent=c1)

    user = User.objects.create_user(username="u_ok", password="pass12345")
    UserMembership.objects.create(user=user, org_unit=b1, is_active=True)

    client = APIClient()
    login = client.post("/api/auth/login/", {"username": "u_ok", "password": "pass12345"}, format="json")
    assert login.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    r = client.get("/api/iam/context/", HTTP_X_COMPANY_ID=str(c1.id), HTTP_X_BRANCH_ID=str(b1.id))
    assert r.status_code == 200
    assert r.data["company_id"] == c1.id
    assert r.data["branch_id"] == b1.id
