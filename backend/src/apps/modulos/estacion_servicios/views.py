from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import serializers
from rest_framework import status

from django.utils.dateparse import parse_date

from apps.modulos.common.permissions import rbac_permission

from apps.modulos.org.models import BranchProfile, UserFuelUoMPreference

from apps.modulos.estacion_servicios.models import FuelDispense, FuelSale, FuelShift
from apps.modulos.estacion_servicios.serializers import (
    DispenseCreateIn,
    DispenseOut,
    FuelDailyCloseReportOut,
    FuelShiftCloseReportOut,
    SaleCancelIn,
    SaleCompensateRetryIn,
    SaleCreateIn,
    SaleOut,
    ShiftCloseIn,
    ShiftOpenIn,
    ShiftReadOut,
    ShiftOut,
)
from apps.modulos.estacion_servicios.services import (
    FuelConflictError,
    build_daily_close_report,
    build_shift_close_report,
    cancel_sale,
    close_shift,
    create_sale_with_status,
    list_dispenses,
    list_sales,
    list_shifts,
    open_shift,
    record_dispense,
    retry_sale_compensation,
)


class FuelHealthView(APIView):
    authentication_classes = []
    permission_classes = []

    def get(self, request):
        return Response({"ok": True, "module": "fuel"})


class FuelShiftOpenView(APIView):
    permission_classes = [rbac_permission("fuel.shift.open")]

    def post(self, request):
        ser = ShiftOpenIn(data=request.data)
        ser.is_valid(raise_exception=True)

        result = open_shift(
            request=request,
            company=request.company,
            branch=request.branch,
            actor_user=request.user,
            opened_at=ser.validated_data.get("opened_at"),
            note=ser.validated_data.get("note", ""),
        )
        body = ShiftOut(result.shift).data
        if result.duplicate:
            return Response({**body, "idempotency_status": "DUPLICATE_PROCESSED"}, status=status.HTTP_200_OK)
        return Response(body, status=status.HTTP_201_CREATED)


class FuelShiftCloseView(APIView):
    permission_classes = [rbac_permission("fuel.shift.close")]

    def post(self, request, shift_id: int):
        ser = ShiftCloseIn(data=request.data)
        ser.is_valid(raise_exception=True)

        shift = get_object_or_404(FuelShift, pk=shift_id, company=request.company, branch=request.branch)

        shift = close_shift(
            request=request,
            shift=shift,
            actor_user=request.user,
            closed_at=ser.validated_data.get("closed_at"),
            note=ser.validated_data.get("note", ""),
        )
        return Response(ShiftOut(shift).data, status=200)


class FuelShiftListView(APIView):
    permission_classes = [rbac_permission("fuel.shift.read")]

    def get(self, request):
        if request.branch is None:
            return Response({"detail": "X-Branch-Id requerido."}, status=status.HTTP_400_BAD_REQUEST)

        qs = list_shifts(
            company=request.company,
            branch=request.branch,
            status=request.query_params.get("status"),
            from_s=request.query_params.get("from"),
            to_s=request.query_params.get("to"),
        )
        data = ShiftReadOut(qs, many=True).data
        return Response({"count": len(data), "results": data}, status=status.HTTP_200_OK)


class FuelShiftDetailView(APIView):
    permission_classes = [rbac_permission("fuel.shift.read")]

    def get(self, request, shift_id: int):
        if request.branch is None:
            return Response({"detail": "X-Branch-Id requerido."}, status=status.HTTP_400_BAD_REQUEST)

        shift = get_object_or_404(FuelShift, pk=shift_id, company=request.company, branch=request.branch)
        return Response(ShiftReadOut(shift).data, status=status.HTTP_200_OK)


