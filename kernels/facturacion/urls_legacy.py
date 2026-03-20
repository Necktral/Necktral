from __future__ import annotations

from django.urls import path

from .views import BillingHealthView, InvoiceCreateView

urlpatterns = [
    path("health-legacy/", BillingHealthView.as_view()),
    path("invoices/", InvoiceCreateView.as_view()),
]
