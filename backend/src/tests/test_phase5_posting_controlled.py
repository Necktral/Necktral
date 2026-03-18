from __future__ import annotations

import json
from datetime import timedelta
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.utils import timezone

from apps.accounting.models import FiscalPeriod, JournalDraft, JournalEntry
from apps.cec.models import CloseRun
from apps.iam.models import OrgUnit
from apps.integration.models import OutboxEvent
from apps.integration.services import publish_outbox_event

User = get_user_model()


def _mk_scope():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


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


def _mk_billing_event(*, company: OrgUnit, branch: OrgUnit, user, doc_id: int = 7001, number: int = 1):
    publish_outbox_event(
        source_module="BILLING",
        event_type="DocumentIssued",
        payload={
            "doc_id": int(doc_id),
            "doc_type": "INVOICE",
            "series": "A",
            "number": int(number),
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


@pytest.mark.django_db
def test_post_journal_drafts_posts_and_is_idempotent():
    company, branch = _mk_scope()
    user = User.objects.create_user(username="phase5_ok", password="x")
    call_command("seed_posting_rules_v1", company_id=company.id)
    run = _mk_packaged_run(company=company, branch=branch, user=user)
    _mk_billing_event(company=company, branch=branch, user=user)

    call_command("project_shadow_ledger", run_id=str(run.run_id))
    draft = JournalDraft.objects.get(close_run_id=str(run.run_id))
    assert draft.state == JournalDraft.State.VALIDATED

    first_out = StringIO()
    call_command("post_journal_drafts", run_id=str(run.run_id), company_id=company.id, stdout=first_out)
    payload = json.loads(first_out.getvalue())
    assert payload["posted"] == 1
    assert payload["failed"] == 0
    assert JournalEntry.objects.filter(draft=draft).count() == 1

    draft.refresh_from_db()
    assert draft.state == JournalDraft.State.POSTED
    assert OutboxEvent.objects.filter(source_module="ACCOUNTING", event_type="JournalPosted").exists()

    second_out = StringIO()
    call_command("post_journal_drafts", run_id=str(run.run_id), company_id=company.id, stdout=second_out)
    payload2 = json.loads(second_out.getvalue())
    assert payload2["posted"] == 0
    assert payload2["failed"] == 0
    assert JournalEntry.objects.filter(draft=draft).count() == 1


@pytest.mark.django_db
def test_post_journal_drafts_blocks_closed_period():
    company, branch = _mk_scope()
    user = User.objects.create_user(username="phase5_closed", password="x")
    call_command("seed_posting_rules_v1", company_id=company.id)
    run = _mk_packaged_run(company=company, branch=branch, user=user)
    _mk_billing_event(company=company, branch=branch, user=user)
    call_command("project_shadow_ledger", run_id=str(run.run_id))

    draft = JournalDraft.objects.get(close_run_id=str(run.run_id))
    dt_local = timezone.localtime(draft.economic_event.occurred_at)
    period, _ = FiscalPeriod.objects.get_or_create(
        company=company,
        year=dt_local.year,
        month=dt_local.month,
    )
    period.status = FiscalPeriod.Status.CLOSED
    period.closed_at = timezone.now()
    period.closed_by = user
    period.save(update_fields=["status", "closed_at", "closed_by"])

    with pytest.raises(CommandError):
        call_command("post_journal_drafts", run_id=str(run.run_id), company_id=company.id)

    draft.refresh_from_db()
    assert draft.state == JournalDraft.State.VALIDATED
    assert JournalEntry.objects.filter(draft=draft).count() == 0


@pytest.mark.django_db
def test_post_journal_drafts_require_approved_and_auto_approve():
    company, branch = _mk_scope()
    user = User.objects.create_user(username="phase5_approved", password="x")
    call_command("seed_posting_rules_v1", company_id=company.id)
    run = _mk_packaged_run(company=company, branch=branch, user=user)
    _mk_billing_event(company=company, branch=branch, user=user)
    call_command("project_shadow_ledger", run_id=str(run.run_id))
    draft = JournalDraft.objects.get(close_run_id=str(run.run_id))
    assert draft.state == JournalDraft.State.VALIDATED

    out_skip = StringIO()
    call_command(
        "post_journal_drafts",
        run_id=str(run.run_id),
        company_id=company.id,
        require_approved=True,
        no_strict=True,
        stdout=out_skip,
    )
    skipped_payload = json.loads(out_skip.getvalue())
    assert skipped_payload["posted"] == 0
    assert skipped_payload["skipped"] >= 1

    out_post = StringIO()
    call_command(
        "post_journal_drafts",
        run_id=str(run.run_id),
        company_id=company.id,
        require_approved=True,
        auto_approve=True,
        stdout=out_post,
    )
    posted_payload = json.loads(out_post.getvalue())
    assert posted_payload["approved"] == 1
    assert posted_payload["posted"] == 1

    draft.refresh_from_db()
    assert draft.state == JournalDraft.State.POSTED
    assert JournalEntry.objects.filter(draft=draft).count() == 1


@pytest.mark.django_db
def test_approve_journal_drafts_command():
    company, branch = _mk_scope()
    user = User.objects.create_user(username="phase5_approve", password="x")
    call_command("seed_posting_rules_v1", company_id=company.id)
    run = _mk_packaged_run(company=company, branch=branch, user=user)
    _mk_billing_event(company=company, branch=branch, user=user)
    call_command("project_shadow_ledger", run_id=str(run.run_id))

    draft = JournalDraft.objects.get(close_run_id=str(run.run_id))
    assert draft.state == JournalDraft.State.VALIDATED

    out = StringIO()
    call_command("approve_journal_drafts", run_id=str(run.run_id), company_id=company.id, stdout=out)
    payload = json.loads(out.getvalue())

    assert payload["approved"] == 1
    assert payload["failed"] == 0
    draft.refresh_from_db()
    assert draft.state == JournalDraft.State.APPROVED_FOR_POSTING
    assert OutboxEvent.objects.filter(source_module="ACCOUNTING", event_type="JournalDraftApproved").exists()


@pytest.mark.django_db
def test_close_fiscal_period_requires_no_pending_drafts():
    company, branch = _mk_scope()
    user = User.objects.create_user(username="phase5_close", password="x")
    call_command("seed_posting_rules_v1", company_id=company.id)
    run = _mk_packaged_run(company=company, branch=branch, user=user)
    _mk_billing_event(company=company, branch=branch, user=user)
    call_command("project_shadow_ledger", run_id=str(run.run_id))
    draft = JournalDraft.objects.get(close_run_id=str(run.run_id))
    dt_local = timezone.localtime(draft.economic_event.occurred_at)

    with pytest.raises(CommandError):
        call_command(
            "close_fiscal_period",
            company_id=company.id,
            year=dt_local.year,
            month=dt_local.month,
        )

    call_command(
        "approve_journal_drafts",
        run_id=str(run.run_id),
        company_id=company.id,
    )
    call_command(
        "post_journal_drafts",
        run_id=str(run.run_id),
        company_id=company.id,
        require_approved=True,
    )

    out = StringIO()
    call_command(
        "close_fiscal_period",
        company_id=company.id,
        year=dt_local.year,
        month=dt_local.month,
        stdout=out,
    )
    payload = json.loads(out.getvalue())
    assert payload["status"] == FiscalPeriod.Status.CLOSED
    assert payload["pending_drafts"] == 0
    assert payload["force_applied"] is False
    assert payload["gate_summary"]["blocked"] is False
    assert payload["gate_summary"]["pending_drafts_count"] == 0
    assert OutboxEvent.objects.filter(source_module="ACCOUNTING", event_type="PeriodClosed").exists()


@pytest.mark.django_db
def test_close_fiscal_period_force_allows_pending_drafts_if_no_other_gates_fail():
    company, branch = _mk_scope()
    user = User.objects.create_user(username="phase5_close_force_pending", password="x")
    call_command("seed_posting_rules_v1", company_id=company.id)
    run = _mk_packaged_run(company=company, branch=branch, user=user)
    _mk_billing_event(company=company, branch=branch, user=user)
    call_command("project_shadow_ledger", run_id=str(run.run_id))
    draft = JournalDraft.objects.get(close_run_id=str(run.run_id))
    dt_local = timezone.localtime(draft.economic_event.occurred_at)

    out = StringIO()
    call_command(
        "close_fiscal_period",
        company_id=company.id,
        year=dt_local.year,
        month=dt_local.month,
        force=True,
        stdout=out,
    )
    payload = json.loads(out.getvalue())
    assert payload["status"] == FiscalPeriod.Status.CLOSED
    assert payload["force_applied"] is True
    assert payload["pending_drafts"] >= 1
    assert payload["gate_summary"]["force_applied"] is True
    assert payload["gate_summary"]["blocked"] is False
    assert payload["gate_summary"]["pending_drafts_count"] >= 1


@pytest.mark.django_db
def test_close_fiscal_period_force_blocks_when_failed_outbox_exists():
    company, branch = _mk_scope()
    user = User.objects.create_user(username="phase5_close_force_failed_outbox", password="x")
    call_command("seed_posting_rules_v1", company_id=company.id)
    run = _mk_packaged_run(company=company, branch=branch, user=user)
    _mk_billing_event(company=company, branch=branch, user=user)
    call_command("project_shadow_ledger", run_id=str(run.run_id))
    call_command("approve_journal_drafts", run_id=str(run.run_id), company_id=company.id)
    call_command("post_journal_drafts", run_id=str(run.run_id), company_id=company.id, require_approved=True)

    draft = JournalDraft.objects.get(close_run_id=str(run.run_id))
    dt_local = timezone.localtime(draft.economic_event.occurred_at)

    failed = publish_outbox_event(
        source_module="INVENTORY",
        event_type="InventoryAdjusted",
        payload={
            "movement_id": 9090,
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
    failed.last_error = "broker timeout"
    failed.occurred_at = draft.economic_event.occurred_at
    failed.save(update_fields=["status", "last_error", "occurred_at"])

    with pytest.raises(CommandError) as exc_info:
        call_command(
            "close_fiscal_period",
            company_id=company.id,
            year=dt_local.year,
            month=dt_local.month,
            force=True,
        )
    assert "outbox fallido" in str(exc_info.value)

    blocked = OutboxEvent.objects.filter(source_module="ACCOUNTING", event_type="PeriodCloseBlocked").order_by("-id").first()
    assert blocked is not None
    gate = (blocked.payload or {}).get("data", {}).get("gate_summary", {})
    assert int(gate.get("failed_outbox_count") or 0) >= 1
    assert "FAILED_OUTBOX" in list(gate.get("blocking_reasons") or [])


@pytest.mark.django_db
def test_close_fiscal_period_force_blocks_when_accounting_outbox_failed():
    company, branch = _mk_scope()
    user = User.objects.create_user(username="phase5_close_force_failed_outbox_accounting", password="x")
    call_command("seed_posting_rules_v1", company_id=company.id)
    run = _mk_packaged_run(company=company, branch=branch, user=user)
    _mk_billing_event(company=company, branch=branch, user=user)
    call_command("project_shadow_ledger", run_id=str(run.run_id))
    call_command("approve_journal_drafts", run_id=str(run.run_id), company_id=company.id)
    call_command("post_journal_drafts", run_id=str(run.run_id), company_id=company.id, require_approved=True)

    draft = JournalDraft.objects.get(close_run_id=str(run.run_id))
    dt_local = timezone.localtime(draft.economic_event.occurred_at)

    failed = OutboxEvent.objects.filter(source_module="ACCOUNTING", event_type="JournalPosted").order_by("-id").first()
    assert failed is not None
    failed.status = OutboxEvent.Status.FAILED
    failed.last_error = "projection dispatcher failure"
    failed.occurred_at = draft.economic_event.occurred_at
    failed.save(update_fields=["status", "last_error", "occurred_at"])

    with pytest.raises(CommandError) as exc_info:
        call_command(
            "close_fiscal_period",
            company_id=company.id,
            year=dt_local.year,
            month=dt_local.month,
            force=True,
        )
    assert "outbox fallido" in str(exc_info.value)

    blocked = OutboxEvent.objects.filter(source_module="ACCOUNTING", event_type="PeriodCloseBlocked").order_by("-id").first()
    assert blocked is not None
    gate = (blocked.payload or {}).get("data", {}).get("gate_summary", {})
    assert int(gate.get("failed_outbox_count") or 0) >= 1
    assert "FAILED_OUTBOX" in list(gate.get("blocking_reasons") or [])
    sample_modules = {str(row.get("source_module")) for row in list(gate.get("failed_outbox_sample") or [])}
    assert "ACCOUNTING" in sample_modules


@pytest.mark.django_db
def test_close_fiscal_period_force_blocks_when_operational_events_are_unlinked():
    company, branch = _mk_scope()
    user = User.objects.create_user(username="phase5_close_force_reconcile", password="x")
    event = publish_outbox_event(
        source_module="BILLING",
        event_type="DocumentIssued",
        payload={
            "doc_id": 9901,
            "doc_type": "INVOICE",
            "series": "A",
            "number": 1,
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
    dt_local = timezone.localtime(event.occurred_at)

    with pytest.raises(CommandError) as exc_info:
        call_command(
            "close_fiscal_period",
            company_id=company.id,
            year=dt_local.year,
            month=dt_local.month,
            force=True,
        )
    message = str(exc_info.value)
    assert "descuadres reconciliación" in message or "eventos operacionales pendientes" in message

    blocked = OutboxEvent.objects.filter(source_module="ACCOUNTING", event_type="PeriodCloseBlocked").order_by("-id").first()
    assert blocked is not None
    gate = (blocked.payload or {}).get("data", {}).get("gate_summary", {})
    assert int(gate.get("pending_operational_events_count") or 0) >= 1
    assert int(gate.get("reconciliation_mismatch_count") or 0) >= 1


@pytest.mark.django_db
def test_close_fiscal_period_force_blocks_when_draft_exception_exists():
    company, branch = _mk_scope()
    user = User.objects.create_user(username="phase5_close_force_draft_exception", password="x")
    call_command("seed_posting_rules_v1", company_id=company.id)
    run = _mk_packaged_run(company=company, branch=branch, user=user)
    _mk_billing_event(company=company, branch=branch, user=user)
    call_command("project_shadow_ledger", run_id=str(run.run_id))

    draft = JournalDraft.objects.get(close_run_id=str(run.run_id))
    draft.state = JournalDraft.State.EXCEPTION
    draft.save(update_fields=["state"])
    dt_local = timezone.localtime(draft.economic_event.occurred_at)

    with pytest.raises(CommandError) as exc_info:
        call_command(
            "close_fiscal_period",
            company_id=company.id,
            year=dt_local.year,
            month=dt_local.month,
            force=True,
        )
    assert "drafts en excepción" in str(exc_info.value)

    blocked = OutboxEvent.objects.filter(source_module="ACCOUNTING", event_type="PeriodCloseBlocked").order_by("-id").first()
    assert blocked is not None
    gate = (blocked.payload or {}).get("data", {}).get("gate_summary", {})
    assert int(gate.get("draft_exception_count") or 0) >= 1
    assert "DRAFT_EXCEPTION" in list(gate.get("blocking_reasons") or [])


@pytest.mark.django_db
def test_reverse_journal_entry_command_is_idempotent():
    company, branch = _mk_scope()
    user = User.objects.create_user(username="phase5_reverse", password="x")
    call_command("seed_posting_rules_v1", company_id=company.id)
    run = _mk_packaged_run(company=company, branch=branch, user=user)
    _mk_billing_event(company=company, branch=branch, user=user)
    call_command("project_shadow_ledger", run_id=str(run.run_id))
    call_command("approve_journal_drafts", run_id=str(run.run_id), company_id=company.id)
    call_command("post_journal_drafts", run_id=str(run.run_id), company_id=company.id, require_approved=True)

    entry = JournalEntry.objects.get(draft__close_run_id=str(run.run_id))

    out1 = StringIO()
    call_command(
        "reverse_journal_entry",
        company_id=company.id,
        entry_id=entry.id,
        reason="Ajuste de cierre",
        stdout=out1,
    )
    payload1 = json.loads(out1.getvalue())
    assert payload1["original_entry_id"] == entry.id
    assert payload1["idempotent"] is False

    out2 = StringIO()
    call_command(
        "reverse_journal_entry",
        company_id=company.id,
        entry_id=entry.id,
        reason="Ajuste de cierre",
        stdout=out2,
    )
    payload2 = json.loads(out2.getvalue())
    assert payload2["idempotent"] is True
    assert payload2["reversal_entry_id"] == payload1["reversal_entry_id"]
    assert JournalEntry.objects.filter(reversed_entry_id=entry.id).count() == 1
    assert OutboxEvent.objects.filter(source_module="ACCOUNTING", event_type="JournalReversed").exists()


@pytest.mark.django_db
def test_reverse_journal_entries_batch_command_by_run():
    company, branch = _mk_scope()
    user = User.objects.create_user(username="phase5_reverse_batch", password="x")
    call_command("seed_posting_rules_v1", company_id=company.id)
    run = _mk_packaged_run(company=company, branch=branch, user=user)
    _mk_billing_event(company=company, branch=branch, user=user, doc_id=7101, number=1)
    _mk_billing_event(company=company, branch=branch, user=user, doc_id=7102, number=2)
    call_command("project_shadow_ledger", run_id=str(run.run_id))
    call_command("approve_journal_drafts", run_id=str(run.run_id), company_id=company.id)
    call_command("post_journal_drafts", run_id=str(run.run_id), company_id=company.id, require_approved=True)

    out1 = StringIO()
    call_command(
        "reverse_journal_entries_batch",
        company_id=company.id,
        run_id=str(run.run_id),
        reason="Ajuste por lote",
        stdout=out1,
    )
    payload1 = json.loads(out1.getvalue())
    assert payload1["attempted"] == 2
    assert payload1["reversed"] == 2
    assert payload1["idempotent"] == 0
    assert payload1["failed"] == 0

    out2 = StringIO()
    call_command(
        "reverse_journal_entries_batch",
        company_id=company.id,
        run_id=str(run.run_id),
        reason="Ajuste por lote",
        stdout=out2,
    )
    payload2 = json.loads(out2.getvalue())
    assert payload2["attempted"] == 2
    assert payload2["reversed"] == 0
    assert payload2["idempotent"] == 2
    assert payload2["failed"] == 0
