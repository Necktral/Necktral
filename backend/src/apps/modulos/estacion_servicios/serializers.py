"""Serializers del módulo Fuel (precedente).

Contrato de unidades (sin ambigüedad):
- Persistimos litros como unidad canónica (para reportes/cierres).
- Conservamos el valor ingresado (volume + volume_uom) para trazabilidad.
- Conservamos el precio ingresado (unit_price + unit_price_uom) y persistimos el canónico por litro.
- El input soporta legacy 'liters' + 'unit_price' (interpretado como PER_LITER) y el contrato nuevo.
"""

from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from rest_framework import serializers

from apps.modulos.estacion_servicios.models import (
    GALLON_TO_LITER,
    FuelDispense,
    FuelPaymentMethod,
    FuelPriceUOM,
    FuelProduct,
    FuelSale,
    FuelSaleType,
    FuelVolumeUOM,
    FuelShift,
)

from apps.modulos.org.models import BranchProfile, UserFuelUoMPreference


VOL_Q = Decimal("0.0001")


class ShiftOpenIn(serializers.Serializer):
    opened_at = serializers.DateTimeField(required=False)
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)


class ShiftOut(serializers.ModelSerializer):
    class Meta:
        model = FuelShift
        fields = ["id", "status", "opened_at", "closed_at", "note"]


class ShiftCloseIn(serializers.Serializer):
    closed_at = serializers.DateTimeField(required=False)
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)


class ShiftReadOut(serializers.ModelSerializer):
    opened_by_id = serializers.IntegerField(read_only=True)
    closed_by_id = serializers.IntegerField(read_only=True)
    branch_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = FuelShift
        fields = [
            "id",
            "status",
            "opened_at",
            "closed_at",
            "opened_by_id",
            "closed_by_id",
            "note",
            "branch_id",
        ]


