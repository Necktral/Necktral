from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import override_settings

from apps.modulos.iam.models import OrgUnit
from apps.modulos.integration.models import OutboxEvent
from kernels.facturacion.models import BillingDocument, DocStatus
from kernels.facturacion.services import create_draft, issue_doc, void_doc


_VALID_ACCOUNTING_STATUSES = {"DRAFT_VALIDATED", "POSTED"}


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

    User = get_user_model()
    user = User.objects.create_user(
        username=f"tester_{token}",
        email=f"tester_{token}@example.com",
        password="Secret123!",
    )
    request = SimpleNamespace(
        company=company,
        branch=branch,
        user=user,
        META={},
        headers={},
        path="/test/billing/",
        method="POST",
        request_id=f"req-{token}",
    )
    return company, branch, user, request


@pytest.mark.django_db
def test_billing_issue_updates_document_and_outbox_with_accounting_link():
    _, _, user, request = _build_scope()

    draft = create_draft(
        request=request,
        actor=user,
        doc_type="INVOICE",
        series="A",
        currency="NIO",
        customer_name="Cliente Demo",
        customer_ref="C-001",
        is_fiscal=False,
        lines=[
            {
                "description": "Servicio",
                "quantity": "2",
                "unit_price": "100",
                "tax_rate": "0.15",
            }
        ],
        idempotency_key=f"draft-{uuid.uuid4().hex}",
    )

    out = issue_doc(
        request=request,
        actor=user,
        doc_id=draft.doc_id,
        apply_inventory=False,
        print_after_issue=False,
        idempotency_key=f"issue-{uuid.uuid4().hex}",
    )

    assert out["accounting_status"] in _VALID_ACCOUNTING_STATUSES
    assert out["journal_draft_id"] is not None

    doc = BillingDocument.objects.get(id=draft.doc_id)
    assert doc.status == DocStatus.ISSUED
    assert doc.accounting_journal_draft_id == out["journal_draft_id"]

    ev = OutboxEvent.objects.filter(source_module="BILLING", event_type="DocumentIssued").order_by("-id").first()
    assert ev is not None
    data = ev.payload.get("data", {})
    assert data.get("doc_id") == doc.id
    assert data.get("accounting_status") == out["accounting_status"]


@pytest.mark.django_db
def test_billing_void_returns_accounting_state():
    _, _, user, request = _build_scope()

    draft = create_draft(
        request=request,
        actor=user,
        doc_type="INVOICE",
        series="A",
        currency="NIO",
        customer_name="Cliente Demo",
        customer_ref="C-002",
        is_fiscal=False,
        lines=[
            {
                "description": "Producto",
                "quantity": "1",
                "unit_price": "50",
                "tax_rate": "0.15",
            }
        ],
        idempotency_key=f"draft-{uuid.uuid4().hex}",
    )

    issue_doc(
        request=request,
        actor=user,
        doc_id=draft.doc_id,
        apply_inventory=False,
        print_after_issue=False,
        idempotency_key=f"issue-{uuid.uuid4().hex}",
    )

    out = void_doc(
        request=request,
        actor=user,
        doc_id=draft.doc_id,
        reason="TEST_VOID",
    )

    assert out["accounting_status"] in _VALID_ACCOUNTING_STATUSES
    assert out["journal_draft_id"] is not None

    doc = BillingDocument.objects.get(id=draft.doc_id)
    assert doc.status == DocStatus.VOIDED
    assert doc.accounting_journal_draft_id == out["journal_draft_id"]


@override_settings(ACCOUNTING_OPERATIONAL_LINK_MODE="async")
@pytest.mark.django_db
def test_billing_issue_async_mode_is_projected_later():
    company, _, user, request = _build_scope()

    draft = create_draft(
        request=request,
        actor=user,
        doc_type="INVOICE",
        series="A",
        currency="NIO",
        customer_name="Cliente Async",
        customer_ref="C-ASYNC",
        is_fiscal=False,
        lines=[
            {
                "description": "Servicio async",
                "quantity": "2",
                "unit_price": "75",
                "tax_rate": "0.15",
            }
        ],
        idempotency_key=f"draft-{uuid.uuid4().hex}",
    )

    out = issue_doc(
        request=request,
        actor=user,
        doc_id=draft.doc_id,
        apply_inventory=False,
        print_after_issue=False,
        idempotency_key=f"issue-{uuid.uuid4().hex}",
    )
    assert out["accounting_status"] == BillingDocument.AccountingStatus.PENDING_RULESET
    assert out["journal_draft_id"] is None

    doc = BillingDocument.objects.get(id=draft.doc_id)
    assert doc.accounting_status == BillingDocument.AccountingStatus.PENDING_RULESET

    ev = OutboxEvent.objects.filter(source_module="BILLING", event_type="DocumentIssued").order_by("-id").first()
    assert ev is not None
    payload_data = ev.payload.get("data", {})
    assert payload_data.get("doc_id") == doc.id

    call_command("run_operational_accounting_projector", company_id=company.id, limit=100)

    doc.refresh_from_db()
    assert doc.accounting_status in _VALID_ACCOUNTING_STATUSES
    assert doc.accounting_journal_draft_id is not None

    ev.refresh_from_db()
    projected_data = ev.payload.get("data", {})
    assert projected_data.get("accounting_status") == doc.accounting_status

    # Segunda corrida idempotente: no debe degradar estado ya proyectado.
    call_command("run_operational_accounting_projector", company_id=company.id, limit=100)
    doc.refresh_from_db()
    assert doc.accounting_status in _VALID_ACCOUNTING_STATUSES
