from __future__ import annotations

from django.contrib import admin

from .models import AuditChainHeadV2, AuditEvent


@admin.register(AuditChainHeadV2)
class AuditChainHeadV2Admin(admin.ModelAdmin):
    list_display = ("partition_key", "last_event_hash", "updated_at")


@admin.register(AuditEvent)
class AuditEventAdmin(admin.ModelAdmin):
    list_display = (
        "timestamp_server",
        "module",
        "event_type",
        "reason_code",
        "actor_user",
        "subject_type",
        "subject_id",
        "path",
        "method",
    )
    list_filter = ("module", "event_type", "reason_code", "subject_type", "method")
    search_fields = ("subject_id", "path", "user_agent", "event_hash", "prev_event_hash")
    ordering = ("-timestamp_server",)
    date_hierarchy = "timestamp_server"
    readonly_fields = (
        "event_id",
        "schema_version",
        "module",
        "event_type",
        "reason_code",
        "subject_type",
        "subject_id",
        "timestamp_server",
        "actor_user",
        "device_id",
        "ip_server_seen",
        "offline_mode",
        "user_agent",
        "path",
        "method",
        "before_snapshot",
        "after_snapshot",
        "metadata",
        "prev_event_hash",
        "event_hash",
        "signature",
    )

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        # Permitimos ver detalle (GET) pero no editar
        if request.method in ("GET", "HEAD", "OPTIONS"):
            return True
        return False

    def has_delete_permission(self, request, obj=None):
        return False