class FuelDispenseCreateView(APIView):
    """GET list / POST create (misma ruta por compatibilidad)."""

    def get_permissions(self):
        if self.request.method == "GET":
            return [rbac_permission("fuel.dispense.read")()]
        if self.request.method == "POST":
            return [rbac_permission("fuel.dispense.create")()]
        return [rbac_permission("fuel.dispense.read")()]

    def get(self, request):
        if request.branch is None:
            return Response({"detail": "X-Branch-Id requerido."}, status=status.HTTP_400_BAD_REQUEST)

        shift_id = request.query_params.get("shift_id")
        product = request.query_params.get("product")

        qs = list_dispenses(
            company=request.company,
            branch=request.branch,
            shift_id=int(shift_id) if shift_id else None,
            product=product,
            from_s=request.query_params.get("from"),
            to_s=request.query_params.get("to"),
        )
        data = DispenseOut(qs, many=True).data
        return Response({"count": len(data), "results": data}, status=status.HTTP_200_OK)

    def post(self, request):
        ser = DispenseCreateIn(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)

        shift = get_object_or_404(
            FuelShift,
            pk=ser.validated_data["shift_id"],
            company=request.company,
            branch=request.branch,
        )

        # Contrato de despacho (sin ambigüedad):
        # - La API acepta legacy liters+unit_price (interpretado como LITER + PER_LITER).
        # - En el contrato nuevo: volume + volume_uom y unit_price + unit_price_uom.
        # - El service persiste litros (canónico) y precio por litro (canónico), y conserva los valores ingresados.
        dispense = record_dispense(
            request=request,
            company=request.company,
            branch=request.branch,
            shift=shift,
            actor_user=request.user,
            occurred_at=ser.validated_data.get("occurred_at"),
            product=ser.validated_data["product"],
            volume_entered=ser.validated_data["volume"],
            volume_uom=ser.validated_data["volume_uom"],
            unit_price_entered=ser.validated_data["unit_price_entered"],
            unit_price_uom=ser.validated_data["unit_price_uom"],
            vehicle_plate=ser.validated_data.get("vehicle_plate", ""),
            vehicle_ref=ser.validated_data.get("vehicle_ref", ""),
            driver_name=ser.validated_data.get("driver_name", ""),
            pump_code=ser.validated_data.get("pump_code", ""),
            nozzle_code=ser.validated_data.get("nozzle_code", ""),
            meter_reading=ser.validated_data.get("meter_reading"),
            external_ref=ser.validated_data.get("external_ref", ""),
            note=ser.validated_data.get("note", ""),
        )
        return Response(DispenseOut(dispense).data, status=201)


class FuelDispenseDetailView(APIView):
    permission_classes = [rbac_permission("fuel.dispense.read")]

    def get(self, request, dispense_id: int):
        if request.branch is None:
            return Response({"detail": "X-Branch-Id requerido."}, status=status.HTTP_400_BAD_REQUEST)

        dispense = get_object_or_404(FuelDispense, pk=dispense_id, company=request.company, branch=request.branch)
        return Response(DispenseOut(dispense).data, status=status.HTTP_200_OK)


class FuelSaleCreateView(APIView):
    """GET list / POST create (misma ruta por compatibilidad)."""

    def get_permissions(self):
        if self.request.method == "GET":
            return [rbac_permission("fuel.sale.read")()]
        if self.request.method == "POST":
            return [rbac_permission("fuel.sale.create")()]
        return [rbac_permission("fuel.sale.read")()]

    def get(self, request):
        if request.branch is None:
            return Response({"detail": "X-Branch-Id requerido."}, status=status.HTTP_400_BAD_REQUEST)

        shift_id = request.query_params.get("shift_id")

        qs = list_sales(
            company=request.company,
            branch=request.branch,
            shift_id=int(shift_id) if shift_id else None,
            status=request.query_params.get("status"),
            sale_type=request.query_params.get("sale_type"),
            payment_method=request.query_params.get("payment_method"),
            from_s=request.query_params.get("from"),
            to_s=request.query_params.get("to"),
        )
        data = SaleOut(qs, many=True).data
        return Response({"count": len(data), "results": data}, status=status.HTTP_200_OK)

    def post(self, request):
        ser = SaleCreateIn(data=request.data)
        ser.is_valid(raise_exception=True)

        shift = get_object_or_404(
            FuelShift,
            pk=ser.validated_data["shift_id"],
            company=request.company,
            branch=request.branch,
        )

        dispense = get_object_or_404(
            FuelDispense,
            pk=ser.validated_data["dispense_id"],
            company=request.company,
            branch=request.branch,
        )

        try:
            result = create_sale_with_status(
                request=request,
                company=request.company,
                branch=request.branch,
                shift=shift,
                dispense=dispense,
                actor_user=request.user,
                sale_type=ser.validated_data["sale_type"],
                payment_method=ser.validated_data["payment_method"],
                customer_name=ser.validated_data.get("customer_name", ""),
                customer_ref=ser.validated_data.get("customer_ref", ""),
                customer_party_id=ser.validated_data.get("customer_party_id"),
                is_fiscal=ser.validated_data.get("is_fiscal", False),
                idempotency_key=ser.validated_data.get("idempotency_key", ""),
            )
        except FuelConflictError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_409_CONFLICT)

        sale = FuelSale.objects.select_related("dispense", "customer_party").get(pk=result.sale.id)
        response_status = status.HTTP_200_OK if result.idempotent else status.HTTP_201_CREATED
        return Response(SaleOut(sale).data, status=response_status)


