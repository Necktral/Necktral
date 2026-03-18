from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.iam.models import OrgUnit


def _mk_scope() -> tuple[OrgUnit, OrgUnit]:
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


def _write_json(path, payload: dict) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _gate_payload(label: str) -> dict:
    return {
        "schema_version": 1,
        "generated_at": timezone.now().isoformat(),
        "go_live_passed": True,
        "checks": [{"name": f"{label}_ok", "passed": True, "detail": {}}],
        "evidence_hash": "a" * 64,
        "signature": "a" * 64,
        "signature_type": "sha256",
    }


def _preflight_payload(*, company_id: int, branch_id: int, passed: bool) -> dict:
    return {
        "schema_version": 1,
        "generated_at": timezone.now().isoformat(),
        "pilot_scope": {"company_id": company_id, "branch_id": branch_id},
        "preflight_passed": bool(passed),
        "checks": [{"name": "preflight", "passed": bool(passed), "detail": {}}],
        "evidence_hash": "d" * 64,
    }


def _snapshot_payload(*, company_id: int, branch_id: int, passed: bool) -> dict:
    return {
        "schema_version": 1,
        "generated_at": timezone.now().isoformat(),
        "pilot_scope": {"company_id": company_id, "branch_id": branch_id},
        "snapshot_passed": bool(passed),
        "checks": [{"name": "snapshot", "passed": bool(passed), "detail": {}}],
        "evidence_hash": "e" * 64,
    }


def _security_summary(*, passed: bool) -> dict:
    val = bool(passed)
    return {
        "status": "PASS" if val else "FAIL",
        "checks": {
            "gitleaks_clean": val,
            "pip_audit_blocking_clean": val,
            "npm_audit_blocking_clean": val,
            "manage_check_pass": val,
            "audit_chain_pass": val,
            "security_pytest_pass": val,
        },
    }


@pytest.mark.django_db
def test_phase8_manifest_export_compare_and_drift(tmp_path):
    company, branch = _mk_scope()
    left = tmp_path / "phase8_left.json"
    right = tmp_path / "phase8_right.json"
    drift = tmp_path / "phase8_drift.json"

    call_command(
        "export_phase8_env_manifest",
        company_id=company.id,
        branch_id=branch.id,
        parent_company_id=company.id,
        company_ids=[company.id],
        output=str(left),
    )
    call_command(
        "export_phase8_env_manifest",
        company_id=company.id,
        branch_id=branch.id,
        parent_company_id=company.id,
        company_ids=[company.id],
        output=str(right),
    )
    call_command("compare_phase8_env_manifests", left=str(left), right=str(right), strict=True)

    payload = json.loads(left.read_text(encoding="utf-8"))
    payload["phase7"]["parity_fingerprint"] = "DIFF"
    _write_json(drift, payload)
    with pytest.raises(CommandError):
        call_command("compare_phase8_env_manifests", left=str(left), right=str(drift), strict=True)


