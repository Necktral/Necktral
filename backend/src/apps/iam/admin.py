from __future__ import annotations

from django.contrib import admin

from .models import AdminGrant, CompanyLink, LinkGrant, OrgClosure, OrgUnit, UserMembership


@admin.register(CompanyLink)
class CompanyLinkAdmin(admin.ModelAdmin):
    list_display = ("id", "from_company", "to_company", "link_type", "status", "is_active", "created_at")
    list_filter = ("link_type", "status", "is_active")
    search_fields = ("from_company__name", "to_company__name")
    autocomplete_fields = ("from_company", "to_company")
    ordering = ("-created_at",)


@admin.register(LinkGrant)
class LinkGrantAdmin(admin.ModelAdmin):
    list_display = ("id", "link", "permission", "access_mode", "scope_org_unit", "is_active", "valid_from", "valid_to")
    list_filter = ("access_mode", "is_active")
    search_fields = ("permission__code", "link__from_company__name", "link__to_company__name", "scope_org_unit__name")
    autocomplete_fields = ("link", "permission", "scope_org_unit")
    ordering = ("-created_at",)


@admin.register(OrgUnit)
class OrgUnitAdmin(admin.ModelAdmin):
    list_display = ("id", "unit_type", "name", "parent", "is_active")
    list_filter = ("unit_type", "is_active")
    search_fields = ("name", "code")
    ordering = ("unit_type", "name")


@admin.register(UserMembership)
class UserMembershipAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "org_unit", "is_active", "joined_at")
    list_filter = ("is_active", "org_unit__unit_type")
    search_fields = ("user__username", "user__email", "org_unit__name")
    autocomplete_fields = ("user", "org_unit")


@admin.register(AdminGrant)
class AdminGrantAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "capability", "org_unit", "applies_to_subtree", "is_active", "granted_at")
    list_filter = ("capability", "is_active", "applies_to_subtree")
    search_fields = ("user__username", "org_unit__name")
    autocomplete_fields = ("user", "org_unit", "granted_by")


@admin.register(OrgClosure)
class OrgClosureAdmin(admin.ModelAdmin):
    list_display = ("id", "ancestor", "descendant", "depth")
    list_filter = ("depth",)
    search_fields = ("ancestor__name", "descendant__name")

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
