from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP

from django.db import transaction
from django.utils import timezone

from apps.audit.writer import write_event
from apps.iam.models import OrgUnit

from .models import InventoryItem, MovementType, StockBalance, StockMovement, Warehouse


QTY_Q = Decimal("0.0001")
COST_Q = Decimal("0.000001")


def _q_qty(x: Decimal) -> Decimal:
    return Decimal(x).quantize(QTY_Q, rounding=ROUND_HALF_UP)


def _q_cost(x: Decimal) -> Decimal:
    return Decimal(x).quantize(COST_Q, rounding=ROUND_HALF_UP)


def _require_branch(request) -> OrgUnit:
    branch = getattr(request, "branch", None)
    if not branch:
        raise ValueError("X-Branch-Id requerido")
    return branch


@dataclass(frozen=True)
class PostResult:
    movement_id: int
    qty_on_hand: Decimal
    avg_cost: Decimal


def create_item(*, request, company: OrgUnit, actor_user, sku: str, name: str, uom: str = "UNIT") -> InventoryItem:
    with transaction.atomic():
        item = InventoryItem.objects.create(company=company, sku=sku, name=name, uom=uom)

        write_event(
            request=request,
            module="INVENTORY",
            event_type="INVENTORY_ITEM_CREATED",
            reason_code="INVENTORY_OK",
            actor_user=actor_user,
            subject_type="INVENTORY_ITEM",
            subject_id=str(item.id),
            metadata={"sku": sku, "name": name, "uom": uom},
        )
        return item


def _get_or_create_balance_locked(*, company: OrgUnit, branch: OrgUnit, warehouse: Warehouse, item: InventoryItem) -> StockBalance:
    bal = (
        StockBalance.objects.select_for_update()
        .filter(company=company, branch=branch, warehouse=warehouse, item=item)
        .first()
    )
    if bal:
        return bal
    return StockBalance.objects.create(company=company, branch=branch, warehouse=warehouse, item=item)


def _get_warehouse_locked(*, company: OrgUnit, branch: OrgUnit, warehouse_id: int) -> Warehouse:
    try:
        return Warehouse.objects.select_for_update().get(id=warehouse_id, company=company, branch=branch)
    except Warehouse.DoesNotExist:
        raise ValueError("warehouse inválido")


def _get_item_or_error(*, company: OrgUnit, item_id: int) -> InventoryItem:
    try:
        return InventoryItem.objects.get(id=item_id, company=company)
    except InventoryItem.DoesNotExist:
        raise ValueError("item inválido")


def _idempotent_movement_existing(*, company: OrgUnit, idempotency_key: str) -> StockMovement | None:
    if not idempotency_key:
        return None
    return StockMovement.objects.filter(company=company, idempotency_key=idempotency_key).first()


