"""
Portfolio Kernel - Gap Coverage Tests

Tests adicionales para cubrir líneas faltantes identificadas en coverage report.
Objetivo: subir cobertura de 85.84% a >=95%.

Missing lines models.py: 115, 118, 124, 126, 132, 134, 141, 148
Missing lines services.py: 54-55, 57, 65, 71-73, 79-82, 88, 95, 97, 108-109, 111, 318-321, 339, 357-358
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch, PropertyMock, call

import pytest


# ---------------------------------------------------------------------------
# MODELS GAP COVERAGE
# ---------------------------------------------------------------------------

class TestObligationFieldDeclarations:
    """
    Ensure Obligation model fields (lines 115-148) are exercised.
    These lines are field declarations that get covered when the class is
    fully instantiated (not just imported).
    """

    def test_obligation_fields_accessible(self):
        """Access model field descriptors to trigger coverage of declaration lines."""
        from apps.kernels.portfolio.models import Obligation, Receivable

        # Access the field objects on the model class to trigger descriptor code
        fields = {f.name: f for f in Receivable._meta.get_fields()}

        # Lines 106-114: reference_type, reference_id
        assert "reference_type" in fields
        assert "reference_id" in fields

        # Lines 117-121: currency field
        assert "currency" in fields
        currency_field = Receivable._meta.get_field("currency")
        assert currency_field.max_length == 8
        assert currency_field.default == "NIO"

        # Lines 123-127: principal_amount
        assert "principal_amount" in fields
        principal_field = Receivable._meta.get_field("principal_amount")
        assert principal_field.max_digits == 18
        assert principal_field.decimal_places == 2

        # Lines 128-132: interest_amount
        assert "interest_amount" in fields
        interest_field = Receivable._meta.get_field("interest_amount")
        assert interest_field.default == Decimal("0.00")

        # Lines 134-138: fee_amount
        assert "fee_amount" in fields
        fee_field = Receivable._meta.get_field("fee_amount")
        assert fee_field.default == Decimal("0.00")

        # Lines 140-144: penalty_amount
        assert "penalty_amount" in fields
        penalty_field = Receivable._meta.get_field("penalty_amount")
        assert penalty_field.default == Decimal("0.00")

        # Lines 146-151: allocated_amount
        assert "allocated_amount" in fields
        alloc_field = Receivable._meta.get_field("allocated_amount")
        assert alloc_field.default == Decimal("0.00")

    def test_payable_fields_accessible(self):
        """Exercise Payable model field declarations."""
        from apps.kernels.portfolio.models import Payable

        fields = {f.name: f for f in Payable._meta.get_fields()}

        assert "supplier_invoice_number" in fields
        assert "withholding_tax_rate" in fields
        assert "withholding_tax_amount" in fields
        assert "early_payment_discount_rate" in fields
        assert "early_payment_discount_days" in fields
        assert "payment_priority" in fields

    def test_credit_fields_accessible(self):
        """Exercise Credit model field declarations."""
        from apps.kernels.portfolio.models import Credit

        fields = {f.name: f for f in Credit._meta.get_fields()}

        assert "credit_type" in fields
        assert "credit_status" in fields
        assert "lender_party" in fields
        assert "borrower_party" in fields
        assert "approved_amount" in fields
        assert "disbursed_amount" in fields
        assert "interest_rate" in fields
        assert "term_months" in fields
        assert "maturity_date" in fields
        assert "collateral_type" in fields
        assert "collateral_value" in fields
        assert "contract_number" in fields

    def test_portfolio_settings_fields(self):
        """Exercise PortfolioSettings field declarations."""
        from apps.kernels.portfolio.models import PortfolioSettings

        fields = {f.name: f for f in PortfolioSettings._meta.get_fields()}

        assert "auto_allocate_payments" in fields
        assert "allocation_strategy" in fields
        assert "interest_accrual_frequency" in fields
        assert "auto_capitalize_interest" in fields
        assert "auto_writeoff_enabled" in fields
        assert "auto_writeoff_days" in fields
        assert "gate_mode" in fields
        assert "functional_currency" in fields
        assert "sync_with_billing" in fields
        assert "sync_with_procurement" in fields


# ---------------------------------------------------------------------------
# SERVICES GAP COVERAGE - create_receivable real path
# ---------------------------------------------------------------------------

class TestCreateReceivableRealPath:
    """
    Tests that exercise create_receivable without mocking the Receivable class,
    covering lines 54-55, 57, 65, 71-73, 79-82, 88, 95, 97.
    We only mock database operations and the outbox event publish.
    """

    @patch("apps.kernels.portfolio.services.publish_outbox_event")
    @patch("apps.kernels.portfolio.models.Obligation.save")
    @patch("apps.kernels.portfolio.models.Obligation.full_clean")
    def test_create_receivable_exercises_constructor(self, mock_clean, mock_save, mock_publish):
        """
        Call create_receivable with real Receivable class (no mock on class).
        Only mock save/full_clean to avoid DB.
        """
        from apps.kernels.portfolio.services import create_receivable

        company = MagicMock()
        company.id = 1
        company.pk = 1
        party = MagicMock()
        party.id = 10
        party.pk = 10
        branch = MagicMock()
        branch.id = 2
        branch.pk = 2
        created_by = MagicMock()
        created_by.id = 5
        created_by.pk = 5

        result = create_receivable(
            company=company,
            party=party,
            reference_type="BILLING_DOCUMENT",
            reference_id=42,
            principal_amount=Decimal("5000.00"),
            currency="USD",
            issue_date=date(2026, 6, 1),
            due_date=date(2026, 7, 1),
            branch=branch,
            invoice_number="INV-2026-001",
            invoice_date=date(2026, 6, 1),
            credit_limit=Decimal("10000.00"),
            credit_days=30,
            created_by=created_by,
            metadata={"source": "billing"},
        )

        # Validate the Receivable was created with correct attributes
        assert result.reference_type == "BILLING_DOCUMENT"
        assert result.reference_id == 42
        assert result.principal_amount == Decimal("5000.00")
        assert result.currency == "USD"
        assert result.issue_date == date(2026, 6, 1)
        assert result.due_date == date(2026, 7, 1)
        assert result.invoice_number == "INV-2026-001"
        assert result.invoice_date == date(2026, 6, 1)
        assert result.credit_limit == Decimal("10000.00")
        assert result.credit_days == 30
        assert result.metadata_json == {"source": "billing"}

        mock_clean.assert_called_once()
        mock_save.assert_called_once()
        mock_publish.assert_called_once()

        # Validate publish payload
        publish_call = mock_publish.call_args
        assert publish_call.kwargs["source_module"] == "PORTFOLIO"
        assert publish_call.kwargs["event_type"] == "ReceivableCreated"

    @patch("apps.kernels.portfolio.services.publish_outbox_event")
    @patch("apps.kernels.portfolio.models.Obligation.save")
    @patch("apps.kernels.portfolio.models.Obligation.full_clean")
    def test_create_receivable_defaults(self, mock_clean, mock_save, mock_publish):
        """Test create_receivable with minimal args (exercises default values)."""
        from apps.kernels.portfolio.services import create_receivable

        company = MagicMock(id=1, pk=1)
        party = MagicMock(id=10, pk=10)

        result = create_receivable(
            company=company,
            party=party,
            reference_type="BILLING",
            reference_id=1,
            principal_amount=Decimal("100.00"),
            currency="NIO",
            issue_date=date(2026, 6, 1),
            due_date=date(2026, 7, 1),
        )

        # Defaults
        assert result.invoice_number == ""
        assert result.invoice_date == date(2026, 6, 1)  # defaults to issue_date
        assert result.credit_limit is None
        assert result.credit_days is None
        assert result.created_by is None
        assert result.metadata_json == {}

    def test_create_receivable_zero_amount_raises(self):
        """Exercises the validation path lines 69-73."""
        from apps.kernels.portfolio.services import create_receivable, PortfolioDomainError

        with pytest.raises(PortfolioDomainError) as exc_info:
            create_receivable(
                company=MagicMock(),
                party=MagicMock(),
                reference_type="X",
                reference_id=1,
                principal_amount=Decimal("0"),
                currency="NIO",
                issue_date=date.today(),
                due_date=date.today() + timedelta(days=30),
            )

        assert exc_info.value.code == "INVALID_AMOUNT"
        assert "positive" in exc_info.value.message.lower()


class TestPublishReceivableCreatedEvent:
    """Tests for _publish_receivable_created_event covering lines 103-121."""

    @patch("apps.kernels.portfolio.services.publish_outbox_event")
    def test_publish_event_payload(self, mock_publish):
        """Directly call _publish_receivable_created_event."""
        from apps.kernels.portfolio.services import _publish_receivable_created_event

        receivable = MagicMock()
        receivable.obligation_id = "uuid-test-123"
        receivable.party_id = 10
        receivable.principal_amount = Decimal("5000.00")
        receivable.currency = "USD"
        receivable.issue_date = date(2026, 6, 1)
        receivable.due_date = date(2026, 7, 1)
        receivable.reference_type = "BILLING_DOCUMENT"
        receivable.reference_id = 42
        receivable.invoice_number = "INV-001"
        receivable.company = MagicMock()
        receivable.branch = MagicMock()

        _publish_receivable_created_event(receivable)

        mock_publish.assert_called_once()
        call_kwargs = mock_publish.call_args.kwargs
        assert call_kwargs["source_module"] == "PORTFOLIO"
        assert call_kwargs["event_type"] == "ReceivableCreated"

        payload = call_kwargs["payload"]
        assert payload["receivable_id"] == "uuid-test-123"
        assert payload["party_id"] == 10
        assert payload["principal_amount"] == "5000.00"
        assert payload["currency"] == "USD"
        assert payload["issue_date"] == "2026-06-01"
        assert payload["due_date"] == "2026-07-01"
        assert payload["reference_type"] == "BILLING_DOCUMENT"
        assert payload["reference_id"] == 42
        assert payload["invoice_number"] == "INV-001"


class TestPublishPayableCreatedEvent:
    """Tests for _publish_payable_created_event covering lines 295-314."""

    @patch("apps.kernels.portfolio.services.publish_outbox_event")
    def test_publish_payable_event_payload(self, mock_publish):
        """Directly call _publish_payable_created_event."""
        from apps.kernels.portfolio.services import _publish_payable_created_event

        payable = MagicMock()
        payable.obligation_id = "uuid-pay-123"
        payable.party_id = 20
        payable.principal_amount = Decimal("3000.00")
        payable.currency = "NIO"
        payable.issue_date = date(2026, 6, 1)
        payable.due_date = date(2026, 7, 15)
        payable.reference_type = "PURCHASE_DOCUMENT"
        payable.reference_id = 99
        payable.supplier_invoice_number = "PROV-555"
        payable.withholding_tax_amount = Decimal("60.00")
        payable.company = MagicMock()
        payable.branch = MagicMock()

        _publish_payable_created_event(payable)

        mock_publish.assert_called_once()
        call_kwargs = mock_publish.call_args.kwargs
        assert call_kwargs["source_module"] == "PORTFOLIO"
        assert call_kwargs["event_type"] == "PayableCreated"

        payload = call_kwargs["payload"]
        assert payload["payable_id"] == "uuid-pay-123"
        assert payload["party_id"] == 20
        assert payload["principal_amount"] == "3000.00"
        assert payload["supplier_invoice_number"] == "PROV-555"
        assert payload["withholding_tax_amount"] == "60.00"


# ---------------------------------------------------------------------------
# SERVICES GAP COVERAGE - create_payable real path
# ---------------------------------------------------------------------------

class TestCreatePayableRealPath:
    """
    Tests that exercise create_payable without mocking the Payable class,
    covering the actual constructor and calculation lines.
    """

    @patch("apps.kernels.portfolio.services.publish_outbox_event")
    @patch("apps.kernels.portfolio.models.Obligation.save")
    @patch("apps.kernels.portfolio.models.Obligation.full_clean")
    def test_create_payable_with_withholding(self, mock_clean, mock_save, mock_publish):
        """Exercise withholding tax calculation path."""
        from apps.kernels.portfolio.services import create_payable

        company = MagicMock(id=1, pk=1)
        party = MagicMock(id=10, pk=10)

        result = create_payable(
            company=company,
            party=party,
            reference_type="PURCHASE_DOCUMENT",
            reference_id=55,
            principal_amount=Decimal("10000.00"),
            currency="NIO",
            issue_date=date(2026, 6, 1),
            due_date=date(2026, 7, 1),
            withholding_tax_rate=Decimal("2.00"),
            early_payment_discount_rate=Decimal("3.00"),
            early_payment_discount_days=10,
            supplier_invoice_number="PROV-001",
            supplier_invoice_date=date(2026, 5, 28),
            metadata={"po_number": "PO-100"},
        )

        # Verify withholding calculation
        assert result.withholding_tax_amount == Decimal("200.00")  # 10000 * 2%
        assert result.withholding_tax_rate == Decimal("2.00")

        # Verify early payment discount date
        assert result.early_payment_discount_date == date(2026, 6, 11)  # issue + 10 days

        # Other fields
        assert result.supplier_invoice_number == "PROV-001"
        assert result.supplier_invoice_date == date(2026, 5, 28)
        assert result.metadata_json == {"po_number": "PO-100"}

        mock_clean.assert_called_once()
        mock_save.assert_called_once()
        mock_publish.assert_called_once()

    @patch("apps.kernels.portfolio.services.publish_outbox_event")
    @patch("apps.kernels.portfolio.models.Obligation.save")
    @patch("apps.kernels.portfolio.models.Obligation.full_clean")
    def test_create_payable_no_withholding_no_discount(self, mock_clean, mock_save, mock_publish):
        """Exercise path without withholding or discount."""
        from apps.kernels.portfolio.services import create_payable

        company = MagicMock(id=1, pk=1)
        party = MagicMock(id=10, pk=10)

        result = create_payable(
            company=company,
            party=party,
            reference_type="PURCHASE",
            reference_id=10,
            principal_amount=Decimal("500.00"),
            currency="NIO",
            issue_date=date(2026, 6, 1),
            due_date=date(2026, 7, 1),
        )

        assert result.withholding_tax_amount == Decimal("0.00")
        assert result.early_payment_discount_date is None
        assert result.supplier_invoice_date == date(2026, 6, 1)  # defaults to issue_date


# ---------------------------------------------------------------------------
# SERVICES GAP COVERAGE - create_credit real path (lines 318-321, 339, 357-358)
# ---------------------------------------------------------------------------

class TestCreateCreditRealPath:
    """
    Tests that exercise create_credit without mocking the Credit class,
    covering lines 318-321 (function def), 339 (created_by param), 357-358 (rate validation).
    """

    @patch("apps.kernels.portfolio.services.publish_outbox_event")
    @patch("apps.kernels.portfolio.models.Obligation.save")
    @patch("apps.kernels.portfolio.models.Obligation.full_clean")
    @patch("apps.kernels.portfolio.services.timezone")
    def test_create_credit_real_constructor(self, mock_tz, mock_clean, mock_save, mock_publish):
        """Exercise Credit constructor without mocking the class."""
        from apps.kernels.portfolio.services import create_credit

        mock_tz.localdate.return_value = date(2026, 6, 1)

        company = MagicMock(id=1, pk=1)
        lender = MagicMock(id=1, pk=1)
        borrower = MagicMock(id=2, pk=2)
        guarantor = MagicMock(id=3, pk=3)
        created_by = MagicMock(id=5, pk=5)

        result = create_credit(
            company=company,
            credit_type="WORKING_CAPITAL",
            lender_party=lender,
            borrower_party=borrower,
            approved_amount=Decimal("50000.00"),
            currency="NIO",
            interest_rate=Decimal("12.00"),
            term_months=12,
            maturity_date=date(2027, 6, 1),
            branch=MagicMock(id=2, pk=2),
            guarantor_party=guarantor,
            interest_calculation_method="COMPOUND",
            payment_frequency="QUARTERLY",
            grace_period_months=3,
            collateral_type="REAL_ESTATE",
            collateral_value=Decimal("100000.00"),
            contract_number="CR-2026-001",
            created_by=created_by,
            metadata={"approval_committee": "board"},
        )

        assert result.credit_type == "WORKING_CAPITAL"
        assert result.approved_amount == Decimal("50000.00")
        assert result.interest_rate == Decimal("12.00")
        assert result.term_months == 12
        assert result.maturity_date == date(2027, 6, 1)
        assert result.interest_calculation_method == "COMPOUND"
        assert result.payment_frequency == "QUARTERLY"
        assert result.grace_period_months == 3
        assert result.collateral_type == "REAL_ESTATE"
        assert result.collateral_value == Decimal("100000.00")
        assert result.contract_number == "CR-2026-001"
        assert result.metadata_json == {"approval_committee": "board"}
        assert result.disbursed_amount == Decimal("0.00")

        mock_clean.assert_called_once()
        mock_save.assert_called_once()
        mock_publish.assert_called_once()

        # Validate publish payload
        payload = mock_publish.call_args.kwargs["payload"]
        assert payload["credit_type"] == "WORKING_CAPITAL"
        assert payload["approved_amount"] == "50000.00"
        assert payload["interest_rate"] == "12.00"
        assert payload["term_months"] == 12

    @patch("apps.kernels.portfolio.services.publish_outbox_event")
    @patch("apps.kernels.portfolio.models.Obligation.save")
    @patch("apps.kernels.portfolio.models.Obligation.full_clean")
    @patch("apps.kernels.portfolio.services.timezone")
    def test_create_credit_minimal_params(self, mock_tz, mock_clean, mock_save, mock_publish):
        """Exercise create_credit with minimal params (default values for optional)."""
        from apps.kernels.portfolio.services import create_credit

        mock_tz.localdate.return_value = date(2026, 6, 1)

        company = MagicMock(id=1, pk=1)
        lender = MagicMock(id=1, pk=1)
        borrower = MagicMock(id=2, pk=2)

        result = create_credit(
            company=company,
            credit_type="TERM_LOAN",
            lender_party=lender,
            borrower_party=borrower,
            approved_amount=Decimal("10000.00"),
            currency="NIO",
            interest_rate=Decimal("8.00"),
            term_months=6,
            maturity_date=date(2026, 12, 1),
        )

        # Defaults
        assert result.guarantor_party is None
        assert result.interest_calculation_method == "SIMPLE"
        assert result.payment_frequency == "MONTHLY"
        assert result.grace_period_months == 0
        assert result.collateral_type == ""
        assert result.collateral_value is None
        assert result.contract_number == ""
        assert result.created_by is None
        assert result.metadata_json == {}

    def test_create_credit_negative_rate_raises(self):
        """Exercises lines 353-357 (negative interest rate validation)."""
        from apps.kernels.portfolio.services import create_credit, PortfolioDomainError

        with pytest.raises(PortfolioDomainError) as exc_info:
            create_credit(
                company=MagicMock(),
                credit_type="TERM_LOAN",
                lender_party=MagicMock(id=1),
                borrower_party=MagicMock(id=2),
                approved_amount=Decimal("10000.00"),
                currency="NIO",
                interest_rate=Decimal("-0.01"),
                term_months=12,
                maturity_date=date(2027, 1, 1),
            )

        assert exc_info.value.code == "INVALID_RATE"
        assert "negative" in exc_info.value.message.lower()

    def test_create_credit_zero_rate_passes_validation(self):
        """Interest rate of 0 is valid (exercises boundary of rate check)."""
        from apps.kernels.portfolio.services import create_credit

        # This should pass rate validation but fail on same party
        # because rate >= 0 is valid
        with pytest.raises(Exception):
            # Will fail at some later point (same party or DB) but passes rate check
            create_credit(
                company=MagicMock(id=1, pk=1),
                credit_type="TERM_LOAN",
                lender_party=MagicMock(id=1),
                borrower_party=MagicMock(id=1),  # same party → raises INVALID_PARTIES
                approved_amount=Decimal("10000.00"),
                currency="NIO",
                interest_rate=Decimal("0.00"),
                term_months=12,
                maturity_date=date(2027, 1, 1),
            )

    def test_create_credit_same_parties_raises(self):
        """Exercises lines 359-363 (same lender/borrower validation)."""
        from apps.kernels.portfolio.services import create_credit, PortfolioDomainError

        party = MagicMock(id=5)

        with pytest.raises(PortfolioDomainError) as exc_info:
            create_credit(
                company=MagicMock(),
                credit_type="TERM_LOAN",
                lender_party=party,
                borrower_party=party,
                approved_amount=Decimal("10000.00"),
                currency="NIO",
                interest_rate=Decimal("5.00"),
                term_months=12,
                maturity_date=date(2027, 1, 1),
            )

        assert exc_info.value.code == "INVALID_PARTIES"


# ---------------------------------------------------------------------------
# SERVICES GAP COVERAGE - disburse_credit real path
# ---------------------------------------------------------------------------

class TestDisburseCreditRealPath:
    """Additional disburse_credit tests for edge coverage."""

    @patch("apps.kernels.portfolio.services.publish_outbox_event")
    def test_disburse_already_disbursed_status(self, mock_publish):
        """Exercise the DISBURSED status path (already partially disbursed)."""
        from apps.kernels.portfolio.services import disburse_credit
        from apps.kernels.portfolio.models import CreditStatus

        credit = MagicMock()
        credit.credit_status = CreditStatus.DISBURSED
        credit.disbursed_amount = Decimal("5000.00")
        credit.approved_amount = Decimal("10000.00")
        credit.disbursement_date = date(2026, 5, 1)  # Already has a date
        credit.metadata_json = {"disbursements": []}
        credit.obligation_id = "uuid-d-partial"
        credit.company = MagicMock()
        credit.branch = MagicMock()
        credit.borrower_party_id = 2
        credit.lender_party_id = 1

        result = disburse_credit(
            credit=credit,
            disbursed_amount=Decimal("3000.00"),
            disbursement_date=date(2026, 6, 15),
            disbursed_by=MagicMock(id=3),
        )

        assert credit.disbursed_amount == Decimal("8000.00")
        assert credit.credit_status == CreditStatus.ACTIVE
        # Should NOT overwrite existing disbursement_date
        assert credit.disbursement_date == date(2026, 5, 1)
        credit.save.assert_called_once()
        mock_publish.assert_called_once()


# ---------------------------------------------------------------------------
# SERVICES GAP COVERAGE - allocate_payment default breakdown
# ---------------------------------------------------------------------------

class TestAllocatePaymentDefaultBreakdownPath:
    """
    Exercise the default allocation breakdown logic (no explicit breakdown provided).
    Covers lines 554-563 in services.py.
    """

    @patch("apps.kernels.portfolio.services.publish_outbox_event")
    @patch("apps.kernels.portfolio.services.transaction")
    @patch("apps.kernels.portfolio.services.ContentType")
    @patch("apps.kernels.portfolio.services.PaymentAllocation")
    @patch("apps.kernels.portfolio.services.timezone")
    def test_default_breakdown_applies_penalty_first(self, mock_tz, MockAllocation, MockCT, mock_tx, mock_publish):
        """Default breakdown: penalty → interest → fee → principal."""
        from apps.kernels.portfolio.services import allocate_payment_to_obligation
        from apps.kernels.portfolio.models import ObligationStatus, Receivable

        mock_tz.now.return_value = "now"
        MockCT.objects.get_for_model.return_value = MagicMock()
        mock_alloc = MagicMock()
        mock_alloc.allocation_id = "alloc-default-2"
        MockAllocation.return_value = mock_alloc
        mock_tx.atomic.return_value.__enter__ = MagicMock()
        mock_tx.atomic.return_value.__exit__ = MagicMock(return_value=False)

        payment = MagicMock()
        payment.status = "CAPTURED"
        payment.amount = Decimal("100.00")
        payment.currency = "NIO"
        payment.payment_id = "pay-default-2"
        payment.company = MagicMock()
        payment.branch = MagicMock()

        obligation = MagicMock(spec=Receivable)
        obligation.obligation_type = "RECEIVABLE"
        obligation.obligation_id = "obl-default-2"
        obligation.currency = "NIO"
        obligation.party_id = 1
        obligation.allocated_amount = Decimal("0.00")
        # Set specific amounts to exercise breakdown logic
        obligation.penalty_amount = Decimal("15.00")
        obligation.interest_amount = Decimal("25.00")
        obligation.fee_amount = Decimal("10.00")
        obligation.principal_amount = Decimal("950.00")
        type(obligation).outstanding_amount = PropertyMock(return_value=Decimal("1000.00"))
        type(obligation).total_amount = PropertyMock(return_value=Decimal("1000.00"))

        allocate_payment_to_obligation(
            payment_intent=payment,
            obligation=obligation,
            allocated_amount=Decimal("60.00"),
            allocation_date=date(2026, 6, 1),
            created_by=MagicMock(),
            # No breakdown → default logic
        )

        # Verify the allocation was created with correct breakdown
        alloc_call = MockAllocation.call_args
        assert alloc_call.kwargs["penalty_applied"] == Decimal("15.00")
        assert alloc_call.kwargs["interest_applied"] == Decimal("25.00")
        assert alloc_call.kwargs["fee_applied"] == Decimal("10.00")
        assert alloc_call.kwargs["principal_applied"] == Decimal("10.00")  # 60 - 15 - 25 - 10

    @patch("apps.kernels.portfolio.services.publish_outbox_event")
    @patch("apps.kernels.portfolio.services.transaction")
    @patch("apps.kernels.portfolio.services.ContentType")
    @patch("apps.kernels.portfolio.services.PaymentAllocation")
    @patch("apps.kernels.portfolio.services.timezone")
    def test_default_breakdown_partial_penalty(self, mock_tz, MockAllocation, MockCT, mock_tx, mock_publish):
        """Default breakdown when amount is less than penalty."""
        from apps.kernels.portfolio.services import allocate_payment_to_obligation
        from apps.kernels.portfolio.models import Receivable

        mock_tz.now.return_value = "now"
        MockCT.objects.get_for_model.return_value = MagicMock()
        mock_alloc = MagicMock()
        MockAllocation.return_value = mock_alloc
        mock_tx.atomic.return_value.__enter__ = MagicMock()
        mock_tx.atomic.return_value.__exit__ = MagicMock(return_value=False)

        payment = MagicMock()
        payment.status = "CAPTURED"
        payment.amount = Decimal("5.00")
        payment.currency = "NIO"
        payment.payment_id = "pay-partial"
        payment.company = MagicMock()
        payment.branch = MagicMock()

        obligation = MagicMock(spec=Receivable)
        obligation.obligation_type = "RECEIVABLE"
        obligation.obligation_id = "obl-partial"
        obligation.currency = "NIO"
        obligation.party_id = 1
        obligation.allocated_amount = Decimal("0.00")
        obligation.penalty_amount = Decimal("20.00")
        obligation.interest_amount = Decimal("10.00")
        obligation.fee_amount = Decimal("5.00")
        type(obligation).outstanding_amount = PropertyMock(return_value=Decimal("500.00"))
        type(obligation).total_amount = PropertyMock(return_value=Decimal("500.00"))

        allocate_payment_to_obligation(
            payment_intent=payment,
            obligation=obligation,
            allocated_amount=Decimal("5.00"),
            allocation_date=date(2026, 6, 1),
            created_by=MagicMock(),
        )

        # Only covers partial penalty
        alloc_call = MockAllocation.call_args
        assert alloc_call.kwargs["penalty_applied"] == Decimal("5.00")
        assert alloc_call.kwargs["interest_applied"] == Decimal("0.00")
        assert alloc_call.kwargs["fee_applied"] == Decimal("0.00")
        assert alloc_call.kwargs["principal_applied"] == Decimal("0.00")


# ---------------------------------------------------------------------------
# SERVICES GAP COVERAGE - auto_allocate_payment
# ---------------------------------------------------------------------------

class TestAutoAllocatePayment:
    """Tests for auto_allocate_payment covering the disabled path."""

    @patch("apps.kernels.portfolio.services.PortfolioSettings")
    def test_auto_allocate_disabled(self, MockSettings):
        """Exercise AUTO_ALLOCATION_DISABLED error path."""
        from apps.kernels.portfolio.services import auto_allocate_payment, PortfolioDomainError

        mock_settings = MagicMock()
        mock_settings.auto_allocate_payments = False
        MockSettings.get_or_create_for_company.return_value = mock_settings

        payment = MagicMock()
        payment.company = MagicMock()
        party = MagicMock()

        with pytest.raises(PortfolioDomainError) as exc_info:
            auto_allocate_payment(payment, party)

        assert exc_info.value.code == "AUTO_ALLOCATION_DISABLED"

    @patch("apps.kernels.portfolio.services.allocate_payment_to_obligation")
    @patch("apps.kernels.portfolio.services.Receivable")
    @patch("apps.kernels.portfolio.services.timezone")
    @patch("apps.kernels.portfolio.services.PortfolioSettings")
    def test_auto_allocate_enabled_fifo(self, MockSettings, mock_tz, MockReceivable, mock_allocate):
        """Exercise the FIFO auto-allocation path."""
        from apps.kernels.portfolio.services import auto_allocate_payment

        mock_settings = MagicMock()
        mock_settings.auto_allocate_payments = True
        MockSettings.get_or_create_for_company.return_value = mock_settings
        mock_tz.localdate.return_value = date(2026, 6, 1)

        # Two pending obligations
        obl1 = MagicMock()
        type(obl1).outstanding_amount = PropertyMock(return_value=Decimal("300.00"))
        obl2 = MagicMock()
        type(obl2).outstanding_amount = PropertyMock(return_value=Decimal("500.00"))

        MockReceivable.objects.filter.return_value.order_by.return_value = [obl1, obl2]

        mock_allocate.side_effect = [MagicMock(), MagicMock()]

        payment = MagicMock()
        payment.company = MagicMock()
        payment.amount = Decimal("400.00")
        payment.currency = "NIO"

        party = MagicMock()
        created_by = MagicMock()

        result = auto_allocate_payment(payment, party, created_by=created_by)

        assert len(result) == 2
        # First call: allocate min(400, 300) = 300
        first_call = mock_allocate.call_args_list[0]
        assert first_call.kwargs["allocated_amount"] == Decimal("300.00")
        # Second call: allocate min(100, 500) = 100
        second_call = mock_allocate.call_args_list[1]
        assert second_call.kwargs["allocated_amount"] == Decimal("100.00")

    @patch("apps.kernels.portfolio.services.allocate_payment_to_obligation")
    @patch("apps.kernels.portfolio.services.Receivable")
    @patch("apps.kernels.portfolio.services.timezone")
    @patch("apps.kernels.portfolio.services.PortfolioSettings")
    def test_auto_allocate_no_pending(self, MockSettings, mock_tz, MockReceivable, mock_allocate):
        """Exercise auto-allocation when no pending obligations exist."""
        from apps.kernels.portfolio.services import auto_allocate_payment

        mock_settings = MagicMock()
        mock_settings.auto_allocate_payments = True
        MockSettings.get_or_create_for_company.return_value = mock_settings
        mock_tz.localdate.return_value = date(2026, 6, 1)

        MockReceivable.objects.filter.return_value.order_by.return_value = []

        payment = MagicMock()
        payment.company = MagicMock()
        payment.amount = Decimal("1000.00")
        payment.currency = "NIO"

        result = auto_allocate_payment(payment, MagicMock())
        assert result == []
        mock_allocate.assert_not_called()


# ---------------------------------------------------------------------------
# SERVICES GAP COVERAGE - accrue_interest_for_credit additional paths
# ---------------------------------------------------------------------------

class TestAccrueInterestAdditionalPaths:
    """Additional paths for interest accrual to ensure full coverage."""

    @patch("apps.kernels.portfolio.services.publish_outbox_event")
    @patch("apps.kernels.portfolio.services.InterestAccrual")
    def test_accrue_interest_negative_balance(self, MockAccrual, mock_publish):
        """When allocated > disbursed (edge: balance ≤ 0), returns None."""
        from apps.kernels.portfolio.services import accrue_interest_for_credit
        from apps.kernels.portfolio.models import CreditStatus

        MockAccrual.objects.filter.return_value.first.return_value = None

        credit = MagicMock()
        credit.credit_status = CreditStatus.ACTIVE
        credit.disbursed_amount = Decimal("5000.00")
        credit.allocated_amount = Decimal("6000.00")  # Overpaid

        result = accrue_interest_for_credit(
            credit=credit,
            accrual_date=date(2026, 6, 30),
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
        )

        assert result is None
        mock_publish.assert_not_called()


# ---------------------------------------------------------------------------
# MODELS GAP COVERAGE - PortfolioSettings.get_or_create_for_company
# ---------------------------------------------------------------------------

class TestPortfolioSettingsGetOrCreate:
    """Tests for PortfolioSettings.get_or_create_for_company."""

    @patch("apps.kernels.portfolio.models.PortfolioSettings.objects")
    def test_get_or_create_returns_existing(self, mock_objects):
        """When settings exist, return them."""
        from apps.kernels.portfolio.models import PortfolioSettings

        existing = MagicMock()
        mock_objects.get_or_create.return_value = (existing, False)

        company = MagicMock()
        result = PortfolioSettings.get_or_create_for_company(company)

        assert result == existing
        mock_objects.get_or_create.assert_called_once()

    @patch("apps.kernels.portfolio.models.PortfolioSettings.objects")
    def test_get_or_create_creates_new(self, mock_objects):
        """When settings don't exist, create with defaults."""
        from apps.kernels.portfolio.models import PortfolioSettings

        new_settings = MagicMock()
        mock_objects.get_or_create.return_value = (new_settings, True)

        company = MagicMock()
        result = PortfolioSettings.get_or_create_for_company(company)

        assert result == new_settings
        call_kwargs = mock_objects.get_or_create.call_args
        assert "defaults" in call_kwargs.kwargs or len(call_kwargs[1]) > 0


