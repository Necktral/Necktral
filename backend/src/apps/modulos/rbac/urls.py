from django.urls import path

from .views import (
    EffectivePermissionsView,
    InventoryReadDemoView,
    PermissionListView,
    RoleAssignmentListView,
    RoleAssignmentRevokeView,
    RoleDetailView,
    RoleListView,
    RolePermissionManageView,
)

urlpatterns = [
    path("roles/", RoleListView.as_view(), name="role-list"),
    path("roles/<int:role_id>/", RoleDetailView.as_view(), name="role-detail"),
    path("roles/<int:role_id>/permissions/", RolePermissionManageView.as_view(), name="role-permission-manage"),
    path("permissions/", PermissionListView.as_view(), name="permission-list"),
    path("effective-permissions/", EffectivePermissionsView.as_view(), name="effective-permissions"),
    path("assignments/", RoleAssignmentListView.as_view(), name="role-assignment-list"),
    path("assignments/<int:assignment_id>/revoke/", RoleAssignmentRevokeView.as_view(), name="role-assignment-revoke"),
    path("demo/inventory-read/", InventoryReadDemoView.as_view(), name="demo-inventory-read"),
]
