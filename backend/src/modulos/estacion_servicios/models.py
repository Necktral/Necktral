from __future__ import annotations

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone


class FuelProduct(models.TextChoices):
    DIESEL = "DIESEL", "Diesel"
    GASOLINE = "GASOLINE", "Gasolina"


class FuelVolumeUOM(models.TextChoices):
    LITER = "LITER", "Litro"
    # Contrato: "GALLON" se interpreta como galón US.
    GALLON = "GALLON", "Galón (US)"
    # Legacy: se acepta/normaliza a GALLON.
    GALLON_US = "GALLON_US", "Galón (US)"


# Backwards-compat interno: el código previo importaba FuelVolumeUoM.
FuelVolumeUoM = FuelVolumeUOM


class FuelPriceUOM(models.TextChoices):
    PER_LITER = "PER_LITER", "Precio/Litro"
    # Contrato: "PER_GALLON" se interpreta como precio por galón US.
    PER_GALLON = "PER_GALLON", "Precio/Galón (US)"
    # Legacy: se acepta/normaliza a PER_GALLON.
    PER_GALLON_US = "PER_GALLON_US", "Precio/Galón (US)"


GALLON_US_TO_LITER = Decimal("3.785411784")
GALLON_TO_LITER = GALLON_US_TO_LITER


class FuelShiftStatus(models.TextChoices):
    OPEN = "OPEN", "Abierto"
    CLOSED = "CLOSED", "Cerrado"


class FuelSaleStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Activa"
    CANCELLED = "CANCELLED", "Anulada"


class FuelSaleType(models.TextChoices):
    INTERNAL = "INTERNAL", "Consumo interno"
    PUBLIC = "PUBLIC", "Venta al público"
    EMPLOYEE = "EMPLOYEE", "Empleado (crédito/abonos)"


class FuelPaymentMethod(models.TextChoices):
    CASH = "CASH", "Efectivo"
    TRANSFER = "TRANSFER", "Transferencia"
    CREDIT = "CREDIT", "Crédito"


class FuelShift(models.Model):
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="fuel_shifts_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="fuel_shifts_branch")

    status = models.CharField(max_length=16, choices=FuelShiftStatus.choices, default=FuelShiftStatus.OPEN)

    opened_at = models.DateTimeField(default=timezone.now)
    opened_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="fuel_shifts_opened")

    closed_at = models.DateTimeField(null=True, blank=True)
    closed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="fuel_shifts_closed"
    )

    note = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["company", "branch", "status", "opened_at"]),
        ]
        constraints = [
            # Un solo turno abierto por sucursal
            models.UniqueConstraint(
                fields=["branch"],
                condition=models.Q(status=FuelShiftStatus.OPEN),
                name="uniq_open_shift_per_branch",
            )
        ]


class FuelDispense(models.Model):
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="fuel_dispenses_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="fuel_dispenses_branch")
    shift = models.ForeignKey(FuelShift, on_delete=models.PROTECT, related_name="dispenses")

    occurred_at = models.DateTimeField(default=timezone.now)
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="fuel_dispenses")

    product = models.CharField(max_length=16, choices=FuelProduct.choices)

    liters = models.DecimalField(max_digits=12, decimal_places=4)  # canónico para reportes/cierres

    # Lo que el operador capturó (persistido): elimina ambigüedad operativa.
    volume_entered = models.DecimalField(max_digits=12, decimal_places=4)
    volume_uom = models.CharField(max_length=16, choices=FuelVolumeUOM.choices, default=FuelVolumeUOM.LITER)

    # Precio canónico: por litro (base contable/reporting).
    unit_price = models.DecimalField(max_digits=12, decimal_places=4)
    # Precio capturado por el operador + su unidad.
    unit_price_entered = models.DecimalField(max_digits=12, decimal_places=4)
    unit_price_uom = models.CharField(max_length=16, choices=FuelPriceUOM.choices, default=FuelPriceUOM.PER_LITER)

    # Monto principal (fuerte): lo capturado/operativo (entered).
    amount = models.DecimalField(max_digits=14, decimal_places=2)

    # Monto canónico (para cierres/conciliación) y delta por cuantización.
    amount_canonical = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    amount_delta = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))

    vehicle_plate = models.CharField(max_length=32, blank=True, default="")
    vehicle_ref = models.CharField(max_length=64, blank=True, default="")  # número interno, flota, lo que uses
    driver_name = models.CharField(max_length=120, blank=True, default="")

    pump_code = models.CharField(max_length=32, blank=True, default="")
    nozzle_code = models.CharField(max_length=32, blank=True, default="")
    meter_reading = models.DecimalField(max_digits=14, decimal_places=4, null=True, blank=True)

    external_ref = models.CharField(max_length=64, blank=True, default="")  # "pedido", "orden", "vale", tu correlativo
    note = models.CharField(max_length=255, blank=True, default="")

    class Meta:
        indexes = [
            models.Index(fields=["company", "branch", "occurred_at"]),
            models.Index(fields=["shift", "occurred_at"]),
            models.Index(fields=["product", "occurred_at"]),
        ]


