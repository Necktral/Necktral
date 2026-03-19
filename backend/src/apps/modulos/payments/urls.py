from __future__ import annotations

from django.urls import path

from .views import (
    CashMovementCreateView,
    CashSessionCloseView,
    CashSessionListView,
    CashSessionOpenView,
    HealthView,
    PaymentIntentListCreateView,
)


urlpatterns = [
    path("health/", HealthView.as_view()),
    path("intents/", PaymentIntentListCreateView.as_view()),
    path("cash-sessions/", CashSessionListView.as_view()),
    path("cash-sessions/open/", CashSessionOpenView.as_view()),
    path("cash-sessions/<int:session_id>/close/", CashSessionCloseView.as_view()),
    path("cash-sessions/<int:session_id>/movements/", CashMovementCreateView.as_view()),
]
