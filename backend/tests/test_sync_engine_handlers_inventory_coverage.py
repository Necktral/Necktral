from types import SimpleNamespace
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.iam.models import OrgUnit
from apps.sync_engine.errors import SyncRejectError
import apps.sync_engine.handlers_inventory as handlers
from modulos.inventarios.models import InventoryItem, MovementType, StockMovement, Warehouse


def _mk_scope():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


@pytest.mark.django_db
def test_handler_helpers_and_scope_errors():
    payload = {}
    with pytest.raises(SyncRejectError):
        handlers._require_int(payload, "warehouse_id")

    with pytest.raises(SyncRejectError):
        handlers._require_int({"warehouse_id": "x"}, "warehouse_id")

    with pytest.raises(SyncRejectError):
        handlers._require_decimal({"qty": "x"}, "qty")

    with pytest.raises(SyncRejectError):
        handlers._require_decimal({}, "qty")

    assert handlers._optional_str({}, "note") == ""
    assert handlers._optional_str({"note": 123}, "note") == "123"
    assert handlers._optional_bool({}, "flag", default=True) is True

    req = SimpleNamespace()
    with pytest.raises(SyncRejectError):
        handlers._attach_scope_to_request(request=req, company_id=9999, branch_id=None)

    company, branch = _mk_scope()
    req2 = SimpleNamespace()
    handlers._attach_scope_to_request(request=req2, company_id=company.id, branch_id=None)
    assert req2.branch is None

    with pytest.raises(SyncRejectError):
        handlers._attach_scope_to_request(request=req2, company_id=company.id, branch_id=9999)

    err = handlers._map_inventory_error(ValueError("item inválido"))
    assert err.reason_code == "INVENTORY_INVALID_SCOPE"

    err2 = handlers._map_inventory_error(ValueError("from_warehouse_id y to_warehouse_id deben ser distintos"))
    assert err2.reason_code == "INVENTORY_SCHEMA_INVALID"

    err3 = handlers._map_inventory_error(ValueError("stock insuficiente"))
    assert err3.reason_code == "INVENTORY_INSUFFICIENT_STOCK"

    err4 = handlers._map_inventory_error(ValueError("x-branch-id requerido"))
    assert err4.reason_code == "INVENTORY_INVALID_SCOPE"

    err5 = handlers._map_inventory_error(ValueError("warehouse inválido"))
    assert err5.reason_code == "INVENTORY_INVALID_SCOPE"

    err6 = handlers._map_inventory_error(ValueError("qty debe ser mayor que 0"))
    assert err6.reason_code == "INVENTORY_SCHEMA_INVALID"

    err7 = handlers._map_inventory_error(ValueError("unit_cost inválido"))
    assert err7.reason_code == "INVENTORY_SCHEMA_INVALID"

    err8 = handlers._map_inventory_error(ValueError("otro error"))
    assert err8.reason_code == "INVENTORY_SCHEMA_INVALID"

    assert handlers._namespaced_idempotency_key(command_type="INVENTORY_TRANSFER", company_id=1, branch_id=None, raw_key="") == ""


