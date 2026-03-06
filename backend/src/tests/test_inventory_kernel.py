from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.iam.models import OrgUnit, UserMembership

User = get_user_model()


def _mk_org():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


def _login_client(*, username: str, password: str, company: OrgUnit, branch: OrgUnit) -> APIClient:
    client = APIClient()
    resp = client.post("/api/auth/login/", {"username": username, "password": password}, format="json")
    assert resp.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client


def _client_with_membership_only(*, company: OrgUnit, branch: OrgUnit) -> APIClient:
    username = f"u_{uuid.uuid4().hex[:10]}"
    User.objects.create_user(username=username, email="inv@test.com", password="pass12345")

    user = User.objects.get(username=username)
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    return _login_client(username=username, password="pass12345", company=company, branch=branch)


def _client_with_perms(*, company: OrgUnit, branch: OrgUnit, perm_codes: list[str]) -> APIClient:
    from apps.rbac.models import Permission, Role, RoleAssignment, RolePermission

    username = f"u_{uuid.uuid4().hex[:10]}"
    user = User.objects.create_user(username=username, email="inv2@test.com", password="pass12345")

    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perm_codes:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": "", "is_active": True})
        if not perm.is_active:
            perm.is_active = True
            perm.save(update_fields=["is_active"])
        RolePermission.objects.get_or_create(role=role, permission=perm)

    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)

    return _login_client(username=username, password="pass12345", company=company, branch=branch)


@pytest.mark.django_db
def test_inventory_item_create_writes_audit_event():
    company, branch = _mk_org()
    client = _client_with_perms(company=company, branch=branch, perm_codes=["inventory.item.create"])

    sku = f"SKU-{uuid.uuid4().hex[:8]}"
    resp = client.post("/api/inventory/items/", {"sku": sku, "name": "Aceite 20W-50"}, format="json")
    assert resp.status_code == 201
    assert resp.data["sku"] == sku

    assert AuditEvent.objects.filter(module="INVENTORY", event_type="INVENTORY_ITEM_CREATED").exists()


@pytest.mark.django_db
def test_inventory_item_create_denied_is_audited():
    company, branch = _mk_org()
    client = _client_with_membership_only(company=company, branch=branch)

    resp = client.post(
        "/api/inventory/items/",
        {"sku": "SKU-NO-PERM", "name": "No debe crear"},
        format="json",
    )
    assert resp.status_code == 403

    assert AuditEvent.objects.filter(
        event_type="AUTH_ACCESS_DENIED",
        metadata__required_permission="inventory.item.create",
    ).exists()
