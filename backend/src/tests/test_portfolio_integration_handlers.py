"""
Tests for Portfolio Integration Handlers.

Verifica que los eventos de Procurement y Billing se consumen
correctamente para crear Payables y Receivables.
"""
from decimal import Decimal

import pytest
from django.utils import timezone

from apps.modulos.iam.models import OrgUnit
from apps.modulos.integration.models import InboxEvent, OutboxEvent
from apps.modulos.parties.models import Party
from apps.kernels.portfolio.handlers import (
    dispatch_portfolio_event,
    handle_billing_document_issued,
    handle_procurement_document_posted,
)
from apps.kernels.portfolio.models import Payable, PortfolioSettings, Receivable


def _org_tree(*, suffix: str = ""):
    holding = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.HOLDING,
        name=f"Holding{suffix}",
        code=f"H{suffix}",
        is_active=True,
    )
    company = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.COMPANY,
        parent=holding,
        name=f"Company{suffix}",
        code=f"C{suffix}",
        is_active=True,
    )
    branch = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.BRANCH,
        parent=company,
        name=f"Branch{suffix}",
        code=f"B{suffix}",
        is_active=True,
    )
    return holding, company, branch


def _create_party(company, *, name="Supplier Test", party_type=Party.PartyType.JURIDICAL):
    return Party.objects.create(
        company=company,
        party_type=party_type,
        display_name=name,
        legal_name=name,
    )


def _make_outbox_event(*, source_module, event_type, company, branch, payload_data):
    """Helper para crear un OutboxEvent con estructura canónica."""
    return OutboxEvent.objects.create(
        source_module=source_module,
        event_type=event_type,
        schema_version=1,
        company=company,
        branch=branch,
        payload={
            "schema_version": 1,
            "contract_version": "1.0",
            "occurred_at": timezone.now().isoformat(),
            "scope": {
                "company_id": company.id,
                "branch_id": branch.id,
            },
            "actor": {"user_id": None},
            "correlation_id": "",
            "causation_id": "",
            "data": payload_data,
        },
        occurred_at=timezone.now(),
    )


# ============================================================================
# PROCUREMENT → PAYABLE TESTS
# ============================================================================


