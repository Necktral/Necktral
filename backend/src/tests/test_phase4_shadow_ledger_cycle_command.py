from __future__ import annotations

import json
import uuid
from datetime import timedelta
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.modulos.cec.models import CloseRun
from apps.modulos.iam.models import OrgUnit
from apps.modulos.integration.models import InboxEvent
from apps.modulos.integration.services import publish_outbox_event

User = get_user_model()


def _mk_scope():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


def _mk_packaged_run(*, company: OrgUnit, branch: OrgUnit, user):
    now = timezone.now()
    run = CloseRun.objects.create(
        company=company,
        branch=branch,
        run_type=CloseRun.RunType.DAILY,
        status=CloseRun.Status.PACKAGED,
        window_start=now - timedelta(hours=1),
        window_end=now + timedelta(hours=1),
        output_manifest_hash="a" * 64,
        summary_json={"schema_version": 1},
        created_by=user,
    )
    publish_outbox_event(
        source_module="CEC",
        event_type="CloseRunPackaged",
        payload={
            "run_id": str(run.run_id),
            "output_manifest_hash": run.output_manifest_hash,
            "consistency_score": 100,
        },
        company=company,
        branch=branch,
        actor_user=user,
    )
    return run


def _mk_billing_event(*, company: OrgUnit, branch: OrgUnit, user):
    publish_outbox_event(
        source_module="BILLING",
        event_type="DocumentIssued",
        payload={
            "doc_id": 9001,
            "doc_type": "INVOICE",
            "series": "A",
            "number": 1,
            "currency": "NIO",
            "subtotal": "100.00",
            "tax_total": "15.00",
            "total": "115.00",
            "is_fiscal": True,
            "fiscal_adapter_mode": "B",
        },
        company=company,
        branch=branch,
        actor_user=user,
    )


@pytest.mark.django_db
def test_run_shadow_ledger_cycle_ok(tmp_path):
    company, branch = _mk_scope()
    user = User.objects.create_user(username="cycle_ok", password="x")
    call_command("seed_posting_rules_v1", company_id=company.id)
    _mk_packaged_run(company=company, branch=branch, user=user)
    _mk_billing_event(company=company, branch=branch, user=user)

    out = tmp_path / "cycle_ok.json"
    call_command(
        "run_shadow_ledger_cycle",
        company_id=company.id,
        output=str(out),
    )
    payload = json.loads(Path(out).read_text(encoding="utf-8"))

    assert payload["cycle_passed"] is True
    assert payload["projection"]["processed"] >= 1
    assert payload["checks"][0]["name"] == "inbox_failed_within_threshold"
    assert payload["evidence_hash"]
    assert payload["signature_type"] in ("sha256", "hmac-sha256")


@pytest.mark.django_db
def test_run_shadow_ledger_cycle_fails_with_failed_inbox():
    company, _ = _mk_scope()
    call_command("seed_posting_rules_v1", company_id=company.id)
    InboxEvent.objects.create(
        event_id=uuid.uuid4(),
        consumer="accounting.projector",
        source_module="CEC",
        event_type="CloseRunPackaged",
        payload={"run_id": "x"},
        status=InboxEvent.Status.FAILED,
        last_error="temporary failure",
    )

    with pytest.raises(CommandError):
        call_command(
            "run_shadow_ledger_cycle",
            company_id=company.id,
            max_inbox_failed=0,
        )