@pytest.mark.django_db
def test_idempotency_matching_and_transfer_idempotent(monkeypatch):
    company, branch = _mk_scope()
    wh = Warehouse.objects.create(company=company, branch=branch, name="Main", code="M")
    item = InventoryItem.objects.create(company=company, sku="SKU", name="Item", uom="UNIT")

    movement = StockMovement.objects.create(
        company=company,
        branch=branch,
        warehouse=wh,
        item=item,
        movement_type=MovementType.RECEIVE,
        qty_delta=Decimal("1.0000"),
        unit_cost=Decimal("1.000000"),
        total_cost=Decimal("1.000000"),
        idempotency_key="idem-1",
        created_at=timezone.now(),
    )

    assert handlers._movement_matches(
        movement,
        movement_type=MovementType.RECEIVE,
        warehouse_id=wh.id,
        item_id=item.id,
        qty_delta=Decimal("1.0000"),
        unit_cost=Decimal("1.000000"),
    )

    assert (
        handlers._movement_matches(
            movement,
            movement_type=MovementType.ISSUE,
            warehouse_id=wh.id,
            item_id=item.id,
        )
        is False
    )
    assert (
        handlers._movement_matches(
            movement,
            movement_type=MovementType.RECEIVE,
            warehouse_id=wh.id + 1,
            item_id=item.id,
        )
        is False
    )
    assert (
        handlers._movement_matches(
            movement,
            movement_type=MovementType.RECEIVE,
            warehouse_id=wh.id,
            item_id=item.id + 1,
        )
        is False
    )
    assert (
        handlers._movement_matches(
            movement,
            movement_type=MovementType.RECEIVE,
            warehouse_id=wh.id,
            item_id=item.id,
            qty_delta=Decimal("2.0000"),
        )
        is False
    )
    assert (
        handlers._movement_matches(
            movement,
            movement_type=MovementType.RECEIVE,
            warehouse_id=wh.id,
            item_id=item.id,
            unit_cost=Decimal("2.000000"),
        )
        is False
    )

    handlers._ensure_idempotency_match(
        company_id=company.id,
        branch_id=branch.id,
        idempotency_key="idem-1",
        movement_type=MovementType.RECEIVE,
        warehouse_id=wh.id,
        item_id=item.id,
        qty_delta=Decimal("1.0000"),
        unit_cost=Decimal("1.000000"),
    )

    with pytest.raises(SyncRejectError):
        handlers._ensure_idempotency_match(
            company_id=company.id,
            branch_id=branch.id,
            idempotency_key="idem-1",
            movement_type=MovementType.RECEIVE,
            warehouse_id=wh.id,
            item_id=item.id,
            qty_delta=Decimal("2.0000"),
            unit_cost=Decimal("1.000000"),
        )

    def _fake_transfer(*_args, **_kwargs):
        return {"idempotent": True, "movement_id": 99}

    monkeypatch.setattr(handlers.inv_services, "post_transfer", _fake_transfer)

    ctx = {
        "request": SimpleNamespace(),
        "company_id": company.id,
        "branch_id": branch.id,
        "command_id": "cmd-x",
        "command_type": "INVENTORY_TRANSFER",
    }
    payload = {
        "from_warehouse_id": wh.id,
        "to_warehouse_id": wh.id + 1,
        "item_id": item.id,
        "qty": "1.0000",
    }

    res = handlers.handle_inventory_transfer(ctx, payload)
    assert res["refs"]["transfer_out_movement_id"] == 99


@pytest.mark.django_db
def test_handle_inventory_issue_adjust_transfer_variants(monkeypatch):
    company, branch = _mk_scope()
    wh = Warehouse.objects.create(company=company, branch=branch, name="Main", code="M")
    item = InventoryItem.objects.create(company=company, sku="SKU2", name="Item2", uom="UNIT")

    ctx_missing = {
        "request": SimpleNamespace(),
        "company_id": company.id,
        "branch_id": None,
        "command_id": "cmd-x",
        "command_type": "INVENTORY_MOVEMENT_ISSUE",
    }
    with pytest.raises(SyncRejectError):
        handlers.handle_inventory_issue(ctx_missing, {"warehouse_id": wh.id, "item_id": item.id, "qty": "1.0"})
    with pytest.raises(SyncRejectError):
        handlers.handle_inventory_adjust(ctx_missing, {"warehouse_id": wh.id, "item_id": item.id, "new_qty_on_hand": "1"})
    with pytest.raises(SyncRejectError):
        handlers.handle_inventory_transfer(ctx_missing, {"from_warehouse_id": wh.id, "to_warehouse_id": wh.id + 1, "item_id": item.id, "qty": "1"})

    def _fake_issue(*_args, **kwargs):
        assert kwargs.get("allow_negative") is True
        return SimpleNamespace(movement_id=1, qty_on_hand=Decimal("1.0000"), avg_cost=Decimal("1.000000"))

    monkeypatch.setattr(handlers.inv_services, "post_issue", _fake_issue)

    ctx_issue = {
        "request": SimpleNamespace(),
        "company_id": company.id,
        "branch_id": branch.id,
        "command_id": "cmd-issue",
        "command_type": "INVENTORY_MOVEMENT_ISSUE",
    }
    payload_issue = {
        "warehouse_id": wh.id,
        "item_id": item.id,
        "qty": "1.0000",
        "allow_negative": True,
        "note": "n",
        "idempotency_key": "idem-x",
    }
    res_issue = handlers.handle_inventory_issue(ctx_issue, payload_issue)
    assert res_issue["refs"]["movement_id"] == 1

    def _fake_transfer(*_args, **_kwargs):
        return {"out_movement_id": 10, "in_movement_id": 11, "avg_cost": "1.0000"}

    monkeypatch.setattr(handlers.inv_services, "post_transfer", _fake_transfer)

    ctx_transfer = {
        "request": SimpleNamespace(),
        "company_id": company.id,
        "branch_id": branch.id,
        "command_id": "cmd-transfer",
        "command_type": "INVENTORY_TRANSFER",
    }
    payload_transfer = {
        "from_warehouse_id": wh.id,
        "to_warehouse_id": wh.id + 1,
        "item_id": item.id,
        "qty": "1.0000",
    }
    res_transfer = handlers.handle_inventory_transfer(ctx_transfer, payload_transfer)
    assert res_transfer["refs"]["transfer_out_movement_id"] == 10
    assert res_transfer["refs"]["transfer_in_movement_id"] == 11

    res_transfer_v2 = handlers.handle_inventory_transfer_v2(ctx_transfer, payload_transfer)
    assert res_transfer_v2["refs"]["transfer_out_movement_id"] == 10