@pytest.mark.django_db
class TestProcurementToPayable:
    def test_creates_payable_from_procurement_posted_event(self):
        _, company, branch = _org_tree(suffix="_proc1")
        supplier = _create_party(company, name="Proveedor ABC")

        event = _make_outbox_event(
            source_module="PROCUREMENT",
            event_type="ProcurementDocumentPosted",
            company=company,
            branch=branch,
            payload_data={
                "doc_id": 101,
                "doc_type": "PURCHASE_INVOICE",
                "status": "POSTED",
                "series": "P",
                "number": 1,
                "currency": "NIO",
                "subtotal": "1000.00",
                "tax_total": "150.00",
                "total": "1150.00",
                "supplier_ref": "FAC-PROV-001",
                "supplier_party_id": supplier.id,
                "external_ref": "EXT-001",
            },
        )

        result = handle_procurement_document_posted(event)

        assert result["ok"] is True
        assert "payable_id" in result
        assert result["amount"] == "1150.00"
        assert result["party_id"] == supplier.id

        # Verificar que se creó el Payable
        payable = Payable.objects.get(obligation_id=result["payable_id"])
        assert payable.company == company
        assert payable.party == supplier
        assert payable.principal_amount == Decimal("1150.00")
        assert payable.currency == "NIO"
        assert payable.reference_type == "PROCUREMENT"
        assert payable.reference_id == 101
        assert payable.supplier_invoice_number == "FAC-PROV-001"

        # Verificar InboxEvent
        inbox = InboxEvent.objects.get(event_id=event.event_id, consumer="PORTFOLIO")
        assert inbox.status == InboxEvent.Status.PROCESSED

    def test_idempotent_does_not_duplicate(self):
        _, company, branch = _org_tree(suffix="_proc2")
        supplier = _create_party(company, name="Proveedor Idem")

        event = _make_outbox_event(
            source_module="PROCUREMENT",
            event_type="ProcurementDocumentPosted",
            company=company,
            branch=branch,
            payload_data={
                "doc_id": 200,
                "total": "500.00",
                "currency": "NIO",
                "supplier_party_id": supplier.id,
                "supplier_ref": "X",
            },
        )

        result1 = handle_procurement_document_posted(event)
        result2 = handle_procurement_document_posted(event)

        assert result1["ok"] is True
        assert result2["ok"] is True
        assert result2.get("already_processed") is True

        # Solo un Payable creado
        assert Payable.objects.filter(reference_type="PROCUREMENT", reference_id=200).count() == 1

    def test_skips_when_sync_disabled(self):
        _, company, branch = _org_tree(suffix="_proc3")
        supplier = _create_party(company, name="Proveedor Skip")

        # Desactivar sync
        settings = PortfolioSettings.get_or_create_for_company(company)
        settings.sync_with_procurement = False
        settings.save()

        event = _make_outbox_event(
            source_module="PROCUREMENT",
            event_type="ProcurementDocumentPosted",
            company=company,
            branch=branch,
            payload_data={
                "doc_id": 300,
                "total": "700.00",
                "currency": "NIO",
                "supplier_party_id": supplier.id,
            },
        )

        result = handle_procurement_document_posted(event)
        assert result["ok"] is True
        assert result["skipped"] is True
        assert Payable.objects.filter(reference_type="PROCUREMENT", reference_id=300).count() == 0

    def test_skips_when_no_supplier_party(self):
        _, company, branch = _org_tree(suffix="_proc4")

        event = _make_outbox_event(
            source_module="PROCUREMENT",
            event_type="ProcurementDocumentPosted",
            company=company,
            branch=branch,
            payload_data={
                "doc_id": 400,
                "total": "800.00",
                "currency": "NIO",
                "supplier_party_id": None,
            },
        )

        result = handle_procurement_document_posted(event)
        assert result["ok"] is True
        assert result["skipped"] is True


# ============================================================================
# BILLING → RECEIVABLE TESTS
# ============================================================================


