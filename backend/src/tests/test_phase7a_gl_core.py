from __future__ import annotations

import json
import uuid
from datetime import timedelta
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounting.models import (
    ChartOfAccount,
    CompanyAccountingConfig,
    FiscalPeriod,
    FxRate,
    JournalEntry,
    JournalEntryLine,
    RevaluationEntryLink,
    RevaluationRun,
)
from apps.accounting.phase7 import run_fx_revaluation
from apps.accounting.services import AccountingConflictError, close_fiscal_period, post_journal_drafts
from apps.cec.models import CloseRun
from apps.iam.models import OrgUnit, UserMembership
from apps.integration.services import publish_outbox_event
from apps.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _mk_org():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


def _mk_user(username_prefix: str = "u"):
    username = f"{username_prefix}_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=username, email=f"{username}@test.local", password="pass12345")


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
        payload={"run_id": str(run.run_id), "output_manifest_hash": run.output_manifest_hash, "consistency_score": 100},
        company=company,
        branch=branch,
        actor_user=user,
    )
    return run


def _mk_billing_event(*, company: OrgUnit, branch: OrgUnit, user, number: int = 1):
    publish_outbox_event(
        source_module="BILLING",
        event_type="DocumentIssued",
        payload={
            "doc_id": int(8000 + number),
            "doc_type": "INVOICE",
            "series": "B",
            "number": int(number),
            "currency": "NIO",
            "subtotal": "150.00",
            "tax_total": "22.50",
            "total": "172.50",
            "is_fiscal": True,
            "fiscal_adapter_mode": "B",
        },
        company=company,
        branch=branch,
        actor_user=user,
    )


def _seed_coa_for_billing(*, company: OrgUnit, include_tax: bool = True):
    rows = [
        ("1101", "Caja y bancos", ChartOfAccount.AccountType.ASSET),
        ("4101", "Ventas gravadas", ChartOfAccount.AccountType.REVENUE),
        ("7991", "Ganancia por diferencia cambiaria", ChartOfAccount.AccountType.REVENUE),
        ("6991", "Pérdida por diferencia cambiaria", ChartOfAccount.AccountType.EXPENSE),
    ]
    if include_tax:
        rows.append(("2101", "IVA por pagar", ChartOfAccount.AccountType.LIABILITY))
    created = {}
    for code, name, account_type in rows:
        created[code] = ChartOfAccount.objects.create(
            company=company,
            code=code,
            name=name,
            account_type=account_type,
            is_postable=True,
            is_active=True,
            is_revaluable=(code == "1101"),
        )
    CompanyAccountingConfig.objects.update_or_create(
        company=company,
        defaults={
            "phase7_enabled": True,
            "functional_currency": "NIO",
            "fx_gain_account": created.get("7991"),
            "fx_loss_account": created.get("6991"),
        },
    )
    return created


def _client_with_perms(*, company: OrgUnit, branch: OrgUnit, perm_codes: list[str]) -> APIClient:
    user = _mk_user("api")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)
    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perm_codes:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)

    client = APIClient()
    resp = client.post("/api/backend/auth/login/", {"username": user.username, "password": "pass12345"}, format="json")
    assert resp.status_code == 200
    access = resp.data.get("access") if isinstance(resp.data, dict) else None
    if isinstance(access, str) and access:
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {access}"
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client


@pytest.mark.django_db
def test_phase7_posting_creates_journal_entry_lines():
    company, branch = _mk_org()
    user = _mk_user("owner")
    _seed_coa_for_billing(company=company, include_tax=True)
    call_command("seed_posting_rules_v1", company_id=company.id)
    run = _mk_packaged_run(company=company, branch=branch, user=user)
    _mk_billing_event(company=company, branch=branch, user=user, number=1)
    call_command("project_shadow_ledger", run_id=str(run.run_id))

    result = post_journal_drafts(company_id=company.id, run_id=str(run.run_id), require_approved=False)
    assert result.posted == 1
    assert result.failed == 0

    entry = JournalEntry.objects.get(draft__close_run_id=str(run.run_id))
    assert entry.lines.count() == 3
    assert str(sum(x.debit_base for x in entry.lines.all())) == str(entry.debit_total)
    assert str(sum(x.credit_base for x in entry.lines.all())) == str(entry.credit_total)


