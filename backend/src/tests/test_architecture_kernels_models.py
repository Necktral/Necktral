from __future__ import annotations

import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError

from apps.accounting.models import EconomicEvent, FiscalPeriod, JournalDraft, JournalEntry, PostingRuleSet
from apps.iam.models import OrgUnit
from apps.integration.models import InboxEvent
from apps.payments.models import CashSession


def _mk_scope():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


@pytest.mark.django_db
def test_accounting_journal_entry_rejects_unbalanced_values():
    company, branch = _mk_scope()
    period = FiscalPeriod.objects.create(company=company, year=2026, month=3, status=FiscalPeriod.Status.OPEN)
    event = EconomicEvent.objects.create(
        source_module="BILLING",
        event_type="DocumentIssued",
        company=company,
        branch=branch,
        payload={"doc_id": 1},
    )
    rule = PostingRuleSet.objects.create(code="default", version=1, status=PostingRuleSet.Status.ACTIVE)
    draft = JournalDraft.objects.create(
        economic_event=event,
        rule_set=rule,
        total_debit="100.00",
        total_credit="100.00",
        lines_json=[{"account": "1101", "debit": "100.00", "credit": "0.00"}],
    )

    entry = JournalEntry(
        draft=draft,
        period=period,
        company=company,
        branch=branch,
        debit_total="100.00",
        credit_total="99.99",
    )
    with pytest.raises(ValidationError):
        entry.full_clean()


@pytest.mark.django_db
def test_accounting_journal_entry_rejects_posting_in_closed_period():
    company, branch = _mk_scope()
    period = FiscalPeriod.objects.create(company=company, year=2026, month=3, status=FiscalPeriod.Status.CLOSED)
    event = EconomicEvent.objects.create(
        source_module="BILLING",
        event_type="DocumentIssued",
        company=company,
        branch=branch,
        payload={"doc_id": 1},
    )
    rule = PostingRuleSet.objects.create(code="default", version=1, status=PostingRuleSet.Status.ACTIVE)
    draft = JournalDraft.objects.create(
        economic_event=event,
        rule_set=rule,
        total_debit="100.00",
        total_credit="100.00",
    )

    entry = JournalEntry(
        draft=draft,
        period=period,
        company=company,
        branch=branch,
        debit_total="100.00",
        credit_total="100.00",
        is_posted=True,
    )
    with pytest.raises(ValidationError):
        entry.full_clean()


@pytest.mark.django_db
def test_payments_cash_session_difference_invariant():
    company, branch = _mk_scope()
    # Reusa superuser de django para evitar dependencias adicionales
    from django.contrib.auth import get_user_model

    User = get_user_model()
    user = User.objects.create_user(username="cash_user", password="x")

    session = CashSession(
        company=company,
        branch=branch,
        opened_by=user,
        status=CashSession.Status.COUNT_PENDING,
        expected_amount="100.00",
        counted_amount="90.00",
        difference_amount="0.00",
    )
    with pytest.raises(ValidationError):
        session.full_clean()


@pytest.mark.django_db
def test_integration_inbox_enforces_idempotency_per_consumer():
    first = InboxEvent.objects.create(
        event_id="9de8b2e5-6f52-4b77-b218-02c9f596f226",
        consumer="accounting.projector",
        source_module="BILLING",
        event_type="DocumentIssued",
        payload={"doc_id": 1},
    )
    assert first.status == InboxEvent.Status.RECEIVED

    with pytest.raises(IntegrityError):
        InboxEvent.objects.create(
            event_id="9de8b2e5-6f52-4b77-b218-02c9f596f226",
            consumer="accounting.projector",
            source_module="BILLING",
            event_type="DocumentIssued",
            payload={"doc_id": 1},
        )
