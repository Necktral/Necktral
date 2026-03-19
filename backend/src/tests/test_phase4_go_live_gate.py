from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.modulos.accounting.certification import collect_phase4_env_manifest
from apps.modulos.iam.models import OrgUnit
from apps.modulos.integration.models import InboxEvent


def _mk_company() -> OrgUnit:
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    return OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _happy_evidence_payload(*, run_id: str) -> dict:
    return {
        "run_id": run_id,
        "passed": True,
        "blocked": False,
        "replay_performed": True,
        "deterministic_replay": True,
        "close_run_status": "PACKAGED",
        "first_manifest_hash": "a" * 64,
        "second_manifest_hash": "a" * 64,
        "first_counts": {
            "economic_events": 2,
            "journal_drafts": 2,
            "open_accounting_exceptions": 0,
        },
        "second_counts": {
            "economic_events": 2,
            "journal_drafts": 2,
            "open_accounting_exceptions": 0,
        },
    }


def _blocked_evidence_payload(*, run_id: str) -> dict:
    return {
        "run_id": run_id,
        "passed": True,
        "blocked": True,
        "replay_performed": False,
        "deterministic_replay": True,
        "close_run_status": "REOPENED_EXCEPTION",
        "first_manifest_hash": "b" * 64,
        "second_manifest_hash": "b" * 64,
        "first_counts": {
            "economic_events": 2,
            "journal_drafts": 0,
            "open_accounting_exceptions": 2,
        },
        "second_counts": {
            "economic_events": 2,
            "journal_drafts": 0,
            "open_accounting_exceptions": 2,
        },
    }


@pytest.mark.django_db
def test_verify_phase4_go_live_passes(tmp_path):
    company = _mk_company()
    call_command("seed_posting_rules_v1", company_id=company.id)

    left = tmp_path / "staging.json"
    right = tmp_path / "prod.json"
    happy = tmp_path / "happy.json"
    blocked = tmp_path / "blocked.json"
    out = tmp_path / "gate_report.json"

    manifest = collect_phase4_env_manifest(company_id=company.id)
    _write_json(left, manifest)
    _write_json(right, manifest)
    _write_json(happy, _happy_evidence_payload(run_id=str(uuid.uuid4())))
    _write_json(blocked, _blocked_evidence_payload(run_id=str(uuid.uuid4())))

    call_command(
        "verify_phase4_go_live",
        company_id=company.id,
        staging_manifest=str(left),
        prod_manifest=str(right),
        happy_evidence=str(happy),
        blocked_evidence=str(blocked),
        output=str(out),
    )

    report = json.loads(out.read_text(encoding="utf-8"))
    assert report["go_live_passed"] is True
    assert report["evidence_hash"]
    assert report["signature_type"] in ("sha256", "hmac-sha256")


@pytest.mark.django_db
def test_verify_phase4_go_live_fails_on_drift(tmp_path):
    company = _mk_company()
    call_command("seed_posting_rules_v1", company_id=company.id)

    left = tmp_path / "staging.json"
    right = tmp_path / "prod.json"
    happy = tmp_path / "happy.json"
    blocked = tmp_path / "blocked.json"

    manifest = collect_phase4_env_manifest(company_id=company.id)
    drifted = dict(manifest)
    drifted_env = dict(manifest.get("environment") or {})
    drifted_env["timezone"] = "UTC"
    drifted["environment"] = drifted_env

    _write_json(left, manifest)
    _write_json(right, drifted)
    _write_json(happy, _happy_evidence_payload(run_id=str(uuid.uuid4())))
    _write_json(blocked, _blocked_evidence_payload(run_id=str(uuid.uuid4())))

    with pytest.raises(CommandError):
        call_command(
            "verify_phase4_go_live",
            company_id=company.id,
            staging_manifest=str(left),
            prod_manifest=str(right),
            happy_evidence=str(happy),
            blocked_evidence=str(blocked),
        )


@pytest.mark.django_db
def test_verify_phase4_go_live_fails_on_inbox_failed(tmp_path):
    company = _mk_company()
    call_command("seed_posting_rules_v1", company_id=company.id)

    left = tmp_path / "staging.json"
    right = tmp_path / "prod.json"
    happy = tmp_path / "happy.json"
    blocked = tmp_path / "blocked.json"

    manifest = collect_phase4_env_manifest(company_id=company.id)
    _write_json(left, manifest)
    _write_json(right, manifest)
    _write_json(happy, _happy_evidence_payload(run_id=str(uuid.uuid4())))
    _write_json(blocked, _blocked_evidence_payload(run_id=str(uuid.uuid4())))

    InboxEvent.objects.create(
        event_id=uuid.uuid4(),
        consumer="accounting.projector",
        source_module="CEC",
        event_type="CloseRunPackaged",
        payload={"run_id": "x"},
        status=InboxEvent.Status.FAILED,
        last_error="broker timeout",
    )

    with pytest.raises(CommandError):
        call_command(
            "verify_phase4_go_live",
            company_id=company.id,
            staging_manifest=str(left),
            prod_manifest=str(right),
            happy_evidence=str(happy),
            blocked_evidence=str(blocked),
            max_inbox_failed=0,
        )

