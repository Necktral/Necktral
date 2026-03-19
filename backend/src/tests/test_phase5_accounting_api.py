from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.modulos.accounting.models import FiscalPeriod, JournalDraft, JournalEntry
from apps.modulos.cec.models import CloseRun
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.integration.models import OutboxEvent
from apps.modulos.integration.services import publish_outbox_event
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _mk_org():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


def _client_with_perms(*, company: OrgUnit, branch: OrgUnit, perm_codes: list[str]) -> tuple[APIClient, Any]:
    username = f"u_{uuid.uuid4().hex[:10]}"
    email = f"{username}@test.local"
    user = User.objects.create_user(username=username, email=email, password="pass12345")

    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perm_codes:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)

    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)

    client = APIClient()
    resp = client.post("/api/backend/auth/login/", {"username": username, "password": "pass12345"}, format="json")
    assert resp.status_code == 200
    access = resp.data.get("access") if isinstance(resp.data, dict) else None
    if isinstance(access, str) and access:
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {access}"
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client, user


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
        payload={
            "run_id": str(run.run_id),
            "output_manifest_hash": run.output_manifest_hash,
            "consistency_score": 100,
        },
        company=company,
        branch=branch,
        actor_user=user,
    )
    return run


def _mk_billing_event(*, company: OrgUnit, branch: OrgUnit, user, doc_id: int = 8001, number: int = 1):
    publish_outbox_event(
        source_module="BILLING",
        event_type="DocumentIssued",
        payload={
            "doc_id": int(doc_id),
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


@pytest.mark.django_db
def test_accounting_api_happy_path_approve_post_and_close_period():
    company, branch = _mk_org()
    approver_client, approver_user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "accounting.journal_draft.read",
            "accounting.journal_draft.approve",
        ],
    )
    poster_client, poster_user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "accounting.journal_draft.post",
            "accounting.journal_entry.read",
        ],
    )
    closer_client, closer_user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "accounting.period.read",
            "accounting.period.close",
        ],
    )
    call_command("seed_posting_rules_v1", company_id=company.id)
    run = _mk_packaged_run(company=company, branch=branch, user=approver_user)
    _mk_billing_event(company=company, branch=branch, user=approver_user)
    call_command("project_shadow_ledger", run_id=str(run.run_id))

    list_resp = approver_client.get(f"/api/accounting/journal-drafts/?run_id={run.run_id}")
    assert list_resp.status_code == 200
    assert list_resp.data["count"] >= 1
    assert list_resp.data["results"][0]["state"] == JournalDraft.State.VALIDATED

    approve_resp = approver_client.post(
        "/api/accounting/journal-drafts/approve/",
        {"run_id": str(run.run_id)},
        format="json",
    )
    assert approve_resp.status_code == 200
    assert approve_resp.data["approved"] == 1
    assert approve_resp.data["failed"] == 0

    post_resp = poster_client.post(
        "/api/accounting/journal-drafts/post/",
        {"run_id": str(run.run_id), "require_approved": True},
        format="json",
    )
    assert post_resp.status_code == 200
    assert post_resp.data["posted"] == 1
    assert post_resp.data["failed"] == 0

    draft = JournalDraft.objects.get(close_run_id=str(run.run_id))
    assert draft.state == JournalDraft.State.POSTED
    assert draft.approved_by_id == approver_user.id
    assert JournalEntry.objects.filter(draft=draft).count() == 1
    assert JournalEntry.objects.get(draft=draft).posted_by_id == poster_user.id

    local_dt = timezone.localtime(draft.economic_event.occurred_at)
    close_resp = closer_client.post(
        "/api/accounting/periods/close/",
        {"year": local_dt.year, "month": local_dt.month},
        format="json",
    )
    assert close_resp.status_code == 200
    assert close_resp.data["status"] == FiscalPeriod.Status.CLOSED
    assert close_resp.data["pending_drafts"] == 0
    assert close_resp.data["force_applied"] is False
    assert close_resp.data["gate_summary"]["blocked"] is False
    assert close_resp.data["gate_summary"]["pending_drafts_count"] == 0

    periods_resp = closer_client.get(f"/api/accounting/periods/?year={local_dt.year}")
    assert periods_resp.status_code == 200
    assert periods_resp.data["count"] >= 1

    entries_resp = poster_client.get("/api/accounting/journal-entries/")
    assert entries_resp.status_code == 200
    assert entries_resp.data["count"] >= 1

    event_types = set(
        OutboxEvent.objects.filter(source_module="ACCOUNTING").values_list("event_type", flat=True)
    )
    assert "JournalDraftApproved" in event_types
    assert "JournalPosted" in event_types
    assert "PeriodClosed" in event_types