def post_receive(
    *,
    request,
    actor,
    warehouse_id: int,
    item_id: int,
    qty: Decimal,
    unit_cost: Decimal,
    idempotency_key: str = "",
    note: str = "",
) -> PostResult:
    company: OrgUnit = request.company
    branch = _require_branch(request)

    qty = _q_qty(qty)
    unit_cost = _q_cost(unit_cost)
    if qty <= 0:
        raise ValueError("qty debe ser > 0")
    if unit_cost < 0:
        raise ValueError("unit_cost debe ser >= 0")

    with transaction.atomic():
        existing = _idempotent_movement_existing(company=company, idempotency_key=idempotency_key)
        if existing:
            bal = StockBalance.objects.filter(company=company, branch=branch, warehouse_id=warehouse_id, item_id=item_id).first()
            if not bal:
                return PostResult(movement_id=existing.id, qty_on_hand=Decimal("0.0000"), avg_cost=Decimal("0.000000"))
            return PostResult(movement_id=existing.id, qty_on_hand=bal.qty_on_hand, avg_cost=bal.avg_cost)

        warehouse = _get_warehouse_locked(company=company, branch=branch, warehouse_id=warehouse_id)
        item = _get_item_or_error(company=company, item_id=item_id)
        bal = _get_or_create_balance_locked(company=company, branch=branch, warehouse=warehouse, item=item)

        total_cost = _q_cost(qty * unit_cost)
        new_qty = _q_qty(bal.qty_on_hand + qty)
        if new_qty == 0:
            new_avg = Decimal("0.000000")
        else:
            new_avg = _q_cost(((bal.qty_on_hand * bal.avg_cost) + total_cost) / new_qty)

        mov = StockMovement.objects.create(
            company=company,
            branch=branch,
            warehouse=warehouse,
            item=item,
            movement_type=MovementType.RECEIVE,
            qty_delta=qty,
            unit_cost=unit_cost,
            total_cost=total_cost,
            note=note or "",
            idempotency_key=idempotency_key or "",
            created_by=getattr(actor, "pk", None) and actor,
        )

        bal.qty_on_hand = new_qty
        bal.avg_cost = new_avg
        bal.updated_at = timezone.now()
        bal.save(update_fields=["qty_on_hand", "avg_cost", "updated_at"])

        write_event(
            request=request,
            module="INVENTORY",
            event_type="INVENTORY_MOVEMENT_POSTED",
            reason_code="INVENTORY_OK",
            actor_user=actor,
            subject_type="INVENTORY_MOVEMENT",
            subject_id=str(mov.id),
            metadata={
                "movement_type": mov.movement_type,
                "warehouse_id": warehouse_id,
                "item_id": item_id,
                "qty": str(qty),
                "unit_cost": str(unit_cost),
                "total_cost": str(total_cost),
                "idempotency_key": idempotency_key,
            },
        )

        return PostResult(movement_id=mov.id, qty_on_hand=bal.qty_on_hand, avg_cost=bal.avg_cost)


def post_issue(
    *,
    request,
    actor,
    warehouse_id: int,
    item_id: int,
    qty: Decimal,
    allow_negative: bool = False,
    idempotency_key: str = "",
    note: str = "",
    source_module: str = "",
    source_type: str = "",
    source_id: str = "",
) -> PostResult:
    company: OrgUnit = request.company
    branch = _require_branch(request)

    qty = _q_qty(qty)
    if qty <= 0:
        raise ValueError("qty debe ser > 0")

    with transaction.atomic():
        existing = _idempotent_movement_existing(company=company, idempotency_key=idempotency_key)
        if existing:
            bal = StockBalance.objects.filter(company=company, branch=branch, warehouse_id=warehouse_id, item_id=item_id).first()
            if not bal:
                return PostResult(movement_id=existing.id, qty_on_hand=Decimal("0.0000"), avg_cost=Decimal("0.000000"))
            return PostResult(movement_id=existing.id, qty_on_hand=bal.qty_on_hand, avg_cost=bal.avg_cost)

        warehouse = _get_warehouse_locked(company=company, branch=branch, warehouse_id=warehouse_id)
        item = _get_item_or_error(company=company, item_id=item_id)
        bal = _get_or_create_balance_locked(company=company, branch=branch, warehouse=warehouse, item=item)

        if not allow_negative and bal.qty_on_hand < qty:
            raise ValueError("stock insuficiente")

        unit_cost = bal.avg_cost
        total_cost = _q_cost(qty * unit_cost)
        new_qty = _q_qty(bal.qty_on_hand - qty)
        new_avg = Decimal("0.000000") if new_qty == 0 else bal.avg_cost

        mov = StockMovement.objects.create(
            company=company,
            branch=branch,
            warehouse=warehouse,
            item=item,
            movement_type=MovementType.ISSUE,
            qty_delta=_q_qty(Decimal("0") - qty),
            unit_cost=unit_cost,
            total_cost=_q_cost(Decimal("0") - total_cost),
            source_module=source_module or "",
            source_type=source_type or "",
            source_id=source_id or "",
            note=note or "",
            idempotency_key=idempotency_key or "",
            created_by=getattr(actor, "pk", None) and actor,
        )

        bal.qty_on_hand = new_qty
        bal.avg_cost = new_avg
        bal.updated_at = timezone.now()
        bal.save(update_fields=["qty_on_hand", "avg_cost", "updated_at"])

        write_event(
            request=request,
            module="INVENTORY",
            event_type="INVENTORY_MOVEMENT_POSTED",
            reason_code="INVENTORY_OK",
            actor_user=actor,
            subject_type="INVENTORY_MOVEMENT",
            subject_id=str(mov.id),
            metadata={
                "movement_type": mov.movement_type,
                "warehouse_id": warehouse_id,
                "item_id": item_id,
                "qty": str(qty),
                "unit_cost": str(unit_cost),
                "total_cost": str(total_cost),
                "allow_negative": allow_negative,
                "idempotency_key": idempotency_key,
            },
        )

        return PostResult(movement_id=mov.id, qty_on_hand=bal.qty_on_hand, avg_cost=bal.avg_cost)


