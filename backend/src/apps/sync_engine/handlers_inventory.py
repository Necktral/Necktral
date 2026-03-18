from __future__ import annotations

from decimal import Decimal
from typing import Any

from apps.iam.models import OrgUnit

from modulos.inventarios import services as inv_services
from modulos.inventarios.models import MovementType, StockMovement

from .errors import SyncRejectError
from .registry import HandlerResult, register


CANONICAL_COMMANDS: dict[str, str] = {
    "INVENTORY_MOVEMENT_RECEIVE": "INVENTORY.MOVEMENT.RECEIVE",
    "INVENTORY.MOVEMENT.RECEIVE": "INVENTORY.MOVEMENT.RECEIVE",
    "INVENTORY_MOVEMENT_ISSUE": "INVENTORY.MOVEMENT.ISSUE",
    "INVENTORY.MOVEMENT.ISSUE": "INVENTORY.MOVEMENT.ISSUE",
    "INVENTORY_MOVEMENT_ADJUST": "INVENTORY.MOVEMENT.ADJUST",
    "INVENTORY.MOVEMENT.ADJUST": "INVENTORY.MOVEMENT.ADJUST",
    "INVENTORY_TRANSFER": "INVENTORY.TRANSFER",
    "INVENTORY.TRANSFER": "INVENTORY.TRANSFER",
}


def _require_int(payload: dict[str, Any], key: str) -> int:
    v = payload.get(key, None)
    if v is None:
        raise SyncRejectError("INVENTORY_SCHEMA_INVALID", {key: "required"})
    try:
        return int(v)
    except Exception:
        raise SyncRejectError("INVENTORY_SCHEMA_INVALID", {key: "invalid"})


def _require_decimal(payload: dict[str, Any], key: str) -> Decimal:
    v = payload.get(key, None)
    if v is None:
        raise SyncRejectError("INVENTORY_SCHEMA_INVALID", {key: "required"})
    try:
        return Decimal(str(v))
    except Exception:
        raise SyncRejectError("INVENTORY_SCHEMA_INVALID", {key: "invalid"})


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
        raise SyncRejectError("INVENTORY_INVALID_SCOPE", {"company_id": "unknown"})

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
        raise SyncRejectError("INVENTORY_INVALID_SCOPE", {"branch_id": "unknown"})

    request.branch = branch


def _map_inventory_error(err: Exception) -> SyncRejectError:
    msg = str(err).lower()
    if "stock insuficiente" in msg:
        return SyncRejectError("INVENTORY_INSUFFICIENT_STOCK", {"detail": str(err)})
    if "x-branch-id requerido" in msg:
        return SyncRejectError("INVENTORY_INVALID_SCOPE", {"detail": str(err)})
    if "warehouse inválido" in msg:
        return SyncRejectError("INVENTORY_INVALID_SCOPE", {"detail": str(err)})
    if "item inválido" in msg:
        return SyncRejectError("INVENTORY_INVALID_SCOPE", {"detail": str(err)})
    if "from_warehouse_id" in msg and "to_warehouse_id" in msg:
        return SyncRejectError("INVENTORY_SCHEMA_INVALID", {"detail": str(err)})
    if "qty debe ser" in msg or "unit_cost" in msg:
        return SyncRejectError("INVENTORY_SCHEMA_INVALID", {"detail": str(err)})
    return SyncRejectError("INVENTORY_SCHEMA_INVALID", {"detail": str(err)})


def _canonical_command_type(command_type: str) -> str:
    return CANONICAL_COMMANDS.get(command_type, command_type)


def _namespaced_idempotency_key(
    *, command_type: str, company_id: int, branch_id: int | None, raw_key: str
) -> str:
    if not raw_key:
        return ""
    canonical = _canonical_command_type(command_type)
    branch_value = "" if branch_id is None else str(branch_id)
    return f"{canonical}:{company_id}:{branch_value}:{raw_key}"


