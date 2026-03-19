from __future__ import annotations

from types import SimpleNamespace

import pytest

from apps.modulos.accounting import certification_phase12 as phase12


def _dispatch_result():
    return SimpleNamespace(attempted=0, sent=0, retried=0, failed=0)


def _health():
    return {
        "phase7a": {
            "missing_lines_count": 0,
            "stale_revaluation_count": 0,
            "unbalanced_entries_count": 0,
            "inbox_failed_count": 0,
            "outbox_failed_count": 0,
        },
        "phase7b": {
            "open_intercompany_count": 0,
            "disputed_intercompany_count": 0,
            "blocked_consolidation_count": 0,
            "open_consolidation_exception_count": 0,
            "inbox_failed_count": 0,
            "outbox_failed_count": 0,
        },
        "inbox_failed_count": 0,
        "outbox_failed_count": 0,
    }


def _patch_common(monkeypatch: pytest.MonkeyPatch, *, reval_status: str) -> None:
    monkeypatch.setattr(phase12, "dispatch_outbox_events", lambda *args, **kwargs: _dispatch_result())
    monkeypatch.setattr(
        phase12,
        "post_journal_drafts",
        lambda *args, **kwargs: SimpleNamespace(attempted=1, approved=0, posted=0, skipped=1, failed=0, errors=[]),
    )
    monkeypatch.setattr(
        phase12,
        "run_fx_revaluation",
        lambda *args, **kwargs: SimpleNamespace(
            run_id="reval-1",
            status=reval_status,
            idempotent=True,
            entries_created=0,
            issues_count=1 if reval_status == "BLOCKED" else 0,
        ),
    )
    monkeypatch.setattr(
        phase12,
        "run_intercompany_cycle",
        lambda *args, **kwargs: SimpleNamespace(
            processed=0,
            confirmed=0,
            differences=0,
            disputed=0,
            closed=0,
            open_items=0,
            report_hash="ic-hash",
        ),
    )
    monkeypatch.setattr(
        phase12,
        "run_consolidation",
        lambda *args, **kwargs: SimpleNamespace(
            run_id="cons-1",
            status="COMPLETED",
            idempotent=True,
            manifest_hash="cons-hash",
            issues_count=0,
        ),
    )
    monkeypatch.setattr(phase12, "collect_phase12_operational_health", lambda *args, **kwargs: _health())


def test_fx_blocked_policy_alert_allows_blocked_with_warning(monkeypatch: pytest.MonkeyPatch):
    _patch_common(monkeypatch, reval_status="BLOCKED")
    result = phase12.run_phase12_monthly_close(
        company_id=5,
        parent_company_id=5,
        company_ids=[5],
        year=2026,
        month=3,
        fx_blocked_policy="ALERT",
    )
    assert result.cycle_passed is True
    assert result.report["fx_policy_applied"] == "ALERT"
    assert result.report["revaluation"]["status"] == "BLOCKED"
    assert result.report["revaluation"]["fx_blocked_warning"] is True
    assert len(result.report["warnings"]) >= 1


def test_fx_blocked_policy_block_rejects_blocked(monkeypatch: pytest.MonkeyPatch):
    _patch_common(monkeypatch, reval_status="BLOCKED")
    result = phase12.run_phase12_monthly_close(
        company_id=5,
        parent_company_id=5,
        company_ids=[5],
        year=2026,
        month=3,
        fx_blocked_policy="BLOCK",
    )
    assert result.cycle_passed is False
    fx_check = next(x for x in result.report["checks"] if x["name"] == "fx_revaluation_policy")
    assert fx_check["passed"] is False
