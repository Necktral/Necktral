from django.urls import path

from .views import InventoryReadDemoView
from .views import (
    RoleListView,
    PermissionListView,
)

urlpatterns = [
    path("demo/inventory-read/", InventoryReadDemoView.as_view(), name="demo-inventory-read"),
    path("roles/", RoleListView.as_view(), name="role-list"),
    path("permissions/", PermissionListView.as_view(), name="permission-list"),
]