class FuelSale(models.Model):
    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="fuel_sales_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="fuel_sales_branch")
    shift = models.ForeignKey(FuelShift, on_delete=models.PROTECT, related_name="sales")

    dispense = models.OneToOneField(FuelDispense, on_delete=models.PROTECT, related_name="sale")

    sale_type = models.CharField(max_length=16, choices=FuelSaleType.choices)
    payment_method = models.CharField(max_length=16, choices=FuelPaymentMethod.choices)

    # “party snapshot” mínimo (sin depender aún del módulo de clientes)
    customer_name = models.CharField(max_length=200, blank=True, default="")
    customer_ref = models.CharField(max_length=64, blank=True, default="")  # cédula, código cliente, interno, lo que uses

    total_amount = models.DecimalField(max_digits=14, decimal_places=2)

    status = models.CharField(max_length=16, choices=FuelSaleStatus.choices, default=FuelSaleStatus.ACTIVE)

    created_at = models.DateTimeField(default=timezone.now)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="fuel_sales_created")

    cancelled_at = models.DateTimeField(null=True, blank=True)
    cancelled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="fuel_sales_cancelled"
    )
    cancel_reason = models.CharField(max_length=255, blank=True, default="")

    is_fiscal = models.BooleanField(default=False)  # preparado para el futuro

    # Integración Fuel -> Billing -> Inventory
    billing_doc = models.ForeignKey(
        "facturacion.BillingDocument",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="fuel_sales",
    )
    inventory_movement = models.ForeignKey(
        "inventarios.StockMovement",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="fuel_sales",
    )
    inventory_reversal_movement = models.ForeignKey(
        "inventarios.StockMovement",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="fuel_sales_reversals",
    )

    class Meta:
        indexes = [
            models.Index(fields=["company", "branch", "created_at"]),
            models.Index(fields=["status", "created_at"]),
        ]


class FuelUoMPreference(models.Model):
    """Preferencias de unidades para Fuel (recordar selección).

    Decisión fuerte (v1):
    - Modelo unificado para defaults de volumen y precio.
    - Precedencia para resolver "effective":
      1) (company, branch, user, product)
      2) (company, branch, user, ALL)
      3) (company, branch, NULL, product)
      4) (company, branch, NULL, ALL)
      5) fallback hardcode: DIESEL => GALLON/PER_GALLON, GASOLINE => LITER/PER_LITER
    """

    company = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="fuel_uom_prefs_company")
    branch = models.ForeignKey("iam.OrgUnit", on_delete=models.PROTECT, related_name="fuel_uom_prefs_branch")
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="fuel_uom_prefs_unified",
    )

    # product="" significa "ALL".
    product = models.CharField(max_length=16, blank=True, default="")

    default_volume_uom = models.CharField(max_length=16, choices=FuelVolumeUOM.choices)
    default_price_uom = models.CharField(max_length=16, choices=FuelPriceUOM.choices)

    updated_at = models.DateTimeField(default=timezone.now)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="fuel_uom_prefs_updated",
    )

    class Meta:
        indexes = [
            models.Index(fields=["company", "branch", "user", "product"]),
            models.Index(fields=["company", "branch", "product"]),
        ]
        constraints = [
            # Un solo default de sucursal por product (incluye ALL="").
            models.UniqueConstraint(
                fields=["company", "branch", "product"],
                condition=models.Q(user__isnull=True),
                name="uq_fuel_uom_pref_branch_product",
            ),
            # Un solo override por usuario+sucursal por product.
            models.UniqueConstraint(
                fields=["company", "branch", "user", "product"],
                condition=models.Q(user__isnull=False),
                name="uq_fuel_uom_pref_user_branch_product",
            ),
        ]
