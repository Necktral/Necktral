from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone

from apps.modulos.accounting.models import DraftValidationResult, EconomicEvent, JournalDraft, PostingRuleSet
from apps.modulos.cec.models import CECException, CloseRun
from apps.modulos.iam.models import OrgUnit
from apps.modulos.integration.models import InboxEvent, OutboxEvent
from apps.modulos.integration.services import publish_outbox_event

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
    trigger = publish_outbox_event(
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
    return run, trigger


def _mk_billing_issued_event(*, company: OrgUnit, branch: OrgUnit, user):
    return publish_outbox_event(
        source_module="BILLING",
        event_type="DocumentIssued",
        payload={
            "doc_id": 101,
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


@pytest.mark.django_db
def test_seed_posting_rules_v1_is_idempotent():
    company, _ = _mk_scope()

    call_command("seed_posting_rules_v1", company_id=company.id)
    call_command("seed_posting_rules_v1", company_id=company.id)

    rows = PostingRuleSet.objects.filter(code="shadow_ledger_v1", scope_company=company, status=PostingRuleSet.Status.ACTIVE)
    assert rows.count() == 1
    rule_set = rows.first()
    assert rule_set is not None
    assert rule_set.rules_json["version"] == "1.0"
    assert isinstance(rule_set.rules_json.get("rules"), list)
    assert len(rule_set.rules_json["rules"]) > 0


@pytest.mark.django_db
def test_project_shadow_ledger_for_run_generates_economic_events_and_valid_drafts():
    company, branch = _mk_scope()
    user = User.objects.create_user(username="phase4_ok", password="x")

    call_command("seed_posting_rules_v1", company_id=company.id)
    run, _ = _mk_packaged_run(company=company, branch=branch, user=user)
    billing_event = _mk_billing_issued_event(company=company, branch=branch, user=user)

    call_command("project_shadow_ledger", run_id=str(run.run_id))
    run.refresh_from_db()
    assert run.status == CloseRun.Status.PACKAGED

    ee = EconomicEvent.objects.get(company=company, source_outbox_event_id=billing_event.event_id)
    assert ee.close_run_id == str(run.run_id)

    draft = JournalDraft.objects.get(economic_event=ee)
    assert draft.state == JournalDraft.State.VALIDATED
    assert Decimal(draft.total_debit) == Decimal("115.00")
    assert Decimal(draft.total_credit) == Decimal("115.00")
    assert DraftValidationResult.objects.filter(draft=draft, passed=True, is_blocking=False).exists()

    assert OutboxEvent.objects.filter(source_module="ACCOUNTING", event_type="EconomicEventRegistered").exists()
    assert OutboxEvent.objects.filter(source_module="ACCOUNTING", event_type="JournalDraftGenerated").exists()
    assert OutboxEvent.objects.filter(source_module="ACCOUNTING", event_type="ShadowLedgerProjected").exists()

    ee_count = EconomicEvent.objects.count()
    draft_count = JournalDraft.objects.count()
    exc_count = CECException.objects.filter(close_run=run, source_module="ACCOUNTING").count()

    call_command("project_shadow_ledger", run_id=str(run.run_id))
    assert EconomicEvent.objects.count() == ee_count
    assert JournalDraft.objects.count() == draft_count
    assert CECException.objects.filter(close_run=run, source_module="ACCOUNTING").count() == exc_count


@pytest.mark.django_db
def test_project_shadow_ledger_reopens_run_when_ruleset_is_missing():
    company, branch = _mk_scope()
    user = User.objects.create_user(username="phase4_block", password="x")
    run, _ = _mk_packaged_run(company=company, branch=branch, user=user)
    _mk_billing_issued_event(company=company, branch=branch, user=user)

    call_command("project_shadow_ledger", run_id=str(run.run_id))
    run.refresh_from_db()

    assert run.status == CloseRun.Status.REOPENED_EXCEPTION
    assert CECException.objects.filter(
        close_run=run,
        source_module="ACCOUNTING",
        code="SHADOW_RULESET_NOT_FOUND",
        status=CECException.Status.OPEN,
    ).count() == 1
    assert OutboxEvent.objects.filter(source_module="CEC", event_type="CloseRunBlocked").exists()


@pytest.mark.django_db
def test_project_shadow_ledger_batch_uses_inbox_idempotency():
    company, branch = _mk_scope()
    user = User.objects.create_user(username="phase4_batch", password="x")

    call_command("seed_posting_rules_v1", company_id=company.id)
    run, trigger = _mk_packaged_run(company=company, branch=branch, user=user)
    _mk_billing_issued_event(company=company, branch=branch, user=user)

    stdout = StringIO()
    call_command("project_shadow_ledger", limit=100, stdout=stdout)
    run.refresh_from_db()
    assert run.status == CloseRun.Status.PACKAGED

    inbox = InboxEvent.objects.get(event_id=trigger.event_id, consumer="accounting.projector")
    assert inbox.status == InboxEvent.Status.PROCESSED
    assert EconomicEvent.objects.filter(close_run_id=str(run.run_id)).count() == 1
    assert JournalDraft.objects.filter(close_run_id=str(run.run_id)).count() == 1

    call_command("project_shadow_ledger", limit=100, stdout=StringIO())
    assert EconomicEvent.objects.filter(close_run_id=str(run.run_id)).count() == 1
    assert JournalDraft.objects.filter(close_run_id=str(run.run_id)).count() == 1


@pytest.mark.django_db
def test_project_shadow_ledger_batch_skips_non_packaged_run_without_failed_inbox():
    company, branch = _mk_scope()
    user = User.objects.create_user(username="phase4_skip_non_packaged", password="x")
    run, trigger = _mk_packaged_run(company=company, branch=branch, user=user)
    run.status = CloseRun.Status.REOPENED_EXCEPTION
    run.save(update_fields=["status", "updated_at"])

    stdout = StringIO()
    call_command("project_shadow_ledger", limit=100, stdout=stdout)

    inbox = InboxEvent.objects.get(event_id=trigger.event_id, consumer="accounting.projector")
    assert inbox.status == InboxEvent.Status.PROCESSED
    assert inbox.last_error.startswith("SKIPPED_NON_PACKAGED:")
    assert InboxEvent.objects.filter(consumer="accounting.projector", status=InboxEvent.Status.FAILED).count() == 0
