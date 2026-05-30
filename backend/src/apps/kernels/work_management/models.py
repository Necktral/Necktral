"""
Work Management Kernel - Models

Gestión operativa del trabajo: turnos, asistencia y bitácoras de mantenimiento.
Integración directa con HR (Employee) e IAM (OrgUnit).
"""
from __future__ import annotations

import uuid
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


# ---------------------------------------------------------------------------
# WorkShift - Turnos configurables por empresa/sucursal
# ---------------------------------------------------------------------------


class WorkShift(models.Model):
    """
    Turno de trabajo configurable.

    Cada empresa/sucursal puede definir sus propios turnos.
    Un turno define horario base para control de asistencia.
    """

    class ShiftType(models.TextChoices):
        FIXED = "FIXED", _("Fixed")
        ROTATING = "ROTATING", _("Rotating")
        FLEXIBLE = "FLEXIBLE", _("Flexible")
        SPLIT = "SPLIT", _("Split")

    shift_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
    )
    company = models.ForeignKey(
        "iam.OrgUnit",
        on_delete=models.PROTECT,
        related_name="work_shifts",
        help_text="Empresa propietaria del turno",
    )
    branch = models.ForeignKey(
        "iam.OrgUnit",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="branch_work_shifts",
        help_text="Sucursal (opcional, si aplica solo a una sucursal)",
    )
    name = models.CharField(max_length=120, help_text="Nombre del turno (ej. Matutino, Nocturno)")
    code = models.CharField(max_length=32, blank=True, default="")
    shift_type = models.CharField(
        max_length=16,
        choices=ShiftType.choices,
        default=ShiftType.FIXED,
    )

    # Horarios
    start_time = models.TimeField(help_text="Hora de inicio del turno")
    end_time = models.TimeField(help_text="Hora de fin del turno")
    break_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Minutos de descanso incluidos en el turno",
    )

    # Tolerancias (en minutos)
    late_tolerance_minutes = models.PositiveIntegerField(
        default=10,
        help_text="Minutos de tolerancia para llegada tarde",
    )
    early_departure_tolerance_minutes = models.PositiveIntegerField(
        default=5,
        help_text="Minutos de tolerancia para salida anticipada",
    )

    # Config
    is_overnight = models.BooleanField(
        default=False,
        help_text="Si el turno cruza medianoche (ej. 22:00 - 06:00)",
    )
    is_active = models.BooleanField(default=True)

    # Auditoría
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="work_shifts_created",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "work_management"
        constraints = [
            models.UniqueConstraint(
                fields=["company", "name"],
                name="uq_workshift_company_name",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "is_active"]),
            models.Index(fields=["company", "branch", "is_active"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.start_time}-{self.end_time})"

    @property
    def duration_minutes(self) -> int:
        """Duración neta del turno en minutos (sin descanso)."""
        from datetime import datetime, timedelta

        start_dt = datetime.combine(datetime.today(), self.start_time)
        end_dt = datetime.combine(datetime.today(), self.end_time)
        if self.is_overnight:
            end_dt += timedelta(days=1)
        total = int((end_dt - start_dt).total_seconds() / 60)
        return total - self.break_minutes

    def clean(self):
        super().clean()
        if not self.is_overnight and self.start_time and self.end_time:
            if self.end_time <= self.start_time:
                raise ValidationError(
                    {"end_time": _("End time must be after start time for non-overnight shifts.")}
                )


# ---------------------------------------------------------------------------
# Attendance - Control de asistencia
# ---------------------------------------------------------------------------


