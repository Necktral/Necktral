import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest

from apps.iam.models import OrgUnit
from modulos.inventarios import services as inv_services
from modulos.inventarios.models import InventoryItem, MovementType, StockMovement, Warehouse
from apps.sync_engine import handlers_inventory as inv_handlers
from apps.sync_engine.errors import SyncRejectError


def _mk_scope():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


def _request(company: OrgUnit, branch: OrgUnit | None):
    return SimpleNamespace(company=company, branch=branch, META={}, path="/", method="POST")


def _seed_warehouse_item(*, company: OrgUnit, branch: OrgUnit):
    wh = Warehouse.objects.create(company=company, branch=branch, name="WH", code="W")
    item = InventoryItem.objects.create(company=company, sku=f"SKU-{uuid.uuid4().hex[:6]}", name="Item", uom="UNIT")
    return wh, item


@pytest.mark.django_db
def test_post_receive_invalid_qty_and_cost():
    company, branch = _mk_scope()
    wh, item = _seed_warehouse_item(company=company, branch=branch)
    req = _request(company, branch)

    with pytest.raises(ValueError, match="qty debe ser > 0"):
        inv_services.post_receive(
            request=req,
            actor=None,
            warehouse_id=wh.id,
            item_id=item.id,
            qty=Decimal("0"),
            unit_cost=Decimal("1.0"),
        )

    with pytest.raises(ValueError, match="unit_cost debe ser >= 0"):
        inv_services.post_receive(
            request=req,
            actor=None,
            warehouse_id=wh.id,
            item_id=item.id,
            qty=Decimal("1"),
            unit_cost=Decimal("-0.01"),
        )


@pytest.mark.django_db
def test_post_receive_invalid_scope_entities():
    company, branch = _mk_scope()
    req = _request(company, branch)

    with pytest.raises(ValueError, match="warehouse inválido"):
        inv_services.post_receive(
            request=req,
            actor=None,
            warehouse_id=999,
            item_id=999,
            qty=Decimal("1"),
            unit_cost=Decimal("1"),
        )

    wh, _ = _seed_warehouse_item(company=company, branch=branch)
    with pytest.raises(ValueError, match="item inválido"):
        inv_services.post_receive(
            request=req,
            actor=None,
            warehouse_id=wh.id,
            item_id=999,
            qty=Decimal("1"),
            unit_cost=Decimal("1"),
        )


@pytest.mark.django_db
def test_post_receive_idempotent_returns_existing_balance():
    company, branch = _mk_scope()
    wh, item = _seed_warehouse_item(company=company, branch=branch)
    req = _request(company, branch)

    first = inv_services.post_receive(
        request=req,
        actor=None,
        warehouse_id=wh.id,
        item_id=item.id,
        qty=Decimal("2.0000"),
        unit_cost=Decimal("1.000000"),
        idempotency_key="idem-1",
    )
    second = inv_services.post_receive(
        request=req,
        actor=None,
        warehouse_id=wh.id,
        item_id=item.id,
        qty=Decimal("2.0000"),
        unit_cost=Decimal("1.000000"),
        idempotency_key="idem-1",
    )

    assert first.movement_id == second.movement_id
    assert str(second.qty_on_hand) == "2.0000"


@pytest.mark.django_db
def test_post_issue_insufficient_stock_and_allow_negative():
    company, branch = _mk_scope()
    wh, item = _seed_warehouse_item(company=company, branch=branch)
    req = _request(company, branch)

    with pytest.raises(ValueError, match="stock insuficiente"):
        inv_services.post_issue(
            request=req,
            actor=None,
            warehouse_id=wh.id,
            item_id=item.id,
            qty=Decimal("1.0000"),
            allow_negative=False,
        )

    res = inv_services.post_issue(
        request=req,
        actor=None,
        warehouse_id=wh.id,
        item_id=item.id,
        qty=Decimal("1.0000"),
        allow_negative=True,
    )
    assert res.movement_id


@pytest.mark.django_db
def test_post_adjust_idempotent_returns_existing():
    company, branch = _mk_scope()
    wh, item = _seed_warehouse_item(company=company, branch=branch)
    req = _request(company, branch)

    inv_services.post_receive(
        request=req,
        actor=None,
        warehouse_id=wh.id,
        item_id=item.id,
        qty=Decimal("5"),
        unit_cost=Decimal("1"),
    )

    first = inv_services.post_adjust(
        request=req,
        actor=None,
        warehouse_id=wh.id,
        item_id=item.id,
        new_qty_on_hand=Decimal("3"),
        idempotency_key="adj-1",
    )
    second = inv_services.post_adjust(
        request=req,
        actor=None,
        warehouse_id=wh.id,
        item_id=item.id,
        new_qty_on_hand=Decimal("3"),
        idempotency_key="adj-1",
    )

    assert first.movement_id == second.movement_id