@pytest.mark.django_db
def test_phase7_posting_fails_when_coa_missing_account():
    company, branch = _mk_org()
    user = _mk_user("owner")
    _seed_coa_for_billing(company=company, include_tax=False)
    call_command("seed_posting_rules_v1", company_id=company.id)
    run = _mk_packaged_run(company=company, branch=branch, user=user)
    _mk_billing_event(company=company, branch=branch, user=user, number=2)
    call_command("project_shadow_ledger", run_id=str(run.run_id))

    result = post_journal_drafts(company_id=company.id, run_id=str(run.run_id), require_approved=False)
    assert result.posted == 0
    assert result.failed >= 1
    assert "GL Fase7 invalid" in result.errors[0]["error"]
    assert JournalEntry.objects.filter(draft__close_run_id=str(run.run_id)).count() == 0


@pytest.mark.django_db
def test_phase7_reporting_api_endpoints_work():
    company, branch = _mk_org()
    user = _mk_user("owner")
    _seed_coa_for_billing(company=company, include_tax=True)
    call_command("seed_posting_rules_v1", company_id=company.id)
    run = _mk_packaged_run(company=company, branch=branch, user=user)
    _mk_billing_event(company=company, branch=branch, user=user, number=3)
    call_command("project_shadow_ledger", run_id=str(run.run_id))
    post_result = post_journal_drafts(company_id=company.id, run_id=str(run.run_id), require_approved=False)
    assert post_result.posted == 1

    dt = timezone.localdate()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "accounting.report.read",
            "accounting.coa.read",
            "accounting.fx_rate.read",
        ],
    )

    tb = client.get(f"/api/accounting/reports/trial-balance/?year={dt.year}&month={dt.month}")
    assert tb.status_code == 200
    assert tb.data["count"] >= 3

    gl = client.get(f"/api/accounting/reports/general-ledger/?account_code=1101&year={dt.year}&month={dt.month}")
    assert gl.status_code == 200
    assert gl.data["count"] >= 1

    pnl = client.get(f"/api/accounting/reports/pnl/?year={dt.year}&month={dt.month}")
    assert pnl.status_code == 200
    assert "totals" in pnl.data

    bs = client.get(f"/api/accounting/reports/balance-sheet/?as_of={dt.isoformat()}")
    assert bs.status_code == 200
    assert "assets" in bs.data


@pytest.mark.django_db
def test_phase7_fx_revaluation_executes_and_is_idempotent():
    company, _branch = _mk_org()
    actor = _mk_user("fx")
    accounts = _seed_coa_for_billing(company=company, include_tax=True)
    cfg = CompanyAccountingConfig.objects.get(company=company)
    cfg.fx_gain_account = accounts["7991"]
    cfg.fx_loss_account = accounts["6991"]
    cfg.save(update_fields=["fx_gain_account", "fx_loss_account", "updated_at"])

    now = timezone.localdate()
    period, _ = FiscalPeriod.objects.get_or_create(company=company, year=now.year, month=now.month)
    econ = None
    from apps.accounting.models import EconomicEvent, JournalDraft, PostingRuleSet

    econ = EconomicEvent.objects.create(
        source_module="ACCOUNTING",
        event_type="SeedFxExposure",
        company=company,
        payload={"data": {"currency": "USD"}},
    )
    ruleset = PostingRuleSet.objects.create(
        code="seed_rule",
        version=1,
        status=PostingRuleSet.Status.ACTIVE,
        fiscal_mode=PostingRuleSet.FiscalMode.BOTH,
        scope_company=company,
        rules_json={"version": "1.0", "rules": []},
    )
    jdraft = JournalDraft.objects.create(
        economic_event=econ,
        rule_set=ruleset,
        state=JournalDraft.State.POSTED,
        total_debit="3500.00",
        total_credit="3500.00",
        lines_json=[
            {"account": "1101", "side": "DEBIT", "amount": "3500.00", "currency": "USD", "fx_rate": "35.00000000", "amount_tx": "100.00"},
            {"account": "2101", "side": "CREDIT", "amount": "3500.00", "currency": "USD", "fx_rate": "35.00000000", "amount_tx": "100.00"},
        ],
        posted_at=timezone.now(),
    )
    jentry = JournalEntry.objects.create(
        draft=jdraft,
        period=period,
        company=company,
        entry_date=now,
        description="FX seed",
        debit_total="3500.00",
        credit_total="3500.00",
        posted_by=actor,
    )
    JournalEntryLine.objects.create(
        journal_entry=jentry,
        line_no=1,
        account=accounts["1101"],
        account_code_snapshot="1101",
        currency="USD",
        fx_rate="35.00000000",
        amount_tx="100.00",
        debit_base="3500.00",
        credit_base="0.00",
    )
    JournalEntryLine.objects.create(
        journal_entry=jentry,
        line_no=2,
        account=accounts["2101"],
        account_code_snapshot="2101",
        currency="USD",
        fx_rate="35.00000000",
        amount_tx="100.00",
        debit_base="0.00",
        credit_base="3500.00",
    )

    FxRate.objects.create(
        company=company,
        rate_date=now,
        from_currency="USD",
        to_currency="NIO",
        rate_type=FxRate.RateType.CLOSING,
        rate="36.00000000",
    )

    first = run_fx_revaluation(company_id=company.id, year=now.year, month=now.month, strict=True, actor_user=actor)
    assert first.status == RevaluationRun.Status.COMPLETED
    assert first.entries_created >= 1

    second = run_fx_revaluation(company_id=company.id, year=now.year, month=now.month, strict=True, actor_user=actor)
    assert second.idempotent is True
    assert RevaluationEntryLink.objects.count() >= 1


