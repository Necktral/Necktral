from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.modulos.accounting.models import IntercompanyDisputeReason, IntercompanyTransaction
from apps.modulos.cec.models import CECException
from apps.modulos.iam.models import CompanyLink, LinkGrant, OrgUnit, UserMembership
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _mk_scope():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="Holding-F11")
    source_company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="Source-F11", parent=holding)
    source_branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="Source-B-F11", parent=source_company)
    target_company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="Target-F11", parent=holding)
    target_branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="Target-B-F11", parent=target_company)
    return source_company, source_branch, target_company, target_branch


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


def _grant(*, from_company: OrgUnit, to_company: OrgUnit, permission_code: str):
    perm, _ = Permission.objects.get_or_create(code=permission_code, defaults={"description": permission_code, "is_active": True})
    link, _ = CompanyLink.objects.get_or_create(
        from_company=from_company,
        to_company=to_company,
        defaults={"status": CompanyLink.Status.ACTIVE, "is_active": True},
    )
    LinkGrant.objects.update_or_create(
        link=link,
        permission=perm,
        access_mode=LinkGrant.AccessMode.WRITE,
        scope_org_unit=None,
        defaults={"is_active": True, "valid_from": None, "valid_to": None},
    )


def _seed_reason(company: OrgUnit, code: str = "AMOUNT_MISMATCH") -> IntercompanyDisputeReason:
    return IntercompanyDisputeReason.objects.create(
        company=company,
        code=code,
        version=1,
        title="Diferencia de monto",
        description="Diferencia detectada",
        severity=IntercompanyDisputeReason.Severity.HIGH,
        requires_evidence=True,
        is_active=True,
    )


