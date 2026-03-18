from __future__ import annotations

import uuid
from decimal import Decimal
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model

from apps.iam.models import OrgUnit
from apps.integration.models import OutboxEvent
from apps.integration.services import CANONICAL_OUTBOX_ENVELOPE_FIELDS, create_or_get_inbox_event, publish_outbox_event
from modulos.facturacion.services import create_draft, issue_doc, void_doc
from modulos.inventarios.services import create_item, post_receive
from modulos.inventarios.models import Warehouse

User = get_user_model()


def _build_scope():
    token = uuid.uuid4().hex[:8]
    holding = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.HOLDING,
        name=f"Holding {token}",
        code=f"H-{token}",
    )
    company = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.COMPANY,
        parent=holding,
        name=f"Company {token}",
        code=f"C-{token}",
    )
    branch = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.BRANCH,
        parent=company,
        name=f"Branch {token}",
        code=f"B-{token}",
    )
    user = User.objects.create_user(
        username=f"user_{token}",
        email=f"user_{token}@example.com",
        password="Secret123!",
    )
    request = SimpleNamespace(
        company=company,
        branch=branch,
        user=user,
        META={},
        headers={},
        path="/test/operational/",
        method="POST",
        request_id=f"req-{token}",
    )
    return company, branch, user, request


def _event_data(event: OutboxEvent) -> dict:
    payload = event.payload if isinstance(event.payload, dict) else {}
    data = payload.get("data", {})
    return data if isinstance(data, dict) else {}


def _required_contract_keys(data: dict) -> None:
    assert "source_module" in data
    assert "source_type" in data
    assert "source_id" in data
    assert "accounting_status" in data
    assert "accounting_error" in data
    assert "economic_event_id" in data
    assert "journal_draft_id" in data
    assert "journal_entry_id" in data


def _assert_canonical_outbox_envelope(payload: dict, *, company_id: int, branch_id: int, user_id: int) -> None:
    assert set(payload.keys()) == set(CANONICAL_OUTBOX_ENVELOPE_FIELDS)
    assert int(payload.get("schema_version") or 0) == 1
    assert payload.get("contract_version") == "1.0"
    assert isinstance(payload.get("occurred_at"), str) and payload["occurred_at"]
    assert payload.get("scope") == {"company_id": company_id, "branch_id": branch_id}
    assert payload.get("actor") == {"user_id": user_id}
    assert isinstance(payload.get("data"), dict)


def _latest_event(*, source_module: str, event_type: str) -> OutboxEvent:
    ev = OutboxEvent.objects.filter(source_module=source_module, event_type=event_type).order_by("-id").first()
    assert ev is not None
    return ev


@pytest.mark.django_db
def test_credit_note_issue_emits_contract_fields_and_correlation():
    _, _, user, request = _build_scope()

    draft = create_draft(
        request=request,
        actor=user,
        doc_type="CREDIT_NOTE",
        series="NC",
        currency="NIO",
        customer_name="Cliente",
        customer_ref="CLI-001",
        is_fiscal=False,
        lines=[
            {
                "description": "Descuento post-venta",
                "quantity": "1",
                "unit_price": "35",
                "tax_rate": "0.00",
            }
        ],
        idempotency_key=f"draft-{uuid.uuid4().hex}",
        source_module="FUEL",
        source_type="SALE_ADJUSTMENT",
        source_id="fuel-sale-1",
        correlation_id="corr-credit-note",
        causation_id="cause-credit-note-draft",
    )

    issue_doc(
        request=request,
        actor=user,
        doc_id=draft.doc_id,
        apply_inventory=False,
        print_after_issue=False,
        idempotency_key=f"issue-{uuid.uuid4().hex}",
        correlation_id="corr-credit-note",
        causation_id="cause-credit-note-issue",
    )

    ev = _latest_event(source_module="BILLING", event_type="DocumentIssued")
    payload = ev.payload if isinstance(ev.payload, dict) else {}
    data = _event_data(ev)

    _assert_canonical_outbox_envelope(payload, company_id=request.company.id, branch_id=request.branch.id, user_id=user.id)
    assert payload.get("correlation_id") == "corr-credit-note"
    assert payload.get("causation_id") == "cause-credit-note-issue"
    assert data.get("doc_id") == draft.doc_id
    assert data.get("doc_type") == "CREDIT_NOTE"
    _required_contract_keys(data)


@pytest.mark.django_db
def test_document_issue_is_idempotent_without_duplicate_documentissued_event():
    _, _, user, request = _build_scope()
    draft = create_draft(
        request=request,
        actor=user,
        doc_type="INVOICE",
        series="A",
        currency="NIO",
        customer_name="Cliente",
        customer_ref="CLI-002",
        is_fiscal=False,
        lines=[
            {
                "description": "Servicio",
                "quantity": "1",
                "unit_price": "50",
                "tax_rate": "0.15",
            }
        ],
        idempotency_key=f"draft-{uuid.uuid4().hex}",
    )

    first = issue_doc(
        request=request,
        actor=user,
        doc_id=draft.doc_id,
        apply_inventory=False,
        print_after_issue=False,
        idempotency_key=f"issue-{uuid.uuid4().hex}",
    )
    second = issue_doc(
        request=request,
        actor=user,
        doc_id=draft.doc_id,
        apply_inventory=False,
        print_after_issue=False,
        idempotency_key=f"issue-{uuid.uuid4().hex}",
    )

    assert first.get("ok") is True
    assert second.get("already_issued") is True

    doc_issued_events = [
        ev
        for ev in OutboxEvent.objects.filter(source_module="BILLING", event_type="DocumentIssued").order_by("id")
        if _event_data(ev).get("doc_id") == draft.doc_id
    ]
    assert len(doc_issued_events) == 1


