import uuid
from decimal import Decimal
from types import SimpleNamespace
from datetime import timedelta

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone

from apps.accounts.models import User
from apps.iam.models import OrgUnit
from apps.sync_engine.errors import SyncRejectError
from apps.sync_engine.models import Device, DeviceEnrollmentChallenge
from apps.sync_engine import handlers_inventory as inv_handlers
from modulos.inventarios import services as inv_services
from modulos.inventarios.models import InventoryItem, Warehouse


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
def test_sync_reject_error_str():
    err = SyncRejectError("INVENTORY_SCHEMA_INVALID")
    assert str(err) == "INVENTORY_SCHEMA_INVALID"


@pytest.mark.django_db
def test_device_and_enrollment_clean_validations():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    other_company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C2", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)

    device = Device(company=other_company, branch=branch, public_key=b"0" * 32, label="dev")
    with pytest.raises(ValidationError):
        device.full_clean()

    user = User.objects.create_user(username=f"u_{uuid.uuid4().hex[:6]}", password="x")
    ch = DeviceEnrollmentChallenge(
        company=other_company,
        branch=branch,
        enrollment_code_hash="x" * 64,
        expires_at=timezone.now() + timedelta(minutes=5),
        created_by_user=user,
    )
    with pytest.raises(ValidationError):
        ch.full_clean()

    ch.company = company
    ch.branch = branch
    ch.enrollment_code_hash = "y" * 64
    ch.expires_at = timezone.now() - timedelta(minutes=1)
    ch.full_clean()
    assert ch.is_valid_now() is False


@pytest.mark.django_db
def test_handlers_inventory_receive_issue_adjust_transfer_and_aliases():
    company, branch = _mk_scope()
    wh_from, item = _seed_warehouse_item(company=company, branch=branch)
    wh_to = Warehouse.objects.create(company=company, branch=branch, name="WH2", code="W2")
    req = _request(company, branch)

    ctx = {
        "request": req,
        "company_id": company.id,
        "branch_id": branch.id,
        "command_id": str(uuid.uuid4()),
        "command_type": "INVENTORY_MOVEMENT_RECEIVE",
    }

    res = inv_handlers.handle_inventory_receive(
        ctx,
        {"warehouse_id": wh_from.id, "item_id": item.id, "qty": "3.0000", "unit_cost": "1.000000"},
    )
    assert res["refs"]["movement_id"]

    inv_handlers.handle_inventory_receive_v2(ctx, {"warehouse_id": wh_from.id, "item_id": item.id, "qty": "1.0000", "unit_cost": "1.000000"})

    res_issue = inv_handlers.handle_inventory_issue(
        ctx,
        {"warehouse_id": wh_from.id, "item_id": item.id, "qty": "1.0000", "allow_negative": True},
    )
    assert res_issue["refs"]["movement_id"]

    res_adjust = inv_handlers.handle_inventory_adjust(
        ctx,
        {"warehouse_id": wh_from.id, "item_id": item.id, "new_qty_on_hand": "2.0000"},
    )
    assert res_adjust["refs"]["movement_id"]

    res_transfer = inv_handlers.handle_inventory_transfer(
        ctx,
        {"from_warehouse_id": wh_from.id, "to_warehouse_id": wh_to.id, "item_id": item.id, "qty": "1.0000"},
    )
    assert res_transfer["refs"]["transfer_out_movement_id"]

    inv_handlers.handle_inventory_issue_v2(ctx, {"warehouse_id": wh_from.id, "item_id": item.id, "qty": "1.0000", "allow_negative": True})
    inv_handlers.handle_inventory_adjust_v2(ctx, {"warehouse_id": wh_from.id, "item_id": item.id, "new_qty_on_hand": "2.0000"})
    inv_handlers.handle_inventory_transfer_v2(ctx, {"from_warehouse_id": wh_from.id, "to_warehouse_id": wh_to.id, "item_id": item.id, "qty": "1.0000"})


@pytest.mark.django_db
def test_handlers_inventory_schema_and_scope_errors():
    company, branch = _mk_scope()
    req = _request(company, branch)

    ctx = {
        "request": req,
        "company_id": company.id,
        "branch_id": None,
        "command_id": str(uuid.uuid4()),
        "command_type": "INVENTORY_MOVEMENT_RECEIVE",
    }

    with pytest.raises(SyncRejectError) as exc:
        inv_handlers.handle_inventory_receive(ctx, {"warehouse_id": 1, "item_id": 1, "qty": "1.0", "unit_cost": "1.0"})
    assert exc.value.reason_code == "INVENTORY_INVALID_SCOPE"

    ctx["branch_id"] = branch.id
    with pytest.raises(SyncRejectError) as exc:
        inv_handlers.handle_inventory_receive(ctx, {"item_id": 1, "qty": "1.0", "unit_cost": "1.0"})
    assert exc.value.reason_code == "INVENTORY_SCHEMA_INVALID"

    with pytest.raises(SyncRejectError) as exc:
        inv_handlers.handle_inventory_adjust(ctx, {"warehouse_id": 1, "item_id": 1, "new_qty_on_hand": "x"})
    assert exc.value.reason_code == "INVENTORY_SCHEMA_INVALID"
