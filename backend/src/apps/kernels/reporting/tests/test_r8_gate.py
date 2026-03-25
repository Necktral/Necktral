from __future__ import annotations

import json
from pathlib import Path

import pytest
from django.core.management import call_command

from apps.kernels.reporting.models import ReportRun


@pytest.mark.django_db
def test_reporting_r8_gate_warn_mode_does_not_fail(tmp_path: Path):
    ReportRun.objects.create(
        dataset_key="accounting.pnl.period",
        status="SUCCEEDED",
        quality_status="FAIL",
        quality_checks_json=[{"name": "required_totals", "status": "FAIL"}],
        row_count=1,
        duration_ms=120,
    )
    out = tmp_path / "gate_warn.json"
    call_command(
        "reporting_r8_gate",
        output=str(out),
        today="2026-04-01",
        warn_until="2026-04-07",
        hard_fail_from="2026-04-08",
        window_hours=24,
    )
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["mode"] == "WARN"
    assert payload["gate_status"] == "WARN"
    assert payload["failure_class"] == "quality_breach"
    assert payload["trigger_metric"] == "accounting.pnl.period.quality_fail_runs"
    assert isinstance(payload["breaches"], list) and payload["breaches"]


@pytest.mark.django_db
def test_reporting_r8_gate_hard_fail_mode_blocks(tmp_path: Path):
    ReportRun.objects.create(
        dataset_key="accounting.pnl.period",
        status="SUCCEEDED",
        quality_status="FAIL",
        quality_checks_json=[{"name": "required_totals", "status": "FAIL"}],
        row_count=1,
        duration_ms=120,
    )
    out = tmp_path / "gate_fail.json"
    with pytest.raises(SystemExit) as exc:
        call_command(
            "reporting_r8_gate",
            output=str(out),
            today="2026-04-08",
            warn_until="2026-04-07",
            hard_fail_from="2026-04-08",
            window_hours=24,
        )
    assert exc.value.code == 2
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["mode"] == "HARD_FAIL"
    assert payload["gate_status"] == "FAIL"
    assert payload["failure_class"] == "quality_breach"
    assert payload["trigger_metric"] == "accounting.pnl.period.quality_fail_runs"


@pytest.mark.django_db
def test_reporting_r8_gate_prioritizes_app_error_over_quality(tmp_path: Path):
    ReportRun.objects.create(
        dataset_key="accounting.pnl.period",
        status="FAILED",
        quality_status="FAIL",
        quality_checks_json=[{"name": "required_totals", "status": "FAIL"}],
        row_count=0,
        duration_ms=0,
        error_detail="boom",
    )
    out = tmp_path / "gate_app_error.json"
    with pytest.raises(SystemExit) as exc:
        call_command(
            "reporting_r8_gate",
            output=str(out),
            today="2026-04-08",
            warn_until="2026-04-07",
            hard_fail_from="2026-04-08",
            window_hours=24,
        )
    assert exc.value.code == 2
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["failure_class"] == "app_error"
    assert payload["trigger_metric"] == "runs_failed"
    assert any(b.get("failure_class") == "app_error" for b in payload["breaches"])


@pytest.mark.django_db
def test_reporting_r8_gate_classifies_infra_error_when_observability_fails(tmp_path: Path, monkeypatch):
    from apps.kernels.reporting.management.commands import reporting_r8_gate as gate_module

    def _boom(*args, **kwargs):  # noqa: ARG001
        raise RuntimeError("snapshot failed")

    monkeypatch.setattr(gate_module, "build_reporting_observability", _boom)

    out = tmp_path / "gate_infra_error.json"
    with pytest.raises(SystemExit) as exc:
        call_command(
            "reporting_r8_gate",
            output=str(out),
            today="2026-04-08",
            warn_until="2026-04-07",
            hard_fail_from="2026-04-08",
            window_hours=24,
        )
    assert exc.value.code == 2
    payload = json.loads(out.read_text(encoding="utf-8"))
    assert payload["failure_class"] == "infra_error"
    assert payload["trigger_metric"] == "observability.build_error"
    assert any(b.get("metric") == "observability.build_error" for b in payload["breaches"])
