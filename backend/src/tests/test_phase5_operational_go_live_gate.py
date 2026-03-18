from __future__ import annotations

import json
from pathlib import Path

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError


def _write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _pilot_stage3_payload(*, generated_at: str, stable: bool, close_ok: bool = True) -> dict:
    failed_outbox_total = 0 if stable else 1
    return {
        "generated_at": generated_at,
        "action": "stage3",
        "close_attempt": {"ok": bool(close_ok)},
        "snapshot": {
            "failed_outbox": {
                "total": int(failed_outbox_total),
                "by_module": {
                    "BILLING": int(failed_outbox_total),
                    "INVENTORY": 0,
                    "ACCOUNTING": 0,
                },
            },
            "reconciliation": {
                "summary": {
                    "drafts_exception": 0,
                    "pending_operational_events": 0,
                },
                "by_event_type": [],
            },
            "fuel_compensation": {
                "pending_count": 0,
                "failed_count": 0,
            },
        },
    }


def _gate_payload(*, passed: bool) -> dict:
    return {
        "gate_name": "operational_performance_balance_profile",
        "passed": bool(passed),
    }


def _review_payload(
    *,
    generated_at: str,
    review_date: str,
    reviewer: str,
    role: str,
    status: str,
    summary: str,
    final_signoff: bool = False,
) -> dict:
    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "review_date": review_date,
        "reviewer": reviewer,
        "role": role,
        "status": status,
        "summary": summary,
        "linked_evidence": [],
        "final_signoff": bool(final_signoff),
    }


def _excused_day_payload(
    *,
    generated_at: str,
    exception_date: str,
    status: str = "APPROVED",
    exception_type: str = "FORCE_MAJEURE",
) -> dict:
    return {
        "schema_version": 1,
        "generated_at": generated_at,
        "exception_date": exception_date,
        "exception_type": exception_type,
        "status": status,
        "reported_by": "ops_manager",
        "approved_by": "finance_owner",
        "summary": "Cierre por fuerza mayor.",
        "impact": "Sin operación presencial.",
        "linked_evidence": [],
    }


def _build_seven_days_stable(tmp_path: Path):
    for idx in range(7):
        day = idx + 1
        report = _pilot_stage3_payload(
            generated_at=f"2026-03-{day:02d}T10:00:00+00:00",
            stable=True,
        )
        _write_json(tmp_path / f"d{day}" / "pilot_stage3.json", report)
    _write_json(tmp_path / "performance" / "gate_report.json", _gate_payload(passed=True))


def _build_unstable_evidence(tmp_path: Path):
    for idx in range(7):
        day = idx + 1
        report = _pilot_stage3_payload(
            generated_at=f"2026-03-{day:02d}T10:00:00+00:00",
            stable=(day <= 3),  # corta streak de estabilidad
        )
        _write_json(tmp_path / f"d{day}" / "pilot_stage3.json", report)
    _write_json(tmp_path / "performance" / "gate_report.json", _gate_payload(passed=False))


def _write_owner_reviews(
    tmp_path: Path,
    *,
    functional_status: str = "APPROVED",
    technical_status: str = "APPROVED",
    include_final_signoff: bool = True,
):
    _write_json(
        tmp_path / "reviews" / "operational_go_live_review_FUNCTIONAL_20260307_100000.json",
        _review_payload(
            generated_at="2026-03-07T10:00:00+00:00",
            review_date="2026-03-07",
            reviewer="owner_functional",
            role="FUNCTIONAL",
            status=functional_status,
            summary="Revision funcional del piloto.",
        ),
    )
    _write_json(
        tmp_path / "reviews" / "operational_go_live_review_TECHNICAL_20260307_100500.json",
        _review_payload(
            generated_at="2026-03-07T10:05:00+00:00",
            review_date="2026-03-07",
            reviewer="owner_technical",
            role="TECHNICAL",
            status=technical_status,
            summary="Revision tecnica del piloto.",
        ),
    )
    if include_final_signoff:
        _write_json(
            tmp_path / "reviews" / "operational_go_live_final_signoff.json",
            _review_payload(
                generated_at="2026-03-07T10:10:00+00:00",
                review_date="2026-03-07",
                reviewer="owner_technical",
                role="TECHNICAL",
                status="FINAL_APPROVED",
                summary="Aprobacion final para go-live.",
                final_signoff=True,
            ),
        )


