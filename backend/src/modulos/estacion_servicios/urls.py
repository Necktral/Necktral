from django.urls import path

from modulos.estacion_servicios.views import (
    FuelDispenseCreateView,
    FuelDispenseDetailView,
    FuelDailyCloseReportView,
    FuelHealthView,
    FuelSaleDetailView,
    FuelSaleCreateView,
    FuelSaleCancelView,
    FuelShiftDetailView,
    FuelShiftListView,
    FuelShiftCloseView,
    FuelShiftCloseReportView,
    FuelShiftOpenView,
    FuelUoMPreferencesView,
)

urlpatterns = [
    path("health/", FuelHealthView.as_view(), name="fuel-health"),
    path("shifts/open/", FuelShiftOpenView.as_view(), name="fuel-shift-open"),
    path("shifts/<int:shift_id>/close/", FuelShiftCloseView.as_view(), name="fuel-shift-close"),
    path("shifts/", FuelShiftListView.as_view(), name="fuel-shift-list"),
    path("shifts/<int:shift_id>/", FuelShiftDetailView.as_view(), name="fuel-shift-detail"),
    # GET list / POST create (misma ruta para compatibilidad)
    path("dispenses/", FuelDispenseCreateView.as_view(), name="fuel-dispense-list-create"),
    path("dispenses/<int:dispense_id>/", FuelDispenseDetailView.as_view(), name="fuel-dispense-detail"),
    path("uom-preferences/", FuelUoMPreferencesView.as_view(), name="fuel-uom-preferences"),
    # GET list / POST create (misma ruta para compatibilidad)
    path("sales/", FuelSaleCreateView.as_view(), name="fuel-sale-list-create"),
    path("sales/<int:sale_id>/", FuelSaleDetailView.as_view(), name="fuel-sale-detail"),
    path("sales/<int:sale_id>/cancel/", FuelSaleCancelView.as_view(), name="fuel-sale-cancel"),

    path("reports/shift-close/<int:shift_id>/", FuelShiftCloseReportView.as_view(), name="fuel-report-shift-close"),
    path("reports/daily-close/", FuelDailyCloseReportView.as_view(), name="fuel-report-daily-close"),
]
