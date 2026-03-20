from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from apps.modulos.iam.models import OrgUnit
from apps.modulos.integration.models import OutboxEvent
from kernels.inventarios.models import InventoryItem, StockMovement, Warehouse
from kernels.inventarios.services import post_adjust, post_receive, post_transfer


_VALID_ACCOUNTING_STATUSES = {"DRAFT_VALIDATED", "POSTED"}


def _build_scope():
    token = uuid.uuid4().hex[:8]
    holding = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.HOLDING,
        name=f"Holding {token}",
        code=f"H-{token}",
    )
    company = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.COMPANY,
        parent=holding,
        name=f"Company {token}",
        code=f"C-{token}",
    )
    branch = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.BRANCH,
        parent=company,
        name=f"Branch {token}",
        code=f"B-{token}",
    )

    User = get_user_model()
    user = User.objects.create_user(
        username=f"tester_{token}",
        email=f"tester_{token}@example.com",
        password="Secret123!",
    )
    request = SimpleNamespace(
        company=company,
        branch=branch,
        user=user,
        META={},
        headers={},
        path="/test/inventory/",
        method="POST",
        request_id=f"req-{token}",
    )
    return company, branch, user, request


@pytest.mark.django_db
def test_inventory_adjust_includes_accounting_link_and_adjust_rule_signal():
    company, branch, user, request = _build_scope()
    wh = Warehouse.objects.create(company=company, branch=branch, name="Main", code="MAIN")
    item = InventoryItem.objects.create(company=company, sku=f"SKU-{uuid.uuid4().hex[:6]}", name="Diesel")

    post_receive(
        request=request,
        actor=user,
        warehouse_id=wh.id,
        item_id=item.id,
        qty=Decimal("10.0000"),
        unit_cost=Decimal("2.500000"),
        idempotency_key=f"recv-{uuid.uuid4().hex}",
    )

    out = post_adjust(
        request=request,
        actor=user,
        warehouse_id=wh.id,
        item_id=item.id,
        new_qty_on_hand=Decimal("8.0000"),
        idempotency_key=f"adj-{uuid.uuid4().hex}",
    )

    assert out.accounting_status in _VALID_ACCOUNTING_STATUSES
    assert out.accounting_journal_draft_id is not None

    movement = StockMovement.objects.get(id=out.movement_id)
    assert movement.accounting_journal_draft_id == out.accounting_journal_draft_id

    ev = (
        OutboxEvent.objects.filter(source_module="INVENTORY", event_type="InventoryAdjusted")
        .order_by("-id")
        .first()
    )
    assert ev is not None
    data = ev.payload.get("data", {})
    assert data.get("movement_type") == "ADJUST"
    assert data.get("accounting_status") == out.accounting_status


@pytest.mark.django_db
def test_inventory_transfer_propagates_accounting_link_to_both_movements():
    company, branch, user, request = _build_scope()
    wh_from = Warehouse.objects.create(company=company, branch=branch, name="A", code="A")
    wh_to = Warehouse.objects.create(company=company, branch=branch, name="B", code="B")
    item = InventoryItem.objects.create(company=company, sku=f"SKU-{uuid.uuid4().hex[:6]}", name="Gasolina")

    post_receive(
        request=request,
        actor=user,
        warehouse_id=wh_from.id,
        item_id=item.id,
        qty=Decimal("20.0000"),
        unit_cost=Decimal("3.000000"),
        idempotency_key=f"recv-{uuid.uuid4().hex}",
    )

    out = post_transfer(
        request=request,
        actor=user,
        from_warehouse_id=wh_from.id,
        to_warehouse_id=wh_to.id,
        item_id=item.id,
        qty=Decimal("5.0000"),
        idempotency_key=f"xfer-{uuid.uuid4().hex}",
    )

    assert out["accounting_status"] in _VALID_ACCOUNTING_STATUSES
    assert out["journal_draft_id"] is not None

    out_mov = StockMovement.objects.get(id=out["out_movement_id"])
    in_mov = StockMovement.objects.get(id=out["in_movement_id"])

    assert out_mov.accounting_status == in_mov.accounting_status
    assert out_mov.accounting_journal_draft_id == in_mov.accounting_journal_draft_id
    assert out_mov.accounting_journal_entry_id == in_mov.accounting_journal_entry_id