class FuelSaleDetailView(APIView):
    permission_classes = [rbac_permission("fuel.sale.read")]

    def get(self, request, sale_id: int):
        if request.branch is None:
            return Response({"detail": "X-Branch-Id requerido."}, status=status.HTTP_400_BAD_REQUEST)

        sale = get_object_or_404(
            FuelSale.objects.select_related("dispense", "customer_party"),
            pk=sale_id,
            company=request.company,
            branch=request.branch,
        )
        return Response(SaleOut(sale).data, status=status.HTTP_200_OK)


class FuelSaleCancelView(APIView):
    permission_classes = [rbac_permission("fuel.sale.void")]

    def post(self, request, sale_id: int):
        ser = SaleCancelIn(data=request.data)
        ser.is_valid(raise_exception=True)

        sale = get_object_or_404(FuelSale, pk=sale_id, company=request.company, branch=request.branch)

        sale = cancel_sale(
            request=request,
            sale=sale,
            actor_user=request.user,
            reason=ser.validated_data.get("reason", ""),
        )

        sale = FuelSale.objects.select_related("dispense", "customer_party").get(pk=sale.id)
        return Response(SaleOut(sale).data, status=200)


class FuelSaleCompensateRetryView(APIView):
    permission_classes = [rbac_permission("fuel.sale.void")]

    def post(self, request, sale_id: int):
        ser = SaleCompensateRetryIn(data=request.data)
        ser.is_valid(raise_exception=True)

        sale = get_object_or_404(FuelSale, pk=sale_id, company=request.company, branch=request.branch)
        sale = retry_sale_compensation(
            request=request,
            sale=sale,
            actor_user=request.user,
            reason=ser.validated_data.get("reason", ""),
        )
        sale = FuelSale.objects.select_related("dispense", "customer_party").get(pk=sale.id)
        return Response(SaleOut(sale).data, status=200)


class FuelShiftCloseReportView(APIView):
    permission_classes = [rbac_permission("fuel.reports.view")]

    def get(self, request, shift_id: int):
        if request.branch is None:
            return Response({"detail": "X-Branch-Id requerido."}, status=status.HTTP_400_BAD_REQUEST)

        shift = get_object_or_404(FuelShift, pk=shift_id, company=request.company, branch=request.branch)
        payload = build_shift_close_report(company=request.company, branch=request.branch, shift=shift)

        out = {
            "shift": ShiftReadOut(payload["shift"]).data,
            "totals_by_product": payload["totals_by_product"],
            "sales_by_type": payload["sales_by_type"],
            "sales_by_payment_method": payload["sales_by_payment_method"],
            "counts": payload["counts"],
            "alerts": payload["alerts"],
        }
        return Response(FuelShiftCloseReportOut(out).data, status=status.HTTP_200_OK)


