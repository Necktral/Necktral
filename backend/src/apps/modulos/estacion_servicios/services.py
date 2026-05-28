"""Servicios del módulo Fuel (precedente).

Precedente de dominio:
- liters es canónico (para cierres/reportes).
- volume_entered/volume_uom preservan exactamente lo ingresado (trazabilidad).
- unit_price es canónico por litro (base para totales/reporting).
- unit_price_entered/unit_price_uom preservan exactamente lo pactado/capturado (no discutir después).
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, date, time, timedelta
from uuid import uuid4

from django.db import IntegrityError, transaction
from django.utils import timezone
from django.db.models import Q, Sum, Count
from django.utils.dateparse import parse_datetime, parse_date

from rest_framework.exceptions import ValidationError

from apps.modulos.audit.writer import write_event
from apps.modulos.integration.services import publish_outbox_event
from apps.modulos.parties.models import Party

from apps.modulos.estacion_servicios.models import (
    FuelDispense,
    FuelSale,
    FuelSaleStatus,
    FuelShift,
    FuelShiftStatus,
    FuelPriceUOM,
    FuelVolumeUOM,
    GALLON_TO_LITER,
)


MONEY_Q = Decimal("0.01")
VOLUME_Q = Decimal("0.0001")
COMPENSATION_MAX_ATTEMPTS = 5
COMPENSATION_BACKOFF_MAX_MINUTES = 60


@dataclass(frozen=True)
class FuelCompensationCycleResult:
    attempted: int
    succeeded: int
    failed: int
    still_pending: int
    errors: list[dict[str, str]]


@dataclass(frozen=True)
class OpenShiftResult:
    shift: FuelShift
    duplicate: bool


class FuelConflictError(ValueError):
    """Conflicto de idempotencia en operaciones Fuel."""


@dataclass(frozen=True)
class FuelSaleCreateResult:
    sale: FuelSale
    idempotent: bool


def _fuel_inventory_sku(product: str) -> str:
    return f"FUEL-{str(product).upper()}"


def _fuel_inventory_name(product: str) -> str:
    return f"Fuel {str(product).title()}"


def _get_or_create_fuel_warehouse(*, company, branch):
    from apps.kernels.inventarios.models import Warehouse

    wh = Warehouse.objects.filter(company=company, branch=branch, code="FUEL").first()
    if wh:
        return wh
    try:
        return Warehouse.objects.create(company=company, branch=branch, name="Fuel", code="FUEL", is_active=True)
    except IntegrityError:
        # Carrera concurrente: si otro proceso lo creó, lo tomamos.
        wh2 = Warehouse.objects.filter(company=company, branch=branch, code="FUEL").first()
        if wh2:
            return wh2
        raise


def _get_or_create_fuel_item(*, request, company, actor_user, product: str):
    from apps.kernels.inventarios.models import InventoryItem
    from apps.kernels.inventarios.services import create_item

    sku = _fuel_inventory_sku(product)
    item = InventoryItem.objects.filter(company=company, sku=sku).first()
    if item:
        return item
    # Fuel siempre emite/consume en litros canónicos.
    return create_item(
        request=request,
        company=company,
        actor_user=actor_user,
        sku=sku,
        name=_fuel_inventory_name(product),
        uom="LITER",
    )


def _money(x: Decimal) -> Decimal:
    return x.quantize(MONEY_Q, rounding=ROUND_HALF_UP)


def _volume(x: Decimal) -> Decimal:
    return Decimal(x).quantize(VOLUME_Q, rounding=ROUND_HALF_UP)


def _next_compensation_retry_at(*, now: datetime, attempt: int):
    delay = min(2**max(1, int(attempt)), COMPENSATION_BACKOFF_MAX_MINUTES)
    return now + timedelta(minutes=delay)


def _ensure_flow_correlation_id(*, sale: FuelSale) -> str:
    current = str(sale.flow_correlation_id or "").strip()
    if current:
        return current
    corr = f"fuel-sale-{sale.id}-{uuid4().hex[:12]}"
    sale.flow_correlation_id = corr
    sale.save(update_fields=["flow_correlation_id"])
    return corr


def _fuel_outbox_payload(*, sale: FuelSale, reason: str = "", attempt: int | None = None, error: str = "") -> dict:
    payload = {
        "sale_id": int(sale.id),
        "status": str(sale.status),
        "flow_correlation_id": str(sale.flow_correlation_id or ""),
        "source_module": "FUEL",
        "source_type": "SALE",
        "source_id": str(sale.id),
        "billing_doc_id": sale.billing_doc_id,
        "inventory_movement_id": sale.inventory_movement_id,
        "inventory_reversal_movement_id": sale.inventory_reversal_movement_id,
        "customer_party_id": int(sale.customer_party_id) if sale.customer_party_id else None,
    }
    if reason:
        payload["reason"] = str(reason)
    if attempt is not None:
        payload["attempt"] = int(attempt)
    if error:
        payload["error"] = str(error)
    if sale.compensation_next_retry_at is not None:
        payload["compensation_next_retry_at"] = sale.compensation_next_retry_at.isoformat()
    return payload


def _publish_fuel_outbox_event(
    *,
    request=None,
    sale: FuelSale,
    event_type: str,
    actor_user=None,
    reason: str = "",
    attempt: int | None = None,
    error: str = "",
    causation_id: str = "",
):
    publish_outbox_event(
        request=request,
        source_module="FUEL",
        event_type=event_type,
        payload=_fuel_outbox_payload(sale=sale, reason=reason, attempt=attempt, error=error),
        actor_user=actor_user,
        company=sale.company,
        branch=sale.branch,
        correlation_id=str(sale.flow_correlation_id or ""),
        causation_id=causation_id or str(sale.flow_correlation_id or ""),
    )


def _to_liters(*, volume_entered: Decimal, volume_uom: str) -> Decimal:
    """Convierte el volumen ingresado a litros canónicos.

    Regla fuerte:
    - Toda persistencia/reporting usa litros (precisión 4 decimales).
    - Si la unidad no es soportada, se rechaza (evita datos inconsistentes).
    """
    v = _volume(volume_entered)
    if volume_uom == FuelVolumeUOM.LITER:
        return v
    if volume_uom == FuelVolumeUOM.GALLON:
        return _volume(v * GALLON_TO_LITER)
    raise ValidationError({"detail": "Unidad de volumen inválida."})


def _to_unit_price_per_liter(*, unit_price_entered: Decimal, unit_price_uom: str) -> Decimal:
    """Convierte el precio ingresado a precio canónico por litro.

    Regla fuerte:
    - Persistimos unit_price como "precio por litro".
    - Preservamos unit_price_entered + unit_price_uom como lo pactado/capturado.
    """
    p = _volume(unit_price_entered)
    if unit_price_uom == FuelPriceUOM.PER_LITER:
        return p
    if unit_price_uom == FuelPriceUOM.PER_GALLON:
        return _volume(p / GALLON_TO_LITER)
    if unit_price_uom == FuelPriceUOM.PER_GALLON_US:
        return _volume(p / GALLON_TO_LITER)
    raise ValidationError({"detail": "Unidad de precio inválida."})


def _require_branch(branch):
    if branch is None:
        raise ValidationError({"detail": "X-Branch-Id requerido para operación de estación."})
    return branch


def _dt_range_from_query(*, from_s: str | None, to_s: str | None) -> tuple[datetime | None, datetime | None]:
    """Parsea rangos de tiempo desde query params.

    Acepta:
    - ISO datetime (con o sin zona)
    - ISO date (YYYY-MM-DD) => inicio del día / fin del día
    """

    def _parse(v: str | None, *, is_end: bool) -> datetime | None:
        if not v:
            return None
        dt = parse_datetime(v)
        if dt is not None:
            if timezone.is_naive(dt):
                dt = timezone.make_aware(dt, timezone.get_current_timezone())
            return dt
        d = parse_date(v)
        if d is None:
            raise ValidationError({"detail": f"Fecha/hora inválida: {v}"})
        t = time.max if is_end else time.min
        dt2 = datetime.combine(d, t)
        return timezone.make_aware(dt2, timezone.get_current_timezone())

    return _parse(from_s, is_end=False), _parse(to_s, is_end=True)


def list_shifts(*, company, branch, status: str | None = None, from_s: str | None = None, to_s: str | None = None):
    branch = _require_branch(branch)
    qs = FuelShift.objects.filter(company=company, branch=branch)
    if status:
        qs = qs.filter(status=status)
    dt_from, dt_to = _dt_range_from_query(from_s=from_s, to_s=to_s)
    if dt_from is not None:
        qs = qs.filter(opened_at__gte=dt_from)
    if dt_to is not None:
        qs = qs.filter(opened_at__lte=dt_to)
    return qs.order_by("-opened_at", "-id")


def get_shift(*, company, branch, shift_id: int) -> FuelShift:
    branch = _require_branch(branch)
    return FuelShift.objects.get(pk=shift_id, company=company, branch=branch)


def list_dispenses(
    *,
    company,
    branch,
    shift_id: int | None = None,
    product: str | None = None,
    from_s: str | None = None,
    to_s: str | None = None,
):
    branch = _require_branch(branch)
    qs = FuelDispense.objects.filter(company=company, branch=branch)
    if shift_id is not None:
        qs = qs.filter(shift_id=shift_id)
    if product:
        qs = qs.filter(product=product)
    dt_from, dt_to = _dt_range_from_query(from_s=from_s, to_s=to_s)
    if dt_from is not None:
        qs = qs.filter(occurred_at__gte=dt_from)
    if dt_to is not None:
        qs = qs.filter(occurred_at__lte=dt_to)
    return qs.order_by("-occurred_at", "-id")


def get_dispense(*, company, branch, dispense_id: int) -> FuelDispense:
    branch = _require_branch(branch)
    return FuelDispense.objects.get(pk=dispense_id, company=company, branch=branch)


def list_sales(
    *,
    company,
    branch,
    shift_id: int | None = None,
    status: str | None = None,
    sale_type: str | None = None,
    payment_method: str | None = None,
    from_s: str | None = None,
    to_s: str | None = None,
):
    branch = _require_branch(branch)
    qs = FuelSale.objects.filter(company=company, branch=branch).select_related("dispense", "customer_party")
    if shift_id is not None:
        qs = qs.filter(shift_id=shift_id)
    if status:
        qs = qs.filter(status=status)
    if sale_type:
        qs = qs.filter(sale_type=sale_type)
    if payment_method:
        qs = qs.filter(payment_method=payment_method)
    dt_from, dt_to = _dt_range_from_query(from_s=from_s, to_s=to_s)
    if dt_from is not None:
        qs = qs.filter(created_at__gte=dt_from)
    if dt_to is not None:
        qs = qs.filter(created_at__lte=dt_to)
    return qs.order_by("-created_at", "-id")


def get_sale(*, company, branch, sale_id: int) -> FuelSale:
    branch = _require_branch(branch)
    return FuelSale.objects.select_related("dispense", "customer_party").get(pk=sale_id, company=company, branch=branch)


def _gallons_from_liters(liters: Decimal) -> Decimal:
    return _volume(Decimal(liters) / GALLON_TO_LITER)


def build_shift_close_report(*, company, branch, shift: FuelShift) -> dict:
    branch = _require_branch(branch)
    if shift.company_id != company.id or shift.branch_id != branch.id:
        raise ValidationError({"detail": "Shift fuera de scope."})

    disp_qs = FuelDispense.objects.filter(company=company, branch=branch, shift=shift)
    sale_qs = FuelSale.objects.filter(company=company, branch=branch, shift=shift)

    by_product = (
        disp_qs.values("product")
        .annotate(
            dispense_count=Count("id"),
            liters=Sum("liters"),
            amount=Sum("amount"),
            amount_canonical=Sum("amount_canonical"),
            amount_delta=Sum("amount_delta"),
        )
        .order_by("product")
    )

    totals_by_product = []
    for row in by_product:
        liters = row.get("liters") or Decimal("0")
        totals_by_product.append(
            {
                "key": row["product"],
                "dispense_count": int(row.get("dispense_count") or 0),
                "liters": f"{_volume(Decimal(liters)):.4f}",
                "gallons_equiv": f"{_gallons_from_liters(Decimal(liters)):.4f}",
                "amount": f"{_money(Decimal(row.get('amount') or 0)):.2f}",
                "amount_canonical": f"{_money(Decimal(row.get('amount_canonical') or 0)):.2f}",
                "amount_delta": f"{_money(Decimal(row.get('amount_delta') or 0)):.2f}",
            }
        )

    sales_active = sale_qs.filter(status=FuelSaleStatus.ACTIVE)
    sales_cancelled = sale_qs.filter(status=FuelSaleStatus.CANCELLED)

    sales_by_type = list(
        sales_active.values("sale_type").annotate(count=Count("id"), total=Sum("total_amount")).order_by("sale_type")
    )
    for row in sales_by_type:
        row["total"] = f"{_money(Decimal(row.get('total') or 0)):.2f}"

    sales_by_payment_method = list(
        sales_active.values("payment_method")
        .annotate(count=Count("id"), total=Sum("total_amount"))
        .order_by("payment_method")
    )
    for row in sales_by_payment_method:
        row["total"] = f"{_money(Decimal(row.get('total') or 0)):.2f}"

    amount_delta_abs_sum = disp_qs.aggregate(x=Sum("amount_delta"))
    alerts = {
        "cancelled_sales": int(sales_cancelled.count()),
        "amount_delta_sum": f"{_money(Decimal((amount_delta_abs_sum.get('x') or 0))):.2f}",
    }

    counts = {
        "dispenses": int(disp_qs.count()),
        "sales_active": int(sales_active.count()),
        "sales_cancelled": int(sales_cancelled.count()),
    }

    return {
        "shift": shift,
        "totals_by_product": totals_by_product,
        "sales_by_type": sales_by_type,
        "sales_by_payment_method": sales_by_payment_method,
        "counts": counts,
        "alerts": alerts,
    }


def build_daily_close_report(*, company, branch, report_date: date) -> dict:
    branch = _require_branch(branch)
    tz = timezone.get_current_timezone()
    start = timezone.make_aware(datetime.combine(report_date, time.min), tz)
    end = timezone.make_aware(datetime.combine(report_date, time.max), tz)

    disp_qs = FuelDispense.objects.filter(company=company, branch=branch, occurred_at__gte=start, occurred_at__lte=end)
    sale_qs = FuelSale.objects.filter(company=company, branch=branch, created_at__gte=start, created_at__lte=end)

    by_product = (
        disp_qs.values("product")
        .annotate(
            dispense_count=Count("id"),
            liters=Sum("liters"),
            amount=Sum("amount"),
            amount_canonical=Sum("amount_canonical"),
            amount_delta=Sum("amount_delta"),
        )
        .order_by("product")
    )

    totals_by_product = []
    for row in by_product:
        liters = row.get("liters") or Decimal("0")
        totals_by_product.append(
            {
                "key": row["product"],
                "dispense_count": int(row.get("dispense_count") or 0),
                "liters": f"{_volume(Decimal(liters)):.4f}",
                "gallons_equiv": f"{_gallons_from_liters(Decimal(liters)):.4f}",
                "amount": f"{_money(Decimal(row.get('amount') or 0)):.2f}",
                "amount_canonical": f"{_money(Decimal(row.get('amount_canonical') or 0)):.2f}",
                "amount_delta": f"{_money(Decimal(row.get('amount_delta') or 0)):.2f}",
            }
        )

    sales_active = sale_qs.filter(status=FuelSaleStatus.ACTIVE)
    sales_cancelled = sale_qs.filter(status=FuelSaleStatus.CANCELLED)

    sales_by_type = list(
        sales_active.values("sale_type").annotate(count=Count("id"), total=Sum("total_amount")).order_by("sale_type")
    )
    for row in sales_by_type:
        row["total"] = f"{_money(Decimal(row.get('total') or 0)):.2f}"

    sales_by_payment_method = list(
        sales_active.values("payment_method")
        .annotate(count=Count("id"), total=Sum("total_amount"))
        .order_by("payment_method")
    )
    for row in sales_by_payment_method:
        row["total"] = f"{_money(Decimal(row.get('total') or 0)):.2f}"

    amount_delta_sum = disp_qs.aggregate(x=Sum("amount_delta"))
    alerts = {
        "cancelled_sales": int(sales_cancelled.count()),
        "amount_delta_sum": f"{_money(Decimal((amount_delta_sum.get('x') or 0))):.2f}",
    }

    counts = {
        "dispenses": int(disp_qs.count()),
        "sales_active": int(sales_active.count()),
        "sales_cancelled": int(sales_cancelled.count()),
    }

    return {
        "date": report_date,
        "branch_id": branch.id,
        "totals_by_product": totals_by_product,
        "sales_by_type": sales_by_type,
        "sales_by_payment_method": sales_by_payment_method,
        "counts": counts,
        "alerts": alerts,
    }


@transaction.atomic
def open_shift(*, request=None, company, branch, actor_user, opened_at=None, note: str = "") -> OpenShiftResult:
    branch = _require_branch(branch)
    existing = (
        FuelShift.objects.select_for_update()
        .filter(company=company, branch=branch, status=FuelShiftStatus.OPEN)
        .order_by("-opened_at", "-id")
        .first()
    )
    if existing is not None:
        return OpenShiftResult(shift=existing, duplicate=True)

    try:
        # Aisla la inserción en savepoint para poder recuperar el turno abierto
        # fuera del bloque fallido cuando hay carrera concurrente.
        with transaction.atomic():
            shift = FuelShift.objects.create(
                company=company,
                branch=branch,
                opened_by=actor_user,
                opened_at=opened_at or timezone.now(),
                note=note or "",
                status=FuelShiftStatus.OPEN,
            )
    except IntegrityError:
        recovered = (
            FuelShift.objects.filter(company=company, branch=branch, status=FuelShiftStatus.OPEN)
            .order_by("-opened_at", "-id")
            .first()
        )
        if recovered is not None:
            return OpenShiftResult(shift=recovered, duplicate=True)
        raise ValidationError({"detail": "No se pudo abrir el turno en este momento. Intente nuevamente."})

    write_event(
        request=request,
        module="FUEL",
        event_type="FUEL_SHIFT_OPENED",
        reason_code="FUEL_OK",
        subject_type="FUEL_SHIFT",
        subject_id=str(shift.id),
        actor_user=actor_user,
        after_snapshot={"note": shift.note, "opened_at": shift.opened_at.isoformat()},
        metadata={"company_id": str(company.id), "branch_id": str(branch.id)},
    )
    return OpenShiftResult(shift=shift, duplicate=False)


@transaction.atomic
def close_shift(*, request=None, shift: FuelShift, actor_user, closed_at=None, note: str = "") -> FuelShift:
    if shift.status != FuelShiftStatus.OPEN:
        raise ValidationError({"detail": "Shift ya está cerrado."})

    shift.status = FuelShiftStatus.CLOSED
    shift.closed_by = actor_user
    shift.closed_at = closed_at or timezone.now()
    if note:
        shift.note = (shift.note + " | " + note).strip(" |")
    shift.save(update_fields=["status", "closed_by", "closed_at", "note"])

    write_event(
        request=request,
        module="FUEL",
        event_type="FUEL_SHIFT_CLOSED",
        reason_code="SHIFT_CLOSED",
        subject_type="FUEL_SHIFT",
        subject_id=str(shift.id),
        actor_user=actor_user,
        after_snapshot={"note": note, "closed_at": shift.closed_at.isoformat()},
        metadata={"company_id": str(shift.company_id), "branch_id": str(shift.branch_id)},
    )
    return shift


@transaction.atomic
def record_dispense(
    *,
    request=None,
    company,
    branch,
    shift: FuelShift,
    actor_user,
    occurred_at=None,
    product: str,
    volume_entered: Decimal,
    volume_uom: str,
    unit_price_entered: Decimal,
    unit_price_uom: str,
    vehicle_plate: str = "",
    vehicle_ref: str = "",
    driver_name: str = "",
    pump_code: str = "",
    nozzle_code: str = "",
    meter_reading=None,
    external_ref: str = "",
    note: str = "",
) -> FuelDispense:
    branch = _require_branch(branch)

    if shift.status != FuelShiftStatus.OPEN:
        raise ValidationError({"detail": "No se puede despachar: turno cerrado."})

    # Contrato de cálculo (sin ambigüedad):
    # - volume_entered_q + volume_uom: lo que el operador capturó.
    # - liters: canónico (4 decimales) para cierres/reportes.
    # - unit_price_per_liter: canónico (4 decimales) para cierres/reportes.
    # - amount (fuerte): monto operativo (entered) = volume_entered_q * unit_price_entered_q (dinero 2dp).
    # - amount_canonical: monto canónico = liters * unit_price_per_liter (dinero 2dp).
    # - amount_delta: drift por cuantización = amount - amount_canonical.
    volume_entered_q = _volume(volume_entered)
    liters = _to_liters(volume_entered=volume_entered_q, volume_uom=volume_uom)
    gallons_equiv = _volume(Decimal(liters) / GALLON_TO_LITER)

    unit_price_entered_q = _volume(unit_price_entered)
    unit_price_per_liter = _to_unit_price_per_liter(
        unit_price_entered=unit_price_entered_q,
        unit_price_uom=unit_price_uom,
    )

    amount_entered = _money(Decimal(volume_entered_q) * Decimal(unit_price_entered_q))
    amount_canonical = _money(Decimal(liters) * Decimal(unit_price_per_liter))
    amount_delta = _money(Decimal(amount_entered) - Decimal(amount_canonical))

    d = FuelDispense.objects.create(
        company=company,
        branch=branch,
        shift=shift,
        occurred_at=occurred_at or timezone.now(),
        recorded_by=actor_user,
        product=product,
        liters=liters,
        volume_entered=volume_entered_q,
        volume_uom=volume_uom,
        unit_price=unit_price_per_liter,
        unit_price_entered=unit_price_entered_q,
        unit_price_uom=unit_price_uom,
        amount=amount_entered,
        amount_canonical=amount_canonical,
        amount_delta=amount_delta,
        vehicle_plate=vehicle_plate or "",
        vehicle_ref=vehicle_ref or "",
        driver_name=driver_name or "",
        pump_code=pump_code or "",
        nozzle_code=nozzle_code or "",
        meter_reading=meter_reading,
        external_ref=external_ref or "",
        note=note or "",
    )

    write_event(
        request=request,
        module="FUEL",
        event_type="FUEL_DISPENSE_RECORDED",
        reason_code="FUEL_OK",
        subject_type="FUEL_DISPENSE",
        subject_id=str(d.id),
        actor_user=actor_user,
        after_snapshot={
            "shift_id": shift.id,
            "amount": str(amount_entered),
            "amount_canonical": str(amount_canonical),
            "amount_delta": str(amount_delta),
            "product": product,
            "liters": str(liters),
            "gallons_equiv": str(gallons_equiv),
            "volume_entered": str(volume_entered_q),
            "volume_uom": str(volume_uom),
            "unit_price_per_liter": str(unit_price_per_liter),
            "unit_price_per_gallon": str(_volume(Decimal(unit_price_per_liter) * GALLON_TO_LITER)),
            "unit_price_entered": str(unit_price_entered_q),
            "unit_price_uom": str(unit_price_uom),
        },
        metadata={"company_id": str(company.id), "branch_id": str(branch.id)},
    )
    return d

def _normalize_sale_idempotency_key(value: str | None) -> str:
    return str(value or "").strip()


def _idempotent_sale_existing(*, company, idempotency_key: str) -> FuelSale | None:
    if not idempotency_key:
        return None
    return (
        FuelSale.objects.select_for_update()
        .filter(company=company, idempotency_key=idempotency_key)
        .first()
    )


def _load_customer_party(*, customer_party_id: int | None, company) -> Party | None:
    if customer_party_id is None:
        return None
    try:
        customer_party_pk = int(customer_party_id)
    except (TypeError, ValueError) as exc:
        raise ValidationError({"customer_party_id": "customer_party_id inválido."}) from exc
    if customer_party_pk <= 0:
        raise ValidationError({"customer_party_id": "customer_party_id inválido."})

    customer_party = Party.objects.filter(id=customer_party_pk, company=company).first()
    if customer_party is None:
        raise ValidationError({"customer_party_id": "customer_party no existe en esta company."})
    return customer_party


def _assert_sale_idempotency_payload_matches(
    *,
    sale: FuelSale,
    branch,
    shift: FuelShift,
    dispense: FuelDispense,
    sale_type: str,
    payment_method: str,
    customer_name: str,
    customer_ref: str,
    customer_party_id: int | None,
    is_fiscal: bool,
) -> None:
    expected_customer_name = customer_name or ""
    expected_customer_ref = customer_ref or ""
    mismatches: list[str] = []

    comparisons = {
        "branch_id": (sale.branch_id, branch.id),
        "shift_id": (sale.shift_id, shift.id),
        "dispense_id": (sale.dispense_id, dispense.id),
        "sale_type": (str(sale.sale_type), str(sale_type)),
        "payment_method": (str(sale.payment_method), str(payment_method)),
        "customer_name": (sale.customer_name or "", expected_customer_name),
        "customer_ref": (sale.customer_ref or "", expected_customer_ref),
        "customer_party_id": (sale.customer_party_id, customer_party_id),
        "is_fiscal": (bool(sale.is_fiscal), bool(is_fiscal)),
    }
    for field, (actual, expected) in comparisons.items():
        if actual != expected:
            mismatches.append(field)

    if mismatches:
        raise FuelConflictError("Idempotency key reutilizada con payload distinto.")


@transaction.atomic
def create_sale_with_status(
    *,
    request=None,
    company,
    branch,
    shift: FuelShift,
    dispense: FuelDispense,
    actor_user,
    sale_type: str,
    payment_method: str,
    customer_name: str = "",
    customer_ref: str = "",
    customer_party_id: int | None = None,
    is_fiscal: bool = False,
    idempotency_key: str = "",
) -> FuelSaleCreateResult:
    branch = _require_branch(branch)
    normalized_idempotency_key = _normalize_sale_idempotency_key(idempotency_key)
    customer_party = _load_customer_party(customer_party_id=customer_party_id, company=company)
    normalized_customer_party_id = int(customer_party.id) if customer_party is not None else None

    existing = _idempotent_sale_existing(company=company, idempotency_key=normalized_idempotency_key)
    if existing is not None:
        _assert_sale_idempotency_payload_matches(
            sale=existing,
            branch=branch,
            shift=shift,
            dispense=dispense,
            sale_type=sale_type,
            payment_method=payment_method,
            customer_name=customer_name,
            customer_ref=customer_ref,
            customer_party_id=normalized_customer_party_id,
            is_fiscal=is_fiscal,
        )
        return FuelSaleCreateResult(sale=existing, idempotent=True)

    if shift.status != FuelShiftStatus.OPEN:
        raise ValidationError({"detail": "No se puede facturar: turno cerrado."})

    if dispense.shift_id != shift.id:
        raise ValidationError({"detail": "Dispense no pertenece a ese turno."})

    if hasattr(dispense, "sale"):
        raise ValidationError({"detail": "Este despacho ya tiene venta asociada."})

    sale_kwargs = {
        "company": company,
        "branch": branch,
        "shift": shift,
        "dispense": dispense,
        "sale_type": sale_type,
        "payment_method": payment_method,
        "idempotency_key": normalized_idempotency_key,
        "customer_name": customer_name or "",
        "customer_ref": customer_ref or "",
        "customer_party": customer_party,
        "total_amount": dispense.amount,
        "created_by": actor_user,
        "is_fiscal": bool(is_fiscal),
    }
    try:
        with transaction.atomic():
            sale = FuelSale.objects.create(**sale_kwargs)
    except IntegrityError:
        if not normalized_idempotency_key:
            raise
        existing = _idempotent_sale_existing(company=company, idempotency_key=normalized_idempotency_key)
        if existing is None:
            raise
        _assert_sale_idempotency_payload_matches(
            sale=existing,
            branch=branch,
            shift=shift,
            dispense=dispense,
            sale_type=sale_type,
            payment_method=payment_method,
            customer_name=customer_name,
            customer_ref=customer_ref,
            customer_party_id=normalized_customer_party_id,
            is_fiscal=is_fiscal,
        )
        return FuelSaleCreateResult(sale=existing, idempotent=True)

    sale.flow_correlation_id = f"fuel-sale-{sale.id}-{uuid4().hex[:12]}"
    sale.save(update_fields=["flow_correlation_id"])

    # Integración Fuel -> Billing -> Inventory (transaccional)
    # Decisión: no bloqueamos venta por stock (allow_negative=True) para no detener operación.
    from apps.kernels.inventarios.services import post_issue
    from apps.kernels.facturacion.services import create_draft, issue_doc
    from apps.kernels.facturacion.models import DocType

    warehouse = _get_or_create_fuel_warehouse(company=company, branch=branch)
    item = _get_or_create_fuel_item(request=request, company=company, actor_user=actor_user, product=dispense.product)

    inv_res = post_issue(
        request=request,
        actor=actor_user,
        warehouse_id=int(warehouse.id),
        item_id=int(item.id),
        qty=dispense.liters,
        allow_negative=True,
        idempotency_key=f"fuel:sale:{sale.id}:issue",
        note=f"Fuel sale {sale.id} ({dispense.product})",
        source_module="FUEL",
        source_type="SALE",
        source_id=str(sale.id),
        correlation_id=sale.flow_correlation_id,
        causation_id=f"{sale.flow_correlation_id}:inventory-issue",
    )

    bill_res = create_draft(
        request=request,
        actor=actor_user,
        doc_type=DocType.INVOICE,
        series="FUEL",
        currency="NIO",
        customer_name=sale.customer_name,
        customer_ref=sale.customer_ref,
        customer_party_id=sale.customer_party_id,
        is_fiscal=bool(sale.is_fiscal),
        lines=[
            {
                "description": f"Fuel {dispense.product}",
                "quantity": dispense.liters,
                "unit_price": dispense.unit_price,
                "tax_rate": Decimal("0.0000"),
                "inventory_item_id": int(item.id),
            }
        ],
        idempotency_key=f"fuel:sale:{sale.id}",
        payment_method=sale.payment_method,
        source_module="FUEL",
        source_type="SALE",
        source_id=str(sale.id),
        correlation_id=sale.flow_correlation_id,
        causation_id=f"{sale.flow_correlation_id}:billing-draft",
    )

    issue_doc(
        request=request,
        actor=actor_user,
        doc_id=bill_res.doc_id,
        apply_inventory=False,
        correlation_id=sale.flow_correlation_id,
        causation_id=f"{sale.flow_correlation_id}:billing-issue",
    )

    sale.billing_doc_id = int(bill_res.doc_id)
    sale.inventory_movement_id = int(inv_res.movement_id)
    sale.save(update_fields=["billing_doc", "inventory_movement"])

    write_event(
        request=request,
        module="FUEL",
        event_type="FUEL_SALE_CREATED",
        reason_code="FUEL_OK",
        subject_type="FUEL_SALE",
        subject_id=str(sale.id),
        actor_user=actor_user,
        after_snapshot={
            "dispense_id": dispense.id,
            "amount": str(sale.total_amount),
            "sale_type": sale_type,
            "payment_method": payment_method,
            "customer_party_id": int(sale.customer_party_id) if sale.customer_party_id else None,
            "billing_doc_id": sale.billing_doc_id,
            "inventory_movement_id": sale.inventory_movement_id,
            "flow_correlation_id": sale.flow_correlation_id,
        },
        metadata={"company_id": str(company.id), "branch_id": str(branch.id)},
    )
    _publish_fuel_outbox_event(
        request=request,
        sale=sale,
        event_type="FuelSaleCreated",
        actor_user=actor_user,
        causation_id=f"{sale.flow_correlation_id}:sale-created",
    )
    return FuelSaleCreateResult(sale=sale, idempotent=False)


def create_sale(
    *,
    request=None,
    company,
    branch,
    shift: FuelShift,
    dispense: FuelDispense,
    actor_user,
    sale_type: str,
    payment_method: str,
    customer_name: str = "",
    customer_ref: str = "",
    customer_party_id: int | None = None,
    is_fiscal: bool = False,
    idempotency_key: str = "",
) -> FuelSale:
    return create_sale_with_status(
        request=request,
        company=company,
        branch=branch,
        shift=shift,
        dispense=dispense,
        actor_user=actor_user,
        sale_type=sale_type,
        payment_method=payment_method,
        customer_name=customer_name,
        customer_ref=customer_ref,
        customer_party_id=customer_party_id,
        is_fiscal=is_fiscal,
        idempotency_key=idempotency_key,
    ).sale


def _attempt_sale_compensation(*, request=None, sale: FuelSale, actor_user, reason: str = "") -> FuelSale:
    from decimal import Decimal as _D
    effective_request = request
    if effective_request is None:
        class _FuelRequestShim:
            company: object
            branch: object
            data: dict[str, object]

            def __init__(self, *, company, branch) -> None:
                self.company = company
                self.branch = branch
                self.data = {}

        effective_request = _FuelRequestShim(company=sale.company, branch=sale.branch)

    now = timezone.now()
    corr = _ensure_flow_correlation_id(sale=sale)
    attempt = int(sale.compensation_attempts) + 1
    errors: list[str] = []

    if sale.billing_doc_id:
        try:
            from apps.kernels.facturacion.services import void_doc

            void_doc(
                request=effective_request,
                actor=actor_user,
                doc_id=int(sale.billing_doc_id),
                reason=reason or "VOID",
                correlation_id=corr,
                causation_id=f"{corr}:cancel:{attempt}:billing-void",
            )
        except Exception as exc:  # noqa: BLE001
            errors.append(f"billing_void:{exc}")

    if sale.inventory_movement_id and not sale.inventory_reversal_movement_id:
        try:
            from apps.kernels.inventarios.models import StockMovement
            from apps.kernels.inventarios.services import post_receive

            mov = StockMovement.objects.get(id=int(sale.inventory_movement_id))
            qty = _D("0") - _D(mov.qty_delta)

            rev = post_receive(
                request=effective_request,
                actor=actor_user,
                warehouse_id=int(mov.warehouse_id),
                item_id=int(mov.item_id),
                qty=qty,
                unit_cost=_D(mov.unit_cost),
                idempotency_key=f"fuel:sale:{sale.id}:reverse",
                note=f"Reverse fuel sale {sale.id}",
                source_module="FUEL",
                source_type="SALE_REVERSAL",
                source_id=str(sale.id),
                correlation_id=corr,
                causation_id=f"{corr}:cancel:{attempt}:inventory-reverse",
            )
            sale.inventory_reversal_movement_id = int(rev.movement_id)
        except Exception as exc:  # noqa: BLE001
            errors.append(f"inventory_reverse:{exc}")

    sale.compensation_attempts = int(attempt)
    sale.last_compensation_at = now
    if reason:
        sale.cancel_reason = str(reason)

    if errors:
        sale.compensation_last_error = "; ".join(errors)[:255]
        if attempt >= int(COMPENSATION_MAX_ATTEMPTS):
            sale.status = FuelSaleStatus.COMPENSATION_FAILED
            sale.compensation_next_retry_at = None
            sale.save(
                update_fields=[
                    "status",
                    "cancel_reason",
                    "compensation_attempts",
                    "compensation_last_error",
                    "compensation_next_retry_at",
                    "last_compensation_at",
                    "inventory_reversal_movement",
                ]
            )
            _publish_fuel_outbox_event(
                request=request,
                sale=sale,
                event_type="FuelSaleCompensationFailed",
                actor_user=actor_user,
                reason=sale.cancel_reason,
                attempt=attempt,
                error=sale.compensation_last_error,
                causation_id=f"{corr}:cancel:{attempt}:failed",
            )
            return sale

        sale.status = FuelSaleStatus.COMPENSATING
        sale.compensation_next_retry_at = _next_compensation_retry_at(now=now, attempt=attempt)
        sale.save(
            update_fields=[
                "status",
                "cancel_reason",
                "compensation_attempts",
                "compensation_last_error",
                "compensation_next_retry_at",
                "last_compensation_at",
                "inventory_reversal_movement",
            ]
        )
        _publish_fuel_outbox_event(
            request=request,
            sale=sale,
            event_type="FuelSaleCompensating",
            actor_user=actor_user,
            reason=sale.cancel_reason,
            attempt=attempt,
            error=sale.compensation_last_error,
            causation_id=f"{corr}:cancel:{attempt}:pending",
        )
        return sale

    sale.status = FuelSaleStatus.CANCELLED
    sale.cancelled_by = actor_user
    if sale.cancelled_at is None:
        sale.cancelled_at = now
    sale.compensation_last_error = ""
    sale.compensation_next_retry_at = None
    sale.save(
        update_fields=[
            "status",
            "cancelled_by",
            "cancelled_at",
            "cancel_reason",
            "compensation_attempts",
            "compensation_last_error",
            "compensation_next_retry_at",
            "last_compensation_at",
            "inventory_reversal_movement",
        ]
    )
    _publish_fuel_outbox_event(
        request=request,
        sale=sale,
        event_type="FuelSaleCancelled",
        actor_user=actor_user,
        reason=sale.cancel_reason,
        attempt=attempt,
        causation_id=f"{corr}:cancel:{attempt}:success",
    )
    if actor_user is not None or request is not None:
        write_event(
            request=request,
            module="FUEL",
            event_type="FUEL_SALE_VOIDED",
            reason_code="FUEL_OK",
            subject_type="FUEL_SALE",
            subject_id=str(sale.id),
            actor_user=actor_user,
            after_snapshot={"reason": sale.cancel_reason, "status": sale.status},
            metadata={"company_id": str(sale.company_id), "branch_id": str(sale.branch_id)},
        )
    return sale


@transaction.atomic
def cancel_sale(*, request=None, sale: FuelSale, actor_user, reason: str = "") -> FuelSale:
    if sale.status == FuelSaleStatus.CANCELLED:
        return sale
    if sale.status not in (
        FuelSaleStatus.ACTIVE,
        FuelSaleStatus.COMPENSATING,
        FuelSaleStatus.COMPENSATION_FAILED,
    ):
        raise ValidationError({"detail": "Estado de venta inválido para anulación."})

    corr = _ensure_flow_correlation_id(sale=sale)
    _publish_fuel_outbox_event(
        request=request,
        sale=sale,
        event_type="FuelSaleCancelRequested",
        actor_user=actor_user,
        reason=reason or sale.cancel_reason or "",
        attempt=int(sale.compensation_attempts) + 1,
        causation_id=f"{corr}:cancel-requested",
    )
    return _attempt_sale_compensation(
        request=request,
        sale=sale,
        actor_user=actor_user,
        reason=reason or sale.cancel_reason or "VOID",
    )


@transaction.atomic
def retry_sale_compensation(*, request=None, sale: FuelSale, actor_user, reason: str = "") -> FuelSale:
    if sale.status == FuelSaleStatus.CANCELLED:
        return sale
    if sale.status not in (FuelSaleStatus.COMPENSATING, FuelSaleStatus.COMPENSATION_FAILED):
        raise ValidationError({"detail": "La venta no está en estado reintentable."})
    corr = _ensure_flow_correlation_id(sale=sale)
    _publish_fuel_outbox_event(
        request=request,
        sale=sale,
        event_type="FuelSaleCompensationRetried",
        actor_user=actor_user,
        reason=reason or sale.cancel_reason or "",
        attempt=int(sale.compensation_attempts) + 1,
        causation_id=f"{corr}:retry-requested",
    )
    return _attempt_sale_compensation(
        request=request,
        sale=sale,
        actor_user=actor_user,
        reason=reason or sale.cancel_reason or "VOID",
    )


def run_fuel_compensation_cycle(
    *,
    company=None,
    branch=None,
    limit: int = 100,
    include_failed: bool = False,
    actor_user=None,
    now=None,
) -> FuelCompensationCycleResult:
    clock = now or timezone.now()
    limit_n = max(1, int(limit))

    due_filter = Q(status=FuelSaleStatus.COMPENSATING) & (
        Q(compensation_next_retry_at__isnull=True) | Q(compensation_next_retry_at__lte=clock)
    )
    if bool(include_failed):
        due_filter = due_filter | Q(status=FuelSaleStatus.COMPENSATION_FAILED)

    qs = FuelSale.objects.filter(due_filter)
    if company is not None:
        qs = qs.filter(company=company)
    if branch is not None:
        qs = qs.filter(branch=branch)

    sale_ids = list(qs.order_by("compensation_next_retry_at", "id").values_list("id", flat=True)[:limit_n])
    attempted = succeeded = failed = still_pending = 0
    errors: list[dict[str, str]] = []

    for sale_id in sale_ids:
        attempted += 1
        try:
            with transaction.atomic():
                sale = FuelSale.objects.select_for_update().get(id=int(sale_id))
                if sale.status not in (FuelSaleStatus.COMPENSATING, FuelSaleStatus.COMPENSATION_FAILED):
                    continue
                if (
                    sale.status == FuelSaleStatus.COMPENSATING
                    and sale.compensation_next_retry_at is not None
                    and sale.compensation_next_retry_at > clock
                ):
                    still_pending += 1
                    continue
                updated = retry_sale_compensation(
                    request=None,
                    sale=sale,
                    actor_user=actor_user,
                    reason=sale.cancel_reason or "",
                )
                if updated.status == FuelSaleStatus.CANCELLED:
                    succeeded += 1
                elif updated.status == FuelSaleStatus.COMPENSATING:
                    still_pending += 1
                else:
                    failed += 1
        except Exception as exc:  # noqa: BLE001
            failed += 1
            errors.append({"sale_id": str(sale_id), "error": str(exc)})

    return FuelCompensationCycleResult(
        attempted=int(attempted),
        succeeded=int(succeeded),
        failed=int(failed),
        still_pending=int(still_pending),
        errors=errors,
    )