def _movement_matches(
    movement: StockMovement,
    *,
    movement_type: str,
    warehouse_id: int,
    item_id: int,
    qty_delta: Decimal | None = None,
    unit_cost: Decimal | None = None,
) -> bool:
    if movement.movement_type != movement_type:
        return False
    if movement.warehouse_id != warehouse_id:
        return False
    if movement.item_id != item_id:
        return False
    if qty_delta is not None and movement.qty_delta != qty_delta:
        return False
    if unit_cost is not None and movement.unit_cost != unit_cost:
        return False
    return True


def _ensure_idempotency_match(
    *,
    company_id: int,
    branch_id: int | None,
    idempotency_key: str,
    movement_type: str,
    warehouse_id: int,
    item_id: int,
    qty_delta: Decimal | None = None,
    unit_cost: Decimal | None = None,
) -> None:
    if not idempotency_key:
        return
    qs = StockMovement.objects.filter(company_id=company_id, idempotency_key=idempotency_key)
    if branch_id is not None:
        qs = qs.filter(branch_id=branch_id)
    existing = qs.first()
    if not existing:
        return
    if _movement_matches(
        existing,
        movement_type=movement_type,
        warehouse_id=warehouse_id,
        item_id=item_id,
        qty_delta=qty_delta,
        unit_cost=unit_cost,
    ):
        return
    raise SyncRejectError(
        "INVENTORY_IDEMPOTENCY_CONFLICT",
        {"idempotency_key": idempotency_key, "existing_movement_id": existing.id},
    )