class FuelDailyCloseReportView(APIView):
    permission_classes = [rbac_permission("fuel.reports.view")]

    def get(self, request):
        if request.branch is None:
            return Response({"detail": "X-Branch-Id requerido."}, status=status.HTTP_400_BAD_REQUEST)

        date_s = request.query_params.get("date")
        if not date_s:
            return Response({"detail": "Query param 'date' requerido (YYYY-MM-DD)."}, status=status.HTTP_400_BAD_REQUEST)

        d = parse_date(date_s)
        if d is None:
            return Response({"detail": "Fecha inválida. Use YYYY-MM-DD."}, status=status.HTTP_400_BAD_REQUEST)

        payload = build_daily_close_report(company=request.company, branch=request.branch, report_date=d)
        return Response(FuelDailyCloseReportOut(payload).data, status=status.HTTP_200_OK)


class FuelUoMPreferencesIn(serializers.Serializer):
    """Entrada para guardar preferencia de UoM de Fuel.

    Contrato:
    - Los campos son opcionales (NULL => usa default de sucursal).
    - Valores válidos: LITER o GALLON.
    """

    gasoline_volume_uom = serializers.ChoiceField(choices=["LITER", "GALLON"], required=False)
    diesel_volume_uom = serializers.ChoiceField(choices=["LITER", "GALLON"], required=False)


class FuelUoMPreferencesView(APIView):
    """Preferencias de UoM para Fuel.

    Precedente:
    - Esto existe para que el UI "recuerde selección" por usuario y/o por sucursal.
    - El backend sigue siendo determinista: el request nuevo puede traer volume_uom explícito.
    - Si el request no lo trae, el serializer puede tomar estos defaults para mejorar UX.
    """

    permission_classes = [rbac_permission("fuel.uom_preferences.manage")]

    @staticmethod
    def _get_branch_defaults(branch) -> dict:
        # Defaults del sistema si aún no existe BranchProfile (por seguridad).
        defaults = {
            "gasoline_volume_uom": "LITER",
            "diesel_volume_uom": "GALLON",
        }
        try:
            bp = branch.branch_profile
        except BranchProfile.DoesNotExist:
            bp = None

        if bp is not None:
            defaults["gasoline_volume_uom"] = bp.fuel_default_volume_uom_gasoline
            defaults["diesel_volume_uom"] = bp.fuel_default_volume_uom_diesel
        return defaults

    def get(self, request):
        branch = request.branch
        if branch is None:
            return Response({"detail": "X-Branch-Id requerido."}, status=400)

        branch_defaults = self._get_branch_defaults(branch)
        pref = UserFuelUoMPreference.objects.filter(user=request.user, branch=branch).first()

        gasoline = (pref.gasoline_volume_uom if pref and pref.gasoline_volume_uom else branch_defaults["gasoline_volume_uom"])
        diesel = (pref.diesel_volume_uom if pref and pref.diesel_volume_uom else branch_defaults["diesel_volume_uom"])

        try:
            _ = branch.branch_profile
            has_branch_profile = True
        except BranchProfile.DoesNotExist:
            has_branch_profile = False

        sources = {
            "gasoline": "user" if (pref and pref.gasoline_volume_uom) else ("branch" if has_branch_profile else "default"),
            "diesel": "user" if (pref and pref.diesel_volume_uom) else ("branch" if has_branch_profile else "default"),
        }

        return Response(
            {
                "gasoline_volume_uom": gasoline,
                "diesel_volume_uom": diesel,
                "sources": sources,
            },
            status=200,
        )

    def put(self, request):
        branch = request.branch
        if branch is None:
            return Response({"detail": "X-Branch-Id requerido."}, status=400)

        ser = FuelUoMPreferencesIn(data=request.data)
        ser.is_valid(raise_exception=True)

        pref, _ = UserFuelUoMPreference.objects.get_or_create(user=request.user, branch=branch)
        if "gasoline_volume_uom" in ser.validated_data:
            pref.gasoline_volume_uom = ser.validated_data.get("gasoline_volume_uom")
        if "diesel_volume_uom" in ser.validated_data:
            pref.diesel_volume_uom = ser.validated_data.get("diesel_volume_uom")
        pref.save(update_fields=["gasoline_volume_uom", "diesel_volume_uom", "updated_at"])

        return self.get(request)
