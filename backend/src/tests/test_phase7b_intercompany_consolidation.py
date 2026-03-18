from __future__ import annotations

import json
import uuid
from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.accounting.models import (
    ChartOfAccount,
    CompanyAccountingConfig,
    ConsolidationRun,
    EconomicEvent,
    FiscalPeriod,
    IntercompanyDisputeReason,
    IntercompanyTransaction,
    JournalDraft,
    JournalEntry,
    JournalEntryLine,
    PostingRuleSet,
)
from apps.accounting.phase7b import (
    Phase7BValidationError,
    close_intercompany_transaction,
    confirm_intercompany_transaction,
    create_intercompany_transaction,
    reconcile_intercompany_transaction,
    run_consolidation,
)
from apps.cec.models import CECException
from apps.iam.models import CompanyLink, LinkGrant, OrgUnit, UserMembership
from apps.integration.models import OutboxEvent
from apps.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _mk_orgs():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="Holding")
    company_a = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="Company A", parent=holding)
    branch_a = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="Branch A", parent=company_a)
    company_b = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="Company B", parent=holding)
    branch_b = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="Branch B", parent=company_b)
    return company_a, branch_a, company_b, branch_b


def _mk_user(prefix: str) -> Any:
    username = f"{prefix}_{uuid.uuid4().hex[:8]}"
    return User.objects.create_user(username=username, email=f"{username}@test.local", password="pass12345")