class DispenseCreateIn(serializers.Serializer):
    """Entrada para registrar un despacho.

    Contrato:
    - Se acepta 'liters' (legacy) o 'volume' (nuevo), pero no ambos.
    - Contrato nuevo: volume_uom y unit_price_uom permiten cálculo sin ambigüedad.
    - Compatibilidad: se acepta alias 'uom' (histórico) y se mapea a volume_uom.
    - Se normaliza a 4 decimales para que el cálculo sea determinista.
    """
    shift_id = serializers.IntegerField()
    occurred_at = serializers.DateTimeField(required=False)

    product = serializers.ChoiceField(choices=FuelProduct.choices)

    # Legacy (litros implícitos)
    liters = serializers.DecimalField(max_digits=12, decimal_places=4, required=False, min_value=Decimal("0.0001"))

    # Nuevo (entrada explícita)
    volume = serializers.DecimalField(max_digits=12, decimal_places=4, required=False, min_value=Decimal("0.0001"))
    volume_uom = serializers.ChoiceField(choices=FuelVolumeUOM.choices, required=False)
    # Alias histórico (aceptado): "uom" => volume_uom
    uom = serializers.CharField(required=False)

    # unit_price (request) representa el precio ingresado por el operador.
    unit_price = serializers.DecimalField(max_digits=12, decimal_places=4)
    unit_price_uom = serializers.ChoiceField(choices=FuelPriceUOM.choices, required=False)

    vehicle_plate = serializers.CharField(required=False, allow_blank=True, max_length=32)
    vehicle_ref = serializers.CharField(required=False, allow_blank=True, max_length=64)
    driver_name = serializers.CharField(required=False, allow_blank=True, max_length=120)

    pump_code = serializers.CharField(required=False, allow_blank=True, max_length=32)
    nozzle_code = serializers.CharField(required=False, allow_blank=True, max_length=32)
    meter_reading = serializers.DecimalField(max_digits=14, decimal_places=4, required=False, allow_null=True)

    external_ref = serializers.CharField(required=False, allow_blank=True, max_length=64)
    note = serializers.CharField(required=False, allow_blank=True, max_length=255)

    def validate(self, attrs):
        liters = attrs.pop("liters", None)
        volume = attrs.get("volume")
        volume_uom = attrs.get("volume_uom")

        uom_alias = attrs.pop("uom", None)
        if volume_uom is None and uom_alias is not None:
            # Compatibilidad: aceptamos valores antiguos (GALLON_US) y los normalizamos al contrato actual (GALLON).
            if str(uom_alias) == "GALLON_US":
                volume_uom = FuelVolumeUOM.GALLON
            else:
                volume_uom = str(uom_alias)

        if liters is not None and volume is not None:
            raise serializers.ValidationError({"detail": "Enviar solo 'liters' o ('volume'+'uom'), no ambos."})

        # Normalizar volumen
        if volume is None:
            if liters is None:
                raise serializers.ValidationError({"detail": "Se requiere 'liters' (legacy) o 'volume' (nuevo)."})
            volume = liters
            volume_uom = FuelVolumeUOM.LITER

        if volume_uom is None:
            # Preferencia recordada (user > branch > fallback)
            req = self.context.get("request")
            if req is not None and getattr(req, "branch", None) is not None:
                branch = req.branch
                try:
                    bp = branch.branch_profile
                except BranchProfile.DoesNotExist:
                    bp = None
                branch_default = {
                    FuelProduct.GASOLINE: "LITER",
                    FuelProduct.DIESEL: "GALLON",
                }
                if isinstance(bp, BranchProfile):
                    branch_default[FuelProduct.GASOLINE] = bp.fuel_default_volume_uom_gasoline
                    branch_default[FuelProduct.DIESEL] = bp.fuel_default_volume_uom_diesel

                pref = UserFuelUoMPreference.objects.filter(user=req.user, branch=branch).first()
                if pref is not None:
                    if attrs.get("product") == FuelProduct.GASOLINE and pref.gasoline_volume_uom:
                        volume_uom = pref.gasoline_volume_uom
                    elif attrs.get("product") == FuelProduct.DIESEL and pref.diesel_volume_uom:
                        volume_uom = pref.diesel_volume_uom

                if volume_uom is None:
                    volume_uom = branch_default[attrs.get("product")]
            else:
                # Fallback sin request/context
                volume_uom = "GALLON" if attrs.get("product") == FuelProduct.DIESEL else "LITER"

        if volume_uom == FuelVolumeUOM.GALLON_US:
            # Si algún cliente aún manda el valor viejo, lo normalizamos.
            volume_uom = FuelVolumeUOM.GALLON

        attrs["volume"] = Decimal(volume).quantize(VOL_Q, rounding=ROUND_HALF_UP)
        attrs["volume_uom"] = volume_uom

        # Normalizar precio
        unit_price_entered = Decimal(attrs["unit_price"]).quantize(VOL_Q, rounding=ROUND_HALF_UP)
        unit_price_uom = attrs.get("unit_price_uom")
        if unit_price_uom is None:
            # Si no se declara, asumimos que el precio aplica a la unidad del volumen ingresado.
            unit_price_uom = FuelPriceUOM.PER_GALLON if volume_uom == FuelVolumeUOM.GALLON else FuelPriceUOM.PER_LITER

        if unit_price_uom == FuelPriceUOM.PER_GALLON_US:
            unit_price_uom = FuelPriceUOM.PER_GALLON

        attrs["unit_price_entered"] = unit_price_entered
        attrs["unit_price_uom"] = unit_price_uom
        return attrs


class DispenseOut(serializers.ModelSerializer):
    """Salida de un despacho.

    Precedente:
    - Siempre devolvemos litros y galones (derivado a 4 decimales).
    - unit_price es canónico por litro.
    - unit_price_per_gallon se deriva desde unit_price.
    - También devolvemos lo capturado: volume_entered + volume_uom, unit_price_entered + unit_price_uom.
    """
    gallons_equiv = serializers.SerializerMethodField()
    # Backwards-compat: nombre anterior
    gallons_us = serializers.SerializerMethodField()

    # Precios explícitos
    unit_price_per_liter = serializers.SerializerMethodField()
    unit_price_per_gallon = serializers.SerializerMethodField()

    # Backwards-compat: nombre anterior
    uom_entered = serializers.SerializerMethodField()

    def _gallons_equiv(self, obj: FuelDispense) -> str:
        # Siempre mostramos ambas unidades: litros (canónico) y galón US (derivado)
        if obj.liters is None:
            return "0.0000"
        g = (Decimal(obj.liters) / GALLON_TO_LITER).quantize(VOL_Q, rounding=ROUND_HALF_UP)
        return f"{g:.4f}"

    def get_gallons_equiv(self, obj: FuelDispense) -> str:
        return self._gallons_equiv(obj)

    def get_gallons_us(self, obj: FuelDispense) -> str:
        return self._gallons_equiv(obj)

    def get_uom_entered(self, obj: FuelDispense) -> str:
        return obj.volume_uom

    def get_unit_price_per_liter(self, obj: FuelDispense) -> str:
        if obj.unit_price is None:
            return "0.0000"
        p = Decimal(obj.unit_price).quantize(VOL_Q, rounding=ROUND_HALF_UP)
        return f"{p:.4f}"

    def get_unit_price_per_gallon(self, obj: FuelDispense) -> str:
        if obj.unit_price is None:
            return "0.0000"
        p = (Decimal(obj.unit_price) * GALLON_TO_LITER).quantize(VOL_Q, rounding=ROUND_HALF_UP)
        return f"{p:.4f}"

    class Meta:
        model = FuelDispense
        fields = [
            "id",
            "occurred_at",
            "product",
            "volume_entered",
            "volume_uom",
            "uom_entered",
            "liters",
            "gallons_equiv",
            "gallons_us",
            "unit_price",
            "unit_price_per_gallon",
            "unit_price_entered",
            "unit_price_uom",
            "unit_price_per_liter",
            "amount",
            "amount_canonical",
            "amount_delta",
            "vehicle_plate",
            "vehicle_ref",
            "driver_name",
            "pump_code",
            "nozzle_code",
            "meter_reading",
            "external_ref",
            "note",
        ]