class Attendance(models.Model):
    """
    Registro de asistencia de un empleado.

    Vinculado directamente a Employee (HR) y opcionalmente a un WorkShift.
    Permite registro de entrada/salida con cálculo automático de horas.
    """

    class Status(models.TextChoices):
        PRESENT = "PRESENT", _("Present")
        ABSENT = "ABSENT", _("Absent")
        LATE = "LATE", _("Late")
        HALF_DAY = "HALF_DAY", _("Half Day")
        ON_LEAVE = "ON_LEAVE", _("On Leave")
        HOLIDAY = "HOLIDAY", _("Holiday")

    class CheckMethod(models.TextChoices):
        MANUAL = "MANUAL", _("Manual")
        BIOMETRIC = "BIOMETRIC", _("Biometric")
        MOBILE_GPS = "MOBILE_GPS", _("Mobile GPS")
        QR_CODE = "QR_CODE", _("QR Code")
        SYSTEM = "SYSTEM", _("System Auto")

    attendance_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
    )
    company = models.ForeignKey(
        "iam.OrgUnit",
        on_delete=models.PROTECT,
        related_name="attendances",
    )
    branch = models.ForeignKey(
        "iam.OrgUnit",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="branch_attendances",
    )
    employee = models.ForeignKey(
        "hr.Employee",
        on_delete=models.PROTECT,
        related_name="attendances",
    )
    shift = models.ForeignKey(
        WorkShift,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="attendances",
    )

    # Fecha del registro
    attendance_date = models.DateField(db_index=True, help_text="Fecha de la asistencia")

    # Tiempos de entrada/salida
    check_in = models.DateTimeField(null=True, blank=True, help_text="Hora de entrada")
    check_out = models.DateTimeField(null=True, blank=True, help_text="Hora de salida")
    check_in_method = models.CharField(
        max_length=16,
        choices=CheckMethod.choices,
        default=CheckMethod.MANUAL,
    )
    check_out_method = models.CharField(
        max_length=16,
        choices=CheckMethod.choices,
        default=CheckMethod.MANUAL,
    )

    # Estado y horas
    status = models.CharField(
        max_length=16,
        choices=Status.choices,
        default=Status.PRESENT,
        db_index=True,
    )
    worked_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Horas trabajadas calculadas",
    )
    overtime_hours = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("0.00"),
        help_text="Horas extra",
    )
    late_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Minutos de retraso",
    )
    early_departure_minutes = models.PositiveIntegerField(
        default=0,
        help_text="Minutos de salida anticipada",
    )

    # Ubicación (para check móvil)
    check_in_latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
    )
    check_in_longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
    )
    check_out_latitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
    )
    check_out_longitude = models.DecimalField(
        max_digits=10,
        decimal_places=7,
        null=True,
        blank=True,
    )

    # Notas y metadata
    notes = models.TextField(blank=True, default="")
    metadata_json = models.JSONField(default=dict, blank=True)

    # Auditoría
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="attendances_created",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="attendances_approved",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "work_management"
        constraints = [
            models.UniqueConstraint(
                fields=["employee", "attendance_date"],
                name="uq_attendance_employee_date",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "attendance_date"]),
            models.Index(fields=["employee", "attendance_date"]),
            models.Index(fields=["company", "branch", "attendance_date"]),
            models.Index(fields=["status", "attendance_date"]),
        ]
        ordering = ["-attendance_date"]

    def __str__(self):
        return f"{self.employee} - {self.attendance_date} ({self.status})"

    def calculate_worked_hours(self) -> Decimal:
        """Calcula horas trabajadas a partir de check_in y check_out."""
        if not self.check_in or not self.check_out:
            return Decimal("0.00")
        diff = self.check_out - self.check_in
        hours = Decimal(str(diff.total_seconds())) / Decimal("3600")
        return hours.quantize(Decimal("0.01"))

    def calculate_late_minutes(self) -> int:
        """Calcula minutos de retraso respecto al turno."""
        if not self.shift or not self.check_in:
            return 0
        from datetime import datetime

        scheduled_start = datetime.combine(self.attendance_date, self.shift.start_time)
        scheduled_start = timezone.make_aware(scheduled_start, timezone.get_current_timezone())
        if self.check_in > scheduled_start:
            diff = (self.check_in - scheduled_start).total_seconds() / 60
            tolerance = self.shift.late_tolerance_minutes
            return max(0, int(diff) - tolerance)
        return 0

    def update_calculations(self):
        """Actualiza campos calculados."""
        self.worked_hours = self.calculate_worked_hours()
        self.late_minutes = self.calculate_late_minutes()

        # Auto-determinar status basado en datos
        if self.late_minutes > 0 and self.status == self.Status.PRESENT:
            self.status = self.Status.LATE

    def clean(self):
        super().clean()
        if self.check_in and self.check_out and self.check_out <= self.check_in:
            raise ValidationError({"check_out": _("Check-out must be after check-in.")})

    def save(self, *args, **kwargs):
        if self.check_in and self.check_out:
            self.update_calculations()
        super().save(*args, **kwargs)


# ---------------------------------------------------------------------------
# MaintenanceLog - Bitácora de mantenimiento
# ---------------------------------------------------------------------------


