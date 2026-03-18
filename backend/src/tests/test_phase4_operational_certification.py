from __future__ import annotations

import json
from datetime import timedelta
from pathlib import Path

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.cec.models import CECException, CloseRun
from apps.iam.models import OrgUnit
from apps.integration.models import OutboxEvent
from apps.integration.services import publish_outbox_event

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
            "doc_id": 501,
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
def test_phase4_manifest_export_and_compare_ok(tmp_path):
    company, _ = _mk_scope()
    call_command("seed_posting_rules_v1", company_id=company.id)

    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    call_command("export_phase4_env_manifest", company_id=company.id, output=str(left))
    call_command("export_phase4_env_manifest", company_id=company.id, output=str(right))

    assert left.exists()
    assert right.exists()
    call_command("compare_phase4_env_manifests", left=str(left), right=str(right))


@pytest.mark.django_db
def test_phase4_manifest_compare_detects_drift(tmp_path):
    company, _ = _mk_scope()
    call_command("seed_posting_rules_v1", company_id=company.id)

    left = tmp_path / "left.json"
    right = tmp_path / "right.json"
    call_command("export_phase4_env_manifest", company_id=company.id, output=str(left))
    data = json.loads(Path(left).read_text(encoding="utf-8"))
    data["environment"]["timezone"] = "UTC"
    Path(right).write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    with pytest.raises(CommandError):
        call_command("compare_phase4_env_manifests", left=str(left), right=str(right))


@pytest.mark.django_db
def test_certify_shadow_ledger_run_happy_path(tmp_path):
    company, branch = _mk_scope()
    user = User.objects.create_user(username="cert_ok", password="x")
    call_command("seed_posting_rules_v1", company_id=company.id)
    run = _mk_packaged_run(company=company, branch=branch, user=user)
    _mk_billing_event(company=company, branch=branch, user=user)

    out = tmp_path / "evidence_ok.json"
    call_command("certify_shadow_ledger_run", run_id=str(run.run_id), company_id=company.id, output=str(out))
    payload = json.loads(out.read_text(encoding="utf-8"))

    assert payload["passed"] is True
    assert payload["blocked"] is False
    assert payload["replay_performed"] is True
    assert payload["deterministic_replay"] is True
    assert payload["first_manifest_hash"] == payload["second_manifest_hash"]

    run.refresh_from_db()
    assert run.status == CloseRun.Status.PACKAGED
    assert OutboxEvent.objects.filter(source_module="ACCOUNTING", event_type="ShadowLedgerProjected").exists()


@pytest.mark.django_db
def test_certify_shadow_ledger_run_blocked_path(tmp_path):
    company, branch = _mk_scope()
    user = User.objects.create_user(username="cert_block", password="x")
    run = _mk_packaged_run(company=company, branch=branch, user=user)
    _mk_billing_event(company=company, branch=branch, user=user)

    out = tmp_path / "evidence_block.json"
    call_command(
        "certify_shadow_ledger_run",
        run_id=str(run.run_id),
        company_id=company.id,
        expect_blocked=True,
        output=str(out),
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    run.refresh_from_db()

    assert payload["passed"] is True
    assert payload["blocked"] is True
    assert payload["replay_performed"] is False
    assert run.status == CloseRun.Status.REOPENED_EXCEPTION
    assert CECException.objects.filter(
        close_run=run,
        source_module="ACCOUNTING",
        status=CECException.Status.OPEN,
    ).exists()