def post_adjust(
    *,
    request,
    actor,
    warehouse_id: int,
    item_id: int,
    new_qty_on_hand: Decimal,
    idempotency_key: str = "",
    note: str = "",
) -> PostResult:
    company: OrgUnit = request.company
    branch = _require_branch(request)

    new_qty_on_hand = _q_qty(new_qty_on_hand)

    with transaction.atomic():
        existing = _idempotent_movement_existing(company=company, idempotency_key=idempotency_key)
        if existing:
            bal = StockBalance.objects.filter(company=company, branch=branch, warehouse_id=warehouse_id, item_id=item_id).first()
            if not bal:
                return PostResult(movement_id=existing.id, qty_on_hand=Decimal("0.0000"), avg_cost=Decimal("0.000000"))
            return PostResult(movement_id=existing.id, qty_on_hand=bal.qty_on_hand, avg_cost=bal.avg_cost)

        warehouse = _get_warehouse_locked(company=company, branch=branch, warehouse_id=warehouse_id)
        item = _get_item_or_error(company=company, item_id=item_id)
        bal = _get_or_create_balance_locked(company=company, branch=branch, warehouse=warehouse, item=item)

        delta = _q_qty(new_qty_on_hand - bal.qty_on_hand)
        unit_cost = bal.avg_cost
        total_cost = _q_cost(delta * unit_cost)

        mov = StockMovement.objects.create(
            company=company,
            branch=branch,
            warehouse=warehouse,
            item=item,
            movement_type=MovementType.ADJUST,
            qty_delta=delta,
            unit_cost=unit_cost,
            total_cost=total_cost,
            note=note or "",
            idempotency_key=idempotency_key or "",
            created_by=getattr(actor, "pk", None) and actor,
        )

        bal.qty_on_hand = new_qty_on_hand
        bal.updated_at = timezone.now()
        bal.save(update_fields=["qty_on_hand", "updated_at"])

        write_event(
            request=request,
            module="INVENTORY",
            event_type="INVENTORY_ADJUSTMENT_POSTED",
            reason_code="INVENTORY_OK",
            actor_user=actor,
            subject_type="INVENTORY_MOVEMENT",
            subject_id=str(mov.id),
            metadata={
                "movement_type": mov.movement_type,
                "warehouse_id": warehouse_id,
                "item_id": item_id,
                "new_qty_on_hand": str(new_qty_on_hand),
                "delta": str(delta),
                "unit_cost": str(unit_cost),
                "idempotency_key": idempotency_key,
            },
        )

        return PostResult(movement_id=mov.id, qty_on_hand=bal.qty_on_hand, avg_cost=bal.avg_cost)