class SaleCreateIn(serializers.Serializer):
    shift_id = serializers.IntegerField()
    dispense_id = serializers.IntegerField()

    sale_type = serializers.ChoiceField(choices=FuelSaleType.choices)
    payment_method = serializers.ChoiceField(choices=FuelPaymentMethod.choices)

    customer_name = serializers.CharField(required=False, allow_blank=True, max_length=200)
    customer_ref = serializers.CharField(required=False, allow_blank=True, max_length=64)
    customer_party_id = serializers.IntegerField(required=False, allow_null=True)
    idempotency_key = serializers.CharField(required=False, allow_blank=True, max_length=96)

    is_fiscal = serializers.BooleanField(required=False)

    def validate(self, attrs):
        customer_party_id = attrs.get("customer_party_id")
        if customer_party_id is not None and int(customer_party_id) <= 0:
            raise serializers.ValidationError("customer_party_id debe ser > 0")
        return attrs


class SaleCancelIn(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)


class SaleCompensateRetryIn(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, max_length=255)


class SaleOut(serializers.ModelSerializer):
    dispense = DispenseOut()

    billing_doc_id = serializers.IntegerField(read_only=True)
    inventory_movement_id = serializers.IntegerField(read_only=True)
    inventory_reversal_movement_id = serializers.IntegerField(read_only=True)
    compensation_pending = serializers.SerializerMethodField()
    customer_party_id = serializers.IntegerField(read_only=True)
    customer_party_display_name = serializers.SerializerMethodField()

    def get_compensation_pending(self, obj: FuelSale) -> bool:
        return str(obj.status) == "COMPENSATING"

    def get_customer_party_display_name(self, obj: FuelSale) -> str:
        customer_party = obj.customer_party
        return customer_party.display_name if customer_party is not None else ""

    class Meta:
        model = FuelSale
        fields = [
            "id",
            "status",
            "sale_type",
            "payment_method",
            "customer_name",
            "customer_ref",
            "customer_party_id",
            "customer_party_display_name",
            "total_amount",
            "is_fiscal",
            "created_at",
            "flow_correlation_id",
            "billing_doc_id",
            "inventory_movement_id",
            "inventory_reversal_movement_id",
            "compensation_pending",
            "compensation_attempts",
            "compensation_last_error",
            "compensation_next_retry_at",
            "last_compensation_at",
            "dispense",
            "cancelled_at",
            "cancel_reason",
        ]


class FuelReportLine(serializers.Serializer):
    """Línea genérica para totales del módulo Fuel.

    Nota: usamos strings para decimales porque DRF los serializa así en el resto del módulo.
    """

    key = serializers.CharField()
    dispense_count = serializers.IntegerField()
    liters = serializers.CharField()
    gallons_equiv = serializers.CharField()
    amount = serializers.CharField()
    amount_canonical = serializers.CharField()
    amount_delta = serializers.CharField()


class FuelShiftCloseReportOut(serializers.Serializer):
    shift = ShiftReadOut()
    totals_by_product = FuelReportLine(many=True)
    sales_by_type = serializers.ListField(child=serializers.DictField(), required=True)
    sales_by_payment_method = serializers.ListField(child=serializers.DictField(), required=True)
    counts = serializers.DictField()
    alerts = serializers.DictField()


class FuelDailyCloseReportOut(serializers.Serializer):
    date = serializers.DateField()
    branch_id = serializers.IntegerField()
    totals_by_product = FuelReportLine(many=True)
    sales_by_type = serializers.ListField(child=serializers.DictField(), required=True)
    sales_by_payment_method = serializers.ListField(child=serializers.DictField(), required=True)
    counts = serializers.DictField()
    alerts = serializers.DictField()