@pytest.mark.django_db
class TestBillingToReceivable:
    def test_creates_receivable_from_billing_issued_event(self):
        _, company, branch = _org_tree(suffix="_bill1")
        customer = _create_party(company, name="Cliente XYZ")

        event = _make_outbox_event(
            source_module="BILLING",
            event_type="DocumentIssued",
            company=company,
            branch=branch,
            payload_data={
                "doc_id": 501,
                "doc_type": "INVOICE",
                "status": "ISSUED",
                "series": "F",
                "number": 1,
                "currency": "USD",
                "subtotal": "2000.00",
                "tax_total": "300.00",
                "total": "2300.00",
                "is_fiscal": True,
                "payment_method": "CREDIT",
                "customer_party_id": customer.id,
            },
        )

        result = handle_billing_document_issued(event)

        assert result["ok"] is True
        assert "receivable_id" in result
        assert result["amount"] == "2300.00"
        assert result["party_id"] == customer.id

        # Verificar que se creó el Receivable
        receivable = Receivable.objects.get(obligation_id=result["receivable_id"])
        assert receivable.company == company
        assert receivable.party == customer
        assert receivable.principal_amount == Decimal("2300.00")
        assert receivable.currency == "USD"
        assert receivable.reference_type == "BILLING"
        assert receivable.reference_id == 501
        assert receivable.invoice_number == "F-1"

    def test_skips_cash_payment_method(self):
        _, company, branch = _org_tree(suffix="_bill2")
        customer = _create_party(company, name="Cliente Cash")

        event = _make_outbox_event(
            source_module="BILLING",
            event_type="DocumentIssued",
            company=company,
            branch=branch,
            payload_data={
                "doc_id": 600,
                "total": "100.00",
                "currency": "NIO",
                "payment_method": "CASH",
                "customer_party_id": customer.id,
            },
        )

        result = handle_billing_document_issued(event)
        assert result["ok"] is True
        assert result["skipped"] is True
        assert "cash sale" in result["reason"]

    def test_skips_card_payment_method(self):
        _, company, branch = _org_tree(suffix="_bill3")
        customer = _create_party(company, name="Cliente Card")

        event = _make_outbox_event(
            source_module="BILLING",
            event_type="DocumentIssued",
            company=company,
            branch=branch,
            payload_data={
                "doc_id": 601,
                "total": "200.00",
                "currency": "NIO",
                "payment_method": "CARD",
                "customer_party_id": customer.id,
            },
        )

        result = handle_billing_document_issued(event)
        assert result["ok"] is True
        assert result["skipped"] is True

    def test_skips_when_sync_disabled(self):
        _, company, branch = _org_tree(suffix="_bill4")
        customer = _create_party(company, name="Cliente NoSync")

        settings = PortfolioSettings.get_or_create_for_company(company)
        settings.sync_with_billing = False
        settings.save()

        event = _make_outbox_event(
            source_module="BILLING",
            event_type="DocumentIssued",
            company=company,
            branch=branch,
            payload_data={
                "doc_id": 700,
                "total": "500.00",
                "currency": "NIO",
                "payment_method": "CREDIT",
                "customer_party_id": customer.id,
            },
        )

        result = handle_billing_document_issued(event)
        assert result["ok"] is True
        assert result["skipped"] is True

    def test_skips_when_no_customer_party(self):
        _, company, branch = _org_tree(suffix="_bill5")

        event = _make_outbox_event(
            source_module="BILLING",
            event_type="DocumentIssued",
            company=company,
            branch=branch,
            payload_data={
                "doc_id": 800,
                "total": "1000.00",
                "currency": "NIO",
                "payment_method": "CREDIT",
                "customer_party_id": None,
            },
        )

        result = handle_billing_document_issued(event)
        assert result["ok"] is True
        assert result["skipped"] is True

    def test_idempotent_does_not_duplicate_receivable(self):
        _, company, branch = _org_tree(suffix="_bill6")
        customer = _create_party(company, name="Cliente Idem")

        event = _make_outbox_event(
            source_module="BILLING",
            event_type="DocumentIssued",
            company=company,
            branch=branch,
            payload_data={
                "doc_id": 900,
                "total": "3000.00",
                "currency": "NIO",
                "payment_method": "CREDIT",
                "customer_party_id": customer.id,
                "series": "A",
                "number": 99,
            },
        )

        result1 = handle_billing_document_issued(event)
        result2 = handle_billing_document_issued(event)

        assert result1["ok"] is True
        assert result2["ok"] is True
        assert result2.get("already_processed") is True
        assert Receivable.objects.filter(reference_type="BILLING", reference_id=900).count() == 1


# ============================================================================
# DISPATCH TESTS
# ============================================================================


@pytest.mark.django_db
class TestDispatchPortfolioEvent:
    def test_dispatches_procurement_event(self):
        _, company, branch = _org_tree(suffix="_disp1")
        supplier = _create_party(company, name="Dispatch Supplier")

        event = _make_outbox_event(
            source_module="PROCUREMENT",
            event_type="ProcurementDocumentPosted",
            company=company,
            branch=branch,
            payload_data={
                "doc_id": 1001,
                "total": "999.00",
                "currency": "NIO",
                "supplier_party_id": supplier.id,
            },
        )

        result = dispatch_portfolio_event(event)
        assert result is not None
        assert result["ok"] is True

    def test_returns_none_for_unknown_event(self):
        _, company, branch = _org_tree(suffix="_disp2")

        event = _make_outbox_event(
            source_module="UNKNOWN",
            event_type="SomethingHappened",
            company=company,
            branch=branch,
            payload_data={"foo": "bar"},
        )

        result = dispatch_portfolio_event(event)
        assert result is None
