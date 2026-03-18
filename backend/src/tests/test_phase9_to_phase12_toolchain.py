from __future__ import annotations

import json
from datetime import timedelta

import pytest
from django.core.management import call_command
from django.utils import timezone

from apps.accounting.models import IntercompanyDisputeReason
from apps.iam.models import CompanyLink, LinkGrant, OrgUnit
from apps.rbac.models import Permission


def _mk_scope() -> tuple[OrgUnit, OrgUnit]:
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="Holding-P9")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="Company-P9", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="Branch-P9", parent=company)
    return company, branch


def _read_json(path) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.django_db
def test_phase9_toolchain_commands(tmp_path):
    company, branch = _mk_scope()
    call_command("set_branch_fiscal_mode", company_id=company.id, branch_id=branch.id, mode="B")

    staging = tmp_path / "phase9_staging.json"
    prod = tmp_path / "phase9_prod.json"
    happy = tmp_path / "phase9_happy.json"
    blocked = tmp_path / "phase9_blocked.json"
    gate = tmp_path / "phase9_gate.json"
    cycle = tmp_path / "phase9_cycle.json"

    call_command("export_phase9_env_manifest", company_id=company.id, branch_id=branch.id, output=str(staging))
    call_command("export_phase9_env_manifest", company_id=company.id, branch_id=branch.id, output=str(prod))
    call_command("compare_phase9_env_manifests", left=str(staging), right=str(prod), strict=True)

    call_command("certify_adapter_b_provider_run", company_id=company.id, branch_id=branch.id, output=str(happy))
    call_command(
        "certify_adapter_b_provider_run",
        company_id=company.id,
        branch_id=branch.id,
        expect_blocked=True,
        output=str(blocked),
    )
    call_command(
        "verify_phase9_go_live",
        company_id=company.id,
        branch_id=branch.id,
        staging_manifest=str(staging),
        prod_manifest=str(prod),
        happy_evidence=str(happy),
        blocked_evidence=str(blocked),
        max_inbox_failed=0,
        max_outbox_failed=0,
        max_failed_jobs=2,
        max_retry_overdue=0,
        max_contingency_open=2,
        output=str(gate),
        no_strict=True,
    )
    call_command(
        "run_adapter_b_provider_cycle",
        company_id=company.id,
        branch_id=branch.id,
        max_inbox_failed=0,
        max_outbox_failed=0,
        max_failed_jobs=2,
        max_retry_overdue=0,
        max_open_contingency=2,
        output=str(cycle),
        no_strict=True,
    )

    happy_payload = _read_json(happy)
    gate_payload = _read_json(gate)
    cycle_payload = _read_json(cycle)

    assert happy_payload["passed"] is True
    assert happy_payload["provider_mode"] in ("EMULATED", "HTTP", "REAL_HTTP")
    assert gate_payload["evidence_hash"]
    assert "checks" in gate_payload
    assert cycle_payload["evidence_hash"]
    assert "provider" in cycle_payload


@pytest.mark.django_db
def test_phase10_toolchain_commands(tmp_path):
    company, branch = _mk_scope()

    staging = tmp_path / "phase10_staging.json"
    prod = tmp_path / "phase10_prod.json"
    cert = tmp_path / "phase10_cert.json"
    gate = tmp_path / "phase10_gate.json"
    cycle = tmp_path / "phase10_cycle.json"

    call_command("export_phase10_env_manifest", company_id=company.id, branch_id=branch.id, output=str(staging))
    call_command("export_phase10_env_manifest", company_id=company.id, branch_id=branch.id, output=str(prod))
    call_command(
        "certify_phase10_procurement_run",
        company_id=company.id,
        branch_id=branch.id,
        output=str(cert),
    )
    call_command(
        "verify_phase10_go_live",
        company_id=company.id,
        branch_id=branch.id,
        staging_manifest=str(staging),
        prod_manifest=str(prod),
        certification=str(cert),
        max_inbox_failed=0,
        max_outbox_failed=0,
        max_open_procurement_drafts=0,
        max_open_procurement_blocking_exceptions=2,
        output=str(gate),
        no_strict=True,
    )
    call_command(
        "run_phase10_procurement_cycle",
        company_id=company.id,
        branch_id=branch.id,
        max_inbox_failed=0,
        max_outbox_failed=0,
        max_open_procurement_drafts=0,
        max_open_procurement_blocking_exceptions=2,
        max_posting_failed=0,
        output=str(cycle),
        no_strict=True,
    )

    cert_payload = _read_json(cert)
    gate_payload = _read_json(gate)
    cycle_payload = _read_json(cycle)

    assert cert_payload["passed"] is True
    assert cert_payload["go_live_passed"] is True
    assert gate_payload["evidence_hash"]
    assert cycle_payload["evidence_hash"]