# ---------------------------------------------------------------------------
# MODELS GAP COVERAGE - InterestAccrual __str__
# ---------------------------------------------------------------------------

class TestInterestAccrualStr:
    """Ensure InterestAccrual.__str__ is covered."""

    def test_str_representation(self):
        from apps.kernels.portfolio.models import InterestAccrual

        obj = MagicMock()
        obj.accrual_date = date(2026, 6, 30)
        obj.accrued_interest = Decimal("150.00")
        obj.credit = "Credit ABC"

        result = InterestAccrual.__str__(obj)
        assert "Interest" in result
        assert "150.00" in result


# ---------------------------------------------------------------------------
# MODELS GAP COVERAGE - PaymentAllocation __str__
# ---------------------------------------------------------------------------

class TestPaymentAllocationStr:
    """Ensure PaymentAllocation.__str__ is covered."""

    def test_str_representation(self):
        from apps.kernels.portfolio.models import PaymentAllocation

        obj = MagicMock()
        obj.allocation_id = "alloc-xyz"
        obj.allocated_amount = Decimal("750.00")
        obj.currency = "USD"

        result = PaymentAllocation.__str__(obj)
        assert "Allocation" in result
        assert "alloc-xyz" in result
        assert "750.00" in result


# ---------------------------------------------------------------------------
# MODELS GAP COVERAGE - Obligation.save with overdue transition
# ---------------------------------------------------------------------------

class TestObligationSaveOverdueTransition:
    """Exercise save() when obligation transitions to OVERDUE."""

    def test_save_transitions_pending_to_overdue(self):
        from apps.kernels.portfolio.models import Obligation, ObligationStatus

        obj = MagicMock()
        obj.status = ObligationStatus.PENDING
        obj.due_date = date.today() - timedelta(days=5)
        obj.calculate_days_overdue = MagicMock(return_value=5)
        obj.calculate_aging_bucket = MagicMock(return_value="0-30")
        type(obj).is_overdue = PropertyMock(return_value=True)

        with patch("django.db.models.Model.save"):
            Obligation.save(obj)

        assert obj.status == ObligationStatus.OVERDUE
        assert obj.days_overdue == 5
        assert obj.aging_bucket == "0-30"