@pytest.mark.django_db
def test_phase8_cutover_and_burnin_commands(tmp_path):
    company, branch = _mk_scope()
    staging_manifest = tmp_path / "staging_manifest.json"
    prod_manifest = tmp_path / "prod_manifest.json"
    phase6_gate = tmp_path / "phase6_gate.json"
    phase7_gate = tmp_path / "phase7_gate.json"
    phase7b_gate = tmp_path / "phase7b_gate.json"
    cutover_report = tmp_path / "phase8_cutover.json"
    burnin_report = tmp_path / "phase8_burnin.json"
    evidence_dir = tmp_path / "burnin_evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    call_command(
        "export_phase8_env_manifest",
        company_id=company.id,
        branch_id=branch.id,
        parent_company_id=company.id,
        company_ids=[company.id],
        output=str(staging_manifest),
    )
    call_command(
        "export_phase8_env_manifest",
        company_id=company.id,
        branch_id=branch.id,
        parent_company_id=company.id,
        company_ids=[company.id],
        output=str(prod_manifest),
    )
    _write_json(phase6_gate, _gate_payload("phase6"))
    _write_json(phase7_gate, _gate_payload("phase7"))
    _write_json(phase7b_gate, _gate_payload("phase7b"))

    call_command(
        "certify_phase8_cutover",
        company_id=company.id,
        branch_id=branch.id,
        parent_company_id=company.id,
        company_ids=[company.id],
        staging_manifest=str(staging_manifest),
        prod_manifest=str(prod_manifest),
        phase6_gate=str(phase6_gate),
        phase7_gate=str(phase7_gate),
        phase7b_gate=str(phase7b_gate),
        output=str(cutover_report),
    )
    cutover = json.loads(cutover_report.read_text(encoding="utf-8"))
    assert cutover["cutover_passed"] is True
    assert cutover["evidence_hash"]

    call_command(
        "run_phase8_burnin_cycle",
        company_id=company.id,
        branch_id=branch.id,
        parent_company_id=company.id,
        company_ids=[company.id],
        output=str(burnin_report),
        no_strict=True,
    )
    burnin = json.loads(burnin_report.read_text(encoding="utf-8"))
    assert "checks" in burnin
    assert "health" in burnin

    now = timezone.now()
    _write_json(
        evidence_dir / "phase8_burn_1.json",
        {"generated_at": now.isoformat(), "cycle_passed": True, "evidence_hash": "b" * 64},
    )
    _write_json(
        evidence_dir / "phase8_burn_2.json",
        {"generated_at": (now + timedelta(days=1)).isoformat(), "cycle_passed": True, "evidence_hash": "c" * 64},
    )
    _write_json(
        evidence_dir / "phase8_burnin_calendar_tracker.json",
        {"generated_at": (now + timedelta(days=2)).isoformat(), "cycle_passed": False},
    )
    call_command(
        "verify_phase8_burn_in",
        evidence_dir=str(evidence_dir),
        min_days=2,
        max_failed_days=0,
        strict=True,
    )


@pytest.mark.django_db
def test_phase8_precutover_and_rollback_commands(tmp_path):
    company, branch = _mk_scope()
    staging_manifest = tmp_path / "staging_manifest.json"
    prod_manifest = tmp_path / "prod_manifest.json"
    baseline = tmp_path / "phase8_baseline.json"
    preflight = tmp_path / "preflight.json"
    snapshot = tmp_path / "snapshot.json"
    security = tmp_path / "security.json"
    precutover = tmp_path / "precutover.json"
    rollback_ok = tmp_path / "rollback_ok.json"
    rollback_fail = tmp_path / "rollback_fail.json"
    burnin_fail = tmp_path / "burnin_fail.json"

    call_command(
        "export_phase8_env_manifest",
        company_id=company.id,
        branch_id=branch.id,
        parent_company_id=company.id,
        company_ids=[company.id],
        output=str(staging_manifest),
    )
    call_command(
        "export_phase8_env_manifest",
        company_id=company.id,
        branch_id=branch.id,
        parent_company_id=company.id,
        company_ids=[company.id],
        output=str(prod_manifest),
    )
    call_command(
        "export_phase8_release_baseline",
        company_id=company.id,
        branch_id=branch.id,
        parent_company_id=company.id,
        company_ids=[company.id],
        backend_image="registry.local/erp:phase8",
        output=str(baseline),
    )

    _write_json(preflight, _preflight_payload(company_id=company.id, branch_id=branch.id, passed=True))
    _write_json(snapshot, _snapshot_payload(company_id=company.id, branch_id=branch.id, passed=True))
    _write_json(security, _security_summary(passed=True))

    call_command(
        "verify_phase8_precutover",
        company_id=company.id,
        branch_id=branch.id,
        parent_company_id=company.id,
        company_ids=[company.id],
        staging_manifest=str(staging_manifest),
        prod_manifest=str(prod_manifest),
        release_baseline=str(baseline),
        preflight_report=str(preflight),
        snapshot_report=str(snapshot),
        security_summary=str(security),
        output=str(precutover),
        no_strict=True,
    )
    precut_payload = json.loads(precutover.read_text(encoding="utf-8"))
    assert precut_payload["precutover_passed"] is True
    assert precut_payload["evidence_hash"]

    cutover_ok = tmp_path / "cutover_ok.json"
    _write_json(
        cutover_ok,
        {
            "schema_version": 1,
            "generated_at": timezone.now().isoformat(),
            "cutover_passed": True,
            "checks": [
                {"name": "phase6_gate_valid", "passed": True},
                {"name": "phase7_gate_valid", "passed": True},
                {"name": "phase7b_gate_valid", "passed": True},
            ],
            "evidence_hash": "f" * 64,
        },
    )
    call_command(
        "evaluate_phase8_rollback",
        cutover_report=str(cutover_ok),
        output=str(rollback_ok),
    )
    rollback_payload_ok = json.loads(rollback_ok.read_text(encoding="utf-8"))
    assert rollback_payload_ok["rollback_required"] is False

    now = timezone.now()
    _write_json(
        burnin_fail,
        {
            "schema_version": 1,
            "generated_at": (now - timedelta(minutes=20)).isoformat(),
            "health": {
                "phase6": {"inbox_failed_count": 1, "outbox_failed_count": 1, "cec_blocking_open_count": 1},
                "phase7a": {"inbox_failed_count": 0, "outbox_failed_count": 0, "missing_lines_count": 1, "stale_revaluation_count": 1},
                "phase7b": {"inbox_failed_count": 0, "outbox_failed_count": 0},
            },
        },
    )
    with pytest.raises(CommandError):
        call_command(
            "evaluate_phase8_rollback",
            cutover_report=str(cutover_ok),
            burnin_reports=[str(burnin_fail)],
            fail_on_rollback=True,
            output=str(rollback_fail),
        )
    rollback_payload_fail = json.loads(rollback_fail.read_text(encoding="utf-8"))
    assert rollback_payload_fail["rollback_required"] is True