@pytest.mark.django_db
def test_f11_dispute_requires_reason_and_evidence():
    source_company, source_branch, target_company, _ = _mk_scope()
    actor = _mk_user("f11_api")
    _seed_reason(source_company)
    for perm in [
        "accounting.intercompany.read",
        "accounting.intercompany.write",
        "accounting.intercompany.reconcile",
        "accounting.intercompany.dispute",
    ]:
        _grant(from_company=target_company, to_company=source_company, permission_code=perm)
    client = _mk_client(
        user=actor,
        company=source_company,
        branch=source_branch,
        perms=[
            "accounting.intercompany.read",
            "accounting.intercompany.write",
            "accounting.intercompany.reconcile",
            "accounting.intercompany.dispute",
        ],
    )

    create_resp = client.post(
        "/api/accounting/intercompany/transactions/",
        {
            "target_company_id": target_company.id,
            "amount": "100.00",
            "currency": "NIO",
            "source_account_code": "4101",
            "target_account_code": "5101",
            "source_side": "CREDIT",
            "target_side": "DEBIT",
            "description": "f11 dispute required fields",
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

    missing_reason = client.post(
        f"/api/accounting/intercompany/transactions/{tx_id}/dispute/",
        {"source_amount": "100.00", "target_amount": "95.00"},
        format="json",
    )
    assert missing_reason.status_code in (400, 422)

    missing_evidence = client.post(
        f"/api/accounting/intercompany/transactions/{tx_id}/dispute/",
        {
            "source_amount": "100.00",
            "target_amount": "95.00",
            "reason_code": "AMOUNT_MISMATCH",
            "evidence_refs": [],
        },
        format="json",
    )
    assert missing_evidence.status_code == 409

    ok = client.post(
        f"/api/accounting/intercompany/transactions/{tx_id}/dispute/",
        {
            "source_amount": "100.00",
            "target_amount": "95.00",
            "reason_code": "AMOUNT_MISMATCH",
            "evidence_refs": ["s3://ic/f11-evidence-1.pdf"],
            "note": "mismatch",
        },
        format="json",
    )
    assert ok.status_code == 200
    assert ok.data["status"] == IntercompanyTransaction.Status.DISPUTED
    assert ok.data["dispute"]["case_id"] != ""


@pytest.mark.django_db
def test_f11_settlement_zero_tolerance_keeps_disputed():
    source_company, source_branch, target_company, _ = _mk_scope()
    actor = _mk_user("f11_settle")
    _seed_reason(source_company)
    for perm in [
        "accounting.intercompany.read",
        "accounting.intercompany.write",
        "accounting.intercompany.reconcile",
        "accounting.intercompany.dispute",
        "accounting.intercompany.settle",
    ]:
        _grant(from_company=target_company, to_company=source_company, permission_code=perm)
    client = _mk_client(
        user=actor,
        company=source_company,
        branch=source_branch,
        perms=[
            "accounting.intercompany.read",
            "accounting.intercompany.write",
            "accounting.intercompany.reconcile",
            "accounting.intercompany.dispute",
            "accounting.intercompany.settle",
        ],
    )

    create_resp = client.post(
        "/api/accounting/intercompany/transactions/",
        {
            "target_company_id": target_company.id,
            "amount": "100.00",
            "currency": "NIO",
            "source_account_code": "4101",
            "target_account_code": "5101",
            "source_side": "CREDIT",
            "target_side": "DEBIT",
            "description": "f11 settle zero tolerance",
        },
        format="json",
    )
    tx_id = str(create_resp.data["tx_id"])
    client.post(f"/api/accounting/intercompany/transactions/{tx_id}/confirm/", {"allow_same_actor": True}, format="json")
    client.post(
        f"/api/accounting/intercompany/transactions/{tx_id}/dispute/",
        {
            "source_amount": "100.00",
            "target_amount": "95.00",
            "reason_code": "AMOUNT_MISMATCH",
            "evidence_refs": ["s3://ic/f11-evidence-2.pdf"],
        },
        format="json",
    )

    mismatch_settle = client.post(
        f"/api/accounting/intercompany/transactions/{tx_id}/settle/",
        {
            "source_amount": "100.00",
            "target_amount": "99.00",
            "resolution_note": "still mismatch",
            "close_when_confirmed": True,
            "allow_difference": False,
        },
        format="json",
    )
    assert mismatch_settle.status_code == 200
    assert mismatch_settle.data["status"] == IntercompanyTransaction.Status.DISPUTED

    exact_settle = client.post(
        f"/api/accounting/intercompany/transactions/{tx_id}/settle/",
        {
            "source_amount": "100.00",
            "target_amount": "100.00",
            "resolution_note": "resolved",
            "close_when_confirmed": True,
            "allow_difference": False,
        },
        format="json",
    )
    assert exact_settle.status_code == 200
    assert exact_settle.data["status"] == IntercompanyTransaction.Status.CLOSED


@pytest.mark.django_db
def test_f11_sla_escalation_dedupe_cycle(tmp_path):
    source_company, _source_branch, target_company, _ = _mk_scope()
    _seed_reason(source_company)
    for perm in [
        "accounting.intercompany.write",
        "accounting.intercompany.reconcile",
        "accounting.intercompany.dispute",
        "accounting.intercompany.settle",
    ]:
        _grant(from_company=target_company, to_company=source_company, permission_code=perm)

    happy = tmp_path / "happy.json"
    blocked = tmp_path / "blocked.json"
    cycle_1 = tmp_path / "cycle_1.json"
    cycle_2 = tmp_path / "cycle_2.json"

    call_command(
        "certify_phase11_intercompany_sla",
        company_id=source_company.id,
        target_company_id=target_company.id,
        output=str(happy),
        no_strict=True,
    )
    call_command(
        "certify_phase11_intercompany_sla",
        company_id=source_company.id,
        target_company_id=target_company.id,
        expect_blocked=True,
        output=str(blocked),
        no_strict=True,
    )
    call_command(
        "run_phase11_intercompany_cycle",
        company_id=source_company.id,
        max_open_intercompany=999,
        max_disputed_intercompany=999,
        max_open_outside_sla=999,
        max_disputed_outside_sla=999,
        max_stale_confirmed_unclosed=999,
        max_open_blocking_exceptions=999,
        max_inbox_failed=999,
        max_outbox_failed=999,
        output=str(cycle_1),
        no_strict=True,
    )
    count_first = CECException.objects.filter(
        source_module="ACCOUNTING",
        related_object_type="INTERCOMPANY_TX",
        code="INTERCOMPANY_DISPUTE_SLA_BREACH",
        status__in=[CECException.Status.OPEN, CECException.Status.IN_PROGRESS],
    ).count()
    call_command(
        "run_phase11_intercompany_cycle",
        company_id=source_company.id,
        max_open_intercompany=999,
        max_disputed_intercompany=999,
        max_open_outside_sla=999,
        max_disputed_outside_sla=999,
        max_stale_confirmed_unclosed=999,
        max_open_blocking_exceptions=999,
        max_inbox_failed=999,
        max_outbox_failed=999,
        output=str(cycle_2),
        no_strict=True,
    )
    count_second = CECException.objects.filter(
        source_module="ACCOUNTING",
        related_object_type="INTERCOMPANY_TX",
        code="INTERCOMPANY_DISPUTE_SLA_BREACH",
        status__in=[CECException.Status.OPEN, CECException.Status.IN_PROGRESS],
    ).count()

    assert count_first >= 1
    assert count_second == count_first


@pytest.mark.django_db
def test_f11_env_manifest_and_gate_commands(tmp_path):
    source_company, source_branch, target_company, _ = _mk_scope()
    _seed_reason(source_company)
    for perm in [
        "accounting.intercompany.write",
        "accounting.intercompany.reconcile",
        "accounting.intercompany.dispute",
        "accounting.intercompany.settle",
    ]:
        _grant(from_company=target_company, to_company=source_company, permission_code=perm)

    staging = tmp_path / "phase11_staging.json"
    prod = tmp_path / "phase11_prod.json"
    happy = tmp_path / "phase11_happy.json"
    blocked = tmp_path / "phase11_blocked.json"
    gate = tmp_path / "phase11_gate.json"

    call_command("export_phase11_env_manifest", company_id=source_company.id, branch_id=source_branch.id, output=str(staging))
    call_command("export_phase11_env_manifest", company_id=source_company.id, branch_id=source_branch.id, output=str(prod))
    call_command("compare_phase11_env_manifests", left=str(staging), right=str(prod), strict=True)
    call_command(
        "certify_phase11_intercompany_sla",
        company_id=source_company.id,
        target_company_id=target_company.id,
        output=str(happy),
        no_strict=True,
    )
    call_command(
        "certify_phase11_intercompany_sla",
        company_id=source_company.id,
        target_company_id=target_company.id,
        expect_blocked=True,
        output=str(blocked),
        no_strict=True,
    )
    call_command(
        "verify_phase11_go_live",
        company_id=source_company.id,
        staging_manifest=str(staging),
        prod_manifest=str(prod),
        happy_evidence=str(happy),
        blocked_evidence=str(blocked),
        max_open_intercompany=999,
        max_disputed_intercompany=999,
        max_open_outside_sla=999,
        max_disputed_outside_sla=999,
        max_stale_confirmed_unclosed=999,
        max_open_blocking_exceptions=999,
        max_blocked_consolidation=999,
        max_inbox_failed=999,
        max_outbox_failed=999,
        output=str(gate),
        no_strict=True,
    )

    payload = json.loads(gate.read_text(encoding="utf-8"))
    assert payload["evidence_hash"]
    assert "checks" in payload