def _mk_client(*, user: Any, company: OrgUnit, branch: OrgUnit, perms: list[str]) -> APIClient:
    UserMembership.objects.get_or_create(user=user, org_unit=company, defaults={"is_active": True})
    UserMembership.objects.get_or_create(user=user, org_unit=branch, defaults={"is_active": True})
    role = Role.objects.create(name=f"r_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perms:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.get_or_create(user=user, role=role, org_unit=company, defaults={"is_active": True})
    RoleAssignment.objects.get_or_create(user=user, role=role, org_unit=branch, defaults={"is_active": True})

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


def _seed_coa(*, company: OrgUnit):
    rows = {
        "1101": ("Caja", ChartOfAccount.AccountType.ASSET),
        "1301": ("CxC Intercompany", ChartOfAccount.AccountType.ASSET),
        "2109": ("CxP Intercompany", ChartOfAccount.AccountType.LIABILITY),
        "4101": ("Ingresos Intercompany", ChartOfAccount.AccountType.REVENUE),
        "5101": ("Gasto Intercompany", ChartOfAccount.AccountType.EXPENSE),
    }
    out = {}
    for code, (name, account_type) in rows.items():
        out[code] = ChartOfAccount.objects.create(
            company=company,
            code=code,
            name=name,
            account_type=account_type,
            is_postable=True,
            is_active=True,
        )
    return out


def _post_entry(
    *,
    company: OrgUnit,
    branch: OrgUnit,
    actor: Any,
    line1_account: ChartOfAccount,
    line1_side: str,
    line2_account: ChartOfAccount,
    line2_side: str,
    amount: Decimal,
) -> JournalEntry:
    period, _ = FiscalPeriod.objects.get_or_create(company=company, year=2026, month=3, defaults={"status": FiscalPeriod.Status.OPEN})
    event = EconomicEvent.objects.create(
        source_module="ACCOUNTING",
        event_type="IntercompanySeed",
        company=company,
        branch=branch,
        payload={"kind": "seed"},
    )
    ruleset = PostingRuleSet.objects.create(
        code=f"seed_{uuid.uuid4().hex[:6]}",
        version=1,
        status=PostingRuleSet.Status.ACTIVE,
        fiscal_mode=PostingRuleSet.FiscalMode.BOTH,
        scope_company=company,
        rules_json={"version": "1.0", "rules": []},
    )
    draft = JournalDraft.objects.create(
        economic_event=event,
        rule_set=ruleset,
        state=JournalDraft.State.POSTED,
        total_debit=amount,
        total_credit=amount,
        lines_json=[
            {"account": line1_account.code, "side": line1_side, "amount": str(amount)},
            {"account": line2_account.code, "side": line2_side, "amount": str(amount)},
        ],
    )
    entry = JournalEntry.objects.create(
        draft=draft,
        period=period,
        company=company,
        branch=branch,
        debit_total=amount,
        credit_total=amount,
        posted_by=actor,
    )
    JournalEntryLine.objects.create(
        journal_entry=entry,
        line_no=1,
        account=line1_account,
        account_code_snapshot=line1_account.code,
        currency="NIO",
        fx_rate="1.00000000",
        amount_tx=amount,
        debit_base=amount if line1_side == "DEBIT" else Decimal("0.00"),
        credit_base=amount if line1_side == "CREDIT" else Decimal("0.00"),
    )
    JournalEntryLine.objects.create(
        journal_entry=entry,
        line_no=2,
        account=line2_account,
        account_code_snapshot=line2_account.code,
        currency="NIO",
        fx_rate="1.00000000",
        amount_tx=amount,
        debit_base=amount if line2_side == "DEBIT" else Decimal("0.00"),
        credit_base=amount if line2_side == "CREDIT" else Decimal("0.00"),
    )
    return entry


def _grant_intercompany_permission(
    *,
    from_company: OrgUnit,
    to_company: OrgUnit,
    permission_code: str,
) -> None:
    perm, _ = Permission.objects.get_or_create(
        code=permission_code,
        defaults={"description": permission_code, "is_active": True},
    )
    link, _ = CompanyLink.objects.get_or_create(
        from_company=from_company,
        to_company=to_company,
        defaults={"status": CompanyLink.Status.ACTIVE, "is_active": True},
    )
    if link.status != CompanyLink.Status.ACTIVE or not bool(link.is_active):
        link.status = CompanyLink.Status.ACTIVE
        link.is_active = True
        link.save(update_fields=["status", "is_active", "updated_at"])
    LinkGrant.objects.update_or_create(
        link=link,
        permission=perm,
        access_mode=LinkGrant.AccessMode.WRITE,
        scope_org_unit=None,
        defaults={"is_active": True, "valid_from": None, "valid_to": None},
    )


@pytest.mark.django_db
def test_phase7b_intercompany_lifecycle_service():
    company_a, branch_a, company_b, branch_b = _mk_orgs()
    coa_a = _seed_coa(company=company_a)
    coa_b = _seed_coa(company=company_b)
    creator = _mk_user("creator")
    confirmer = _mk_user("confirmer")

    source_entry = _post_entry(
        company=company_a,
        branch=branch_a,
        actor=creator,
        line1_account=coa_a["1301"],
        line1_side="DEBIT",
        line2_account=coa_a["4101"],
        line2_side="CREDIT",
        amount=Decimal("100.00"),
    )
    target_entry = _post_entry(
        company=company_b,
        branch=branch_b,
        actor=confirmer,
        line1_account=coa_b["5101"],
        line1_side="DEBIT",
        line2_account=coa_b["2109"],
        line2_side="CREDIT",
        amount=Decimal("100.00"),
    )
    _grant_intercompany_permission(
        from_company=company_b,
        to_company=company_a,
        permission_code="accounting.intercompany.write",
    )
    _grant_intercompany_permission(
        from_company=company_b,
        to_company=company_a,
        permission_code="accounting.intercompany.reconcile",
    )

    tx = create_intercompany_transaction(
        source_company_id=company_a.id,
        target_company_id=company_b.id,
        amount=Decimal("100.00"),
        source_account_code="4101",
        target_account_code="5101",
        source_side="CREDIT",
        target_side="DEBIT",
        source_journal_entry_id=source_entry.id,
        target_journal_entry_id=target_entry.id,
        actor_user=creator,
    )
    assert tx.status == IntercompanyTransaction.Status.PENDING

    with pytest.raises(Phase7BValidationError):
        confirm_intercompany_transaction(tx_id=str(tx.tx_id), actor_user=creator, allow_same_actor=False)

    confirmed = confirm_intercompany_transaction(tx_id=str(tx.tx_id), actor_user=confirmer, allow_same_actor=False)
    assert confirmed.status == IntercompanyTransaction.Status.CONFIRMED

    rec = reconcile_intercompany_transaction(
        tx_id=str(tx.tx_id),
        source_amount=Decimal("100.00"),
        target_amount=Decimal("100.00"),
        actor_user=confirmer,
    )
    assert rec.status == IntercompanyTransaction.Status.CONFIRMED

    closed = close_intercompany_transaction(tx_id=str(tx.tx_id), actor_user=confirmer)
    assert closed.status == IntercompanyTransaction.Status.CLOSED


@pytest.mark.django_db
def test_phase7b_consolidation_happy_path_and_idempotent():
    company_a, branch_a, company_b, branch_b = _mk_orgs()
    coa_a = _seed_coa(company=company_a)
    coa_b = _seed_coa(company=company_b)
    actor = _mk_user("actor")

    source_entry = _post_entry(
        company=company_a,
        branch=branch_a,
        actor=actor,
        line1_account=coa_a["1301"],
        line1_side="DEBIT",
        line2_account=coa_a["4101"],
        line2_side="CREDIT",
        amount=Decimal("100.00"),
    )
    target_entry = _post_entry(
        company=company_b,
        branch=branch_b,
        actor=actor,
        line1_account=coa_b["5101"],
        line1_side="DEBIT",
        line2_account=coa_b["2109"],
        line2_side="CREDIT",
        amount=Decimal("100.00"),
    )
    _grant_intercompany_permission(
        from_company=company_b,
        to_company=company_a,
        permission_code="accounting.intercompany.write",
    )

    tx = create_intercompany_transaction(
        source_company_id=company_a.id,
        target_company_id=company_b.id,
        amount=Decimal("100.00"),
        source_account_code="4101",
        target_account_code="5101",
        source_side="CREDIT",
        target_side="DEBIT",
        source_journal_entry_id=source_entry.id,
        target_journal_entry_id=target_entry.id,
        actor_user=actor,
    )
    confirm_intercompany_transaction(tx_id=str(tx.tx_id), actor_user=actor, allow_same_actor=True)

    first = run_consolidation(
        parent_company_id=company_a.id,
        year=2026,
        month=3,
        company_ids=[company_a.id, company_b.id],
        strict=True,
        actor_user=actor,
    )
    assert first.status == ConsolidationRun.Status.COMPLETED
    assert first.idempotent is False
    assert first.manifest_hash
    assert first.summary_json["pnl"]["totals"]["net_income"] == "0.00"

    second = run_consolidation(
        parent_company_id=company_a.id,
        year=2026,
        month=3,
        company_ids=[company_a.id, company_b.id],
        strict=True,
        actor_user=actor,
    )
    assert second.idempotent is True
    assert second.manifest_hash == first.manifest_hash


@pytest.mark.django_db
def test_phase7b_consolidation_blocked_when_intercompany_account_codes_missing():
    company_a, branch_a, company_b, branch_b = _mk_orgs()
    coa_a = _seed_coa(company=company_a)
    coa_b = _seed_coa(company=company_b)
    actor = _mk_user("actor")

    source_entry = _post_entry(
        company=company_a,
        branch=branch_a,
        actor=actor,
        line1_account=coa_a["1301"],
        line1_side="DEBIT",
        line2_account=coa_a["4101"],
        line2_side="CREDIT",
        amount=Decimal("100.00"),
    )
    target_entry = _post_entry(
        company=company_b,
        branch=branch_b,
        actor=actor,
        line1_account=coa_b["5101"],
        line1_side="DEBIT",
        line2_account=coa_b["2109"],
        line2_side="CREDIT",
        amount=Decimal("100.00"),
    )
    _grant_intercompany_permission(
        from_company=company_b,
        to_company=company_a,
        permission_code="accounting.intercompany.write",
    )

    tx = create_intercompany_transaction(
        source_company_id=company_a.id,
        target_company_id=company_b.id,
        amount=Decimal("100.00"),
        source_account_code="",
        target_account_code="",
        source_side="CREDIT",
        target_side="DEBIT",
        source_journal_entry_id=source_entry.id,
        target_journal_entry_id=target_entry.id,
        actor_user=actor,
    )
    confirm_intercompany_transaction(tx_id=str(tx.tx_id), actor_user=actor, allow_same_actor=True)

    result = run_consolidation(
        parent_company_id=company_a.id,
        year=2026,
        month=3,
        company_ids=[company_a.id, company_b.id],
        strict=True,
        actor_user=actor,
    )
    assert result.status == ConsolidationRun.Status.BLOCKED
    assert result.issues_count > 0
    assert CECException.objects.filter(
        source_module="ACCOUNTING",
        code="CONSOLIDATION_ACCOUNT_CODE_MISSING",
    ).exists()


@pytest.mark.django_db
def test_phase7b_intercompany_api_and_consolidation_reports():
    company_a, branch_a, company_b, branch_b = _mk_orgs()
    coa_a = _seed_coa(company=company_a)
    coa_b = _seed_coa(company=company_b)
    actor = _mk_user("api")

    _post_entry(
        company=company_a,
        branch=branch_a,
        actor=actor,
        line1_account=coa_a["1301"],
        line1_side="DEBIT",
        line2_account=coa_a["4101"],
        line2_side="CREDIT",
        amount=Decimal("100.00"),
    )
    _post_entry(
        company=company_b,
        branch=branch_b,
        actor=actor,
        line1_account=coa_b["5101"],
        line1_side="DEBIT",
        line2_account=coa_b["2109"],
        line2_side="CREDIT",
        amount=Decimal("100.00"),
    )

    client = _mk_client(
        user=actor,
        company=company_a,
        branch=branch_a,
        perms=[
            "accounting.intercompany.read",
            "accounting.intercompany.write",
            "accounting.intercompany.reconcile",
            "accounting.consolidation.run",
            "accounting.consolidation.read",
        ],
    )
    _grant_intercompany_permission(
        from_company=company_b,
        to_company=company_a,
        permission_code="accounting.intercompany.write",
    )
    _grant_intercompany_permission(
        from_company=company_b,
        to_company=company_a,
        permission_code="accounting.intercompany.reconcile",
    )

    create_resp = client.post(
        "/api/accounting/intercompany/transactions/",
        {
            "target_company_id": company_b.id,
            "amount": "100.00",
            "currency": "NIO",
            "source_account_code": "4101",
            "target_account_code": "5101",
            "source_side": "CREDIT",
            "target_side": "DEBIT",
            "description": "venta intercompany",
        },
        format="json",
    )
    assert create_resp.status_code == 201
    tx_id = create_resp.data["tx_id"]

    confirm_resp = client.post(
        f"/api/accounting/intercompany/transactions/{tx_id}/confirm/",
        {"allow_same_actor": True},
        format="json",
    )
    assert confirm_resp.status_code == 200

    reconcile_resp = client.post(
        f"/api/accounting/intercompany/transactions/{tx_id}/reconcile/",
        {"source_amount": "100.00", "target_amount": "100.00"},
        format="json",
    )
    assert reconcile_resp.status_code == 200

    close_resp = client.post(
        f"/api/accounting/intercompany/transactions/{tx_id}/close/",
        {},
        format="json",
    )
    assert close_resp.status_code == 200

    run_resp = client.post(
        "/api/accounting/consolidation/run/",
        {"year": 2026, "month": 3, "company_ids": [company_a.id, company_b.id], "strict": True},
        format="json",
    )
    assert run_resp.status_code in (200, 201)
    run_id = run_resp.data["run_id"]

    tb = client.get(f"/api/accounting/consolidation/reports/trial-balance/?run_id={run_id}")
    assert tb.status_code == 200
    assert tb.data["count"] >= 1

    pnl = client.get(f"/api/accounting/consolidation/reports/pnl/?run_id={run_id}")
    assert pnl.status_code == 200
    assert "totals" in pnl.data

    bs = client.get(f"/api/accounting/consolidation/reports/balance-sheet/?run_id={run_id}")
    assert bs.status_code == 200
    assert "assets" in bs.data


@pytest.mark.django_db
def test_phase7b_intercompany_dispute_and_settle_api():
    company_a, branch_a, company_b, _branch_b = _mk_orgs()
    actor = _mk_user("api_dispute")

    client = _mk_client(
        user=actor,
        company=company_a,
        branch=branch_a,
        perms=[
            "accounting.intercompany.read",
            "accounting.intercompany.write",
            "accounting.intercompany.reconcile",
            "accounting.intercompany.dispute",
            "accounting.intercompany.settle",
        ],
    )
    _grant_intercompany_permission(
        from_company=company_b,
        to_company=company_a,
        permission_code="accounting.intercompany.write",
    )
    _grant_intercompany_permission(
        from_company=company_b,
        to_company=company_a,
        permission_code="accounting.intercompany.reconcile",
    )
    _grant_intercompany_permission(
        from_company=company_b,
        to_company=company_a,
        permission_code="accounting.intercompany.dispute",
    )
    _grant_intercompany_permission(
        from_company=company_b,
        to_company=company_a,
        permission_code="accounting.intercompany.settle",
    )
    IntercompanyDisputeReason.objects.create(
        company=company_a,
        code="AMOUNT_MISMATCH",
        version=1,
        title="Diferencia de monto",
        description="mismatch",
        severity=IntercompanyDisputeReason.Severity.HIGH,
        requires_evidence=True,
        is_active=True,
    )

    create_resp = client.post(
        "/api/accounting/intercompany/transactions/",
        {
            "target_company_id": company_b.id,
            "amount": "100.00",
            "currency": "NIO",
            "source_account_code": "4101",
            "target_account_code": "5101",
            "source_side": "CREDIT",
            "target_side": "DEBIT",
            "description": "intercompany dispute",
        },
        format="json",
    )
    assert create_resp.status_code == 201
    tx_id = str(create_resp.data["tx_id"])

    confirm_resp = client.post(
        f"/api/accounting/intercompany/transactions/{tx_id}/confirm/",
        {"allow_same_actor": True},
        format="json",
    )
    assert confirm_resp.status_code == 200

    dispute_resp = client.post(
        f"/api/accounting/intercompany/transactions/{tx_id}/dispute/",
        {
            "source_amount": "100.00",
            "target_amount": "95.00",
            "reason_code": "AMOUNT_MISMATCH",
            "evidence_refs": ["s3://bucket/evidence-1.pdf"],
            "note": "mismatch detectado",
        },
        format="json",
    )
    assert dispute_resp.status_code == 200
    assert dispute_resp.data["status"] == IntercompanyTransaction.Status.DISPUTED

    settle_resp = client.post(
        f"/api/accounting/intercompany/transactions/{tx_id}/settle/",
        {
            "source_amount": "100.00",
            "target_amount": "100.00",
            "resolution_note": "mismatch resuelto",
            "close_when_confirmed": True,
            "allow_difference": False,
        },
        format="json",
    )
    assert settle_resp.status_code == 200
    assert settle_resp.data["status"] == IntercompanyTransaction.Status.CLOSED

    assert OutboxEvent.objects.filter(source_module="ACCOUNTING", event_type="IntercompanyDisputeOpened").exists()
    assert OutboxEvent.objects.filter(source_module="ACCOUNTING", event_type="IntercompanyDisputeSettled").exists()


@pytest.mark.django_db
def test_phase7b_certification_and_go_live_commands(tmp_path):
    company_a, branch_a, company_b, branch_b = _mk_orgs()
    coa_a = _seed_coa(company=company_a)
    coa_b = _seed_coa(company=company_b)
    actor = _mk_user("ops")

    source_entry = _post_entry(
        company=company_a,
        branch=branch_a,
        actor=actor,
        line1_account=coa_a["1301"],
        line1_side="DEBIT",
        line2_account=coa_a["4101"],
        line2_side="CREDIT",
        amount=Decimal("100.00"),
    )
    target_entry = _post_entry(
        company=company_b,
        branch=branch_b,
        actor=actor,
        line1_account=coa_b["5101"],
        line1_side="DEBIT",
        line2_account=coa_b["2109"],
        line2_side="CREDIT",
        amount=Decimal("100.00"),
    )
    _grant_intercompany_permission(
        from_company=company_b,
        to_company=company_a,
        permission_code="accounting.intercompany.write",
    )
    tx = create_intercompany_transaction(
        source_company_id=company_a.id,
        target_company_id=company_b.id,
        amount=Decimal("100.00"),
        source_account_code="4101",
        target_account_code="5101",
        source_side="CREDIT",
        target_side="DEBIT",
        source_journal_entry_id=source_entry.id,
        target_journal_entry_id=target_entry.id,
        actor_user=actor,
    )
    confirm_intercompany_transaction(tx_id=str(tx.tx_id), actor_user=actor, allow_same_actor=True)
    close_intercompany_transaction(tx_id=str(tx.tx_id), actor_user=actor, allow_difference=False)

    cert_path = tmp_path / "phase7b_cert.json"
    gate_path = tmp_path / "phase7b_gate.json"
    call_command(
        "certify_phase7b_consolidation",
        "--parent-company-id",
        str(company_a.id),
        "--year",
        "2026",
        "--month",
        "3",
        "--company-ids",
        str(company_a.id),
        str(company_b.id),
        "--output",
        str(cert_path),
    )
    cert_payload = json.loads(cert_path.read_text(encoding="utf-8"))
    assert cert_payload["passed"] is True
    assert cert_payload["deterministic_replay"] is True

    call_command(
        "verify_phase7b_go_live",
        "--company-id",
        str(company_a.id),
        "--certification",
        str(cert_path),
        "--max-open-intercompany",
        "0",
        "--max-disputed-intercompany",
        "0",
        "--max-blocked-consolidation",
        "0",
        "--max-open-consolidation-exception",
        "0",
        "--max-inbox-failed",
        "0",
        "--max-outbox-failed",
        "1000",
        "--output",
        str(gate_path),
    )
    gate_payload = json.loads(gate_path.read_text(encoding="utf-8"))
    assert gate_payload["go_live_passed"] is True


@pytest.mark.django_db
def test_phase7b_write_governance_requires_intercompany_grants():
    company_a, branch_a, company_b, branch_b = _mk_orgs()
    coa_a = _seed_coa(company=company_a)
    coa_b = _seed_coa(company=company_b)
    actor = _mk_user("writer")

    source_entry = _post_entry(
        company=company_a,
        branch=branch_a,
        actor=actor,
        line1_account=coa_a["1301"],
        line1_side="DEBIT",
        line2_account=coa_a["4101"],
        line2_side="CREDIT",
        amount=Decimal("100.00"),
    )
    target_entry = _post_entry(
        company=company_b,
        branch=branch_b,
        actor=actor,
        line1_account=coa_b["5101"],
        line1_side="DEBIT",
        line2_account=coa_b["2109"],
        line2_side="CREDIT",
        amount=Decimal("100.00"),
    )

    with pytest.raises(Phase7BValidationError):
        create_intercompany_transaction(
            source_company_id=company_a.id,
            target_company_id=company_b.id,
            amount=Decimal("100.00"),
            source_account_code="4101",
            target_account_code="5101",
            source_side="CREDIT",
            target_side="DEBIT",
            source_journal_entry_id=source_entry.id,
            target_journal_entry_id=target_entry.id,
            actor_user=actor,
            effective_company_id=company_a.id,
        )

    _grant_intercompany_permission(
        from_company=company_b,
        to_company=company_a,
        permission_code="accounting.intercompany.write",
    )
    tx = create_intercompany_transaction(
        source_company_id=company_a.id,
        target_company_id=company_b.id,
        amount=Decimal("100.00"),
        source_account_code="4101",
        target_account_code="5101",
        source_side="CREDIT",
        target_side="DEBIT",
        source_journal_entry_id=source_entry.id,
        target_journal_entry_id=target_entry.id,
        actor_user=actor,
        effective_company_id=company_a.id,
    )
    assert tx.status == IntercompanyTransaction.Status.PENDING

    with pytest.raises(Phase7BValidationError):
        reconcile_intercompany_transaction(
            tx_id=str(tx.tx_id),
            source_amount=Decimal("100.00"),
            target_amount=Decimal("100.00"),
            actor_user=actor,
            effective_company_id=company_a.id,
        )

    _grant_intercompany_permission(
        from_company=company_b,
        to_company=company_a,
        permission_code="accounting.intercompany.reconcile",
    )
    rec = reconcile_intercompany_transaction(
        tx_id=str(tx.tx_id),
        source_amount=Decimal("100.00"),
        target_amount=Decimal("100.00"),
        actor_user=actor,
        effective_company_id=company_a.id,
    )
    assert rec.status == IntercompanyTransaction.Status.CONFIRMED


@pytest.mark.django_db
def test_staging_first_preflight_snapshot_and_explain_commands(tmp_path):
    company_a, branch_a, company_b, branch_b = _mk_orgs()
    _ = branch_b
    call_command("set_branch_fiscal_mode", company_id=company_a.id, branch_id=branch_a.id, mode="B")

    account = ChartOfAccount.objects.create(
        company=company_a,
        code="1101",
        name="Caja",
        account_type=ChartOfAccount.AccountType.ASSET,
        is_postable=True,
        is_active=True,
    )
    CompanyAccountingConfig.objects.create(
        company=company_a,
        phase7_enabled=True,
        functional_currency="NIO",
    )
    PostingRuleSet.objects.create(
        code="stage_rule",
        version=1,
        status=PostingRuleSet.Status.ACTIVE,
        fiscal_mode=PostingRuleSet.FiscalMode.BOTH,
        scope_company=company_a,
        rules_json={"version": "1.0", "rules": []},
    )

    preflight = tmp_path / "staging_preflight.json"
    snapshot = tmp_path / "finance_snapshot.json"
    explain = tmp_path / "finance_explain.json"

    call_command(
        "export_staging_preflight_manifest",
        company_id=company_a.id,
        branch_id=branch_a.id,
        max_stale_revaluation=1,
        output=str(preflight),
    )
    preflight_payload = json.loads(preflight.read_text(encoding="utf-8"))
    assert preflight_payload["preflight_passed"] is True
    assert preflight_payload["pilot_scope"]["company_id"] == company_a.id
    assert preflight_payload["thresholds"]["open_intercompany"] == 0

    call_command(
        "export_finance_operational_snapshot",
        company_id=company_a.id,
        branch_id=branch_a.id,
        max_stale_revaluation=1,
        output=str(snapshot),
    )
    snapshot_payload = json.loads(snapshot.read_text(encoding="utf-8"))
    assert snapshot_payload["snapshot_passed"] is True
    assert snapshot_payload["health"]["phase7a"]["missing_lines_count"] == 0

    call_command(
        "explain_financial_queries",
        company_id=company_a.id,
        branch_id=branch_a.id,
        account_code=account.code,
        year=2026,
        month=3,
        company_ids=[company_a.id, company_b.id],
        max_critical_scans=100,
        output=str(explain),
    )
    explain_payload = json.loads(explain.read_text(encoding="utf-8"))
    assert explain_payload["summary"]["queries"] == 4
    assert explain_payload["summary"]["failed_explains"] == 0