@pytest.mark.django_db
def test_accounting_api_post_returns_409_when_sod_same_approver_and_no_override():
    company, branch = _mk_org()
    approver_client, user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "accounting.journal_draft.approve",
            "accounting.journal_draft.post",
        ],
    )
    call_command("seed_posting_rules_v1", company_id=company.id)
    run = _mk_packaged_run(company=company, branch=branch, user=user)
    _mk_billing_event(company=company, branch=branch, user=user)
    call_command("project_shadow_ledger", run_id=str(run.run_id))
    draft = JournalDraft.objects.get(close_run_id=str(run.run_id))

    approve_resp = approver_client.post(
        "/api/accounting/journal-drafts/approve/",
        {"run_id": str(run.run_id)},
        format="json",
    )
    assert approve_resp.status_code == 200
    assert approve_resp.data["approved"] == 1

    post_resp = approver_client.post(
        "/api/accounting/journal-drafts/post/",
        {"run_id": str(run.run_id), "require_approved": True, "strict": True},
        format="json",
    )
    assert post_resp.status_code == 409
    assert post_resp.data["error"]["code"] == "CONFLICT"
    details = post_resp.data["error"]["details"]
    assert details["posted"] == 0
    assert details["failed"] >= 1
    assert "SoD" in details["errors"][0]["error"]

    draft.refresh_from_db()
    assert draft.state == JournalDraft.State.APPROVED_FOR_POSTING
    assert JournalEntry.objects.filter(draft=draft).count() == 0


@pytest.mark.django_db
def test_accounting_api_post_returns_409_when_strict_and_period_is_closed():
    company, branch = _mk_org()
    client, user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "accounting.journal_draft.approve",
            "accounting.journal_draft.post",
            "accounting.sod.override",
        ],
    )
    call_command("seed_posting_rules_v1", company_id=company.id)
    run = _mk_packaged_run(company=company, branch=branch, user=user)
    _mk_billing_event(company=company, branch=branch, user=user)
    call_command("project_shadow_ledger", run_id=str(run.run_id))
    draft = JournalDraft.objects.get(close_run_id=str(run.run_id))
    local_dt = timezone.localtime(draft.economic_event.occurred_at)

    approve_resp = client.post(
        "/api/accounting/journal-drafts/approve/",
        {"run_id": str(run.run_id)},
        format="json",
    )
    assert approve_resp.status_code == 200
    assert approve_resp.data["approved"] == 1

    period, _ = FiscalPeriod.objects.get_or_create(company=company, year=local_dt.year, month=local_dt.month)
    period.status = FiscalPeriod.Status.CLOSED
    period.closed_at = timezone.now()
    period.closed_by = user
    period.save(update_fields=["status", "closed_at", "closed_by"])

    post_resp = client.post(
        "/api/accounting/journal-drafts/post/",
        {
            "run_id": str(run.run_id),
            "require_approved": True,
            "allow_same_approver": True,
            "strict": True,
        },
        format="json",
    )
    assert post_resp.status_code == 409
    assert post_resp.data["error"]["code"] == "CONFLICT"
    details = post_resp.data["error"]["details"]
    assert details["posted"] == 0
    assert details["failed"] >= 1
    assert "Periodo cerrado" in details["errors"][0]["error"]


