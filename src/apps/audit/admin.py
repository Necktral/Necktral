from __future__ import annotations

from django.contrib import admin

from .models import AuditChainHead, AuditEvent


@admin.register(AuditChainHead)
class AuditChainHeadAdmin(admin.ModelAdmin):
	list_display = ("id", "last_event_hash", "updated_at")

	def has_add_permission(self, request):
		return False

	def has_delete_permission(self, request, obj=None):
		return False


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
from django.contrib import admin

# Register your models here.
