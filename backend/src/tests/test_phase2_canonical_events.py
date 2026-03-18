from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.iam.models import OrgUnit, UserMembership
from apps.integration.models import OutboxEvent
from apps.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _mk_org():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


def _client_with_perms(*, company: OrgUnit, branch: OrgUnit, perm_codes: list[str]) -> APIClient:
    username = f"u_{uuid.uuid4().hex[:10]}"
    user = User.objects.create_user(username=username, email="events@test.com", password="pass12345")

    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perm_codes:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)

    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)

    client = APIClient()
    resp = client.post("/api/backend/auth/login/", {"username": username, "password": "pass12345"}, format="json")
    assert resp.status_code == 200
    access = resp.data.get("access") if isinstance(resp.data, dict) else None
    if isinstance(access, str) and access:
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {access}"
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client


def _assert_canonical_envelope(event: OutboxEvent, *, company_id: int, branch_id: int):
    payload = event.payload
    assert payload["schema_version"] == 1
    assert payload["contract_version"] == "1.0"
    assert payload["occurred_at"]
    assert payload["scope"]["company_id"] == company_id
    assert payload["scope"]["branch_id"] == branch_id
    assert "user_id" in payload["actor"]
    assert "correlation_id" in payload
    assert "causation_id" in payload
    assert isinstance(payload["data"], dict)


@pytest.mark.django_db
def test_billing_and_inventory_publish_canonical_outbox_events():
    company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "inventory.warehouse.create",
            "inventory.item.create",
            "inventory.movement.receive",
            "billing.doc.create",
            "billing.doc.issue",
        ],
    )

    r_wh = client.post("/api/inventory/warehouses/", {"name": "Main", "code": "M"}, format="json")
    assert r_wh.status_code == 201
    warehouse_id = r_wh.data["id"]

    r_item = client.post("/api/inventory/items/", {"sku": "DIESEL", "name": "Diesel", "uom": "LITER"}, format="json")
    assert r_item.status_code == 201
    item_id = r_item.data["id"]

    r_receive = client.post(
        "/api/inventory/movements/receive/",
        {
            "warehouse_id": warehouse_id,
            "item_id": item_id,
            "qty": "10.0000",
            "unit_cost": "1.250000",
            "idempotency_key": "inv-k-1",
        },
        format="json",
    )
    assert r_receive.status_code == 201

    r_doc = client.post(
        "/api/billing/docs/",
        {
            "doc_type": "INVOICE",
            "series": "A",
            "currency": "NIO",
            "customer_name": "Cliente Canon",
            "lines": [{"description": "Diesel", "quantity": "1.0000", "unit_price": "10.000000", "tax_rate": "0.1500"}],
            "idempotency_key": "bill-k-1",
        },
        format="json",
    )
    assert r_doc.status_code == 201
    doc_id = r_doc.data["id"]

    r_issue = client.post(f"/api/billing/docs/{doc_id}/issue/", {"apply_inventory": False}, format="json")
    assert r_issue.status_code == 200

    billing_event = OutboxEvent.objects.filter(source_module="BILLING", event_type="DocumentIssued").latest("id")
    inventory_event = OutboxEvent.objects.filter(
        source_module="INVENTORY",
        event_type="InventoryMovementPosted",
    ).latest("id")

    _assert_canonical_envelope(billing_event, company_id=company.id, branch_id=branch.id)
    _assert_canonical_envelope(inventory_event, company_id=company.id, branch_id=branch.id)

    assert billing_event.payload["data"]["doc_id"] == doc_id
    assert inventory_event.payload["data"]["movement_type"] == "RECEIVE"