@pytest.mark.django_db
def test_accounting_api_close_period_returns_409_with_pending_drafts():
    company, branch = _mk_org()
    client, user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["accounting.period.close"],
    )
    call_command("seed_posting_rules_v1", company_id=company.id)
    run = _mk_packaged_run(company=company, branch=branch, user=user)
    _mk_billing_event(company=company, branch=branch, user=user)
    call_command("project_shadow_ledger", run_id=str(run.run_id))
    draft = JournalDraft.objects.get(close_run_id=str(run.run_id))
    local_dt = timezone.localtime(draft.economic_event.occurred_at)

    close_resp = client.post(
        "/api/accounting/periods/close/",
        {"year": local_dt.year, "month": local_dt.month},
        format="json",
    )
    assert close_resp.status_code == 409
    assert close_resp.data["error"]["code"] == "CONFLICT"
    assert "drafts pendientes" in close_resp.data["error"]["message"]
    gate = close_resp.data["error"]["details"]["gate_summary"]
    assert gate["blocked"] is True
    assert gate["pending_drafts_count"] >= 1


@pytest.mark.django_db
def test_accounting_api_close_period_force_allows_pending_drafts_only():
    company, branch = _mk_org()
    client, user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["accounting.period.close"],
    )
    call_command("seed_posting_rules_v1", company_id=company.id)
    run = _mk_packaged_run(company=company, branch=branch, user=user)
    _mk_billing_event(company=company, branch=branch, user=user)
    call_command("project_shadow_ledger", run_id=str(run.run_id))
    draft = JournalDraft.objects.get(close_run_id=str(run.run_id))
    local_dt = timezone.localtime(draft.economic_event.occurred_at)

    close_resp = client.post(
        "/api/accounting/periods/close/",
        {"year": local_dt.year, "month": local_dt.month, "force": True},
        format="json",
    )
    assert close_resp.status_code == 200
    assert close_resp.data["status"] == FiscalPeriod.Status.CLOSED
    assert close_resp.data["force_applied"] is True
    assert close_resp.data["gate_summary"]["force_applied"] is True
    assert close_resp.data["gate_summary"]["pending_drafts_count"] >= 1
    assert close_resp.data["gate_summary"]["blocked"] is False


@pytest.mark.django_db
def test_accounting_api_close_period_force_still_blocks_failed_outbox():
    company, branch = _mk_org()
    client, user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["accounting.period.close"],
    )
    call_command("seed_posting_rules_v1", company_id=company.id)
    run = _mk_packaged_run(company=company, branch=branch, user=user)
    _mk_billing_event(company=company, branch=branch, user=user)
    call_command("project_shadow_ledger", run_id=str(run.run_id))
    call_command("approve_journal_drafts", run_id=str(run.run_id), company_id=company.id)
    call_command("post_journal_drafts", run_id=str(run.run_id), company_id=company.id, require_approved=True)
    draft = JournalDraft.objects.get(close_run_id=str(run.run_id))
    local_dt = timezone.localtime(draft.economic_event.occurred_at)

    failed = publish_outbox_event(
        source_module="INVENTORY",
        event_type="InventoryAdjusted",
        payload={
            "movement_id": 801,
            "movement_type": "ADJUST",
            "warehouse_id": 1,
            "item_id": 1,
            "qty_delta": "1.0000",
            "new_qty_on_hand": "1.0000",
            "avg_cost": "1.000000",
        },
        company=company,
        branch=branch,
        actor_user=user,
    )
    failed.status = OutboxEvent.Status.FAILED
    failed.last_error = "dispatch failed"
    failed.occurred_at = draft.economic_event.occurred_at
    failed.save(update_fields=["status", "last_error", "occurred_at"])

    close_resp = client.post(
        "/api/accounting/periods/close/",
        {"year": local_dt.year, "month": local_dt.month, "force": True},
        format="json",
    )
    assert close_resp.status_code == 409
    gate = close_resp.data["error"]["details"]["gate_summary"]
    assert gate["force_applied"] is True
    assert gate["failed_outbox_count"] >= 1
    assert "FAILED_OUTBOX" in gate["blocking_reasons"]