class MaintenanceLog(models.Model):
    """
    Bitácora de mantenimiento para vehículos, equipos o instalaciones.

    Diseñado para uso móvil: un empleado llena la bitácora en campo.
    """

    class AssetType(models.TextChoices):
        VEHICLE = "VEHICLE", _("Vehicle")
        EQUIPMENT = "EQUIPMENT", _("Equipment")
        FACILITY = "FACILITY", _("Facility")
        OTHER = "OTHER", _("Other")

    class MaintenanceType(models.TextChoices):
        PREVENTIVE = "PREVENTIVE", _("Preventive")
        CORRECTIVE = "CORRECTIVE", _("Corrective")
        INSPECTION = "INSPECTION", _("Inspection")
        EMERGENCY = "EMERGENCY", _("Emergency")

    class Priority(models.TextChoices):
        LOW = "LOW", _("Low")
        NORMAL = "NORMAL", _("Normal")
        HIGH = "HIGH", _("High")
        CRITICAL = "CRITICAL", _("Critical")

    class LogStatus(models.TextChoices):
        DRAFT = "DRAFT", _("Draft")
        SUBMITTED = "SUBMITTED", _("Submitted")
        IN_REVIEW = "IN_REVIEW", _("In Review")
        APPROVED = "APPROVED", _("Approved")
        REJECTED = "REJECTED", _("Rejected")
        COMPLETED = "COMPLETED", _("Completed")

    log_id = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        db_index=True,
    )
    company = models.ForeignKey(
        "iam.OrgUnit",
        on_delete=models.PROTECT,
        related_name="maintenance_logs",
    )
    branch = models.ForeignKey(
        "iam.OrgUnit",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="branch_maintenance_logs",
    )

    # Quién lo reporta
    reported_by = models.ForeignKey(
        "hr.Employee",
        on_delete=models.PROTECT,
        related_name="maintenance_logs_reported",
        help_text="Empleado que reporta/llena la bitácora",
    )
    assigned_to = models.ForeignKey(
        "hr.Employee",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="maintenance_logs_assigned",
        help_text="Empleado asignado para ejecución",
    )

    # Activo / recurso
    asset_type = models.CharField(
        max_length=16,
        choices=AssetType.choices,
        db_index=True,
    )
    asset_identifier = models.CharField(
        max_length=120,
        db_index=True,
        help_text="Identificador del activo (placa, número de serie, código interno)",
    )
    asset_description = models.CharField(
        max_length=255,
        blank=True,
        default="",
        help_text="Descripción del activo",
    )

    # Tipo y prioridad
    maintenance_type = models.CharField(
        max_length=16,
        choices=MaintenanceType.choices,
        default=MaintenanceType.INSPECTION,
    )
    priority = models.CharField(
        max_length=16,
        choices=Priority.choices,
        default=Priority.NORMAL,
        db_index=True,
    )
    status = models.CharField(
        max_length=16,
        choices=LogStatus.choices,
        default=LogStatus.DRAFT,
        db_index=True,
    )

    # Contenido de la bitácora
    title = models.CharField(max_length=255, help_text="Título/resumen del mantenimiento")
    description = models.TextField(help_text="Descripción detallada del trabajo realizado o requerido")
    findings = models.TextField(blank=True, default="", help_text="Hallazgos durante la inspección")
    actions_taken = models.TextField(blank=True, default="", help_text="Acciones realizadas")
    parts_used = models.JSONField(
        default=list,
        blank=True,
        help_text="Lista de partes/repuestos usados [{name, qty, cost}]",
    )

    # Métricas
    odometer_reading = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text="Lectura de odómetro (para vehículos)",
    )
    hours_meter_reading = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Lectura de horómetro (para equipos)",
    )
    estimated_cost = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Costo estimado del mantenimiento",
    )
    actual_cost = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Costo real del mantenimiento",
    )

    # Fechas
    scheduled_date = models.DateField(
        null=True,
        blank=True,
        help_text="Fecha programada del mantenimiento",
    )
    started_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Inicio de ejecución",
    )
    completed_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Fin de ejecución",
    )
    next_maintenance_date = models.DateField(
        null=True,
        blank=True,
        help_text="Próxima fecha de mantenimiento programado",
    )

    # Ubicación (llenado móvil)
    latitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)
    longitude = models.DecimalField(max_digits=10, decimal_places=7, null=True, blank=True)

    # Metadata y notas
    notes = models.TextField(blank=True, default="")
    metadata_json = models.JSONField(default=dict, blank=True)

    # Auditoría
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="maintenance_logs_approved",
    )
    approved_at = models.DateTimeField(null=True, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="maintenance_logs_created",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        app_label = "work_management"
        indexes = [
            models.Index(fields=["company", "status", "priority"]),
            models.Index(fields=["company", "asset_type", "asset_identifier"]),
            models.Index(fields=["reported_by", "status"]),
            models.Index(fields=["assigned_to", "status"]),
            models.Index(fields=["company", "branch", "status"]),
            models.Index(fields=["scheduled_date"]),
            models.Index(fields=["next_maintenance_date"]),
        ]
        ordering = ["-created_at"]

    def __str__(self):
        return f"[{self.asset_type}] {self.title} - {self.status}"

    def clean(self):
        super().clean()
        if self.started_at and self.completed_at and self.completed_at <= self.started_at:
            raise ValidationError(
                {"completed_at": _("Completion time must be after start time.")}
            )
