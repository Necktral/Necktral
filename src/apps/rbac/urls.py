from django.urls import path

from .views import InventoryReadDemoView

urlpatterns = [
    path("demo/inventory-read/", InventoryReadDemoView.as_view(), name="demo-inventory-read"),
]
