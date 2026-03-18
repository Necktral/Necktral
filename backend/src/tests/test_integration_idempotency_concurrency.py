from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import uuid

import pytest
from django.contrib.auth import get_user_model
from django.db import close_old_connections, connections

from apps.iam.models import OrgUnit
from apps.integration.models import InboxEvent, OutboxEvent
from apps.integration.services import create_or_get_inbox_event
from modulos.estacion_servicios.models import FuelShift, FuelShiftStatus
from modulos.estacion_servicios.services import open_shift


@pytest.mark.django_db(transaction=True)
def test_inbox_create_or_get_is_concurrent_idempotent():
    event = OutboxEvent.objects.create(
        source_module="CEC",
        event_type="CloseRunPackaged",
        payload={"run_id": str(uuid.uuid4())},
    )
    consumer = "accounting.projector"

    def _worker() -> tuple[int, bool]:
        close_old_connections()
        try:
            row, created = create_or_get_inbox_event(event=event, consumer=consumer)
            return int(row.id), bool(created)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: _worker(), range(16)))
    connections.close_all()

    row_ids = {row_id for row_id, _ in results}
    assert len(row_ids) == 1
    assert InboxEvent.objects.filter(event_id=event.event_id, consumer=consumer).count() == 1


@pytest.mark.django_db(transaction=True)
def test_open_shift_is_concurrent_open_or_return_existing():
    User = get_user_model()
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="Holding")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="Company", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="Branch", parent=company)
    actor = User.objects.create_user(username=f"fuel_{uuid.uuid4().hex[:8]}", password="pass12345")

    def _worker() -> tuple[int, bool]:
        close_old_connections()
        try:
            result = open_shift(request=None, company=company, branch=branch, actor_user=actor)
            return int(result.shift.id), bool(result.duplicate)
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=8) as pool:
        results = list(pool.map(lambda _: _worker(), range(12)))
    connections.close_all()

    shift_ids = {shift_id for shift_id, _ in results}
    assert len(shift_ids) == 1
    assert any(not duplicate for _, duplicate in results)
    assert any(duplicate for _, duplicate in results)
    assert FuelShift.objects.filter(company=company, branch=branch, status=FuelShiftStatus.OPEN).count() == 1
