from __future__ import annotations

from django.urls import path

from .views import (
    AdjustView,
    BalanceView,
    HealthView,
    IssueView,
    ItemCreateView,
    ReceiveView,
    TransferView,
    WarehouseCreateView,
)


urlpatterns = [
    path("health/", HealthView.as_view()),
    path("warehouses/", WarehouseCreateView.as_view()),
    path("items/", ItemCreateView.as_view()),
    path("movements/receive/", ReceiveView.as_view()),
    path("movements/issue/", IssueView.as_view()),
    path("movements/adjust/", AdjustView.as_view()),
    path("transfers/", TransferView.as_view()),
    path("balances/", BalanceView.as_view()),
]
