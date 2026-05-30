"""Work Management Kernel - Serializers"""
from __future__ import annotations

from rest_framework import serializers


# ---------------------------------------------------------------------------
# WorkShift
# ---------------------------------------------------------------------------


class WorkShiftCreateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120)
    code = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    shift_type = serializers.ChoiceField(
        choices=["FIXED", "ROTATING", "FLEXIBLE", "SPLIT"],
        default="FIXED",
    )
    branch_id = serializers.IntegerField(required=False, allow_null=True)
    start_time = serializers.TimeField()
    end_time = serializers.TimeField()
    break_minutes = serializers.IntegerField(min_value=0, default=0)
    late_tolerance_minutes = serializers.IntegerField(min_value=0, default=10)
    early_departure_tolerance_minutes = serializers.IntegerField(min_value=0, default=5)
    is_overnight = serializers.BooleanField(default=False)


class WorkShiftUpdateSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=120, required=False)
    code = serializers.CharField(max_length=32, required=False, allow_blank=True)
    shift_type = serializers.ChoiceField(
        choices=["FIXED", "ROTATING", "FLEXIBLE", "SPLIT"],
        required=False,
    )
    branch_id = serializers.IntegerField(required=False, allow_null=True)
    start_time = serializers.TimeField(required=False)
    end_time = serializers.TimeField(required=False)
    break_minutes = serializers.IntegerField(min_value=0, required=False)
    late_tolerance_minutes = serializers.IntegerField(min_value=0, required=False)
    early_departure_tolerance_minutes = serializers.IntegerField(min_value=0, required=False)
    is_overnight = serializers.BooleanField(required=False)
    is_active = serializers.BooleanField(required=False)


# ---------------------------------------------------------------------------
# Attendance
# ---------------------------------------------------------------------------


class AttendanceCheckInSerializer(serializers.Serializer):
    employee_id = serializers.IntegerField()
    shift_id = serializers.IntegerField(required=False, allow_null=True)
    branch_id = serializers.IntegerField(required=False, allow_null=True)
    check_in_method = serializers.ChoiceField(
        choices=["MANUAL", "BIOMETRIC", "MOBILE_GPS", "QR_CODE", "SYSTEM"],
        default="MANUAL",
    )
    latitude = serializers.DecimalField(max_digits=10, decimal_places=7, required=False, allow_null=True)
    longitude = serializers.DecimalField(max_digits=10, decimal_places=7, required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class AttendanceCheckOutSerializer(serializers.Serializer):
    check_out_method = serializers.ChoiceField(
        choices=["MANUAL", "BIOMETRIC", "MOBILE_GPS", "QR_CODE", "SYSTEM"],
        default="MANUAL",
    )
    latitude = serializers.DecimalField(max_digits=10, decimal_places=7, required=False, allow_null=True)
    longitude = serializers.DecimalField(max_digits=10, decimal_places=7, required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class AttendanceManualSerializer(serializers.Serializer):
    """Para registros manuales/retroactivos de asistencia."""
    employee_id = serializers.IntegerField()
    attendance_date = serializers.DateField()
    shift_id = serializers.IntegerField(required=False, allow_null=True)
    branch_id = serializers.IntegerField(required=False, allow_null=True)
    status = serializers.ChoiceField(
        choices=["PRESENT", "ABSENT", "LATE", "HALF_DAY", "ON_LEAVE", "HOLIDAY"],
    )
    check_in = serializers.DateTimeField(required=False, allow_null=True)
    check_out = serializers.DateTimeField(required=False, allow_null=True)
    worked_hours = serializers.DecimalField(max_digits=5, decimal_places=2, required=False)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


# ---------------------------------------------------------------------------
# MaintenanceLog
# ---------------------------------------------------------------------------


class MaintenanceLogCreateSerializer(serializers.Serializer):
    branch_id = serializers.IntegerField(required=False, allow_null=True)
    reported_by_id = serializers.IntegerField()
    assigned_to_id = serializers.IntegerField(required=False, allow_null=True)
    asset_type = serializers.ChoiceField(choices=["VEHICLE", "EQUIPMENT", "FACILITY", "OTHER"])
    asset_identifier = serializers.CharField(max_length=120)
    asset_description = serializers.CharField(max_length=255, required=False, allow_blank=True, default="")
    maintenance_type = serializers.ChoiceField(
        choices=["PREVENTIVE", "CORRECTIVE", "INSPECTION", "EMERGENCY"],
        default="INSPECTION",
    )
    priority = serializers.ChoiceField(
        choices=["LOW", "NORMAL", "HIGH", "CRITICAL"],
        default="NORMAL",
    )
    title = serializers.CharField(max_length=255)
    description = serializers.CharField()
    scheduled_date = serializers.DateField(required=False, allow_null=True)
    estimated_cost = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True)
    latitude = serializers.DecimalField(max_digits=10, decimal_places=7, required=False, allow_null=True)
    longitude = serializers.DecimalField(max_digits=10, decimal_places=7, required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class MaintenanceLogUpdateSerializer(serializers.Serializer):
    assigned_to_id = serializers.IntegerField(required=False, allow_null=True)
    priority = serializers.ChoiceField(
        choices=["LOW", "NORMAL", "HIGH", "CRITICAL"],
        required=False,
    )
    status = serializers.ChoiceField(
        choices=["DRAFT", "SUBMITTED", "IN_REVIEW", "APPROVED", "REJECTED", "COMPLETED"],
        required=False,
    )
    findings = serializers.CharField(required=False, allow_blank=True)
    actions_taken = serializers.CharField(required=False, allow_blank=True)
    parts_used = serializers.ListField(child=serializers.DictField(), required=False)
    odometer_reading = serializers.IntegerField(min_value=0, required=False, allow_null=True)
    hours_meter_reading = serializers.DecimalField(
        max_digits=10, decimal_places=2, required=False, allow_null=True
    )
    actual_cost = serializers.DecimalField(max_digits=14, decimal_places=2, required=False, allow_null=True)
    next_maintenance_date = serializers.DateField(required=False, allow_null=True)
    notes = serializers.CharField(required=False, allow_blank=True)