@pytest.mark.django_db
def test_accounting_api_close_period_force_blocks_failed_accounting_outbox():
    company, branch = _mk_org()
    client, user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["accounting.period.close"],
    )
    call_command("seed_posting_rules_v1", company_id=company.id)
    run = _mk_packaged_run(company=company, branch=branch, user=user)
    _mk_billing_event(company=company, branch=branch, user=user)
    call_command("project_shadow_ledger", run_id=str(run.run_id))
    call_command("approve_journal_drafts", run_id=str(run.run_id), company_id=company.id)
    call_command("post_journal_drafts", run_id=str(run.run_id), company_id=company.id, require_approved=True)
    draft = JournalDraft.objects.get(close_run_id=str(run.run_id))
    local_dt = timezone.localtime(draft.economic_event.occurred_at)

    failed = OutboxEvent.objects.filter(source_module="ACCOUNTING", event_type="JournalPosted").order_by("-id").first()
    assert failed is not None
    failed.status = OutboxEvent.Status.FAILED
    failed.last_error = "accounting outbox dead-letter"
    failed.occurred_at = draft.economic_event.occurred_at
    failed.save(update_fields=["status", "last_error", "occurred_at"])

    close_resp = client.post(
        "/api/accounting/periods/close/",
        {"year": local_dt.year, "month": local_dt.month, "force": True},
        format="json",
    )
    assert close_resp.status_code == 409
    gate = close_resp.data["error"]["details"]["gate_summary"]
    assert gate["force_applied"] is True
    assert gate["failed_outbox_count"] >= 1
    assert "FAILED_OUTBOX" in gate["blocking_reasons"]
    sample_modules = {str(row.get("source_module")) for row in list(gate.get("failed_outbox_sample") or [])}
    assert "ACCOUNTING" in sample_modules


@pytest.mark.django_db
def test_accounting_api_close_period_force_blocks_operational_reconciliation_mismatch():
    company, branch = _mk_org()
    client, user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["accounting.period.close"],
    )
    event = publish_outbox_event(
        source_module="BILLING",
        event_type="DocumentIssued",
        payload={
            "doc_id": 8901,
            "doc_type": "INVOICE",
            "series": "A",
            "number": 9,
            "currency": "NIO",
            "subtotal": "100.00",
            "tax_total": "15.00",
            "total": "115.00",
            "is_fiscal": True,
            "fiscal_adapter_mode": "B",
        },
        company=company,
        branch=branch,
        actor_user=user,
    )
    local_dt = timezone.localtime(event.occurred_at)

    close_resp = client.post(
        "/api/accounting/periods/close/",
        {"year": local_dt.year, "month": local_dt.month, "force": True},
        format="json",
    )
    assert close_resp.status_code == 409
    gate = close_resp.data["error"]["details"]["gate_summary"]
    assert gate["reconciliation_mismatch_count"] >= 1
    assert gate["pending_operational_events_count"] >= 1
    assert "RECONCILIATION_MISMATCH" in gate["blocking_reasons"]
    assert "PENDING_OPERATIONAL_EVENTS" in gate["blocking_reasons"]


@pytest.mark.django_db
def test_accounting_api_close_period_force_blocks_draft_exception():
    company, branch = _mk_org()
    client, user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["accounting.period.close"],
    )
    call_command("seed_posting_rules_v1", company_id=company.id)
    run = _mk_packaged_run(company=company, branch=branch, user=user)
    _mk_billing_event(company=company, branch=branch, user=user)
    call_command("project_shadow_ledger", run_id=str(run.run_id))
    draft = JournalDraft.objects.get(close_run_id=str(run.run_id))
    draft.state = JournalDraft.State.EXCEPTION
    draft.save(update_fields=["state"])
    local_dt = timezone.localtime(draft.economic_event.occurred_at)

    close_resp = client.post(
        "/api/accounting/periods/close/",
        {"year": local_dt.year, "month": local_dt.month, "force": True},
        format="json",
    )
    assert close_resp.status_code == 409
    gate = close_resp.data["error"]["details"]["gate_summary"]
    assert gate["draft_exception_count"] >= 1
    assert "DRAFT_EXCEPTION" in gate["blocking_reasons"]