@pytest.mark.django_db
def test_handle_inventory_adjust_success_and_aliases(monkeypatch):
    company, branch = _mk_scope()
    wh = Warehouse.objects.create(company=company, branch=branch, name="Adj", code="A")
    item = InventoryItem.objects.create(company=company, sku="SKU3", name="Item3", uom="UNIT")

    def _fake_adjust(*_args, **_kwargs):
        return SimpleNamespace(movement_id=5, qty_on_hand=Decimal("2.0000"), avg_cost=Decimal("1.500000"))

    monkeypatch.setattr(handlers.inv_services, "post_adjust", _fake_adjust)

    ctx = {
        "request": SimpleNamespace(),
        "company_id": company.id,
        "branch_id": branch.id,
        "command_id": "cmd-adj",
        "command_type": "INVENTORY_MOVEMENT_ADJUST",
    }
    payload = {
        "warehouse_id": wh.id,
        "item_id": item.id,
        "new_qty_on_hand": "2.0000",
    }

    res = handlers.handle_inventory_adjust(ctx, payload)
    assert res["refs"]["movement_id"] == 5

    res_v2 = handlers.handle_inventory_adjust_v2(ctx, payload)
    assert res_v2["refs"]["movement_id"] == 5


@pytest.mark.django_db
def test_handle_inventory_adjust_value_error_mapped(monkeypatch):
    company, branch = _mk_scope()
    wh = Warehouse.objects.create(company=company, branch=branch, name="AdjErr", code="AE")
    item = InventoryItem.objects.create(company=company, sku="SKU5", name="Item5", uom="UNIT")

    def _raise_adjust(*_args, **_kwargs):
        raise ValueError("item inválido")

    monkeypatch.setattr(handlers.inv_services, "post_adjust", _raise_adjust)

    ctx = {
        "request": SimpleNamespace(),
        "company_id": company.id,
        "branch_id": branch.id,
        "command_id": "cmd-adj-err",
        "command_type": "INVENTORY_MOVEMENT_ADJUST",
    }
    payload = {
        "warehouse_id": wh.id,
        "item_id": item.id,
        "new_qty_on_hand": "2.0000",
    }

    with pytest.raises(SyncRejectError) as exc:
        handlers.handle_inventory_adjust(ctx, payload)
    assert exc.value.reason_code == "INVENTORY_INVALID_SCOPE"


@pytest.mark.django_db
def test_handle_inventory_receive_v2_success(monkeypatch):
    company, branch = _mk_scope()
    wh = Warehouse.objects.create(company=company, branch=branch, name="Rec", code="R")
    item = InventoryItem.objects.create(company=company, sku="SKU4", name="Item4", uom="UNIT")

    def _fake_receive(*_args, **_kwargs):
        return SimpleNamespace(movement_id=7, qty_on_hand=Decimal("3.0000"), avg_cost=Decimal("2.000000"))

    monkeypatch.setattr(handlers.inv_services, "post_receive", _fake_receive)

    ctx = {
        "request": SimpleNamespace(),
        "company_id": company.id,
        "branch_id": branch.id,
        "command_id": "cmd-rec",
        "command_type": "INVENTORY_MOVEMENT_RECEIVE",
    }
    payload = {
        "warehouse_id": wh.id,
        "item_id": item.id,
        "qty": "1.0000",
        "unit_cost": "2.000000",
    }

    res = handlers.handle_inventory_receive_v2(ctx, payload)
    assert res["refs"]["movement_id"] == 7


@pytest.mark.django_db
def test_handle_inventory_transfer_value_error_mapped(monkeypatch):
    company, branch = _mk_scope()
    wh = Warehouse.objects.create(company=company, branch=branch, name="TrErr", code="TE")
    item = InventoryItem.objects.create(company=company, sku="SKU6", name="Item6", uom="UNIT")

    def _raise_transfer(*_args, **_kwargs):
        raise ValueError("qty debe ser")

    monkeypatch.setattr(handlers.inv_services, "post_transfer", _raise_transfer)

    ctx = {
        "request": SimpleNamespace(),
        "company_id": company.id,
        "branch_id": branch.id,
        "command_id": "cmd-tr-err",
        "command_type": "INVENTORY_TRANSFER",
    }
    payload = {
        "from_warehouse_id": wh.id,
        "to_warehouse_id": wh.id + 1,
        "item_id": item.id,
        "qty": "1.0000",
    }

    with pytest.raises(SyncRejectError) as exc:
        handlers.handle_inventory_transfer(ctx, payload)
    assert exc.value.reason_code == "INVENTORY_SCHEMA_INVALID"
