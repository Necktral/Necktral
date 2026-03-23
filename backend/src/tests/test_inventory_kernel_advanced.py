from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _mk_org():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


def _client_with_perms(*, company: OrgUnit, branch: OrgUnit, perm_codes: list[str]) -> APIClient:
    username = f"u_{uuid.uuid4().hex[:10]}"
    user = User.objects.create_user(username=username, email="inv-adv@test.com", password="pass12345")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perm_codes:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)

    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)

    client = APIClient()
    login = client.post("/api/backend/auth/login/", {"username": username, "password": "pass12345"}, format="json")
    assert login.status_code == 200
    token = login.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {token}"
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client


@pytest.mark.django_db
def test_inventory_items_and_warehouses_list_patch_flow():
    company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "inventory.item.read",
            "inventory.item.create",
            "inventory.item.update",
            "inventory.warehouse.create",
            "inventory.balance.read",
        ],
    )

    wh_resp = client.post("/api/inventory/warehouses/", {"name": "Main", "code": "MAIN"}, format="json")
    assert wh_resp.status_code == 201
    wh_id = int(wh_resp.data["id"])

    sku = f"SKU-{uuid.uuid4().hex[:8]}"
    item_resp = client.post(
        "/api/inventory/items/",
        {"sku": sku, "name": "Aceite", "uom": "UNIT"},
        format="json",
    )
    assert item_resp.status_code == 201
    item_id = int(item_resp.data["id"])

    items = client.get(f"/api/inventory/items/?q={sku}")
    assert items.status_code == 200
    assert items.data["count"] >= 1
    assert len(items.data["results"]) >= 1

    patch_item = client.patch(
        f"/api/inventory/items/{item_id}/",
        {"name": "Aceite Premium", "is_active": False},
        format="json",
    )
    assert patch_item.status_code == 200
    assert patch_item.data["name"] == "Aceite Premium"
    assert patch_item.data["is_active"] is False

    warehouses = client.get("/api/inventory/warehouses/?q=main")
    assert warehouses.status_code == 200
    assert warehouses.data["count"] >= 1

    patch_wh = client.patch(
        f"/api/inventory/warehouses/{wh_id}/",
        {"name": "Main Updated", "is_active": False},
        format="json",
    )
    assert patch_wh.status_code == 200
    assert patch_wh.data["name"] == "Main Updated"
    assert patch_wh.data["is_active"] is False

    balances = client.get("/api/inventory/balances/?limit=20&offset=0")
    assert balances.status_code == 200
    assert "results" in balances.data


@pytest.mark.django_db
def test_inventory_balances_list_and_ledger_filters():
    company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "inventory.warehouse.create",
            "inventory.item.create",
            "inventory.movement.receive",
            "inventory.balance.read",
        ],
    )

    wh_resp = client.post("/api/inventory/warehouses/", {"name": "Main", "code": "B1"}, format="json")
    assert wh_resp.status_code == 201
    wh_id = int(wh_resp.data["id"])

    item_resp = client.post(
        "/api/inventory/items/",
        {"sku": "LUBE-01", "name": "Lubricante", "uom": "UNIT"},
        format="json",
    )
    assert item_resp.status_code == 201
    item_id = int(item_resp.data["id"])

    receive = client.post(
        "/api/inventory/movements/receive/",
        {
            "warehouse_id": wh_id,
            "item_id": item_id,
            "qty": "12.0000",
            "unit_cost": "4.250000",
            "idempotency_key": f"recv-{uuid.uuid4().hex}",
        },
        format="json",
    )
    assert receive.status_code == 201

    balances = client.get("/api/inventory/balances/?q=lube&limit=10&offset=0")
    assert balances.status_code == 200
    assert balances.data["count"] >= 1
    assert any(int(row["item_id"]) == item_id for row in balances.data["results"])

    ledger = client.get(f"/api/inventory/ledger/?item_id={item_id}&movement_type=RECEIVE&limit=1&offset=0")
    assert ledger.status_code == 200
    assert ledger.data["count"] >= 1
    assert len(ledger.data["results"]) == 1
    assert ledger.data["results"][0]["movement_type"] == "RECEIVE"

    future = client.get("/api/inventory/ledger/?date_from=2099-01-01T00:00:00Z&limit=10")
    assert future.status_code == 200
    assert future.data["count"] == 0


@pytest.mark.django_db
def test_inventory_command_batch_applied_duplicate_rejected():
    company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "inventory.movement.post",
            "inventory.warehouse.create",
            "inventory.item.create",
        ],
    )

    wh_resp = client.post("/api/inventory/warehouses/", {"name": "Main", "code": "BATCH"}, format="json")
    assert wh_resp.status_code == 201
    wh_id = int(wh_resp.data["id"])

    item_resp = client.post(
        "/api/inventory/items/",
        {"sku": f"BATCH-{uuid.uuid4().hex[:6]}", "name": "Batch Item", "uom": "UNIT"},
        format="json",
    )
    assert item_resp.status_code == 201
    item_id = int(item_resp.data["id"])

    idem = f"idem-{uuid.uuid4().hex}"
    payload = {
        "commands": [
            {
                "command_id": str(uuid.uuid4()),
                "type": "INVENTORY.MOVEMENT.RECEIVE",
                "payload": {
                    "warehouse_id": wh_id,
                    "item_id": item_id,
                    "qty": "5.0000",
                    "unit_cost": "2.000000",
                    "idempotency_key": idem,
                },
            },
            {
                "command_id": str(uuid.uuid4()),
                "type": "INVENTORY.MOVEMENT.RECEIVE",
                "payload": {
                    "warehouse_id": wh_id,
                    "item_id": item_id,
                    "qty": "5.0000",
                    "unit_cost": "2.000000",
                    "idempotency_key": idem,
                },
            },
            {
                "command_id": str(uuid.uuid4()),
                "type": "INVENTORY.MOVEMENT.ISSUE",
                "payload": {
                    "warehouse_id": wh_id,
                    "item_id": item_id,
                    "qty": "0.0000",
                },
            },
        ]
    }

    resp = client.post("/api/inventory/commands/batch/", payload, format="json")
    assert resp.status_code == 200
    assert resp.data["summary"]["total"] == 3
    assert resp.data["summary"]["applied"] == 1
    assert resp.data["summary"]["duplicate"] == 1
    assert resp.data["summary"]["rejected"] == 1

    statuses = [row["status"] for row in resp.data["results"]]
    assert statuses.count("APPLIED") == 1
    assert statuses.count("DUPLICATE") == 1
    assert statuses.count("REJECTED") == 1


