from __future__ import annotations

from django.contrib import admin

from .models import AppliedCommand, Device, DeviceEnrollmentChallenge, SyncReceipt


@admin.register(Device)
class DeviceAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "branch", "label", "status", "last_seen_at", "created_at")
    list_filter = ("status", "company")
    search_fields = ("id", "label")


@admin.register(DeviceEnrollmentChallenge)
class DeviceEnrollmentChallengeAdmin(admin.ModelAdmin):
    list_display = ("id", "company", "branch", "expires_at", "used_at", "created_at")
    list_filter = ("company",)
    search_fields = ("id", "enrollment_code_hash")


@admin.register(AppliedCommand)
class AppliedCommandAdmin(admin.ModelAdmin):
    list_display = (
        "command_id",
        "device",
        "company",
        "branch",
        "command_type",
        "result_status",
        "received_at",
        "applied_at",
    )
    list_filter = ("result_status", "company", "command_type")
    search_fields = ("command_id", "device__id", "command_type")


@admin.register(SyncReceipt)
class SyncReceiptAdmin(admin.ModelAdmin):
    list_display = (
        "batch_id",
        "device",
        "server_time",
        "received_count",
        "applied_count",
        "rejected_count",
        "duplicate_count",
    )
    search_fields = ("batch_id", "device__id")