@register("INVENTORY_MOVEMENT_RECEIVE")
def handle_inventory_receive(ctx: dict[str, Any], payload: dict[str, Any]) -> HandlerResult:
    request = ctx["request"]
    company_id = int(ctx["company_id"])
    branch_id = ctx.get("branch_id")
    if branch_id is None:
        raise SyncRejectError("INVENTORY_INVALID_SCOPE", {"branch_id": "required"})

    _attach_scope_to_request(request=request, company_id=company_id, branch_id=int(branch_id))

    warehouse_id = _require_int(payload, "warehouse_id")
    item_id = _require_int(payload, "item_id")
    qty = _require_decimal(payload, "qty")
    unit_cost = _require_decimal(payload, "unit_cost")

    note = _optional_str(payload, "note")
    explicit_idempotency = _optional_str(payload, "idempotency_key")
    scoped_idempotency = _namespaced_idempotency_key(
        command_type=str(ctx.get("command_type") or ""),
        company_id=company_id,
        branch_id=int(branch_id),
        raw_key=explicit_idempotency,
    )
    _ensure_idempotency_match(
        company_id=company_id,
        branch_id=int(branch_id),
        idempotency_key=scoped_idempotency,
        movement_type=MovementType.RECEIVE,
        warehouse_id=warehouse_id,
        item_id=item_id,
        qty_delta=inv_services._q_qty(qty),
        unit_cost=inv_services._q_cost(unit_cost),
    )
    idempotency_key = scoped_idempotency or str(ctx["command_id"])

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
        raise _map_inventory_error(e)

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
        raise SyncRejectError("INVENTORY_INVALID_SCOPE", {"branch_id": "required"})

    _attach_scope_to_request(request=request, company_id=company_id, branch_id=int(branch_id))

    warehouse_id = _require_int(payload, "warehouse_id")
    item_id = _require_int(payload, "item_id")
    qty = _require_decimal(payload, "qty")
    allow_negative = _optional_bool(payload, "allow_negative", False)

    note = _optional_str(payload, "note")
    explicit_idempotency = _optional_str(payload, "idempotency_key")
    scoped_idempotency = _namespaced_idempotency_key(
        command_type=str(ctx.get("command_type") or ""),
        company_id=company_id,
        branch_id=int(branch_id),
        raw_key=explicit_idempotency,
    )
    _ensure_idempotency_match(
        company_id=company_id,
        branch_id=int(branch_id),
        idempotency_key=scoped_idempotency,
        movement_type=MovementType.ISSUE,
        warehouse_id=warehouse_id,
        item_id=item_id,
        qty_delta=inv_services._q_qty(Decimal("0") - qty),
    )
    idempotency_key = scoped_idempotency or str(ctx["command_id"])

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
        raise _map_inventory_error(e)

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
        raise SyncRejectError("INVENTORY_INVALID_SCOPE", {"branch_id": "required"})

    _attach_scope_to_request(request=request, company_id=company_id, branch_id=int(branch_id))

    warehouse_id = _require_int(payload, "warehouse_id")
    item_id = _require_int(payload, "item_id")
    new_qty_on_hand = _require_decimal(payload, "new_qty_on_hand")

    note = _optional_str(payload, "note")
    explicit_idempotency = _optional_str(payload, "idempotency_key")
    scoped_idempotency = _namespaced_idempotency_key(
        command_type=str(ctx.get("command_type") or ""),
        company_id=company_id,
        branch_id=int(branch_id),
        raw_key=explicit_idempotency,
    )
    _ensure_idempotency_match(
        company_id=company_id,
        branch_id=int(branch_id),
        idempotency_key=scoped_idempotency,
        movement_type=MovementType.ADJUST,
        warehouse_id=warehouse_id,
        item_id=item_id,
    )
    idempotency_key = scoped_idempotency or str(ctx["command_id"])

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
        raise _map_inventory_error(e)

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
        raise SyncRejectError("INVENTORY_INVALID_SCOPE", {"branch_id": "required"})

    _attach_scope_to_request(request=request, company_id=company_id, branch_id=int(branch_id))

    from_warehouse_id = _require_int(payload, "from_warehouse_id")
    to_warehouse_id = _require_int(payload, "to_warehouse_id")
    item_id = _require_int(payload, "item_id")
    qty = _require_decimal(payload, "qty")

    note = _optional_str(payload, "note")
    explicit_idempotency = _optional_str(payload, "idempotency_key")
    scoped_idempotency = _namespaced_idempotency_key(
        command_type=str(ctx.get("command_type") or ""),
        company_id=company_id,
        branch_id=int(branch_id),
        raw_key=explicit_idempotency,
    )
    _ensure_idempotency_match(
        company_id=company_id,
        branch_id=int(branch_id),
        idempotency_key=scoped_idempotency,
        movement_type=MovementType.TRANSFER_OUT,
        warehouse_id=from_warehouse_id,
        item_id=item_id,
        qty_delta=inv_services._q_qty(Decimal("0") - qty),
    )
    idempotency_key = scoped_idempotency or str(ctx["command_id"])

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
        raise _map_inventory_error(e)

    if res.get("idempotent"):
        return {
            "refs": {
                "transfer_out_movement_id": res.get("movement_id"),
            }
        }

    return {
        "refs": {
            "transfer_out_movement_id": res["out_movement_id"],
            "transfer_in_movement_id": res["in_movement_id"],
            "avg_cost": res.get("avg_cost"),
        }
    }


@register("INVENTORY.MOVEMENT.RECEIVE")
def handle_inventory_receive_v2(ctx: dict[str, Any], payload: dict[str, Any]) -> HandlerResult:
    return handle_inventory_receive(ctx, payload)


@register("INVENTORY.MOVEMENT.ISSUE")
def handle_inventory_issue_v2(ctx: dict[str, Any], payload: dict[str, Any]) -> HandlerResult:
    return handle_inventory_issue(ctx, payload)


@register("INVENTORY.MOVEMENT.ADJUST")
def handle_inventory_adjust_v2(ctx: dict[str, Any], payload: dict[str, Any]) -> HandlerResult:
    return handle_inventory_adjust(ctx, payload)


@register("INVENTORY.TRANSFER")
def handle_inventory_transfer_v2(ctx: dict[str, Any], payload: dict[str, Any]) -> HandlerResult:
    return handle_inventory_transfer(ctx, payload)
