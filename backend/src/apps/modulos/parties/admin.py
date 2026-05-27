from __future__ import annotations

from django.contrib import admin
from django.core.exceptions import PermissionDenied

from .models import Party, PartyRole


class ReadOnlyMasterDataAdminMixin:
    readonly_message = "Party master data debe modificarse por servicios auditados."

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        if request.method not in {"GET", "HEAD", "OPTIONS"}:
            return False
        return super().has_view_permission(request, obj) or super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return super().has_view_permission(request, obj) or super().has_change_permission(request, obj)

    def get_readonly_fields(self, request, obj=None):
        return [field.name for field in self.model._meta.fields]

    def get_actions(self, request):
        actions = super().get_actions(request)
        actions.pop("delete_selected", None)
        return actions

    def save_model(self, request, obj, form, change):
        raise PermissionDenied(self.readonly_message)

    def delete_model(self, request, obj):
        raise PermissionDenied(self.readonly_message)

    def delete_queryset(self, request, queryset):
        raise PermissionDenied(self.readonly_message)


@admin.register(Party)
class PartyAdmin(ReadOnlyMasterDataAdminMixin, admin.ModelAdmin):
    list_display = ("id", "display_name", "party_type", "status", "company", "tax_id", "national_id", "updated_at")
    list_filter = ("party_type", "status", "company")
    search_fields = ("display_name", "legal_name", "tax_id", "national_id", "email", "phone")
    autocomplete_fields = ("company",)
    ordering = ("display_name",)


@admin.register(PartyRole)
class PartyRoleAdmin(ReadOnlyMasterDataAdminMixin, admin.ModelAdmin):
    list_display = ("id", "party", "role", "is_active", "valid_from", "valid_to")
    list_filter = ("role", "is_active")
    search_fields = ("party__display_name", "party__legal_name", "party__tax_id", "party__national_id")
    autocomplete_fields = ("party",)
    ordering = ("party__display_name", "role")