@pytest.mark.django_db
def test_phase11_and_phase12_toolchain_commands(tmp_path):
    company, branch = _mk_scope()
    target_company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="Company-P11-Target", parent=company.parent)
    parent_company_id = company.id
    company_ids = [company.id]

    for code in [
        "accounting.intercompany.write",
        "accounting.intercompany.reconcile",
        "accounting.intercompany.dispute",
        "accounting.intercompany.settle",
    ]:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
        link, _ = CompanyLink.objects.get_or_create(
            from_company=target_company,
            to_company=company,
            defaults={"status": CompanyLink.Status.ACTIVE, "is_active": True},
        )
        LinkGrant.objects.update_or_create(
            link=link,
            permission=perm,
            access_mode=LinkGrant.AccessMode.WRITE,
            scope_org_unit=None,
            defaults={"is_active": True, "valid_from": None, "valid_to": None},
        )
    IntercompanyDisputeReason.objects.create(
        company=company,
        code="AMOUNT_MISMATCH",
        version=1,
        title="Diferencia",
        description="",
        severity=IntercompanyDisputeReason.Severity.HIGH,
        requires_evidence=True,
        is_active=True,
    )

    phase11_cert = tmp_path / "phase11_cert.json"
    phase11_gate = tmp_path / "phase11_gate.json"
    phase12_staging = tmp_path / "phase12_staging.json"
    phase12_prod = tmp_path / "phase12_prod.json"
    phase12_close = tmp_path / "phase12_monthly_close_202603.json"
    phase12_det = tmp_path / "phase12_det.json"
    phase12_slo = tmp_path / "phase12_slo.json"
    phase12_gate = tmp_path / "phase12_gate.json"

    call_command(
        "certify_phase11_intercompany_sla",
        company_id=company.id,
        target_company_id=target_company.id,
        output=str(phase11_cert),
        no_strict=True,
    )
    call_command(
        "verify_phase11_go_live",
        company_id=company.id,
        certification=str(phase11_cert),
        max_open_intercompany=5,
        max_disputed_intercompany=5,
        max_open_outside_sla=0,
        max_disputed_outside_sla=0,
        max_stale_confirmed_unclosed=0,
        max_blocked_consolidation=5,
        max_inbox_failed=0,
        max_outbox_failed=0,
        output=str(phase11_gate),
        no_strict=True,
    )
    call_command(
        "export_phase12_env_manifest",
        company_id=company.id,
        branch_id=branch.id,
        output=str(phase12_staging),
    )
    call_command(
        "export_phase12_env_manifest",
        company_id=company.id,
        branch_id=branch.id,
        output=str(phase12_prod),
    )
    call_command(
        "compare_phase12_env_manifests",
        left=str(phase12_staging),
        right=str(phase12_prod),
        strict=True,
    )

    target_date = timezone.localdate() - timedelta(days=1)
    call_command(
        "run_phase12_monthly_close",
        company_id=company.id,
        parent_company_id=parent_company_id,
        company_ids=company_ids,
        year=target_date.year,
        month=target_date.month,
        max_inbox_failed=999,
        max_outbox_failed=999,
        max_missing_lines=999,
        max_stale_revaluation=999,
        max_open_intercompany=999,
        max_disputed_intercompany=999,
        max_blocked_consolidation=999,
        max_open_consolidation_exception=999,
        fx_blocked_policy="ALERT",
        output=str(phase12_close),
        no_strict=True,
    )
    call_command(
        "certify_phase12_monthly_determinism",
        company_id=company.id,
        parent_company_id=parent_company_id,
        company_ids=company_ids,
        year=target_date.year,
        month=target_date.month,
        fx_blocked_policy="ALERT",
        output=str(phase12_det),
        no_strict=True,
    )
    call_command(
        "verify_phase12_operational_slo",
        evidence_dir=str(tmp_path),
        pattern="phase12_monthly_close_*.json",
        min_periods=1,
        max_failed_periods=1,
        max_inbox_failed=999,
        max_outbox_failed=999,
        max_missing_lines=999,
        max_stale_revaluation=999,
        max_open_intercompany=999,
        max_disputed_intercompany=999,
        fx_blocked_policy="ALERT",
        output=str(phase12_slo),
        no_strict=True,
    )
    call_command(
        "verify_phase12_go_live",
        company_id=company.id,
        staging_manifest=str(phase12_staging),
        prod_manifest=str(phase12_prod),
        determinism_evidence=str(phase12_det),
        slo_evidence=str(phase12_slo),
        max_inbox_failed=999,
        max_outbox_failed=999,
        max_missing_lines=999,
        max_stale_revaluation=999,
        max_open_intercompany=999,
        max_disputed_intercompany=999,
        max_blocked_consolidation=999,
        max_open_consolidation_exception=999,
        fx_blocked_policy="ALERT",
        output=str(phase12_gate),
        no_strict=True,
    )

    phase11_payload = _read_json(phase11_cert)
    phase12_payload = _read_json(phase12_close)
    slo_payload = _read_json(phase12_slo)
    gate_payload = _read_json(phase12_gate)

    assert phase11_payload["evidence_hash"]
    assert phase12_payload["evidence_hash"]
    assert "checks" in phase12_payload
    assert slo_payload["evidence_hash"]
    assert gate_payload["evidence_hash"]
    assert "checks" in gate_payload