@pytest.mark.django_db
def test_accounting_api_close_period_sod_blocks_same_poster_without_override():
    company, branch = _mk_org()
    approver_client, approver_user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["accounting.journal_draft.approve"],
    )
    poster_closer_client, poster_user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["accounting.journal_draft.post", "accounting.period.close"],
    )
    call_command("seed_posting_rules_v1", company_id=company.id)
    run = _mk_packaged_run(company=company, branch=branch, user=approver_user)
    _mk_billing_event(company=company, branch=branch, user=approver_user)
    call_command("project_shadow_ledger", run_id=str(run.run_id))

    approve_resp = approver_client.post(
        "/api/accounting/journal-drafts/approve/",
        {"run_id": str(run.run_id)},
        format="json",
    )
    assert approve_resp.status_code == 200

    post_resp = poster_closer_client.post(
        "/api/accounting/journal-drafts/post/",
        {"run_id": str(run.run_id), "require_approved": True},
        format="json",
    )
    assert post_resp.status_code == 200
    assert post_resp.data["posted"] == 1

    draft = JournalDraft.objects.get(close_run_id=str(run.run_id))
    local_dt = timezone.localtime(draft.economic_event.occurred_at)
    close_resp = poster_closer_client.post(
        "/api/accounting/periods/close/",
        {"year": local_dt.year, "month": local_dt.month},
        format="json",
    )
    assert close_resp.status_code == 409
    assert close_resp.data["error"]["code"] == "CONFLICT"
    assert "SoD" in close_resp.data["error"]["message"]


@pytest.mark.django_db
def test_accounting_api_reverse_journal_entry_happy_and_idempotent():
    company, branch = _mk_org()
    approver_client, approver_user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["accounting.journal_draft.approve"],
    )
    poster_client, poster_user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["accounting.journal_draft.post"],
    )
    reverser_client, reverser_user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["accounting.journal_entry.reverse", "accounting.journal_entry.read"],
    )
    call_command("seed_posting_rules_v1", company_id=company.id)
    run = _mk_packaged_run(company=company, branch=branch, user=approver_user)
    _mk_billing_event(company=company, branch=branch, user=approver_user)
    call_command("project_shadow_ledger", run_id=str(run.run_id))

    assert approver_client.post(
        "/api/accounting/journal-drafts/approve/",
        {"run_id": str(run.run_id)},
        format="json",
    ).status_code == 200
    assert poster_client.post(
        "/api/accounting/journal-drafts/post/",
        {"run_id": str(run.run_id), "require_approved": True},
        format="json",
    ).status_code == 200

    original_entry = JournalEntry.objects.get(draft__close_run_id=str(run.run_id), posted_by_id=poster_user.id)
    reverse_resp = reverser_client.post(
        f"/api/accounting/journal-entries/{original_entry.id}/reverse/",
        {"reason": "Ajuste por reclasificación"},
        format="json",
    )
    assert reverse_resp.status_code == 201
    assert reverse_resp.data["idempotent"] is False
    reversal_entry_id = reverse_resp.data["reversal_entry_id"]

    reversal_entry = JournalEntry.objects.get(id=reversal_entry_id)
    assert reversal_entry.reversed_entry_id == original_entry.id
    assert reversal_entry.posted_by_id == reverser_user.id

    reverse_again = reverser_client.post(
        f"/api/accounting/journal-entries/{original_entry.id}/reverse/",
        {"reason": "Ajuste por reclasificación"},
        format="json",
    )
    assert reverse_again.status_code == 200
    assert reverse_again.data["idempotent"] is True
    assert reverse_again.data["reversal_entry_id"] == reversal_entry_id
    assert JournalEntry.objects.filter(reversed_entry_id=original_entry.id).count() == 1
    assert OutboxEvent.objects.filter(source_module="ACCOUNTING", event_type="JournalReversed").exists()