def test_verify_operational_pilot_go_live_passes_with_stable_streak_and_signoff(tmp_path: Path):
    _build_seven_days_stable(tmp_path)
    _write_owner_reviews(tmp_path, include_final_signoff=True)
    output = tmp_path / "go_live.json"

    call_command(
        "verify_operational_pilot_go_live",
        evidence_dir=str(tmp_path),
        required_days=7,
        output=str(output),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["go_live_passed"] is True
    checks = {row["name"]: row["passed"] for row in payload.get("checks", [])}
    assert checks.get("pilot_days_available") is True
    assert checks.get("stable_streak_days") is True
    assert checks.get("performance_gate_passed") is True
    assert checks.get("owner_approvals_present") is True
    assert checks.get("open_observations_resolved") is True
    assert checks.get("final_signoff_present") is True
    summary = payload.get("review_summary", {})
    assert summary.get("final_signoff_present") is True
    assert summary.get("latest_status_by_role", {}).get("FUNCTIONAL") == "APPROVED"
    assert summary.get("latest_status_by_role", {}).get("TECHNICAL") == "FINAL_APPROVED"


def test_verify_operational_pilot_go_live_fails_with_unstable_or_gate_fail(tmp_path: Path):
    _build_unstable_evidence(tmp_path)
    _write_owner_reviews(tmp_path, include_final_signoff=True)
    output = tmp_path / "go_live_fail.json"

    with pytest.raises(CommandError):
        call_command(
            "verify_operational_pilot_go_live",
            evidence_dir=str(tmp_path),
            required_days=7,
            output=str(output),
        )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["go_live_passed"] is False
    checks = {row["name"]: row["passed"] for row in payload.get("checks", [])}
    assert checks.get("owner_approvals_present") is True
    assert checks.get("final_signoff_present") is True
    assert checks.get("stable_streak_days") is False
    assert checks.get("performance_gate_passed") is False


def test_verify_operational_pilot_go_live_fails_when_signoff_missing(tmp_path: Path):
    _build_seven_days_stable(tmp_path)
    output = tmp_path / "go_live_no_signoff.json"

    with pytest.raises(CommandError):
        call_command(
            "verify_operational_pilot_go_live",
            evidence_dir=str(tmp_path),
            required_days=7,
            output=str(output),
        )

    payload = json.loads(output.read_text(encoding="utf-8"))
    checks = {row["name"]: row["passed"] for row in payload.get("checks", [])}
    assert checks.get("owner_approvals_present") is False
    assert checks.get("final_signoff_present") is False


def test_verify_operational_pilot_go_live_fails_when_open_observations_exist(tmp_path: Path):
    _build_seven_days_stable(tmp_path)
    _write_owner_reviews(tmp_path, functional_status="OBSERVED", include_final_signoff=True)
    output = tmp_path / "go_live_observed.json"

    with pytest.raises(CommandError):
        call_command(
            "verify_operational_pilot_go_live",
            evidence_dir=str(tmp_path),
            required_days=7,
            output=str(output),
        )

    payload = json.loads(output.read_text(encoding="utf-8"))
    checks = {row["name"]: row["passed"] for row in payload.get("checks", [])}
    assert checks.get("open_observations_resolved") is False
    summary = payload.get("review_summary", {})
    assert "FUNCTIONAL" in list(summary.get("open_observations_roles") or [])


def test_record_operational_go_live_review_writes_default_final_signoff_file(tmp_path: Path):
    call_command(
        "record_operational_go_live_review",
        evidence_dir=str(tmp_path),
        reviewer="owner_technical",
        role="TECHNICAL",
        status="FINAL_APPROVED",
        summary="Aprobacion final del piloto.",
    )

    output = tmp_path / "operational_go_live_final_signoff.json"
    assert output.exists() is True
    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload.get("status") == "FINAL_APPROVED"
    assert payload.get("final_signoff") is True
    assert payload.get("role") == "TECHNICAL"


def test_verify_operational_pilot_go_live_passes_with_excused_day(tmp_path: Path):
    for day in (1, 2, 3, 5, 6, 7):
        _write_json(
            tmp_path / f"d{day}" / "pilot_stage3.json",
            _pilot_stage3_payload(
                generated_at=f"2026-03-{day:02d}T10:00:00+00:00",
                stable=True,
            ),
        )
    _write_json(
        tmp_path / "exceptions" / "operational_go_live_excused_day_FORCE_MAJEURE_20260304_110000.json",
        _excused_day_payload(
            generated_at="2026-03-04T11:00:00+00:00",
            exception_date="2026-03-04",
        ),
    )
    _write_json(tmp_path / "performance" / "gate_report.json", _gate_payload(passed=True))
    _write_owner_reviews(tmp_path, include_final_signoff=True)
    output = tmp_path / "go_live_excused_ok.json"

    call_command(
        "verify_operational_pilot_go_live",
        evidence_dir=str(tmp_path),
        required_days=7,
        allow_excused_days=True,
        max_excused_days=1,
        max_calendar_days=7,
        output=str(output),
    )

    payload = json.loads(output.read_text(encoding="utf-8"))
    assert payload["go_live_passed"] is True
    checks = {row["name"]: row["passed"] for row in payload.get("checks", [])}
    assert checks.get("stable_streak_days") is True
    assert checks.get("excused_days_within_limit") is True
    assert checks.get("calendar_window_within_limit") is True
    summary = payload.get("stability_summary", {})
    assert int(summary.get("stable_streak_days") or 0) == 7
    assert int(summary.get("excused_days_used") or 0) == 1


def test_verify_operational_pilot_go_live_fails_when_excused_days_exceed_limit(tmp_path: Path):
    for day in (1, 2, 4, 6, 7):
        _write_json(
            tmp_path / f"d{day}" / "pilot_stage3.json",
            _pilot_stage3_payload(
                generated_at=f"2026-03-{day:02d}T10:00:00+00:00",
                stable=True,
            ),
        )
    _write_json(
        tmp_path / "exceptions" / "operational_go_live_excused_day_FORCE_MAJEURE_20260303_110000.json",
        _excused_day_payload(
            generated_at="2026-03-03T11:00:00+00:00",
            exception_date="2026-03-03",
        ),
    )
    _write_json(
        tmp_path / "exceptions" / "operational_go_live_excused_day_FORCE_MAJEURE_20260305_110000.json",
        _excused_day_payload(
            generated_at="2026-03-05T11:00:00+00:00",
            exception_date="2026-03-05",
        ),
    )
    _write_json(tmp_path / "performance" / "gate_report.json", _gate_payload(passed=True))
    _write_owner_reviews(tmp_path, include_final_signoff=True)
    output = tmp_path / "go_live_excused_limit_fail.json"

    with pytest.raises(CommandError):
        call_command(
            "verify_operational_pilot_go_live",
            evidence_dir=str(tmp_path),
            required_days=7,
            allow_excused_days=True,
            max_excused_days=1,
            max_calendar_days=7,
            output=str(output),
        )

    payload = json.loads(output.read_text(encoding="utf-8"))
    checks = {row["name"]: row["passed"] for row in payload.get("checks", [])}
    assert checks.get("stable_streak_days") is True
    assert checks.get("excused_days_within_limit") is False


def test_verify_operational_pilot_go_live_fails_when_calendar_window_exceeds_limit(tmp_path: Path):
    for day in (1, 2, 4, 6, 7):
        _write_json(
            tmp_path / f"d{day}" / "pilot_stage3.json",
            _pilot_stage3_payload(
                generated_at=f"2026-03-{day:02d}T10:00:00+00:00",
                stable=True,
            ),
        )
    _write_json(
        tmp_path / "exceptions" / "operational_go_live_excused_day_FORCE_MAJEURE_20260303_110000.json",
        _excused_day_payload(
            generated_at="2026-03-03T11:00:00+00:00",
            exception_date="2026-03-03",
        ),
    )
    _write_json(
        tmp_path / "exceptions" / "operational_go_live_excused_day_FORCE_MAJEURE_20260305_110000.json",
        _excused_day_payload(
            generated_at="2026-03-05T11:00:00+00:00",
            exception_date="2026-03-05",
        ),
    )
    _write_json(tmp_path / "performance" / "gate_report.json", _gate_payload(passed=True))
    _write_owner_reviews(tmp_path, include_final_signoff=True)
    output = tmp_path / "go_live_excused_window_fail.json"

    with pytest.raises(CommandError):
        call_command(
            "verify_operational_pilot_go_live",
            evidence_dir=str(tmp_path),
            required_days=7,
            allow_excused_days=True,
            max_excused_days=2,
            max_calendar_days=6,
            output=str(output),
        )

    payload = json.loads(output.read_text(encoding="utf-8"))
    checks = {row["name"]: row["passed"] for row in payload.get("checks", [])}
    assert checks.get("stable_streak_days") is True
    assert checks.get("calendar_window_within_limit") is False


def test_record_operational_go_live_exception_writes_default_file(tmp_path: Path):
    call_command(
        "record_operational_go_live_exception",
        evidence_dir=str(tmp_path),
        date="2026-03-04",
        exception_type="FORCE_MAJEURE",
        status="APPROVED",
        reported_by="ops_manager",
        approved_by="finance_owner",
        summary="Cierre por fuerza mayor.",
    )

    outputs = list(tmp_path.glob("operational_go_live_excused_day_FORCE_MAJEURE_*.json"))
    assert len(outputs) == 1
    payload = json.loads(outputs[0].read_text(encoding="utf-8"))
    assert payload.get("exception_date") == "2026-03-04"
    assert payload.get("exception_type") == "FORCE_MAJEURE"
    assert payload.get("status") == "APPROVED"
