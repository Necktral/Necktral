from __future__ import annotations

from decimal import Decimal
from typing import Any

from apps.iam.models import OrgUnit

from modulos.inventarios import services as inv_services

from .errors import SyncRejectError
from .registry import HandlerResult, register


def _require_int(payload: dict[str, Any], key: str) -> int:
    v = payload.get(key, None)
    if v is None:
        raise SyncRejectError("SYNC_SCHEMA_INVALID", {key: "required"})
    try:
        return int(v)
    except Exception:
        raise SyncRejectError("SYNC_SCHEMA_INVALID", {key: "invalid"})


def _require_decimal(payload: dict[str, Any], key: str) -> Decimal:
    v = payload.get(key, None)
    if v is None:
        raise SyncRejectError("SYNC_SCHEMA_INVALID", {key: "required"})
    try:
        return Decimal(str(v))
    except Exception:
        raise SyncRejectError("SYNC_SCHEMA_INVALID", {key: "invalid"})


def _optional_str(payload: dict[str, Any], key: str) -> str:
    v = payload.get(key, None)
    if v is None:
        return ""
    return str(v)


def _optional_bool(payload: dict[str, Any], key: str, default: bool = False) -> bool:
    v = payload.get(key, None)
    if v is None:
        return default
    return bool(v)


def _attach_scope_to_request(*, request, company_id: int, branch_id: int | None) -> None:
    company = OrgUnit.objects.filter(id=company_id, unit_type=OrgUnit.UnitType.COMPANY, is_active=True).first()
    if not company:
        raise SyncRejectError("SYNC_SCHEMA_INVALID", {"company_id": "unknown"})

    request.company = company

    if branch_id is None:
        request.branch = None
        return

    branch = OrgUnit.objects.filter(
        id=branch_id,
        unit_type=OrgUnit.UnitType.BRANCH,
        parent_id=company_id,
        is_active=True,
    ).first()
    if not branch:
        raise SyncRejectError("SYNC_SCHEMA_INVALID", {"branch_id": "unknown"})

    request.branch = branch


@register("INVENTORY_MOVEMENT_RECEIVE")
def handle_inventory_receive(ctx: dict[str, Any], payload: dict[str, Any]) -> HandlerResult:
    request = ctx["request"]
    company_id = int(ctx["company_id"])
    branch_id = ctx.get("branch_id")
    if branch_id is None:
        raise SyncRejectError("SYNC_SCHEMA_INVALID", {"branch_id": "required"})

    _attach_scope_to_request(request=request, company_id=company_id, branch_id=int(branch_id))

    warehouse_id = _require_int(payload, "warehouse_id")
    item_id = _require_int(payload, "item_id")
    qty = _require_decimal(payload, "qty")
    unit_cost = _require_decimal(payload, "unit_cost")

    note = _optional_str(payload, "note")
    idempotency_key = _optional_str(payload, "idempotency_key") or str(ctx["command_id"])

    try:
        res = inv_services.post_receive(
            request=request,
            actor=None,
            warehouse_id=warehouse_id,
            item_id=item_id,
            qty=qty,
            unit_cost=unit_cost,
            idempotency_key=idempotency_key,
            note=note,
        )
    except ValueError as e:
        raise SyncRejectError("SYNC_SCHEMA_INVALID", {"detail": str(e)})

    return {
        "refs": {
            "movement_id": res.movement_id,
            "qty_on_hand": str(res.qty_on_hand),
            "avg_cost": str(res.avg_cost),
        }
    }