@pytest.mark.django_db
def test_document_void_emits_contract_fields_and_correlation():
    _, branch, user, request = _build_scope()

    draft = create_draft(
        request=request,
        actor=user,
        doc_type="INVOICE",
        series="A",
        currency="NIO",
        customer_name="Cliente",
        customer_ref="CLI-003",
        is_fiscal=False,
        lines=[
            {
                "description": "Producto",
                "quantity": "2",
                "unit_price": "20",
                "tax_rate": "0.00",
            }
        ],
        idempotency_key=f"draft-{uuid.uuid4().hex}",
        source_module="FUEL",
        source_type="SALE",
        source_id=f"branch-{branch.id}",
    )
    issue_doc(
        request=request,
        actor=user,
        doc_id=draft.doc_id,
        apply_inventory=False,
        print_after_issue=False,
        idempotency_key=f"issue-{uuid.uuid4().hex}",
    )

    void_doc(
        request=request,
        actor=user,
        doc_id=draft.doc_id,
        reason="VOID_TEST",
        correlation_id="corr-void",
        causation_id="cause-void",
    )

    ev = _latest_event(source_module="BILLING", event_type="DocumentVoided")
    payload = ev.payload if isinstance(ev.payload, dict) else {}
    data = _event_data(ev)

    _assert_canonical_outbox_envelope(payload, company_id=request.company.id, branch_id=request.branch.id, user_id=user.id)
    assert payload.get("correlation_id") == "corr-void"
    assert payload.get("causation_id") == "cause-void"
    assert data.get("doc_id") == draft.doc_id
    _required_contract_keys(data)


@pytest.mark.django_db
def test_inventory_receive_idempotent_and_contract_fields_present():
    company, branch, user, request = _build_scope()
    warehouse = Warehouse.objects.create(company=company, branch=branch, name="Main", code="MAIN")
    item = create_item(
        request=request,
        company=company,
        actor_user=user,
        sku=f"SKU-{uuid.uuid4().hex[:8]}",
        name="Diesel",
        uom="LITER",
    )

    key = f"recv-{uuid.uuid4().hex}"
    first = post_receive(
        request=request,
        actor=user,
        warehouse_id=warehouse.id,
        item_id=item.id,
        qty=Decimal("10.0000"),
        unit_cost=Decimal("1.750000"),
        idempotency_key=key,
        source_module="FUEL",
        source_type="SALE_REVERSAL",
        source_id="sale-100",
        correlation_id="corr-recv",
        causation_id="cause-recv",
    )
    second = post_receive(
        request=request,
        actor=user,
        warehouse_id=warehouse.id,
        item_id=item.id,
        qty=Decimal("10.0000"),
        unit_cost=Decimal("1.750000"),
        idempotency_key=key,
        source_module="FUEL",
        source_type="SALE_REVERSAL",
        source_id="sale-100",
        correlation_id="corr-recv",
        causation_id="cause-recv",
    )

    assert first.movement_id == second.movement_id

    movement_events = [
        ev
        for ev in OutboxEvent.objects.filter(source_module="INVENTORY", event_type="InventoryMovementPosted").order_by("id")
        if _event_data(ev).get("movement_id") == first.movement_id
    ]
    assert len(movement_events) == 1

    payload = movement_events[0].payload if isinstance(movement_events[0].payload, dict) else {}
    data = _event_data(movement_events[0])
    _assert_canonical_outbox_envelope(payload, company_id=company.id, branch_id=branch.id, user_id=user.id)
    assert payload.get("correlation_id") == "corr-recv"
    assert payload.get("causation_id") == "cause-recv"
    _required_contract_keys(data)


@pytest.mark.django_db
def test_inbox_upsert_is_idempotent_per_event_and_consumer():
    company, branch, user, request = _build_scope()

    event = publish_outbox_event(
        source_module="TESTING",
        event_type="ContractFrozen",
        payload={"state": "ok"},
        request=request,
        actor_user=user,
        company=company,
        branch=branch,
        correlation_id="corr-inbox",
        causation_id="cause-inbox",
    )

    first, created_first = create_or_get_inbox_event(event=event, consumer="pytest.consumer")
    second, created_second = create_or_get_inbox_event(event=event, consumer="pytest.consumer")

    assert created_first is True
    assert created_second is False
    assert first.id == second.id
    assert first.event_id == event.event_id
    assert first.consumer == "pytest.consumer"
