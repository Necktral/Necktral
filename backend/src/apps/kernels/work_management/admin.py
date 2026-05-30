"""Work Management Kernel - Admin"""
from django.contrib import admin

from .models import Attendance, MaintenanceLog, WorkShift


@admin.register(WorkShift)
class WorkShiftAdmin(admin.ModelAdmin):
    list_display = ("name", "company", "shift_type", "start_time", "end_time", "is_active")
    list_filter = ("company", "shift_type", "is_active")
    search_fields = ("name", "code")


@admin.register(Attendance)
class AttendanceAdmin(admin.ModelAdmin):
    list_display = ("employee", "attendance_date", "status", "check_in", "check_out", "worked_hours")
    list_filter = ("company", "status", "attendance_date")
    search_fields = ("employee__first_name", "employee__last_name")
    date_hierarchy = "attendance_date"


@admin.register(MaintenanceLog)
class MaintenanceLogAdmin(admin.ModelAdmin):
    list_display = ("title", "asset_type", "asset_identifier", "priority", "status", "reported_by")
    list_filter = ("company", "asset_type", "maintenance_type", "priority", "status")
    search_fields = ("title", "asset_identifier", "description")
    date_hierarchy = "created_at"