@pytest.mark.django_db
def test_accounting_api_reverse_sod_blocks_same_poster_without_override():
    company, branch = _mk_org()
    operator_client, operator_user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "accounting.journal_draft.approve",
            "accounting.journal_draft.post",
            "accounting.journal_entry.reverse",
        ],
    )
    call_command("seed_posting_rules_v1", company_id=company.id)
    run = _mk_packaged_run(company=company, branch=branch, user=operator_user)
    _mk_billing_event(company=company, branch=branch, user=operator_user)
    call_command("project_shadow_ledger", run_id=str(run.run_id))

    assert operator_client.post(
        "/api/accounting/journal-drafts/approve/",
        {"run_id": str(run.run_id)},
        format="json",
    ).status_code == 200
    assert operator_client.post(
        "/api/accounting/journal-drafts/post/",
        {"run_id": str(run.run_id), "require_approved": True, "allow_same_approver": True},
        format="json",
    ).status_code == 403

    post_ok = operator_client.post(
        "/api/accounting/journal-drafts/post/",
        {"run_id": str(run.run_id), "require_approved": True},
        format="json",
    )
    assert post_ok.status_code == 409
    assert post_ok.data["error"]["code"] == "CONFLICT"

    # Rehacer posting con override explícito
    operator_override_client, _ = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "accounting.journal_draft.post",
            "accounting.journal_entry.reverse",
            "accounting.sod.override",
        ],
    )
    post_override = operator_override_client.post(
        "/api/accounting/journal-drafts/post/",
        {"run_id": str(run.run_id), "require_approved": True, "allow_same_approver": True},
        format="json",
    )
    assert post_override.status_code == 200
    assert post_override.data["posted"] == 1

    original_entry = JournalEntry.objects.get(draft__close_run_id=str(run.run_id))
    reverse_resp = operator_override_client.post(
        f"/api/accounting/journal-entries/{original_entry.id}/reverse/",
        {"reason": "reversa sin override"},
        format="json",
    )
    assert reverse_resp.status_code == 409
    assert reverse_resp.data["error"]["code"] == "CONFLICT"
    assert "SoD" in reverse_resp.data["error"]["message"]


@pytest.mark.django_db
def test_accounting_api_reverse_allows_override_and_blocks_closed_period():
    company, branch = _mk_org()
    actor_client, actor_user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "accounting.journal_draft.approve",
            "accounting.journal_draft.post",
            "accounting.journal_entry.reverse",
            "accounting.sod.override",
            "accounting.period.close",
        ],
    )
    call_command("seed_posting_rules_v1", company_id=company.id)
    run = _mk_packaged_run(company=company, branch=branch, user=actor_user)
    _mk_billing_event(company=company, branch=branch, user=actor_user)
    call_command("project_shadow_ledger", run_id=str(run.run_id))

    assert actor_client.post(
        "/api/accounting/journal-drafts/approve/",
        {"run_id": str(run.run_id)},
        format="json",
    ).status_code == 200
    assert actor_client.post(
        "/api/accounting/journal-drafts/post/",
        {"run_id": str(run.run_id), "require_approved": True, "allow_same_approver": True},
        format="json",
    ).status_code == 200

    original_entry = JournalEntry.objects.get(draft__close_run_id=str(run.run_id))
    local_dt = timezone.localtime(original_entry.posted_at)
    close_resp = actor_client.post(
        "/api/accounting/periods/close/",
        {"year": local_dt.year, "month": local_dt.month, "allow_same_poster": True},
        format="json",
    )
    assert close_resp.status_code == 200

    reverse_closed = actor_client.post(
        f"/api/accounting/journal-entries/{original_entry.id}/reverse/",
        {
            "reason": "reversa en periodo cerrado",
            "reversal_date": str(local_dt.date()),
            "allow_same_poster": True,
        },
        format="json",
    )
    assert reverse_closed.status_code == 409
    assert reverse_closed.data["error"]["code"] == "CONFLICT"
    assert "Periodo de reversa cerrado" in reverse_closed.data["error"]["message"]


