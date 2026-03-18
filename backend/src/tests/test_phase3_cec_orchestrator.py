from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone

from apps.cec.models import CECException, CloseRun
from apps.cec.services import execute_close_run
from apps.iam.models import OrgUnit
from apps.payments.models import CashSession

User = get_user_model()


def _mk_scope():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


@pytest.mark.django_db
def test_cec_orchestrator_dedupes_exceptions_and_manifest_is_reproducible():
    company, branch = _mk_scope()
    user = User.objects.create_user(username="cec_orch_user", password="x")
    run = CloseRun.objects.create(company=company, branch=branch, run_type=CloseRun.RunType.DAILY, created_by=user)

    now = timezone.now()
    CashSession.objects.create(
        company=company,
        branch=branch,
        opened_by=user,
        closed_by=user,
        status=CashSession.Status.CLOSED,
        opened_at=now - timedelta(hours=2),
        closed_at=now - timedelta(minutes=30),
        opening_amount=Decimal("100.00"),
        expected_amount=Decimal("200.00"),
        counted_amount=Decimal("190.00"),
        difference_amount=Decimal("-10.00"),
    )

    req = SimpleNamespace(
        company=company,
        branch=branch,
        user=user,
        request_id="req-phase3-1",
        headers={},
        META={},
    )
    window_start = now - timedelta(days=1)
    window_end = now + timedelta(days=1)

    first = execute_close_run(
        run=run,
        request=req,
        actor=user,
        window_start=window_start,
        window_end=window_end,
        strict=True,
    )
    run.refresh_from_db()
    first_hash = run.output_manifest_hash
    assert first.status == CloseRun.Status.REOPENED_EXCEPTION
    assert first.blocking_exceptions_count >= 1
    assert first.exceptions_opened_count == 1

    second = execute_close_run(
        run=run,
        request=req,
        actor=user,
        window_start=window_start,
        window_end=window_end,
        strict=True,
    )
    run.refresh_from_db()
    assert second.status == CloseRun.Status.REOPENED_EXCEPTION
    assert second.exceptions_opened_count == 0
    assert run.output_manifest_hash == first_hash

    exceptions = CECException.objects.filter(close_run=run, code="CASH_DIFFERENCE_NONZERO", status=CECException.Status.OPEN)
    assert exceptions.count() == 1