@pytest.mark.django_db
def test_post_transfer_errors_and_idempotent():
    company, branch = _mk_scope()
    wh_from, item = _seed_warehouse_item(company=company, branch=branch)
    wh_to = Warehouse.objects.create(company=company, branch=branch, name="WH2", code="W2")
    req = _request(company, branch)

    with pytest.raises(ValueError, match="from_warehouse_id y to_warehouse_id deben ser distintos"):
        inv_services.post_transfer(
            request=req,
            actor=None,
            from_warehouse_id=wh_from.id,
            to_warehouse_id=wh_from.id,
            item_id=item.id,
            qty=Decimal("1"),
        )

    with pytest.raises(ValueError, match="warehouse inválido"):
        inv_services.post_transfer(
            request=req,
            actor=None,
            from_warehouse_id=999,
            to_warehouse_id=wh_to.id,
            item_id=item.id,
            qty=Decimal("1"),
        )

    with pytest.raises(ValueError, match="stock insuficiente"):
        inv_services.post_transfer(
            request=req,
            actor=None,
            from_warehouse_id=wh_from.id,
            to_warehouse_id=wh_to.id,
            item_id=item.id,
            qty=Decimal("1"),
        )

    inv_services.post_receive(
        request=req,
        actor=None,
        warehouse_id=wh_from.id,
        item_id=item.id,
        qty=Decimal("5"),
        unit_cost=Decimal("1"),
    )

    first = inv_services.post_transfer(
        request=req,
        actor=None,
        from_warehouse_id=wh_from.id,
        to_warehouse_id=wh_to.id,
        item_id=item.id,
        qty=Decimal("2"),
        idempotency_key="tr-1",
    )
    second = inv_services.post_transfer(
        request=req,
        actor=None,
        from_warehouse_id=wh_from.id,
        to_warehouse_id=wh_to.id,
        item_id=item.id,
        qty=Decimal("2"),
        idempotency_key="tr-1",
    )

    assert "out_movement_id" in first
    assert second.get("idempotent") is True


@pytest.mark.django_db
def test_handlers_helpers_and_idempotency_conflict():
    company, branch = _mk_scope()
    wh, item = _seed_warehouse_item(company=company, branch=branch)

    with pytest.raises(SyncRejectError) as exc_info:
        inv_handlers._require_int({}, "warehouse_id")
    assert exc_info.value.reason_code == "INVENTORY_SCHEMA_INVALID"

    with pytest.raises(SyncRejectError) as exc_info:
        inv_handlers._require_decimal({"qty": "x"}, "qty")
    assert exc_info.value.reason_code == "INVENTORY_SCHEMA_INVALID"

    req = _request(company, branch)
    inv_handlers._attach_scope_to_request(request=req, company_id=company.id, branch_id=branch.id)

    with pytest.raises(SyncRejectError) as exc_info:
        inv_handlers._attach_scope_to_request(request=req, company_id=999, branch_id=branch.id)
    assert exc_info.value.reason_code == "INVENTORY_INVALID_SCOPE"

    StockMovement.objects.create(
        company=company,
        branch=branch,
        warehouse=wh,
        item=item,
        movement_type=MovementType.RECEIVE,
        qty_delta=Decimal("1.0000"),
        unit_cost=Decimal("1.000000"),
        total_cost=Decimal("1.000000"),
        idempotency_key="idem-conflict",
    )

    with pytest.raises(SyncRejectError) as exc_info:
        inv_handlers._ensure_idempotency_match(
            company_id=company.id,
            branch_id=branch.id,
            idempotency_key="idem-conflict",
            movement_type=MovementType.RECEIVE,
            warehouse_id=wh.id,
            item_id=item.id,
            qty_delta=Decimal("2.0000"),
            unit_cost=Decimal("1.000000"),
        )
    assert exc_info.value.reason_code == "INVENTORY_IDEMPOTENCY_CONFLICT"


@pytest.mark.django_db
def test_handle_transfer_idempotent_path():
    company, branch = _mk_scope()
    wh_from, item = _seed_warehouse_item(company=company, branch=branch)
    wh_to = Warehouse.objects.create(company=company, branch=branch, name="WH2", code="W2")
    req = _request(company, branch)

    inv_services.post_receive(
        request=req,
        actor=None,
        warehouse_id=wh_from.id,
        item_id=item.id,
        qty=Decimal("4"),
        unit_cost=Decimal("1"),
    )

    ctx = {
        "request": req,
        "company_id": company.id,
        "branch_id": branch.id,
        "command_id": str(uuid.uuid4()),
        "command_type": "INVENTORY_TRANSFER",
    }
    payload = {
        "from_warehouse_id": wh_from.id,
        "to_warehouse_id": wh_to.id,
        "item_id": item.id,
        "qty": "2",
        "idempotency_key": "idem-tr",
    }

    inv_handlers.handle_inventory_transfer(ctx, payload)
    res = inv_handlers.handle_inventory_transfer(ctx, payload)
    assert res["refs"]["transfer_out_movement_id"]


@pytest.mark.django_db
def test_namespaced_idempotency_key():
    key = inv_handlers._namespaced_idempotency_key(
        command_type="INVENTORY_MOVEMENT_RECEIVE",
        company_id=10,
        branch_id=20,
        raw_key="ref-1",
    )
    assert key.startswith("INVENTORY.MOVEMENT.RECEIVE:10:20:")
