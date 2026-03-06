from __future__ import annotations

from django.contrib import admin

from .models import Permission, Role, RoleAssignment, RolePermission, UserRole


@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "is_active")
    search_fields = ("name",)
    list_filter = ("is_active",)
    ordering = ("name",)


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("id", "code", "is_active")
    search_fields = ("code",)
    list_filter = ("is_active",)
    ordering = ("code",)


@admin.register(RolePermission)
class RolePermissionAdmin(admin.ModelAdmin):
    list_display = ("id", "role", "permission")
    search_fields = ("role__name", "permission__code")
    list_filter = ("role__name",)
    autocomplete_fields = ("role", "permission")


@admin.register(UserRole)
class UserRoleAdmin(admin.ModelAdmin):
    """
    Legacy/global. Lo mantenemos por compatibilidad y migración gradual.
    """

    list_display = ("id", "user", "role")
    search_fields = ("user__username", "user__email", "role__name")
    list_filter = ("role__name",)
    autocomplete_fields = ("user", "role")


@admin.register(RoleAssignment)
class RoleAssignmentAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "role", "org_unit", "is_active", "granted_at", "granted_by")
    list_filter = ("is_active", "org_unit__unit_type", "role__name")
    search_fields = ("user__username", "user__email", "role__name", "org_unit__name")
    autocomplete_fields = ("user", "role", "org_unit", "granted_by")
    ordering = ("-granted_at",)