def post_transfer(
    *,
    request,
    actor,
    from_warehouse_id: int,
    to_warehouse_id: int,
    item_id: int,
    qty: Decimal,
    idempotency_key: str = "",
    note: str = "",
) -> dict:
    company: OrgUnit = request.company
    branch = _require_branch(request)

    qty = _q_qty(qty)
    if qty <= 0:
        raise ValueError("qty debe ser > 0")
    if from_warehouse_id == to_warehouse_id:
        raise ValueError("from_warehouse_id y to_warehouse_id deben ser distintos")

    with transaction.atomic():
        existing = _idempotent_movement_existing(company=company, idempotency_key=idempotency_key)
        if existing:
            return {"idempotent": True, "movement_id": existing.id}

        # Lock balances in deterministic order to avoid deadlocks
        wh_ids = sorted([from_warehouse_id, to_warehouse_id])
        wh_map = {
            w.id: w
            for w in Warehouse.objects.select_for_update().filter(id__in=wh_ids, company=company, branch=branch)
        }
        if from_warehouse_id not in wh_map or to_warehouse_id not in wh_map:
            raise ValueError("warehouse inválido")

        item = _get_item_or_error(company=company, item_id=item_id)
        from_wh = wh_map[from_warehouse_id]
        to_wh = wh_map[to_warehouse_id]

        from_bal = _get_or_create_balance_locked(company=company, branch=branch, warehouse=from_wh, item=item)
        to_bal = _get_or_create_balance_locked(company=company, branch=branch, warehouse=to_wh, item=item)

        if from_bal.qty_on_hand < qty:
            raise ValueError("stock insuficiente")

        unit_cost = from_bal.avg_cost
        total_cost = _q_cost(qty * unit_cost)

        out_mov = StockMovement.objects.create(
            company=company,
            branch=branch,
            warehouse=from_wh,
            item=item,
            movement_type=MovementType.TRANSFER_OUT,
            qty_delta=_q_qty(Decimal("0") - qty),
            unit_cost=unit_cost,
            total_cost=_q_cost(Decimal("0") - total_cost),
            note=note or "",
            idempotency_key=idempotency_key or "",
            created_by=getattr(actor, "pk", None) and actor,
        )
        in_mov = StockMovement.objects.create(
            company=company,
            branch=branch,
            warehouse=to_wh,
            item=item,
            movement_type=MovementType.TRANSFER_IN,
            qty_delta=qty,
            unit_cost=unit_cost,
            total_cost=total_cost,
            note=note or "",
            idempotency_key="",  # only one unique key per transfer
            created_by=getattr(actor, "pk", None) and actor,
        )

        from_bal.qty_on_hand = _q_qty(from_bal.qty_on_hand - qty)
        if from_bal.qty_on_hand == 0:
            from_bal.avg_cost = Decimal("0.000000")
        from_bal.updated_at = timezone.now()
        from_bal.save(update_fields=["qty_on_hand", "avg_cost", "updated_at"])

        to_bal.qty_on_hand = _q_qty(to_bal.qty_on_hand + qty)
        # avg_cost stays the same (weighted average is preserved on transfer at same cost)
        if to_bal.qty_on_hand == 0:
            to_bal.avg_cost = unit_cost
        to_bal.updated_at = timezone.now()
        to_bal.save(update_fields=["qty_on_hand", "avg_cost", "updated_at"])

        write_event(
            request=request,
            module="INVENTORY",
            event_type="INVENTORY_TRANSFER_POSTED",
            reason_code="INVENTORY_OK",
            actor_user=actor,
            subject_type="INVENTORY_TRANSFER",
            subject_id=str(out_mov.id),
            metadata={
                "from_warehouse_id": from_warehouse_id,
                "to_warehouse_id": to_warehouse_id,
                "item_id": item_id,
                "qty": str(qty),
                "unit_cost": str(unit_cost),
                "out_movement_id": out_mov.id,
                "in_movement_id": in_mov.id,
                "idempotency_key": idempotency_key,
            },
        )

        return {
            "out_movement_id": out_mov.id,
            "in_movement_id": in_mov.id,
            "from_qty_on_hand": str(from_bal.qty_on_hand),
            "to_qty_on_hand": str(to_bal.qty_on_hand),
            "avg_cost": str(unit_cost),
        }
