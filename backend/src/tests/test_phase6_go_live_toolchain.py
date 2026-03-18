from __future__ import annotations

import json
import uuid
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.iam.models import OrgUnit
from modulos.facturacion.certification import build_phase6_evidence, collect_phase6_env_manifest


def _mk_scope() -> tuple[OrgUnit, OrgUnit]:
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


def _write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _blocked_evidence_payload(*, company_id: int, branch_id: int) -> dict:
    payload = {
        "schema_version": 1,
        "generated_at": "2026-03-08T00:00:00+00:00",
        "pilot_scope": {"company_id": company_id, "branch_id": branch_id},
        "run_id": str(uuid.uuid4()),
        "expect_blocked": True,
        "passed": True,
        "blocked": True,
        "deterministic_replay": True,
        "close_run_status": "REOPENED_EXCEPTION",
        "first_manifest_hash": "b" * 64,
        "second_manifest_hash": "b" * 64,
        "manifest_hash": "b" * 64,
        "first_counts": {
            "print_jobs_total": 2,
            "print_jobs_pending": 0,
            "print_jobs_retry": 0,
            "print_jobs_printed": 0,
            "print_jobs_failed": 2,
            "doc_print_attempt_count": 2,
            "cec_blocking_exceptions": 1,
            "cec_total_exceptions": 1,
            "contingency_docs_open": 1,
            "billing_events_for_doc": 4,
        },
        "second_counts": {
            "print_jobs_total": 2,
            "print_jobs_pending": 0,
            "print_jobs_retry": 0,
            "print_jobs_printed": 0,
            "print_jobs_failed": 2,
            "doc_print_attempt_count": 2,
            "cec_blocking_exceptions": 1,
            "cec_total_exceptions": 1,
            "contingency_docs_open": 1,
            "billing_events_for_doc": 4,
        },
        "job_counts": {"total": 2, "printed": 0, "retry": 0, "failed": 2, "pending": 0},
        "contingency_counts": {"open_contingency_docs": 1},
        "cec_blocking_exceptions": 1,
        "go_live_passed": True,
        "env_manifest": collect_phase6_env_manifest(company_id=company_id, branch_id=branch_id),
    }
    return build_phase6_evidence(payload=payload, secret="")


@pytest.mark.django_db
def test_phase6_manifest_export_and_compare_ok(tmp_path):
    company, branch = _mk_scope()
    call_command("set_branch_fiscal_mode", company_id=company.id, branch_id=branch.id, mode="B")

    left = tmp_path / "phase6_left.json"
    right = tmp_path / "phase6_right.json"
    call_command("export_phase6_env_manifest", company_id=company.id, branch_id=branch.id, output=str(left))
    call_command("export_phase6_env_manifest", company_id=company.id, branch_id=branch.id, output=str(right))

    assert left.exists()
    assert right.exists()
    call_command("compare_phase6_env_manifests", left=str(left), right=str(right))


@pytest.mark.django_db
def test_phase6_manifest_compare_detects_drift(tmp_path):
    company, branch = _mk_scope()
    call_command("set_branch_fiscal_mode", company_id=company.id, branch_id=branch.id, mode="B")

    left = tmp_path / "phase6_left.json"
    right = tmp_path / "phase6_right.json"
    call_command("export_phase6_env_manifest", company_id=company.id, branch_id=branch.id, output=str(left))
    payload = json.loads(Path(left).read_text(encoding="utf-8"))
    payload["environment"]["timezone"] = "UTC"
    _write_json(right, payload)

    with pytest.raises(CommandError):
        call_command("compare_phase6_env_manifests", left=str(left), right=str(right))


@pytest.mark.django_db
def test_certify_adapter_b_run_happy_and_blocked(tmp_path):
    company, branch = _mk_scope()

    happy = tmp_path / "phase6_happy.json"
    call_command(
        "certify_adapter_b_run",
        company_id=company.id,
        branch_id=branch.id,
        output=str(happy),
    )
    happy_payload = json.loads(happy.read_text(encoding="utf-8"))
    assert happy_payload["passed"] is True
    assert happy_payload["go_live_passed"] is True
    assert happy_payload["blocked"] is False
    assert happy_payload["deterministic_replay"] is True
    assert happy_payload["close_run_status"] == "PACKAGED"
    assert happy_payload["job_counts"]["printed"] > 0

    blocked = tmp_path / "phase6_blocked.json"
    call_command(
        "certify_adapter_b_run",
        company_id=company.id,
        branch_id=branch.id,
        expect_blocked=True,
        output=str(blocked),
    )
    blocked_payload = json.loads(blocked.read_text(encoding="utf-8"))
    assert blocked_payload["passed"] is True
    assert blocked_payload["go_live_passed"] is True
    assert blocked_payload["blocked"] is True
    assert blocked_payload["close_run_status"] == "REOPENED_EXCEPTION"
    assert blocked_payload["cec_blocking_exceptions"] > 0


@pytest.mark.django_db
def test_verify_phase6_go_live_passes(tmp_path):
    company, branch = _mk_scope()

    left = tmp_path / "phase6_staging.json"
    right = tmp_path / "phase6_prod.json"
    happy = tmp_path / "phase6_happy.json"
    blocked = tmp_path / "phase6_blocked.json"
    out = tmp_path / "phase6_gate.json"

    call_command("set_branch_fiscal_mode", company_id=company.id, branch_id=branch.id, mode="B")
    call_command("export_phase6_env_manifest", company_id=company.id, branch_id=branch.id, output=str(left))
    call_command("export_phase6_env_manifest", company_id=company.id, branch_id=branch.id, output=str(right))
    call_command("certify_adapter_b_run", company_id=company.id, branch_id=branch.id, output=str(happy))
    _write_json(blocked, _blocked_evidence_payload(company_id=company.id, branch_id=branch.id))

    call_command(
        "verify_phase6_go_live",
        company_id=company.id,
        branch_id=branch.id,
        staging_manifest=str(left),
        prod_manifest=str(right),
        happy_evidence=str(happy),
        blocked_evidence=str(blocked),
        output=str(out),
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["go_live_passed"] is True
    assert payload["evidence_hash"]
    assert payload["signature_type"] in ("sha256", "hmac-sha256")


@pytest.mark.django_db
def test_run_adapter_b_cycle_fails_when_threshold_exceeded(tmp_path):
    company, branch = _mk_scope()
    call_command("set_branch_fiscal_mode", company_id=company.id, branch_id=branch.id, mode="B")
    call_command("certify_adapter_b_run", company_id=company.id, branch_id=branch.id, expect_blocked=True)

    with pytest.raises(CommandError):
        call_command(
            "run_adapter_b_cycle",
            company_id=company.id,
            branch_id=branch.id,
            max_open_contingency=0,
            output=str(tmp_path / "cycle.json"),
        )
