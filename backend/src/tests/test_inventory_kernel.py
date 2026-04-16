from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.modulos.audit.models import AuditEvent
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.kernels.inventarios.services import post_issue, post_receive
from apps.kernels.inventarios.models import InventoryItem, Warehouse

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
    access = resp.data.get("access") if isinstance(resp.data, dict) else None
    if isinstance(access, str) and access:
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {access}"
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
    from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

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


@pytest.mark.django_db
def test_inventory_read_endpoints_require_authentication():
    client = APIClient()
    assert client.get("/api/inventory/warehouses/").status_code == 401
    assert client.get("/api/inventory/items/").status_code == 401
    assert client.get("/api/inventory/movements/?warehouse_id=1&item_id=1").status_code == 401


@pytest.mark.django_db
def test_inventory_read_endpoints_without_permissions_return_403():
    company, branch = _mk_org()
    client = _client_with_membership_only(company=company, branch=branch)

    assert client.get("/api/inventory/warehouses/").status_code == 403
    assert client.get("/api/inventory/items/").status_code == 403
    assert client.get("/api/inventory/movements/?warehouse_id=1&item_id=1").status_code == 403


@pytest.mark.django_db
def test_inventory_warehouses_list_is_scoped_to_active_branch():
    company, branch_a = _mk_org()
    branch_b = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B2", parent=company)

    Warehouse.objects.create(company=company, branch=branch_a, name="Main A", code="A", is_active=True)
    Warehouse.objects.create(company=company, branch=branch_b, name="Main B", code="B", is_active=True)

    client = _client_with_perms(
        company=company,
        branch=branch_a,
        perm_codes=["inventory.balance.read"],
    )
    response = client.get("/api/inventory/warehouses/")
    assert response.status_code == 200
    assert len(response.data) == 1
    assert response.data[0]["name"] == "Main A"


@pytest.mark.django_db
def test_inventory_items_list_supports_q_and_limit_with_max_cap():
    company, branch = _mk_org()
    InventoryItem.objects.create(company=company, sku="DIESEL-A", name="Diesel A", uom="LITER", is_active=True)
    InventoryItem.objects.create(company=company, sku="DIESEL-B", name="Diesel B", uom="LITER", is_active=True)
    InventoryItem.objects.create(company=company, sku="KEROSENE", name="Kerosene", uom="LITER", is_active=True)

    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["inventory.item.read"],
    )

    filtered = client.get("/api/inventory/items/?q=diesel&limit=1")
    assert filtered.status_code == 200
    assert len(filtered.data) == 1
    assert "DIESEL" in filtered.data[0]["sku"]

    capped = client.get("/api/inventory/items/?limit=99")
    assert capped.status_code == 200
    assert len(capped.data) == 3


@pytest.mark.django_db
def test_inventory_movements_history_desc_order_and_limit():
    company, branch = _mk_org()
    user = User.objects.create_user(username=f"user_{uuid.uuid4().hex[:8]}", email="m@test.com", password="pass12345")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    wh = Warehouse.objects.create(company=company, branch=branch, name="Main", code="M", is_active=True)
    item = InventoryItem.objects.create(company=company, sku=f"SKU-{uuid.uuid4().hex[:6]}", name="Diesel", uom="LITER")

    req = type("Req", (), {"company": company, "branch": branch, "META": {}, "path": "/", "method": "POST"})()
    post_receive(
        request=req,
        actor=user,
        warehouse_id=wh.id,
        item_id=item.id,
        qty=Decimal("10.0000"),
        unit_cost=Decimal("1.000000"),
        idempotency_key=f"recv-{uuid.uuid4().hex}",
    )
    post_issue(
        request=req,
        actor=user,
        warehouse_id=wh.id,
        item_id=item.id,
        qty=Decimal("2.0000"),
        idempotency_key=f"iss-{uuid.uuid4().hex}",
    )
    post_issue(
        request=req,
        actor=user,
        warehouse_id=wh.id,
        item_id=item.id,
        qty=Decimal("1.0000"),
        idempotency_key=f"iss-{uuid.uuid4().hex}",
    )

    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["inventory.balance.read"],
    )
    response = client.get(f"/api/inventory/movements/?warehouse_id={wh.id}&item_id={item.id}&limit=2")
    assert response.status_code == 200
    assert len(response.data) == 2
    ids = [row["id"] for row in response.data]
    assert ids == sorted(ids, reverse=True)
