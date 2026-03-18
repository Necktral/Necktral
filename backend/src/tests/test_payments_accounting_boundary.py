from __future__ import annotations

from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from apps.accounting.services import OPERATIONAL_ACCOUNTING_EVENTS, SUPPORTED_ECONOMIC_EVENTS, link_operational_event_to_accounting
from apps.audit.models import AuditEvent
from apps.iam.models import OrgUnit
from apps.integration.models import OutboxEvent
from apps.integration.services import CANONICAL_OUTBOX_ENVELOPE_FIELDS
from apps.payments.services import close_cash_session, create_payment_intent, open_cash_session, post_cash_movement

User = get_user_model()


def _mk_scope():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


def _request(*, company: OrgUnit, branch: OrgUnit, user):
    return SimpleNamespace(
        company=company,
        branch=branch,
        user=user,
        request_id="req-pay-boundary",
        headers={},
        META={},
        path="/api/payments/",
        method="POST",
    )


def _canonical_payload(event: OutboxEvent) -> dict:
    payload = event.payload if isinstance(event.payload, dict) else {}
    assert set(payload.keys()) == set(CANONICAL_OUTBOX_ENVELOPE_FIELDS)
    return payload


@pytest.mark.django_db
def test_payments_events_are_frozen_as_non_operational_direct_accounting_links():
    company, branch = _mk_scope()
    user = User.objects.create_user(username="payments_boundary_user", password="x")
    req = _request(company=company, branch=branch, user=user)

    intent, created = create_payment_intent(
        request=req,
        actor=user,
        amount=Decimal("100.00"),
        currency="NIO",
        idempotency_key="pay-intent-1",
    )
    assert created is False
    session = open_cash_session(request=req, actor=user, opening_amount=Decimal("50.00"))
    post_cash_movement(
        request=req,
        actor=user,
        session_id=session.id,
        movement_type="INCOME",
        amount=Decimal("25.00"),
        reference="ticket-1",
    )
    close_cash_session(
        request=req,
        actor=user,
        session_id=session.id,
        counted_amount=Decimal("70.00"),
    )

    assert intent.status == "INTENDED"
    assert ("PAYMENTS", "CashMovementPosted") in SUPPORTED_ECONOMIC_EVENTS
    assert ("PAYMENTS", "CashSessionClosed") in SUPPORTED_ECONOMIC_EVENTS
    assert ("PAYMENTS", "CashMovementPosted") not in OPERATIONAL_ACCOUNTING_EVENTS
    assert ("PAYMENTS", "CashSessionClosed") not in OPERATIONAL_ACCOUNTING_EVENTS

    created_event = OutboxEvent.objects.filter(source_module="PAYMENTS", event_type="PaymentIntentCreated").order_by("-id").first()
    movement_event = OutboxEvent.objects.filter(source_module="PAYMENTS", event_type="CashMovementPosted").order_by("-id").first()
    close_event = OutboxEvent.objects.filter(source_module="PAYMENTS", event_type="CashSessionClosed").order_by("-id").first()

    assert created_event is not None
    assert movement_event is not None
    assert close_event is not None

    created_payload = _canonical_payload(created_event)
    movement_payload = _canonical_payload(movement_event)
    close_payload = _canonical_payload(close_event)

    assert created_payload["scope"] == {"company_id": company.id, "branch_id": branch.id}
    assert movement_payload["scope"] == {"company_id": company.id, "branch_id": branch.id}
    assert close_payload["scope"] == {"company_id": company.id, "branch_id": branch.id}
    assert close_payload["data"]["difference_amount"] == "-5.00"

    created_link = link_operational_event_to_accounting(outbox_event=created_event, actor_user=user)
    movement_link = link_operational_event_to_accounting(outbox_event=movement_event, actor_user=user)
    close_link = link_operational_event_to_accounting(outbox_event=close_event, actor_user=user)

    assert created_link.status == "UNSUPPORTED"
    assert movement_link.status == "UNSUPPORTED"
    assert close_link.status == "UNSUPPORTED"

    audit_events = list(
        AuditEvent.objects.filter(module="PAYMENTS").order_by("id").values("event_type", "metadata")
    )
    event_types = {row["event_type"] for row in audit_events}
    assert "PAYMENT_INTENT_CREATED" in event_types
    assert "CASH_SESSION_OPENED" in event_types
    assert "CASH_MOVEMENT_POSTED" in event_types
    assert "CASH_SESSION_CLOSED" in event_types

    close_audit = next(row for row in audit_events if row["event_type"] == "CASH_SESSION_CLOSED")
    metadata = close_audit["metadata"] if isinstance(close_audit["metadata"], dict) else {}
    assert metadata.get("request_id") == "req-pay-boundary"
    assert metadata.get("company_id") == str(company.id)
    assert metadata.get("branch_id") == str(branch.id)