@pytest.mark.django_db
def test_item_master_p0_lookups_extended_payload_and_barcode_uniqueness():
    company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "inventory.item.read",
            "inventory.item.create",
            "inventory.item.update",
            "inventory.warehouse.create",
        ],
    )

    wh_resp = client.post("/api/inventory/warehouses/", {"name": "Main WH", "code": "MWH"}, format="json")
    assert wh_resp.status_code == 201
    wh_id = int(wh_resp.data["id"])

    brand_resp = client.post("/api/inventory/lookups/brands/", {"name": "BrandX"}, format="json")
    assert brand_resp.status_code == 201
    brand_id = int(brand_resp.data["id"])

    category_resp = client.post("/api/inventory/lookups/categories/", {"name": "Lubricantes"}, format="json")
    assert category_resp.status_code == 201
    category_id = int(category_resp.data["id"])

    subcategory_resp = client.post(
        "/api/inventory/lookups/categories/",
        {"name": "Sinteticos", "parent_id": category_id},
        format="json",
    )
    assert subcategory_resp.status_code == 201
    subcategory_id = int(subcategory_resp.data["id"])

    tax_profile_resp = client.post(
        "/api/inventory/lookups/tax-profiles/",
        {"code": "IVA15", "name": "IVA 15%", "tax_treatment": "GRAVADO"},
        format="json",
    )
    assert tax_profile_resp.status_code == 201
    tax_profile_id = int(tax_profile_resp.data["id"])

    brand_list = client.get("/api/inventory/lookups/brands/?q=brand")
    assert brand_list.status_code == 200
    assert brand_list.data["count"] >= 1

    category_list = client.get(f"/api/inventory/lookups/categories/?parent_id={category_id}")
    assert category_list.status_code == 200
    assert category_list.data["count"] >= 1

    tax_profile_list = client.get("/api/inventory/lookups/tax-profiles/?q=iva")
    assert tax_profile_list.status_code == 200
    assert tax_profile_list.data["count"] >= 1

    payload = {
        "sku": f"ITEM-P0-{uuid.uuid4().hex[:6]}",
        "name": "Aceite 15W40",
        "item_type": "INVENTARIABLE",
        "status": "ACTIVO",
        "category_id": category_id,
        "subcategory_id": subcategory_id,
        "brand_id": brand_id,
        "barcode": "1234567890123",
        "barcode_type": "EAN13",
        "purchase_enabled": True,
        "sales_enabled": True,
        "controls_stock": True,
        "transfer_enabled": True,
        "uom_base": "UNIT",
        "uom_purchase": "BOX",
        "uom_sale": "UNIT",
        "uom_conversions": [{"to_uom": "BOX", "factor": "12"}],
        "enabled_branch_ids": [int(branch.id)],
        "default_branch_id": int(branch.id),
        "default_warehouse_id": wh_id,
        "min_stock": "2.0000",
        "max_stock": "20.0000",
        "reorder_point": "5.0000",
        "reorder_qty": "6.0000",
        "initial_cost": "10.500000",
        "standard_cost": "10.500000",
        "currency": "NIO",
        "visible_pos": True,
        "tax_profile_id": tax_profile_id,
        "tax_treatment": "GRAVADO",
    }
    item_resp = client.post("/api/inventory/items/", payload, format="json")
    assert item_resp.status_code == 201
    item_id = int(item_resp.data["id"])
    assert item_resp.data["barcode"] == "1234567890123"
    assert item_resp.data["category_id"] == category_id
    assert item_resp.data["tax_profile_id"] == tax_profile_id

    duplicate_payload = dict(payload)
    duplicate_payload["sku"] = f"ITEM-P0-{uuid.uuid4().hex[:6]}"
    duplicate_resp = client.post("/api/inventory/items/", duplicate_payload, format="json")
    assert duplicate_resp.status_code == 400
    duplicate_code = duplicate_resp.data.get("code")
    if not duplicate_code:
        duplicate_code = (
            duplicate_resp.data.get("error", {})
            .get("details", {})
            .get("code")
        )
    assert duplicate_code == "INVENTORY_DUPLICATE_BARCODE"

    by_sku = client.get(f"/api/inventory/items/?sku_exact={payload['sku']}")
    assert by_sku.status_code == 200
    assert by_sku.data["count"] == 1
    assert by_sku.data["results"][0]["id"] == item_id

    by_barcode = client.get("/api/inventory/items/?barcode_exact=1234567890123")
    assert by_barcode.status_code == 200
    assert by_barcode.data["count"] == 1
    assert by_barcode.data["results"][0]["id"] == item_id

    patch_resp = client.patch(
        f"/api/inventory/items/{item_id}/",
        {"item_type": "SERVICIO", "controls_stock": True},
        format="json",
    )
    assert patch_resp.status_code == 200
    assert patch_resp.data["item_type"] == "SERVICIO"
    assert patch_resp.data["controls_stock"] is False
    assert patch_resp.data["transfer_enabled"] is False
