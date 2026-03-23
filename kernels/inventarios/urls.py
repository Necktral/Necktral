from __future__ import annotations

from django.urls import path

from .views import (
    AdjustView,
    BalanceView,
    BrandLookupView,
    CategoryLookupView,
    HealthView,
    InventoryCommandBatchView,
    IssueView,
    ItemDetailView,
    ItemListCreateView,
    LedgerView,
    ReceiveView,
    TaxProfileLookupView,
    TransferView,
    UomLookupView,
    WarehouseDetailView,
    WarehouseListCreateView,
)


urlpatterns = [
    path("health/", HealthView.as_view()),
    path("warehouses/", WarehouseListCreateView.as_view()),
    path("warehouses/<int:warehouse_id>/", WarehouseDetailView.as_view()),
    path("items/", ItemListCreateView.as_view()),
    path("items/<int:item_id>/", ItemDetailView.as_view()),
    path("lookups/uoms/", UomLookupView.as_view()),
    path("lookups/brands/", BrandLookupView.as_view()),
    path("lookups/categories/", CategoryLookupView.as_view()),
    path("lookups/tax-profiles/", TaxProfileLookupView.as_view()),
    path("movements/receive/", ReceiveView.as_view()),
    path("movements/issue/", IssueView.as_view()),
    path("movements/adjust/", AdjustView.as_view()),
    path("transfers/", TransferView.as_view()),
    path("commands/batch/", InventoryCommandBatchView.as_view()),
    path("balances/", BalanceView.as_view()),
    path("ledger/", LedgerView.as_view()),
]
