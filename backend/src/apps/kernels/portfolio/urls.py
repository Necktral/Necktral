"""
Portfolio Kernel URLs
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register(r"receivables", views.ReceivableViewSet, basename="receivable")
router.register(r"payables", views.PayableViewSet, basename="payable")
router.register(r"credits", views.CreditViewSet, basename="credit")
router.register(r"allocations", views.PaymentAllocationViewSet, basename="payment-allocation")
router.register(r"interest-accruals", views.InterestAccrualViewSet, basename="interest-accrual")
router.register(r"settings", views.PortfolioSettingsViewSet, basename="portfolio-settings")

app_name = "portfolio"
urlpatterns = [
    path("", include(router.urls)),
]
