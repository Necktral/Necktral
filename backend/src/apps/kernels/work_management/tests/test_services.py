"""
Work Management Kernel - Unit Tests (Gate 1→2)

Tests de contrato para servicios del kernel.
Pueden fallar sin PostgreSQL real — validación completa es Frente 2.
"""
from __future__ import annotations

from datetime import time, date
from unittest.mock import MagicMock, patch

import pytest


class TestWorkShiftService:
    """Tests para servicio de turnos."""

    def test_create_work_shift_requires_company(self):
        """Un turno siempre requiere company."""
        from apps.kernels.work_management.services import create_work_shift

        with pytest.raises((TypeError, ValueError)):
            create_work_shift(company=None, data={}, request=MagicMock(), actor=MagicMock())

    def test_create_work_shift_validates_times(self):
        """start_time y end_time son obligatorios."""
        from apps.kernels.work_management.serializers import WorkShiftCreateSerializer

        ser = WorkShiftCreateSerializer(data={"name": "Test"})
        assert not ser.is_valid()
        assert "start_time" in ser.errors or "end_time" in ser.errors


class TestAttendanceService:
    """Tests para servicio de asistencia."""

    def test_check_in_serializer_requires_employee(self):
        """Check-in requiere employee_id."""
        from apps.kernels.work_management.serializers import AttendanceCheckInSerializer

        ser = AttendanceCheckInSerializer(data={})
        assert not ser.is_valid()
        assert "employee_id" in ser.errors

    def test_check_out_serializer_accepts_notes(self):
        """Check-out acepta notes opcionales."""
        from apps.kernels.work_management.serializers import AttendanceCheckOutSerializer

        ser = AttendanceCheckOutSerializer(data={"notes": "Salida normal"})
        assert ser.is_valid()


class TestMaintenanceLogService:
    """Tests para servicio de bitácoras de mantenimiento."""

    def test_create_serializer_requires_fields(self):
        """Bitácora requiere campos obligatorios."""
        from apps.kernels.work_management.serializers import MaintenanceLogCreateSerializer

        ser = MaintenanceLogCreateSerializer(data={})
        assert not ser.is_valid()
        # Should require at minimum: asset_type, asset_identifier, title, reported_by_id
        errors = ser.errors
        assert len(errors) > 0