@register("INVENTORY_MOVEMENT_ISSUE")
def handle_inventory_issue(ctx: dict[str, Any], payload: dict[str, Any]) -> HandlerResult:
    request = ctx["request"]
    company_id = int(ctx["company_id"])
    branch_id = ctx.get("branch_id")
    if branch_id is None:
        raise SyncRejectError("SYNC_SCHEMA_INVALID", {"branch_id": "required"})

    _attach_scope_to_request(request=request, company_id=company_id, branch_id=int(branch_id))

    warehouse_id = _require_int(payload, "warehouse_id")
    item_id = _require_int(payload, "item_id")
    qty = _require_decimal(payload, "qty")
    allow_negative = _optional_bool(payload, "allow_negative", False)

    note = _optional_str(payload, "note")
    idempotency_key = _optional_str(payload, "idempotency_key") or str(ctx["command_id"])

    try:
        res = inv_services.post_issue(
            request=request,
            actor=None,
            warehouse_id=warehouse_id,
            item_id=item_id,
            qty=qty,
            allow_negative=allow_negative,
            idempotency_key=idempotency_key,
            note=note,
        )
    except ValueError as e:
        raise SyncRejectError("SYNC_SCHEMA_INVALID", {"detail": str(e)})

    return {
        "refs": {
            "movement_id": res.movement_id,
            "qty_on_hand": str(res.qty_on_hand),
            "avg_cost": str(res.avg_cost),
        }
    }


@register("INVENTORY_MOVEMENT_ADJUST")
def handle_inventory_adjust(ctx: dict[str, Any], payload: dict[str, Any]) -> HandlerResult:
    request = ctx["request"]
    company_id = int(ctx["company_id"])
    branch_id = ctx.get("branch_id")
    if branch_id is None:
        raise SyncRejectError("SYNC_SCHEMA_INVALID", {"branch_id": "required"})

    _attach_scope_to_request(request=request, company_id=company_id, branch_id=int(branch_id))

    warehouse_id = _require_int(payload, "warehouse_id")
    item_id = _require_int(payload, "item_id")
    new_qty_on_hand = _require_decimal(payload, "new_qty_on_hand")

    note = _optional_str(payload, "note")
    idempotency_key = _optional_str(payload, "idempotency_key") or str(ctx["command_id"])

    try:
        res = inv_services.post_adjust(
            request=request,
            actor=None,
            warehouse_id=warehouse_id,
            item_id=item_id,
            new_qty_on_hand=new_qty_on_hand,
            idempotency_key=idempotency_key,
            note=note,
        )
    except ValueError as e:
        raise SyncRejectError("SYNC_SCHEMA_INVALID", {"detail": str(e)})

    return {
        "refs": {
            "movement_id": res.movement_id,
            "qty_on_hand": str(res.qty_on_hand),
            "avg_cost": str(res.avg_cost),
        }
    }


@register("INVENTORY_TRANSFER")
def handle_inventory_transfer(ctx: dict[str, Any], payload: dict[str, Any]) -> HandlerResult:
    request = ctx["request"]
    company_id = int(ctx["company_id"])
    branch_id = ctx.get("branch_id")
    if branch_id is None:
        raise SyncRejectError("SYNC_SCHEMA_INVALID", {"branch_id": "required"})

    _attach_scope_to_request(request=request, company_id=company_id, branch_id=int(branch_id))

    from_warehouse_id = _require_int(payload, "from_warehouse_id")
    to_warehouse_id = _require_int(payload, "to_warehouse_id")
    item_id = _require_int(payload, "item_id")
    qty = _require_decimal(payload, "qty")

    note = _optional_str(payload, "note")
    idempotency_key = _optional_str(payload, "idempotency_key") or str(ctx["command_id"])

    try:
        res = inv_services.post_transfer(
            request=request,
            actor=None,
            from_warehouse_id=from_warehouse_id,
            to_warehouse_id=to_warehouse_id,
            item_id=item_id,
            qty=qty,
            idempotency_key=idempotency_key,
            note=note,
        )
    except ValueError as e:
        raise SyncRejectError("SYNC_SCHEMA_INVALID", {"detail": str(e)})

    return {
        "refs": {
            "transfer_out_movement_id": res["out_movement_id"],
            "transfer_in_movement_id": res["in_movement_id"],
            "avg_cost": res.get("avg_cost"),
        }
    }