@pytest.mark.django_db
def test_phase8_accountant_review_and_signoff_commands(tmp_path):
    evidence_dir = tmp_path / "phase8_evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)

    with pytest.raises(CommandError):
        call_command(
            "verify_phase8_accountant_signoff",
            evidence_dir=str(evidence_dir),
            window_start="2026-03-09",
            window_end="2026-03-22",
            strict=True,
        )

    call_command(
        "record_phase8_accountant_review",
        evidence_dir=str(evidence_dir),
        date="2026-03-10",
        reviewer="contador",
        status="OBSERVED",
        summary="Observación pendiente de ajuste en clasificación de costo.",
    )
    with pytest.raises(CommandError):
        call_command(
            "verify_phase8_accountant_signoff",
            evidence_dir=str(evidence_dir),
            window_start="2026-03-09",
            window_end="2026-03-22",
            strict=True,
        )

    call_command(
        "record_phase8_accountant_review",
        evidence_dir=str(evidence_dir),
        date="2026-03-10",
        reviewer="contador",
        status="APPROVED",
        summary="Observación resuelta con ajuste contable.",
    )
    with pytest.raises(CommandError):
        call_command(
            "verify_phase8_accountant_signoff",
            evidence_dir=str(evidence_dir),
            window_start="2026-03-09",
            window_end="2026-03-22",
            strict=True,
        )

    call_command(
        "record_phase8_accountant_review",
        evidence_dir=str(evidence_dir),
        date="2026-03-22",
        reviewer="contador.principal",
        status="FINAL_APPROVED",
        summary="Aprobación final del contador para cierre de burn-in F8.",
    )
    verify_output = tmp_path / "accountant_verify.json"
    call_command(
        "verify_phase8_accountant_signoff",
        evidence_dir=str(evidence_dir),
        window_start="2026-03-09",
        window_end="2026-03-22",
        output=str(verify_output),
        strict=True,
    )
    verify_payload = json.loads(verify_output.read_text(encoding="utf-8"))
    assert verify_payload["signoff_passed"] is True
    assert verify_payload["final_approved_present"] is True


@pytest.mark.django_db
def test_verify_phase8_burn_in_uses_filename_day_for_smoke(tmp_path):
    evidence_dir = tmp_path / "phase8_smoke_evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    now = timezone.now()

    # Smoke por fechas simuladas: los archivos representan días distintos
    # aunque generated_at sea el mismo instante de ejecución.
    payload = {"generated_at": now.isoformat(), "cycle_passed": True, "evidence_hash": "f" * 64}
    _write_json(evidence_dir / "phase8_burn_20260310.json", payload)
    _write_json(evidence_dir / "phase8_burn_20260311.json", payload)

    call_command(
        "verify_phase8_burn_in",
        evidence_dir=str(evidence_dir),
        min_days=2,
        max_failed_days=0,
        strict=True,
    )
