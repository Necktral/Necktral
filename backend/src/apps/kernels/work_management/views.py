"""Work Management Kernel - Views"""
from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.hr.models import Employee
from apps.modulos.iam.models import OrgUnit

from . import services
from .models import Attendance, MaintenanceLog, WorkShift
from .serializers import (
    AttendanceCheckInSerializer,
    AttendanceCheckOutSerializer,
    AttendanceManualSerializer,
    MaintenanceLogCreateSerializer,
    MaintenanceLogUpdateSerializer,
    WorkShiftCreateSerializer,
    WorkShiftUpdateSerializer,
)


def _get_company(request) -> OrgUnit:
    """Extrae company del request (inyectado por middleware de contexto)."""
    company = getattr(request, "company", None)
    if company is None:
        base = getattr(request, "_request", request)
        company = getattr(base, "company", None)
    if company is None:
        raise ValueError("NO_COMPANY_CONTEXT")
    return company


# ---------------------------------------------------------------------------
# WorkShift Views
# ---------------------------------------------------------------------------


class WorkShiftListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        company = _get_company(request)
        shifts = WorkShift.objects.filter(company=company).order_by("name")
        branch_id = request.query_params.get("branch_id")
        if branch_id:
            shifts = shifts.filter(branch_id=branch_id)
        is_active = request.query_params.get("is_active")
        if is_active is not None:
            shifts = shifts.filter(is_active=is_active.lower() == "true")

        data = list(
            shifts.values(
                "id", "shift_id", "name", "code", "shift_type",
                "start_time", "end_time", "break_minutes",
                "late_tolerance_minutes", "early_departure_tolerance_minutes",
                "is_overnight", "is_active", "branch_id",
                "created_at", "updated_at",
            )
        )
        return Response({"results": data})

    def post(self, request):
        company = _get_company(request)
        ser = WorkShiftCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        shift = services.create_work_shift(
            company=company, data=ser.validated_data, request=request, actor=request.user
        )
        return Response(
            {"id": shift.id, "shift_id": str(shift.shift_id), "name": shift.name},
            status=status.HTTP_201_CREATED,
        )


class WorkShiftDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        company = _get_company(request)
        shift = WorkShift.objects.get(pk=pk, company=company)
        data = {
            "id": shift.id,
            "shift_id": str(shift.shift_id),
            "name": shift.name,
            "code": shift.code,
            "shift_type": shift.shift_type,
            "start_time": shift.start_time,
            "end_time": shift.end_time,
            "break_minutes": shift.break_minutes,
            "late_tolerance_minutes": shift.late_tolerance_minutes,
            "early_departure_tolerance_minutes": shift.early_departure_tolerance_minutes,
            "is_overnight": shift.is_overnight,
            "is_active": shift.is_active,
            "branch_id": shift.branch_id,
            "duration_minutes": shift.duration_minutes,
            "created_at": shift.created_at,
            "updated_at": shift.updated_at,
        }
        return Response(data)

    def patch(self, request, pk):
        company = _get_company(request)
        shift = WorkShift.objects.get(pk=pk, company=company)
        ser = WorkShiftUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        # Filter only provided fields
        update_data = {k: v for k, v in ser.validated_data.items() if k in request.data}
        shift = services.update_work_shift(
            shift=shift, data=update_data, request=request, actor=request.user
        )
        return Response({"id": shift.id, "name": shift.name, "is_active": shift.is_active})


# ---------------------------------------------------------------------------
# Attendance Views
# ---------------------------------------------------------------------------


class AttendanceCheckInView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        company = _get_company(request)
        ser = AttendanceCheckInSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        attendance = services.check_in(
            company=company, data=ser.validated_data, request=request, actor=request.user
        )
        return Response(
            {
                "id": attendance.id,
                "attendance_id": str(attendance.attendance_id),
                "employee_id": attendance.employee_id,
                "check_in": attendance.check_in,
                "status": attendance.status,
            },
            status=status.HTTP_201_CREATED,
        )


class AttendanceCheckOutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        company = _get_company(request)
        attendance = Attendance.objects.get(pk=pk, company=company)
        ser = AttendanceCheckOutSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        attendance = services.check_out(
            attendance=attendance, data=ser.validated_data, request=request, actor=request.user
        )
        return Response(
            {
                "id": attendance.id,
                "check_out": attendance.check_out,
                "worked_hours": str(attendance.worked_hours),
                "late_minutes": attendance.late_minutes,
                "status": attendance.status,
            }
        )


class AttendanceManualView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        company = _get_company(request)
        ser = AttendanceManualSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        attendance = services.register_manual_attendance(
            company=company, data=ser.validated_data, request=request, actor=request.user
        )
        return Response(
            {
                "id": attendance.id,
                "attendance_id": str(attendance.attendance_id),
                "employee_id": attendance.employee_id,
                "date": str(attendance.attendance_date),
                "status": attendance.status,
            },
            status=status.HTTP_201_CREATED,
        )


class AttendanceListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        company = _get_company(request)
        qs = Attendance.objects.filter(company=company).select_related("employee", "shift")

        # Filtros
        employee_id = request.query_params.get("employee_id")
        if employee_id:
            qs = qs.filter(employee_id=employee_id)
        date_from = request.query_params.get("date_from")
        if date_from:
            qs = qs.filter(attendance_date__gte=date_from)
        date_to = request.query_params.get("date_to")
        if date_to:
            qs = qs.filter(attendance_date__lte=date_to)
        att_status = request.query_params.get("status")
        if att_status:
            qs = qs.filter(status=att_status)
        branch_id = request.query_params.get("branch_id")
        if branch_id:
            qs = qs.filter(branch_id=branch_id)

        qs = qs.order_by("-attendance_date")[:100]

        data = []
        for att in qs:
            data.append({
                "id": att.id,
                "attendance_id": str(att.attendance_id),
                "employee_id": att.employee_id,
                "employee_name": f"{att.employee.first_name} {att.employee.last_name}".strip(),
                "attendance_date": str(att.attendance_date),
                "check_in": att.check_in,
                "check_out": att.check_out,
                "status": att.status,
                "worked_hours": str(att.worked_hours),
                "late_minutes": att.late_minutes,
                "shift_name": att.shift.name if att.shift else None,
            })
        return Response({"results": data, "count": len(data)})


# ---------------------------------------------------------------------------
# MaintenanceLog Views
# ---------------------------------------------------------------------------


class MaintenanceLogListCreateView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        company = _get_company(request)
        qs = MaintenanceLog.objects.filter(company=company).select_related(
            "reported_by", "assigned_to"
        )

        # Filtros
        asset_type = request.query_params.get("asset_type")
        if asset_type:
            qs = qs.filter(asset_type=asset_type)
        log_status = request.query_params.get("status")
        if log_status:
            qs = qs.filter(status=log_status)
        priority = request.query_params.get("priority")
        if priority:
            qs = qs.filter(priority=priority)
        asset_identifier = request.query_params.get("asset_identifier")
        if asset_identifier:
            qs = qs.filter(asset_identifier__icontains=asset_identifier)
        branch_id = request.query_params.get("branch_id")
        if branch_id:
            qs = qs.filter(branch_id=branch_id)

        qs = qs.order_by("-created_at")[:100]

        data = []
        for log in qs:
            data.append({
                "id": log.id,
                "log_id": str(log.log_id),
                "asset_type": log.asset_type,
                "asset_identifier": log.asset_identifier,
                "title": log.title,
                "maintenance_type": log.maintenance_type,
                "priority": log.priority,
                "status": log.status,
                "reported_by_name": f"{log.reported_by.first_name} {log.reported_by.last_name}".strip(),
                "assigned_to_name": (
                    f"{log.assigned_to.first_name} {log.assigned_to.last_name}".strip()
                    if log.assigned_to else None
                ),
                "scheduled_date": str(log.scheduled_date) if log.scheduled_date else None,
                "created_at": log.created_at,
            })
        return Response({"results": data, "count": len(data)})

    def post(self, request):
        company = _get_company(request)
        ser = MaintenanceLogCreateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        log = services.create_maintenance_log(
            company=company, data=ser.validated_data, request=request, actor=request.user
        )
        return Response(
            {
                "id": log.id,
                "log_id": str(log.log_id),
                "title": log.title,
                "status": log.status,
            },
            status=status.HTTP_201_CREATED,
        )


class MaintenanceLogDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, pk):
        company = _get_company(request)
        log = MaintenanceLog.objects.select_related(
            "reported_by", "assigned_to"
        ).get(pk=pk, company=company)
        data = {
            "id": log.id,
            "log_id": str(log.log_id),
            "asset_type": log.asset_type,
            "asset_identifier": log.asset_identifier,
            "asset_description": log.asset_description,
            "title": log.title,
            "description": log.description,
            "findings": log.findings,
            "actions_taken": log.actions_taken,
            "parts_used": log.parts_used,
            "maintenance_type": log.maintenance_type,
            "priority": log.priority,
            "status": log.status,
            "reported_by_id": log.reported_by_id,
            "assigned_to_id": log.assigned_to_id,
            "odometer_reading": log.odometer_reading,
            "hours_meter_reading": str(log.hours_meter_reading) if log.hours_meter_reading else None,
            "estimated_cost": str(log.estimated_cost) if log.estimated_cost else None,
            "actual_cost": str(log.actual_cost) if log.actual_cost else None,
            "scheduled_date": str(log.scheduled_date) if log.scheduled_date else None,
            "started_at": log.started_at,
            "completed_at": log.completed_at,
            "next_maintenance_date": str(log.next_maintenance_date) if log.next_maintenance_date else None,
            "notes": log.notes,
            "branch_id": log.branch_id,
            "created_at": log.created_at,
            "updated_at": log.updated_at,
        }
        return Response(data)

    def patch(self, request, pk):
        company = _get_company(request)
        log = MaintenanceLog.objects.get(pk=pk, company=company)
        ser = MaintenanceLogUpdateSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        update_data = {k: v for k, v in ser.validated_data.items() if k in request.data}
        log = services.update_maintenance_log(
            log=log, data=update_data, request=request, actor=request.user
        )
        return Response({"id": log.id, "status": log.status})


class MaintenanceLogSubmitView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        company = _get_company(request)
        log = MaintenanceLog.objects.get(pk=pk, company=company)
        log = services.submit_maintenance_log(log=log, request=request, actor=request.user)
        return Response({"id": log.id, "status": log.status})
