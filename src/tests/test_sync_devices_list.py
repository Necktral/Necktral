import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.iam.models import OrgUnit, UserMembership
from apps.rbac.models import Permission, Role, RoleAssignment, RolePermission
from apps.sync_engine.models import Device

User = get_user_model()

@pytest.mark.django_db
def test_sync_devices_list_returns_devices_for_company():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B1", parent=company)

    user = User.objects.create_user(username="owner_list", password="pass12345")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)

    role = Role.objects.create(name=f"admin_{uuid.uuid4().hex}", is_active=True)
    p, _ = Permission.objects.get_or_create(code="sync.device.revoke", defaults={"is_active": True, "description": ""})
    if not p.is_active:
        p.is_active = True
        p.save(update_fields=["is_active"])
    RolePermission.objects.get_or_create(role=role, permission=p)
    RoleAssignment.objects.get_or_create(user=user, role=role, org_unit=company, defaults={"is_active": True})

    device = Device.objects.create(
        company=company,
        branch=branch,
        label="Tablet-01",
        status=Device.Status.ACTIVE,
        public_key=b"\x01" * 32,
        meta={},
        enrolled_by_user=user,
    )

    client = APIClient()
    login = client.post("/api/auth/login/", {"username": "owner_list", "password": "pass12345"}, format="json")
    assert login.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    r = client.get("/api/sync/devices/?q=Tablet&status=ACTIVE", HTTP_X_COMPANY_ID=str(company.id))
    assert r.status_code == 200

    ids = [x["id"] for x in r.data["results"]]
    assert str(device.id) in ids

@pytest.mark.django_db
def test_sync_devices_list_denied_without_permission_is_audited():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)

    user = User.objects.create_user(username="owner_no_list", password="pass12345")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)

    role = Role.objects.create(name=f"r_{uuid.uuid4().hex}", is_active=True)
    # permiso distinto (no list/revoke)
    p, _ = Permission.objects.get_or_create(code="sync.device.enroll", defaults={"is_active": True, "description": ""})
    RolePermission.objects.get_or_create(role=role, permission=p)
    RoleAssignment.objects.get_or_create(user=user, role=role, org_unit=company, defaults={"is_active": True})

    client = APIClient()
    login = client.post("/api/auth/login/", {"username": "owner_no_list", "password": "pass12345"}, format="json")
    assert login.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    r = client.get("/api/sync/devices/", HTTP_X_COMPANY_ID=str(company.id))
    assert r.status_code == 403

    ev = AuditEvent.objects.filter(
        event_type="AUTH_ACCESS_DENIED",
        path="/api/sync/devices/",
        method="GET",
    ).latest("timestamp_server")
    assert ev.reason_code == "POLICY_PERMISSION_DENIED"
    assert ev.metadata.get("required_permission") == "sync.device.revoke"
