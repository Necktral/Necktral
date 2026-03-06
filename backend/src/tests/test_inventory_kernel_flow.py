from __future__ import annotations

import pytest
from rest_framework.test import APIClient

from apps.iam.models import OrgUnit, UserMembership
from apps.rbac.models import Role, Permission, RoleAssignment, RolePermission
from apps.accounts.models import User
from apps.audit.models import AuditEvent


def _mk_scope():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


def _client_with_perms(user: User, company: OrgUnit, branch: OrgUnit, perms: list[str]) -> APIClient:
    role = Role.objects.create(name="tmp_role", is_active=True)
    for p in perms:
        perm, _ = Permission.objects.get_or_create(code=p, defaults={"description": p, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, origin=RoleAssignment.Origin.MANUAL)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, origin=RoleAssignment.Origin.MANUAL)

    c = APIClient()

    login = c.post(
        "/api/auth/login/",
        {"username": user.username, "password": "x"},
        format="json",
    )
    assert login.status_code == 200
    access = login.data["access"]
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

    c.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    c.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return c


@pytest.mark.django_db
def test_inventory_receive_issue_audited():
    company, branch = _mk_scope()
    user = User.objects.create_user(username="u1", password="x")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    c = _client_with_perms(
        user,
        company,
        branch,
        [
            "inventory.warehouse.create",
            "inventory.item.create",
            "inventory.movement.receive",
            "inventory.movement.issue",
            "inventory.balance.read",
        ],
    )

    r = c.post("/api/inventory/warehouses/", {"name": "Main", "code": "M"}, format="json")
    assert r.status_code == 201
    wh_id = r.data["id"]

    r = c.post("/api/inventory/items/", {"sku": "DIESEL", "name": "Diesel", "uom": "LITER"}, format="json")
    assert r.status_code == 201
    item_id = r.data["id"]

    r = c.post(
        "/api/inventory/movements/receive/",
        {"warehouse_id": wh_id, "item_id": item_id, "qty": "100.0000", "unit_cost": "1.250000", "idempotency_key": "k1"},
        format="json",
    )
    assert r.status_code == 201

    r = c.post(
        "/api/inventory/movements/issue/",
        {"warehouse_id": wh_id, "item_id": item_id, "qty": "10.0000", "idempotency_key": "k2"},
        format="json",
    )
    assert r.status_code == 201

    r = c.get(f"/api/inventory/balances/?warehouse_id={wh_id}&item_id={item_id}")
    assert r.status_code == 200
    assert r.data["qty_on_hand"] == "90.0000"

    # Auditoría: deben existir eventos del módulo INVENTORY
    assert AuditEvent.objects.filter(module="INVENTORY", event_type="INVENTORY_MOVEMENT_POSTED").count() >= 2