@pytest.mark.django_db
def test_phase7_close_period_blocks_same_actor_who_ran_revaluation():
    company, _branch = _mk_org()
    actor = _mk_user("closer")
    accounts = _seed_coa_for_billing(company=company, include_tax=True)
    cfg = CompanyAccountingConfig.objects.get(company=company)
    cfg.fx_gain_account = accounts["7991"]
    cfg.fx_loss_account = accounts["6991"]
    cfg.save(update_fields=["fx_gain_account", "fx_loss_account", "updated_at"])

    now = timezone.localdate()
    FiscalPeriod.objects.get_or_create(company=company, year=now.year, month=now.month, defaults={"status": FiscalPeriod.Status.OPEN})
    run = RevaluationRun.objects.create(
        company=company,
        year=now.year,
        month=now.month,
        scope_hash="x" * 64,
        status=RevaluationRun.Status.COMPLETED,
        executed_by=actor,
        summary_json={"entries_created": 0},
        completed_at=timezone.now(),
    )
    assert run.status == RevaluationRun.Status.COMPLETED

    with pytest.raises(AccountingConflictError):
        close_fiscal_period(
            company_id=company.id,
            year=now.year,
            month=now.month,
            force=True,
            allow_same_poster=False,
            actor_user=actor,
        )


@pytest.mark.django_db
def test_phase7_toolchain_commands_work(tmp_path):
    company, branch = _mk_org()
    user = _mk_user("owner")
    _seed_coa_for_billing(company=company, include_tax=True)
    call_command("seed_rbac_v01")
    call_command("seed_posting_rules_v1", company_id=company.id)
    run = _mk_packaged_run(company=company, branch=branch, user=user)
    _mk_billing_event(company=company, branch=branch, user=user, number=7)
    call_command("project_shadow_ledger", run_id=str(run.run_id))
    post = post_journal_drafts(company_id=company.id, run_id=str(run.run_id), require_approved=False)
    assert post.posted == 1

    today = timezone.localdate()
    FxRate.objects.update_or_create(
        company=company,
        rate_date=today,
        from_currency="USD",
        to_currency="NIO",
        rate_type=FxRate.RateType.CLOSING,
        defaults={"rate": "36.00000000"},
    )

    staging = tmp_path / "phase7_staging.json"
    prod = tmp_path / "phase7_prod.json"
    happy = tmp_path / "phase7_happy.json"
    blocked = tmp_path / "phase7_blocked.json"
    gate = tmp_path / "phase7_gate.json"

    call_command("export_phase7_env_manifest", company_id=company.id, output=str(staging))
    call_command("export_phase7_env_manifest", company_id=company.id, output=str(prod))
    compare_out = StringIO()
    call_command("compare_phase7_env_manifests", left=str(staging), right=str(prod), stdout=compare_out)
    compare_payload = json.loads(compare_out.getvalue())
    assert compare_payload["passed"] is True

    call_command(
        "certify_phase7_gl_run",
        company_id=company.id,
        run_id=str(run.run_id),
        year=today.year,
        month=today.month,
        output=str(happy),
    )
    cfg = CompanyAccountingConfig.objects.get(company=company)
    cfg.fx_gain_account = None
    cfg.save(update_fields=["fx_gain_account", "updated_at"])
    call_command(
        "certify_phase7_gl_run",
        company_id=company.id,
        run_id=str(run.run_id),
        year=today.year,
        month=today.month + 1 if today.month < 12 else today.month - 1,
        expect_blocked=True,
        output=str(blocked),
    )

    call_command(
        "verify_phase7_go_live",
        company_id=company.id,
        staging_manifest=str(staging),
        prod_manifest=str(prod),
        happy_evidence=str(happy),
        blocked_evidence=str(blocked),
        output=str(gate),
    )
    gate_payload = json.loads(gate.read_text(encoding="utf-8"))
    assert gate_payload["go_live_passed"] is True
