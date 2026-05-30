"""Work Management Kernel - Services

Lógica de negocio para turnos, asistencia y bitácoras de mantenimiento.
Transaccional, auditable, integrado con HR.
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.modulos.audit.writer import write_event
from apps.modulos.hr.models import Employee
from apps.modulos.iam.models import OrgUnit

from .models import Attendance, MaintenanceLog, WorkShift


# ---------------------------------------------------------------------------
# WorkShift Services
# ---------------------------------------------------------------------------


def create_work_shift(*, company: OrgUnit, data: dict, request=None, actor=None) -> WorkShift:
    """Crea un turno de trabajo para una empresa."""
    branch_id = data.pop("branch_id", None)
    shift = WorkShift(
        company=company,
        branch_id=branch_id,
        created_by=actor,
        **data,
    )
    shift.full_clean()
    shift.save()

    write_event(
        request=request,
        module="WORK_MANAGEMENT",
        event_type="WORK_SHIFT_CREATED",
        reason_code="OK",
        actor_user=actor,
        subject_type="WORK_SHIFT",
        subject_id=str(shift.id),
        metadata={"shift_name": shift.name, "company_id": company.id},
    )
    return shift


def update_work_shift(*, shift: WorkShift, data: dict, request=None, actor=None) -> WorkShift:
    """Actualiza un turno existente."""
    for field, value in data.items():
        if field == "branch_id":
            shift.branch_id = value
        else:
            setattr(shift, field, value)
    shift.full_clean()
    shift.save()

    write_event(
        request=request,
        module="WORK_MANAGEMENT",
        event_type="WORK_SHIFT_UPDATED",
        reason_code="OK",
        actor_user=actor,
        subject_type="WORK_SHIFT",
        subject_id=str(shift.id),
        metadata={"updated_fields": list(data.keys())},
    )
    return shift


# ---------------------------------------------------------------------------
# Attendance Services
# ---------------------------------------------------------------------------


@transaction.atomic
def check_in(*, company: OrgUnit, data: dict, request=None, actor=None) -> Attendance:
    """Registra entrada de un empleado."""
    employee = Employee.objects.select_related("company").get(
        id=data["employee_id"], company=company, is_active=True
    )
    now = timezone.now()
    today = timezone.localdate()

    # Verificar que no exista ya un registro para hoy
    existing = Attendance.objects.filter(employee=employee, attendance_date=today).first()
    if existing and existing.check_in:
        raise ValueError("ALREADY_CHECKED_IN_TODAY")

    attendance = existing or Attendance(
        company=company,
        branch_id=data.get("branch_id"),
        employee=employee,
        shift_id=data.get("shift_id"),
        attendance_date=today,
        created_by=actor,
    )

    attendance.check_in = now
    attendance.check_in_method = data.get("check_in_method", "MANUAL")
    attendance.status = Attendance.Status.PRESENT

    # GPS
    if data.get("latitude"):
        attendance.check_in_latitude = data["latitude"]
    if data.get("longitude"):
        attendance.check_in_longitude = data["longitude"]
    if data.get("notes"):
        attendance.notes = data["notes"]

    attendance.full_clean()
    attendance.save()

    write_event(
        request=request,
        module="WORK_MANAGEMENT",
        event_type="ATTENDANCE_CHECK_IN",
        reason_code="OK",
        actor_user=actor,
        subject_type="ATTENDANCE",
        subject_id=str(attendance.id),
        metadata={
            "employee_id": employee.id,
            "check_in": now.isoformat(),
            "method": attendance.check_in_method,
        },
    )
    return attendance


@transaction.atomic
def check_out(*, attendance: Attendance, data: dict, request=None, actor=None) -> Attendance:
    """Registra salida de un empleado."""
    if not attendance.check_in:
        raise ValueError("NO_CHECK_IN_FOUND")
    if attendance.check_out:
        raise ValueError("ALREADY_CHECKED_OUT")

    now = timezone.now()
    attendance.check_out = now
    attendance.check_out_method = data.get("check_out_method", "MANUAL")

    # GPS
    if data.get("latitude"):
        attendance.check_out_latitude = data["latitude"]
    if data.get("longitude"):
        attendance.check_out_longitude = data["longitude"]
    if data.get("notes"):
        attendance.notes = f"{attendance.notes}\n{data['notes']}".strip()

    attendance.full_clean()
    attendance.save()  # save() triggers update_calculations

    write_event(
        request=request,
        module="WORK_MANAGEMENT",
        event_type="ATTENDANCE_CHECK_OUT",
        reason_code="OK",
        actor_user=actor,
        subject_type="ATTENDANCE",
        subject_id=str(attendance.id),
        metadata={
            "employee_id": attendance.employee_id,
            "check_out": now.isoformat(),
            "worked_hours": str(attendance.worked_hours),
            "method": attendance.check_out_method,
        },
    )
    return attendance


@transaction.atomic
def register_manual_attendance(
    *, company: OrgUnit, data: dict, request=None, actor=None
) -> Attendance:
    """Registro manual/retroactivo de asistencia (por supervisor)."""
    employee = Employee.objects.get(
        id=data["employee_id"], company=company, is_active=True
    )

    attendance, created = Attendance.objects.get_or_create(
        employee=employee,
        attendance_date=data["attendance_date"],
        defaults={
            "company": company,
            "branch_id": data.get("branch_id"),
            "shift_id": data.get("shift_id"),
            "status": data["status"],
            "check_in": data.get("check_in"),
            "check_out": data.get("check_out"),
            "worked_hours": data.get("worked_hours", 0),
            "notes": data.get("notes", ""),
            "created_by": actor,
        },
    )

    if not created:
        # Actualizar registro existente
        attendance.status = data["status"]
        if data.get("check_in"):
            attendance.check_in = data["check_in"]
        if data.get("check_out"):
            attendance.check_out = data["check_out"]
        if data.get("worked_hours") is not None:
            attendance.worked_hours = data["worked_hours"]
        if data.get("notes"):
            attendance.notes = data["notes"]
        attendance.save()

    write_event(
        request=request,
        module="WORK_MANAGEMENT",
        event_type="ATTENDANCE_MANUAL_REGISTER",
        reason_code="OK",
        actor_user=actor,
        subject_type="ATTENDANCE",
        subject_id=str(attendance.id),
        metadata={
            "employee_id": employee.id,
            "date": str(data["attendance_date"]),
            "status": data["status"],
            "created": created,
        },
    )
    return attendance


# ---------------------------------------------------------------------------
# MaintenanceLog Services
# ---------------------------------------------------------------------------


@transaction.atomic
def create_maintenance_log(
    *, company: OrgUnit, data: dict, request=None, actor=None
) -> MaintenanceLog:
    """Crea una bitácora de mantenimiento."""
    reported_by = Employee.objects.get(
        id=data.pop("reported_by_id"), company=company, is_active=True
    )
    assigned_to_id = data.pop("assigned_to_id", None)

    log = MaintenanceLog(
        company=company,
        branch_id=data.pop("branch_id", None),
        reported_by=reported_by,
        assigned_to_id=assigned_to_id,
        created_by=actor,
        **data,
    )
    log.full_clean()
    log.save()

    write_event(
        request=request,
        module="WORK_MANAGEMENT",
        event_type="MAINTENANCE_LOG_CREATED",
        reason_code="OK",
        actor_user=actor,
        subject_type="MAINTENANCE_LOG",
        subject_id=str(log.id),
        metadata={
            "asset_type": log.asset_type,
            "asset_identifier": log.asset_identifier,
            "maintenance_type": log.maintenance_type,
            "reported_by_id": reported_by.id,
        },
    )
    return log


@transaction.atomic
def update_maintenance_log(
    *, log: MaintenanceLog, data: dict, request=None, actor=None
) -> MaintenanceLog:
    """Actualiza una bitácora de mantenimiento."""
    old_status = log.status

    for field, value in data.items():
        if field == "assigned_to_id":
            log.assigned_to_id = value
        else:
            setattr(log, field, value)

    # Auto-timestamps según status
    new_status = data.get("status")
    if new_status == MaintenanceLog.LogStatus.APPROVED and old_status != new_status:
        log.approved_by = actor
        log.approved_at = timezone.now()
    if new_status == MaintenanceLog.LogStatus.COMPLETED and not log.completed_at:
        log.completed_at = timezone.now()

    log.full_clean()
    log.save()

    write_event(
        request=request,
        module="WORK_MANAGEMENT",
        event_type="MAINTENANCE_LOG_UPDATED",
        reason_code="OK",
        actor_user=actor,
        subject_type="MAINTENANCE_LOG",
        subject_id=str(log.id),
        metadata={
            "updated_fields": list(data.keys()),
            "old_status": old_status,
            "new_status": log.status,
        },
    )
    return log


def submit_maintenance_log(*, log: MaintenanceLog, request=None, actor=None) -> MaintenanceLog:
    """Envía bitácora para revisión (transición DRAFT → SUBMITTED)."""
    if log.status != MaintenanceLog.LogStatus.DRAFT:
        raise ValueError("LOG_NOT_IN_DRAFT_STATUS")
    return update_maintenance_log(
        log=log,
        data={"status": MaintenanceLog.LogStatus.SUBMITTED},
        request=request,
        actor=actor,
    )