@pytest.mark.django_db
def test_accounting_api_reverse_batch_by_run_happy_and_idempotent():
    company, branch = _mk_org()
    approver_client, approver_user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["accounting.journal_draft.approve"],
    )
    poster_client, poster_user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["accounting.journal_draft.post"],
    )
    reverser_client, reverser_user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["accounting.journal_entry.reverse_batch"],
    )
    call_command("seed_posting_rules_v1", company_id=company.id)
    run = _mk_packaged_run(company=company, branch=branch, user=approver_user)
    _mk_billing_event(company=company, branch=branch, user=approver_user, doc_id=9001, number=1)
    _mk_billing_event(company=company, branch=branch, user=approver_user, doc_id=9002, number=2)
    call_command("project_shadow_ledger", run_id=str(run.run_id))

    assert approver_client.post(
        "/api/accounting/journal-drafts/approve/",
        {"run_id": str(run.run_id)},
        format="json",
    ).status_code == 200
    assert poster_client.post(
        "/api/accounting/journal-drafts/post/",
        {"run_id": str(run.run_id), "require_approved": True},
        format="json",
    ).status_code == 200
    assert JournalEntry.objects.filter(draft__close_run_id=str(run.run_id), posted_by_id=poster_user.id).count() == 2

    batch_1 = reverser_client.post(
        "/api/accounting/journal-entries/reverse-batch/",
        {"run_id": str(run.run_id), "reason": "reversa masiva run"},
        format="json",
    )
    assert batch_1.status_code == 200
    assert batch_1.data["attempted"] == 2
    assert batch_1.data["reversed"] == 2
    assert batch_1.data["idempotent"] == 0
    assert batch_1.data["failed"] == 0

    batch_2 = reverser_client.post(
        "/api/accounting/journal-entries/reverse-batch/",
        {"run_id": str(run.run_id), "reason": "reversa masiva run"},
        format="json",
    )
    assert batch_2.status_code == 200
    assert batch_2.data["attempted"] == 2
    assert batch_2.data["reversed"] == 0
    assert batch_2.data["idempotent"] == 2
    assert batch_2.data["failed"] == 0
    assert JournalEntry.objects.filter(company=company, reversed_entry__isnull=False, posted_by_id=reverser_user.id).count() == 2
    assert OutboxEvent.objects.filter(source_module="ACCOUNTING", event_type="JournalReversed").count() >= 2


@pytest.mark.django_db
def test_accounting_api_reverse_batch_strict_conflict_and_override_flow():
    company, branch = _mk_org()
    operator_client, operator_user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "accounting.journal_draft.approve",
            "accounting.journal_draft.post",
            "accounting.journal_entry.reverse_batch",
            "accounting.sod.override",
        ],
    )
    call_command("seed_posting_rules_v1", company_id=company.id)
    run = _mk_packaged_run(company=company, branch=branch, user=operator_user)
    _mk_billing_event(company=company, branch=branch, user=operator_user, doc_id=9101, number=1)
    call_command("project_shadow_ledger", run_id=str(run.run_id))

    assert operator_client.post(
        "/api/accounting/journal-drafts/approve/",
        {"run_id": str(run.run_id)},
        format="json",
    ).status_code == 200
    assert operator_client.post(
        "/api/accounting/journal-drafts/post/",
        {"run_id": str(run.run_id), "require_approved": True, "allow_same_approver": True},
        format="json",
    ).status_code == 200

    strict_resp = operator_client.post(
        "/api/accounting/journal-entries/reverse-batch/",
        {"run_id": str(run.run_id), "reason": "batch sin override", "strict": True},
        format="json",
    )
    assert strict_resp.status_code == 409
    assert strict_resp.data["error"]["code"] == "CONFLICT"
    details = strict_resp.data["error"]["details"]
    assert details["failed"] >= 1
    assert "SoD" in details["errors"][0]["error"]

    non_strict_resp = operator_client.post(
        "/api/accounting/journal-entries/reverse-batch/",
        {"run_id": str(run.run_id), "reason": "batch sin override", "strict": False},
        format="json",
    )
    assert non_strict_resp.status_code == 200
    assert non_strict_resp.data["failed"] >= 1

    override_resp = operator_client.post(
        "/api/accounting/journal-entries/reverse-batch/",
        {
            "run_id": str(run.run_id),
            "reason": "batch con override",
            "allow_same_poster": True,
            "strict": True,
        },
        format="json",
    )
    assert override_resp.status_code == 200
    assert override_resp.data["reversed"] == 1
    assert override_resp.data["failed"] == 0


@pytest.mark.django_db
def test_accounting_api_reverse_batch_requires_permission():
    company, branch = _mk_org()
    client, _ = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["accounting.journal_entry.read"],
    )
    resp = client.post(
        "/api/accounting/journal-entries/reverse-batch/",
        {"run_id": "dummy", "reason": "x"},
        format="json",
    )
    assert resp.status_code == 403


@pytest.mark.django_db
def test_accounting_api_requires_permission_for_approve():
    company, branch = _mk_org()
    client, _ = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["accounting.journal_draft.read"],
    )
    resp = client.post("/api/accounting/journal-drafts/approve/", {}, format="json")
    assert resp.status_code == 403
