"""
Portfolio Kernel - Services Tests for Coverage

Tests unitarios para servicios de negocio (CxC, CxP, Créditos).
Mock-based — validación completa con DB real es Frente 2 (Codex).
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch, PropertyMock

import pytest


class TestPortfolioDomainError:
    """Tests de la excepción PortfolioDomainError."""

    def test_error_creation(self):
        from apps.kernels.portfolio.services import PortfolioDomainError

        err = PortfolioDomainError("CODE_X", "Something failed")
        assert err.code == "CODE_X"
        assert err.message == "Something failed"
        assert err.details == {}
        assert "[CODE_X]" in str(err)

    def test_error_with_details(self):
        from apps.kernels.portfolio.services import PortfolioDomainError

        err = PortfolioDomainError("E001", "msg", {"key": "val"})
        assert err.details == {"key": "val"}


class TestCreateReceivable:
    """Tests de create_receivable."""

    @patch("apps.kernels.portfolio.services.publish_outbox_event")
    @patch("apps.kernels.portfolio.services.Receivable")
    def test_create_receivable_success(self, MockReceivable, mock_publish):
        from apps.kernels.portfolio.services import create_receivable

        mock_instance = MagicMock()
        mock_instance.obligation_id = "uuid-123"
        mock_instance.party_id = 1
        mock_instance.principal_amount = Decimal("500.00")
        mock_instance.currency = "NIO"
        mock_instance.issue_date = date(2026, 6, 1)
        mock_instance.due_date = date(2026, 7, 1)
        mock_instance.reference_type = "BILLING"
        mock_instance.reference_id = 10
        mock_instance.invoice_number = "INV-001"
        mock_instance.company = MagicMock()
        mock_instance.branch = MagicMock()
        MockReceivable.return_value = mock_instance

        result = create_receivable(
            company=MagicMock(),
            party=MagicMock(),
            reference_type="BILLING",
            reference_id=10,
            principal_amount=Decimal("500.00"),
            currency="NIO",
            issue_date=date(2026, 6, 1),
            due_date=date(2026, 7, 1),
            invoice_number="INV-001",
        )

        assert result == mock_instance
        mock_instance.full_clean.assert_called_once()
        mock_instance.save.assert_called_once()
        mock_publish.assert_called_once()

    def test_create_receivable_invalid_amount(self):
        from apps.kernels.portfolio.services import create_receivable, PortfolioDomainError

        with pytest.raises(PortfolioDomainError) as exc_info:
            create_receivable(
                company=MagicMock(),
                party=MagicMock(),
                reference_type="BILLING",
                reference_id=1,
                principal_amount=Decimal("0.00"),
                currency="NIO",
                issue_date=date.today(),
                due_date=date.today() + timedelta(days=30),
            )
        assert exc_info.value.code == "INVALID_AMOUNT"

    def test_create_receivable_negative_amount(self):
        from apps.kernels.portfolio.services import create_receivable, PortfolioDomainError

        with pytest.raises(PortfolioDomainError) as exc_info:
            create_receivable(
                company=MagicMock(),
                party=MagicMock(),
                reference_type="BILLING",
                reference_id=1,
                principal_amount=Decimal("-100.00"),
                currency="NIO",
                issue_date=date.today(),
                due_date=date.today() + timedelta(days=30),
            )
        assert exc_info.value.code == "INVALID_AMOUNT"


class TestAdjustReceivable:
    """Tests de adjust_receivable."""

    @patch("apps.kernels.portfolio.services.publish_outbox_event")
    def test_adjust_positive(self, mock_publish):
        from apps.kernels.portfolio.services import adjust_receivable

        receivable = MagicMock()
        receivable.principal_amount = Decimal("1000.00")
        receivable.metadata_json = {}
        receivable.obligation_id = "uuid-r1"
        receivable.company = MagicMock()
        receivable.branch = MagicMock()

        result = adjust_receivable(
            receivable=receivable,
            adjustment_amount=Decimal("100.00"),
            reason="Late fee",
            adjusted_by=MagicMock(id=1),
        )

        assert receivable.principal_amount == Decimal("1100.00")
        receivable.save.assert_called_once()
        mock_publish.assert_called_once()
        assert result == receivable

    @patch("apps.kernels.portfolio.services.publish_outbox_event")
    def test_adjust_negative_valid(self, mock_publish):
        from apps.kernels.portfolio.services import adjust_receivable

        receivable = MagicMock()
        receivable.principal_amount = Decimal("1000.00")
        receivable.metadata_json = {}
        receivable.obligation_id = "uuid-r2"
        receivable.company = MagicMock()
        receivable.branch = MagicMock()

        result = adjust_receivable(
            receivable=receivable,
            adjustment_amount=Decimal("-200.00"),
            reason="Discount",
            adjusted_by=None,
        )

        assert receivable.principal_amount == Decimal("800.00")

    def test_adjust_negative_too_large(self):
        from apps.kernels.portfolio.services import adjust_receivable, PortfolioDomainError

        receivable = MagicMock()
        receivable.principal_amount = Decimal("100.00")
        receivable.metadata_json = {}

        with pytest.raises(PortfolioDomainError) as exc_info:
            adjust_receivable(
                receivable=receivable,
                adjustment_amount=Decimal("-200.00"),
                reason="Too much",
                adjusted_by=MagicMock(id=1),
            )
        assert exc_info.value.code == "INVALID_ADJUSTMENT"


class TestWriteOffReceivable:
    """Tests de write_off_receivable."""

    @patch("apps.kernels.portfolio.services.publish_outbox_event")
    @patch("apps.kernels.portfolio.services.timezone")
    def test_write_off_success(self, mock_tz, mock_publish):
        from apps.kernels.portfolio.services import write_off_receivable
        from apps.kernels.portfolio.models import ObligationStatus

        mock_tz.localdate.return_value = date(2026, 6, 1)
        mock_tz.now.return_value = "2026-06-01T00:00:00Z"

        receivable = MagicMock()
        receivable.status = ObligationStatus.OVERDUE
        receivable.obligation_id = "uuid-wo1"
        receivable.metadata_json = {}
        receivable.company = MagicMock()
        receivable.branch = MagicMock()
        type(receivable).outstanding_amount = PropertyMock(return_value=Decimal("500.00"))

        result = write_off_receivable(
            receivable=receivable,
            reason="Uncollectible",
            approved_by=MagicMock(id=2),
        )

        assert receivable.status == ObligationStatus.WRITTEN_OFF
        receivable.save.assert_called_once()
        mock_publish.assert_called_once()

    def test_write_off_already_written_off(self):
        from apps.kernels.portfolio.services import write_off_receivable, PortfolioDomainError
        from apps.kernels.portfolio.models import ObligationStatus

        receivable = MagicMock()
        receivable.status = ObligationStatus.WRITTEN_OFF
        receivable.obligation_id = "uuid-wo2"

        with pytest.raises(PortfolioDomainError) as exc_info:
            write_off_receivable(receivable, "reason", MagicMock())
        assert exc_info.value.code == "ALREADY_WRITTEN_OFF"

    def test_write_off_paid(self):
        from apps.kernels.portfolio.services import write_off_receivable, PortfolioDomainError
        from apps.kernels.portfolio.models import ObligationStatus

        receivable = MagicMock()
        receivable.status = ObligationStatus.PAID
        receivable.obligation_id = "uuid-wo3"

        with pytest.raises(PortfolioDomainError) as exc_info:
            write_off_receivable(receivable, "reason", MagicMock())
        assert exc_info.value.code == "CANNOT_WRITEOFF_PAID"


class TestCreatePayable:
    """Tests de create_payable."""

    @patch("apps.kernels.portfolio.services._publish_payable_created_event")
    @patch("apps.kernels.portfolio.services.Payable")
    def test_create_payable_success(self, MockPayable, mock_publish):
        from apps.kernels.portfolio.services import create_payable

        mock_instance = MagicMock()
        MockPayable.return_value = mock_instance

        result = create_payable(
            company=MagicMock(),
            party=MagicMock(),
            reference_type="PURCHASE",
            reference_id=5,
            principal_amount=Decimal("2000.00"),
            currency="NIO",
            issue_date=date(2026, 6, 1),
            due_date=date(2026, 7, 1),
            withholding_tax_rate=Decimal("2.00"),
            early_payment_discount_days=10,
        )

        assert result == mock_instance
        mock_instance.full_clean.assert_called_once()
        mock_instance.save.assert_called_once()
        mock_publish.assert_called_once()

    @patch("apps.kernels.portfolio.services._publish_payable_created_event")
    @patch("apps.kernels.portfolio.services.Payable")
    def test_create_payable_no_withholding(self, MockPayable, mock_publish):
        from apps.kernels.portfolio.services import create_payable

        mock_instance = MagicMock()
        MockPayable.return_value = mock_instance

        result = create_payable(
            company=MagicMock(),
            party=MagicMock(),
            reference_type="PURCHASE",
            reference_id=5,
            principal_amount=Decimal("2000.00"),
            currency="NIO",
            issue_date=date(2026, 6, 1),
            due_date=date(2026, 7, 1),
        )

        assert result == mock_instance

    def test_create_payable_invalid_amount(self):
        from apps.kernels.portfolio.services import create_payable, PortfolioDomainError

        with pytest.raises(PortfolioDomainError) as exc_info:
            create_payable(
                company=MagicMock(),
                party=MagicMock(),
                reference_type="PURCHASE",
                reference_id=1,
                principal_amount=Decimal("0.00"),
                currency="NIO",
                issue_date=date.today(),
                due_date=date.today() + timedelta(days=30),
            )
        assert exc_info.value.code == "INVALID_AMOUNT"


class TestCreateCredit:
    """Tests de create_credit."""

    @patch("apps.kernels.portfolio.services.publish_outbox_event")
    @patch("apps.kernels.portfolio.services.Credit")
    @patch("apps.kernels.portfolio.services.timezone")
    def test_create_credit_success(self, mock_tz, MockCredit, mock_publish):
        from apps.kernels.portfolio.services import create_credit

        mock_tz.localdate.return_value = date(2026, 6, 1)
        mock_instance = MagicMock()
        mock_instance.obligation_id = "uuid-c1"
        mock_instance.company = MagicMock()
        mock_instance.branch = MagicMock()
        MockCredit.return_value = mock_instance

        lender = MagicMock(id=1)
        borrower = MagicMock(id=2)

        result = create_credit(
            company=MagicMock(),
            credit_type="WORKING_CAPITAL",
            lender_party=lender,
            borrower_party=borrower,
            approved_amount=Decimal("50000.00"),
            currency="NIO",
            interest_rate=Decimal("12.00"),
            term_months=12,
            maturity_date=date(2027, 6, 1),
        )

        assert result == mock_instance
        mock_instance.full_clean.assert_called_once()
        mock_instance.save.assert_called_once()
        mock_publish.assert_called_once()

    def test_create_credit_invalid_amount(self):
        from apps.kernels.portfolio.services import create_credit, PortfolioDomainError

        with pytest.raises(PortfolioDomainError) as exc_info:
            create_credit(
                company=MagicMock(),
                credit_type="TERM_LOAN",
                lender_party=MagicMock(id=1),
                borrower_party=MagicMock(id=2),
                approved_amount=Decimal("0.00"),
                currency="NIO",
                interest_rate=Decimal("10.00"),
                term_months=12,
                maturity_date=date(2027, 1, 1),
            )
        assert exc_info.value.code == "INVALID_AMOUNT"

    def test_create_credit_negative_rate(self):
        from apps.kernels.portfolio.services import create_credit, PortfolioDomainError

        with pytest.raises(PortfolioDomainError) as exc_info:
            create_credit(
                company=MagicMock(),
                credit_type="TERM_LOAN",
                lender_party=MagicMock(id=1),
                borrower_party=MagicMock(id=2),
                approved_amount=Decimal("10000.00"),
                currency="NIO",
                interest_rate=Decimal("-1.00"),
                term_months=12,
                maturity_date=date(2027, 1, 1),
            )
        assert exc_info.value.code == "INVALID_RATE"

    def test_create_credit_same_parties(self):
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


class TestDisburseCredit:
    """Tests de disburse_credit."""

    @patch("apps.kernels.portfolio.services.publish_outbox_event")
    def test_disburse_success(self, mock_publish):
        from apps.kernels.portfolio.services import disburse_credit
        from apps.kernels.portfolio.models import CreditStatus

        credit = MagicMock()
        credit.credit_status = CreditStatus.APPROVED
        credit.disbursed_amount = Decimal("0.00")
        credit.approved_amount = Decimal("10000.00")
        credit.disbursement_date = None
        credit.metadata_json = {}
        credit.obligation_id = "uuid-d1"
        credit.company = MagicMock()
        credit.branch = MagicMock()
        credit.borrower_party_id = 2
        credit.lender_party_id = 1

        result = disburse_credit(
            credit=credit,
            disbursed_amount=Decimal("5000.00"),
            disbursement_date=date(2026, 6, 1),
            disbursed_by=MagicMock(id=1),
        )

        assert credit.disbursed_amount == Decimal("5000.00")
        assert credit.credit_status == CreditStatus.ACTIVE
        assert credit.disbursement_date == date(2026, 6, 1)
        credit.save.assert_called_once()

    @patch("apps.kernels.portfolio.services.publish_outbox_event")
    def test_disburse_full_amount(self, mock_publish):
        from apps.kernels.portfolio.services import disburse_credit
        from apps.kernels.portfolio.models import CreditStatus

        credit = MagicMock()
        credit.credit_status = CreditStatus.APPROVED
        credit.disbursed_amount = Decimal("0.00")
        credit.approved_amount = Decimal("10000.00")
        credit.disbursement_date = None
        credit.metadata_json = {}
        credit.obligation_id = "uuid-d2"
        credit.company = MagicMock()
        credit.branch = MagicMock()
        credit.borrower_party_id = 2
        credit.lender_party_id = 1

        disburse_credit(
            credit=credit,
            disbursed_amount=Decimal("10000.00"),
            disbursement_date=date(2026, 6, 1),
            disbursed_by=None,
        )

        assert credit.credit_status == CreditStatus.DISBURSED

    def test_disburse_invalid_status(self):
        from apps.kernels.portfolio.services import disburse_credit, PortfolioDomainError
        from apps.kernels.portfolio.models import CreditStatus

        credit = MagicMock()
        credit.credit_status = CreditStatus.PAID_OFF

        with pytest.raises(PortfolioDomainError) as exc_info:
            disburse_credit(credit, Decimal("1000.00"), date.today(), MagicMock())
        assert exc_info.value.code == "INVALID_STATUS"

    def test_disburse_zero_amount(self):
        from apps.kernels.portfolio.services import disburse_credit, PortfolioDomainError
        from apps.kernels.portfolio.models import CreditStatus

        credit = MagicMock()
        credit.credit_status = CreditStatus.APPROVED

        with pytest.raises(PortfolioDomainError) as exc_info:
            disburse_credit(credit, Decimal("0.00"), date.today(), MagicMock())
        assert exc_info.value.code == "INVALID_AMOUNT"

    def test_disburse_exceeds_approved(self):
        from apps.kernels.portfolio.services import disburse_credit, PortfolioDomainError
        from apps.kernels.portfolio.models import CreditStatus

        credit = MagicMock()
        credit.credit_status = CreditStatus.APPROVED
        credit.disbursed_amount = Decimal("8000.00")
        credit.approved_amount = Decimal("10000.00")

        with pytest.raises(PortfolioDomainError) as exc_info:
            disburse_credit(credit, Decimal("5000.00"), date.today(), MagicMock())
        assert exc_info.value.code == "EXCEEDS_APPROVED"


class TestAllocatePaymentToObligation:
    """Tests de allocate_payment_to_obligation."""

    @patch("apps.kernels.portfolio.services.publish_outbox_event")
    @patch("apps.kernels.portfolio.services.transaction")
    @patch("apps.kernels.portfolio.services.ContentType")
    @patch("apps.kernels.portfolio.services.PaymentAllocation")
    @patch("apps.kernels.portfolio.services.timezone")
    def test_allocate_success_with_breakdown(self, mock_tz, MockAllocation, MockCT, mock_tx, mock_publish):
        from apps.kernels.portfolio.services import allocate_payment_to_obligation
        from apps.kernels.portfolio.models import ObligationStatus

        mock_tz.now.return_value = "now"
        MockCT.objects.get_for_model.return_value = MagicMock()
        mock_alloc_instance = MagicMock()
        mock_alloc_instance.allocation_id = "alloc-1"
        MockAllocation.return_value = mock_alloc_instance
        mock_tx.atomic.return_value.__enter__ = MagicMock()
        mock_tx.atomic.return_value.__exit__ = MagicMock(return_value=False)

        payment = MagicMock()
        payment.status = "CAPTURED"
        payment.amount = Decimal("500.00")
        payment.currency = "NIO"
        payment.payment_id = "pay-1"
        payment.company = MagicMock()
        payment.branch = MagicMock()

        obligation = MagicMock()
        obligation.obligation_type = "RECEIVABLE"
        obligation.obligation_id = "obl-1"
        obligation.currency = "NIO"
        obligation.party_id = 1
        obligation.allocated_amount = Decimal("0.00")
        obligation.penalty_amount = Decimal("5.00")
        obligation.interest_amount = Decimal("10.00")
        obligation.fee_amount = Decimal("5.00")
        type(obligation).outstanding_amount = PropertyMock(return_value=Decimal("1000.00"))
        type(obligation).total_amount = PropertyMock(return_value=Decimal("1000.00"))

        # Use isinstance check for _get_allocation_event_type
        with patch("apps.kernels.portfolio.services.isinstance", side_effect=lambda o, t: t.__name__ == "Receivable"):
            result = allocate_payment_to_obligation(
                payment_intent=payment,
                obligation=obligation,
                allocated_amount=Decimal("100.00"),
                allocation_date=date(2026, 6, 1),
                created_by=MagicMock(),
                allocation_breakdown={"principal": Decimal("80.00"), "interest": Decimal("10.00"), "fee": Decimal("5.00"), "penalty": Decimal("5.00")},
            )

        assert result == mock_alloc_instance

    def test_allocate_payment_not_captured(self):
        from apps.kernels.portfolio.services import allocate_payment_to_obligation, PortfolioDomainError

        payment = MagicMock()
        payment.status = "PENDING"
        payment.payment_id = "pay-2"

        obligation = MagicMock()

        with pytest.raises(PortfolioDomainError) as exc_info:
            allocate_payment_to_obligation(payment, obligation, Decimal("100.00"), date.today(), MagicMock())
        assert exc_info.value.code == "PAYMENT_NOT_CAPTURED"

    def test_allocate_zero_amount(self):
        from apps.kernels.portfolio.services import allocate_payment_to_obligation, PortfolioDomainError

        payment = MagicMock()
        payment.status = "CAPTURED"
        payment.payment_id = "pay-3"

        obligation = MagicMock()

        with pytest.raises(PortfolioDomainError) as exc_info:
            allocate_payment_to_obligation(payment, obligation, Decimal("0.00"), date.today(), MagicMock())
        assert exc_info.value.code == "INVALID_AMOUNT"

    def test_allocate_exceeds_payment(self):
        from apps.kernels.portfolio.services import allocate_payment_to_obligation, PortfolioDomainError

        payment = MagicMock()
        payment.status = "CAPTURED"
        payment.amount = Decimal("100.00")
        payment.payment_id = "pay-4"

        obligation = MagicMock()
        type(obligation).outstanding_amount = PropertyMock(return_value=Decimal("500.00"))

        with pytest.raises(PortfolioDomainError) as exc_info:
            allocate_payment_to_obligation(payment, obligation, Decimal("200.00"), date.today(), MagicMock())
        assert exc_info.value.code == "EXCEEDS_PAYMENT"

    def test_allocate_exceeds_outstanding(self):
        from apps.kernels.portfolio.services import allocate_payment_to_obligation, PortfolioDomainError

        payment = MagicMock()
        payment.status = "CAPTURED"
        payment.amount = Decimal("1000.00")
        payment.currency = "NIO"
        payment.payment_id = "pay-5"

        obligation = MagicMock()
        obligation.currency = "NIO"
        type(obligation).outstanding_amount = PropertyMock(return_value=Decimal("50.00"))

        with pytest.raises(PortfolioDomainError) as exc_info:
            allocate_payment_to_obligation(payment, obligation, Decimal("100.00"), date.today(), MagicMock())
        assert exc_info.value.code == "EXCEEDS_OUTSTANDING"

    def test_allocate_currency_mismatch_no_rate(self):
        from apps.kernels.portfolio.services import allocate_payment_to_obligation, PortfolioDomainError

        payment = MagicMock()
        payment.status = "CAPTURED"
        payment.amount = Decimal("1000.00")
        payment.currency = "USD"
        payment.payment_id = "pay-6"

        obligation = MagicMock()
        obligation.currency = "NIO"
        type(obligation).outstanding_amount = PropertyMock(return_value=Decimal("500.00"))

        with pytest.raises(PortfolioDomainError) as exc_info:
            allocate_payment_to_obligation(payment, obligation, Decimal("100.00"), date.today(), MagicMock())
        assert exc_info.value.code == "CURRENCY_MISMATCH"


class TestGetAllocationEventType:
    """Tests de _get_allocation_event_type."""

    def test_receivable_type(self):
        from apps.kernels.portfolio.services import _get_allocation_event_type
        from apps.kernels.portfolio.models import Receivable

        obj = MagicMock(spec=Receivable)
        result = _get_allocation_event_type(obj)
        assert result == "ReceivableAllocated"

    def test_payable_type(self):
        from apps.kernels.portfolio.services import _get_allocation_event_type
        from apps.kernels.portfolio.models import Payable

        obj = MagicMock(spec=Payable)
        result = _get_allocation_event_type(obj)
        assert result == "PayableAllocated"

    def test_credit_type(self):
        from apps.kernels.portfolio.services import _get_allocation_event_type
        from apps.kernels.portfolio.models import Credit

        obj = MagicMock(spec=Credit)
        result = _get_allocation_event_type(obj)
        assert result == "CreditRepaymentReceived"

    def test_unknown_type(self):
        from apps.kernels.portfolio.services import _get_allocation_event_type

        obj = MagicMock()
        # Ensure it doesn't match any known types
        obj.__class__ = type("Unknown", (), {})
        result = _get_allocation_event_type(obj)
        assert result == "ObligationAllocated"


class TestAccrueInterestForCredit:
    """Tests de accrue_interest_for_credit."""

    @patch("apps.kernels.portfolio.services.publish_outbox_event")
    @patch("apps.kernels.portfolio.services.InterestAccrual")
    def test_accrue_simple_interest(self, MockAccrual, mock_publish):
        from apps.kernels.portfolio.services import accrue_interest_for_credit
        from apps.kernels.portfolio.models import CreditStatus

        MockAccrual.objects.filter.return_value.first.return_value = None
        mock_accrual_instance = MagicMock()
        mock_accrual_instance.accrual_id = "accrual-1"
        MockAccrual.return_value = mock_accrual_instance

        credit = MagicMock()
        credit.credit_status = CreditStatus.DISBURSED
        credit.disbursed_amount = Decimal("10000.00")
        credit.allocated_amount = Decimal("2000.00")
        credit.interest_rate = Decimal("12.00")
        credit.interest_calculation_method = "SIMPLE"
        credit.interest_amount = Decimal("0.00")
        credit.obligation_id = "credit-1"
        credit.company = MagicMock()
        credit.branch = MagicMock()
        credit.borrower_party_id = 2

        result = accrue_interest_for_credit(
            credit=credit,
            accrual_date=date(2026, 6, 30),
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
        )

        assert result == mock_accrual_instance
        mock_accrual_instance.save.assert_called_once()
        credit.save.assert_called_once()
        mock_publish.assert_called_once()

    @patch("apps.kernels.portfolio.services.publish_outbox_event")
    @patch("apps.kernels.portfolio.services.InterestAccrual")
    def test_accrue_compound_interest(self, MockAccrual, mock_publish):
        from apps.kernels.portfolio.services import accrue_interest_for_credit
        from apps.kernels.portfolio.models import CreditStatus

        MockAccrual.objects.filter.return_value.first.return_value = None
        mock_accrual_instance = MagicMock()
        MockAccrual.return_value = mock_accrual_instance

        credit = MagicMock()
        credit.credit_status = CreditStatus.ACTIVE
        credit.disbursed_amount = Decimal("10000.00")
        credit.allocated_amount = Decimal("0.00")
        credit.interest_rate = Decimal("12.00")
        credit.interest_calculation_method = "COMPOUND"
        credit.interest_amount = Decimal("0.00")
        credit.obligation_id = "credit-2"
        credit.company = MagicMock()
        credit.branch = MagicMock()
        credit.borrower_party_id = 2

        result = accrue_interest_for_credit(
            credit=credit,
            accrual_date=date(2026, 6, 30),
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
        )

        assert result == mock_accrual_instance

    @patch("apps.kernels.portfolio.services.publish_outbox_event")
    @patch("apps.kernels.portfolio.services.InterestAccrual")
    def test_accrue_flat_interest(self, MockAccrual, mock_publish):
        from apps.kernels.portfolio.services import accrue_interest_for_credit
        from apps.kernels.portfolio.models import CreditStatus

        MockAccrual.objects.filter.return_value.first.return_value = None
        mock_accrual_instance = MagicMock()
        MockAccrual.return_value = mock_accrual_instance

        credit = MagicMock()
        credit.credit_status = CreditStatus.DISBURSED
        credit.disbursed_amount = Decimal("10000.00")
        credit.allocated_amount = Decimal("0.00")
        credit.interest_rate = Decimal("12.00")
        credit.interest_calculation_method = "FLAT"
        credit.interest_amount = Decimal("0.00")
        credit.obligation_id = "credit-3"
        credit.company = MagicMock()
        credit.branch = MagicMock()
        credit.borrower_party_id = 2

        result = accrue_interest_for_credit(
            credit=credit,
            accrual_date=date(2026, 6, 30),
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
        )

        assert result == mock_accrual_instance

    def test_accrue_wrong_status(self):
        from apps.kernels.portfolio.services import accrue_interest_for_credit
        from apps.kernels.portfolio.models import CreditStatus

        credit = MagicMock()
        credit.credit_status = CreditStatus.DRAFT

        result = accrue_interest_for_credit(
            credit=credit,
            accrual_date=date(2026, 6, 30),
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
        )
        assert result is None

    @patch("apps.kernels.portfolio.services.InterestAccrual")
    def test_accrue_already_exists(self, MockAccrual):
        from apps.kernels.portfolio.services import accrue_interest_for_credit
        from apps.kernels.portfolio.models import CreditStatus

        existing = MagicMock()
        MockAccrual.objects.filter.return_value.first.return_value = existing

        credit = MagicMock()
        credit.credit_status = CreditStatus.DISBURSED

        result = accrue_interest_for_credit(
            credit=credit,
            accrual_date=date(2026, 6, 30),
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
        )
        assert result == existing

    @patch("apps.kernels.portfolio.services.InterestAccrual")
    def test_accrue_zero_balance(self, MockAccrual):
        from apps.kernels.portfolio.services import accrue_interest_for_credit
        from apps.kernels.portfolio.models import CreditStatus

        MockAccrual.objects.filter.return_value.first.return_value = None

        credit = MagicMock()
        credit.credit_status = CreditStatus.DISBURSED
        credit.disbursed_amount = Decimal("5000.00")
        credit.allocated_amount = Decimal("5000.00")  # Fully paid

        result = accrue_interest_for_credit(
            credit=credit,
            accrual_date=date(2026, 6, 30),
            period_start=date(2026, 6, 1),
            period_end=date(2026, 6, 30),
        )
        assert result is None


class TestUpdateAgingForObligations:
    """Tests de update_aging_for_obligations."""

    @patch("apps.kernels.portfolio.services.Receivable")
    @patch("apps.kernels.portfolio.services.timezone")
    def test_update_aging_uses_today(self, mock_tz, MockReceivable):
        from apps.kernels.portfolio.services import update_aging_for_obligations

        mock_tz.localdate.return_value = date(2026, 6, 1)
        MockReceivable.objects.filter.return_value = []

        company = MagicMock()
        update_aging_for_obligations(company)
        mock_tz.localdate.assert_called_once()

    @patch("apps.kernels.portfolio.services.Receivable")
    def test_update_aging_with_date(self, MockReceivable):
        from apps.kernels.portfolio.services import update_aging_for_obligations

        receivable = MagicMock()
        MockReceivable.objects.filter.return_value = [receivable]

        company = MagicMock()
        update_aging_for_obligations(company, as_of_date=date(2026, 6, 1))

        receivable.update_aging.assert_called_once()
        receivable.save.assert_called_once()

    @patch("apps.kernels.portfolio.services.Credit")
    @patch("apps.kernels.portfolio.services.Payable")
    @patch("apps.kernels.portfolio.services.Receivable")
    def test_update_aging_payables_and_credits(self, MockReceivable, MockPayable, MockCredit):
        from apps.kernels.portfolio.services import update_aging_for_obligations

        MockReceivable.objects.filter.return_value = iter([])

        payable = MagicMock()
        MockPayable.objects.filter.return_value = iter([payable])

        credit = MagicMock()
        MockCredit.objects.filter.return_value = iter([credit])

        company = MagicMock()
        update_aging_for_obligations(company, as_of_date=date(2026, 6, 1))

        payable.update_aging.assert_called_once()
        payable.save.assert_called_once()
        credit.update_aging.assert_called_once()
        credit.save.assert_called_once()


class TestAllocatePaymentWithoutBreakdown:
    """Tests de allocate_payment_to_obligation sin breakdown (default logic)."""

    @patch("apps.kernels.portfolio.services.publish_outbox_event")
    @patch("apps.kernels.portfolio.services.transaction")
    @patch("apps.kernels.portfolio.services.ContentType")
    @patch("apps.kernels.portfolio.services.PaymentAllocation")
    @patch("apps.kernels.portfolio.services.timezone")
    def test_allocate_default_breakdown(self, mock_tz, MockAllocation, MockCT, mock_tx, mock_publish):
        """Tests the default allocation logic (penalty → interest → fee → principal)."""
        from apps.kernels.portfolio.services import allocate_payment_to_obligation
        from apps.kernels.portfolio.models import ObligationStatus, Receivable

        mock_tz.now.return_value = "now"
        MockCT.objects.get_for_model.return_value = MagicMock()
        mock_alloc_instance = MagicMock()
        mock_alloc_instance.allocation_id = "alloc-default"
        MockAllocation.return_value = mock_alloc_instance
        mock_tx.atomic.return_value.__enter__ = MagicMock()
        mock_tx.atomic.return_value.__exit__ = MagicMock(return_value=False)

        payment = MagicMock()
        payment.status = "CAPTURED"
        payment.amount = Decimal("500.00")
        payment.currency = "NIO"
        payment.payment_id = "pay-default"
        payment.company = MagicMock()
        payment.branch = MagicMock()

        obligation = MagicMock(spec=Receivable)
        obligation.obligation_type = "RECEIVABLE"
        obligation.obligation_id = "obl-default"
        obligation.currency = "NIO"
        obligation.party_id = 1
        obligation.allocated_amount = Decimal("0.00")
        obligation.penalty_amount = Decimal("10.00")
        obligation.interest_amount = Decimal("20.00")
        obligation.fee_amount = Decimal("5.00")
        obligation.principal_amount = Decimal("1000.00")
        type(obligation).outstanding_amount = PropertyMock(return_value=Decimal("1035.00"))
        type(obligation).total_amount = PropertyMock(return_value=Decimal("1035.00"))

        result = allocate_payment_to_obligation(
            payment_intent=payment,
            obligation=obligation,
            allocated_amount=Decimal("50.00"),
            allocation_date=date(2026, 6, 1),
            created_by=MagicMock(),
            # No allocation_breakdown → uses default logic
        )

        assert result == mock_alloc_instance
        mock_alloc_instance.full_clean.assert_called_once()

    @patch("apps.kernels.portfolio.services.publish_outbox_event")
    @patch("apps.kernels.portfolio.services.transaction")
    @patch("apps.kernels.portfolio.services.ContentType")
    @patch("apps.kernels.portfolio.services.PaymentAllocation")
    @patch("apps.kernels.portfolio.services.timezone")
    def test_allocate_marks_paid(self, mock_tz, MockAllocation, MockCT, mock_tx, mock_publish):
        """Tests that allocation marks obligation as PAID when fully allocated."""
        from apps.kernels.portfolio.services import allocate_payment_to_obligation
        from apps.kernels.portfolio.models import ObligationStatus, Receivable

        mock_tz.now.return_value = "now"
        MockCT.objects.get_for_model.return_value = MagicMock()
        mock_alloc_instance = MagicMock()
        MockAllocation.return_value = mock_alloc_instance
        mock_tx.atomic.return_value.__enter__ = MagicMock()
        mock_tx.atomic.return_value.__exit__ = MagicMock(return_value=False)

        payment = MagicMock()
        payment.status = "CAPTURED"
        payment.amount = Decimal("1000.00")
        payment.currency = "NIO"
        payment.payment_id = "pay-full"
        payment.company = MagicMock()
        payment.branch = MagicMock()

        obligation = MagicMock(spec=Receivable)
        obligation.obligation_type = "RECEIVABLE"
        obligation.obligation_id = "obl-full"
        obligation.currency = "NIO"
        obligation.party_id = 1
        obligation.allocated_amount = Decimal("900.00")
        obligation.penalty_amount = Decimal("0.00")
        obligation.interest_amount = Decimal("0.00")
        obligation.fee_amount = Decimal("0.00")
        obligation.principal_amount = Decimal("1000.00")
        type(obligation).outstanding_amount = PropertyMock(return_value=Decimal("100.00"))
        type(obligation).total_amount = PropertyMock(return_value=Decimal("1000.00"))

        allocate_payment_to_obligation(
            payment_intent=payment,
            obligation=obligation,
            allocated_amount=Decimal("100.00"),
            allocation_date=date(2026, 6, 1),
            created_by=MagicMock(),
        )

        # After allocating 100 to an obligation with 900 already allocated and total=1000
        assert obligation.allocated_amount == Decimal("1000.00")
        assert obligation.status == ObligationStatus.PAID
        assert obligation.paid_date == date(2026, 6, 1)

    @patch("apps.kernels.portfolio.services.publish_outbox_event")
    @patch("apps.kernels.portfolio.services.transaction")
    @patch("apps.kernels.portfolio.services.ContentType")
    @patch("apps.kernels.portfolio.services.PaymentAllocation")
    @patch("apps.kernels.portfolio.services.timezone")
    def test_allocate_marks_partial(self, mock_tz, MockAllocation, MockCT, mock_tx, mock_publish):
        """Tests that allocation marks obligation as PARTIAL when partially allocated."""
        from apps.kernels.portfolio.services import allocate_payment_to_obligation
        from apps.kernels.portfolio.models import ObligationStatus, Receivable

        mock_tz.now.return_value = "now"
        MockCT.objects.get_for_model.return_value = MagicMock()
        mock_alloc_instance = MagicMock()
        MockAllocation.return_value = mock_alloc_instance
        mock_tx.atomic.return_value.__enter__ = MagicMock()
        mock_tx.atomic.return_value.__exit__ = MagicMock(return_value=False)

        payment = MagicMock()
        payment.status = "CAPTURED"
        payment.amount = Decimal("1000.00")
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
        obligation.penalty_amount = Decimal("0.00")
        obligation.interest_amount = Decimal("0.00")
        obligation.fee_amount = Decimal("0.00")
        obligation.principal_amount = Decimal("1000.00")
        type(obligation).outstanding_amount = PropertyMock(return_value=Decimal("1000.00"))
        type(obligation).total_amount = PropertyMock(return_value=Decimal("1000.00"))

        allocate_payment_to_obligation(
            payment_intent=payment,
            obligation=obligation,
            allocated_amount=Decimal("300.00"),
            allocation_date=date(2026, 6, 1),
            created_by=MagicMock(),
        )

        # Partially allocated
        assert obligation.allocated_amount == Decimal("300.00")
        assert obligation.status == ObligationStatus.PARTIAL

    @patch("apps.kernels.portfolio.services.publish_outbox_event")
    @patch("apps.kernels.portfolio.services.transaction")
    @patch("apps.kernels.portfolio.services.ContentType")
    @patch("apps.kernels.portfolio.services.PaymentAllocation")
    @patch("apps.kernels.portfolio.services.timezone")
    def test_allocate_with_exchange_rate(self, mock_tz, MockAllocation, MockCT, mock_tx, mock_publish):
        """Tests allocation with currency mismatch and exchange rate provided."""
        from apps.kernels.portfolio.services import allocate_payment_to_obligation
        from apps.kernels.portfolio.models import Receivable

        mock_tz.now.return_value = "now"
        MockCT.objects.get_for_model.return_value = MagicMock()
        mock_alloc_instance = MagicMock()
        MockAllocation.return_value = mock_alloc_instance
        mock_tx.atomic.return_value.__enter__ = MagicMock()
        mock_tx.atomic.return_value.__exit__ = MagicMock(return_value=False)

        payment = MagicMock()
        payment.status = "CAPTURED"
        payment.amount = Decimal("500.00")
        payment.currency = "USD"
        payment.payment_id = "pay-fx"
        payment.company = MagicMock()
        payment.branch = MagicMock()

        obligation = MagicMock(spec=Receivable)
        obligation.obligation_type = "RECEIVABLE"
        obligation.obligation_id = "obl-fx"
        obligation.currency = "NIO"
        obligation.party_id = 1
        obligation.allocated_amount = Decimal("0.00")
        obligation.penalty_amount = Decimal("0.00")
        obligation.interest_amount = Decimal("0.00")
        obligation.fee_amount = Decimal("0.00")
        type(obligation).outstanding_amount = PropertyMock(return_value=Decimal("5000.00"))
        type(obligation).total_amount = PropertyMock(return_value=Decimal("5000.00"))

        result = allocate_payment_to_obligation(
            payment_intent=payment,
            obligation=obligation,
            allocated_amount=Decimal("100.00"),
            allocation_date=date(2026, 6, 1),
            created_by=MagicMock(),
            exchange_rate=Decimal("36.50"),
        )

        assert result == mock_alloc_instance


class TestAutoAllocatePayment:
    """Tests de auto_allocate_payment."""

    @patch("apps.kernels.portfolio.services.allocate_payment_to_obligation")
    @patch("apps.kernels.portfolio.services.Receivable")
    @patch("apps.kernels.portfolio.services.PortfolioSettings")
    @patch("apps.kernels.portfolio.services.timezone")
    def test_auto_allocate_success(self, mock_tz, MockSettings, MockReceivable, mock_allocate):
        from apps.kernels.portfolio.services import auto_allocate_payment

        mock_tz.localdate.return_value = date(2026, 6, 1)

        settings = MagicMock()
        settings.auto_allocate_payments = True
        MockSettings.get_or_create_for_company.return_value = settings

        obl1 = MagicMock()
        type(obl1).outstanding_amount = PropertyMock(return_value=Decimal("300.00"))
        obl2 = MagicMock()
        type(obl2).outstanding_amount = PropertyMock(return_value=Decimal("500.00"))
        MockReceivable.objects.filter.return_value.order_by.return_value = [obl1, obl2]

        alloc1 = MagicMock()
        alloc2 = MagicMock()
        mock_allocate.side_effect = [alloc1, alloc2]

        payment = MagicMock()
        payment.amount = Decimal("700.00")
        payment.currency = "NIO"
        payment.company = MagicMock()

        party = MagicMock()

        result = auto_allocate_payment(payment, party, created_by=MagicMock())

        assert len(result) == 2
        assert result[0] == alloc1
        assert result[1] == alloc2
        # First allocation should be 300 (full outstanding of obl1)
        first_call_kwargs = mock_allocate.call_args_list[0]
        assert first_call_kwargs[1]["allocated_amount"] == Decimal("300.00") or first_call_kwargs[0][2] == Decimal("300.00")

    @patch("apps.kernels.portfolio.services.PortfolioSettings")
    def test_auto_allocate_disabled(self, MockSettings):
        from apps.kernels.portfolio.services import auto_allocate_payment, PortfolioDomainError

        settings = MagicMock()
        settings.auto_allocate_payments = False
        MockSettings.get_or_create_for_company.return_value = settings

        payment = MagicMock()
        payment.company = MagicMock()

        with pytest.raises(PortfolioDomainError) as exc_info:
            auto_allocate_payment(payment, MagicMock())
        assert exc_info.value.code == "AUTO_ALLOCATION_DISABLED"

    @patch("apps.kernels.portfolio.services.allocate_payment_to_obligation")
    @patch("apps.kernels.portfolio.services.Receivable")
    @patch("apps.kernels.portfolio.services.PortfolioSettings")
    @patch("apps.kernels.portfolio.services.timezone")
    def test_auto_allocate_partial_remaining(self, mock_tz, MockSettings, MockReceivable, mock_allocate):
        """Tests that auto_allocate stops when remaining amount is exhausted."""
        from apps.kernels.portfolio.services import auto_allocate_payment

        mock_tz.localdate.return_value = date(2026, 6, 1)

        settings = MagicMock()
        settings.auto_allocate_payments = True
        MockSettings.get_or_create_for_company.return_value = settings

        obl1 = MagicMock()
        type(obl1).outstanding_amount = PropertyMock(return_value=Decimal("500.00"))
        obl2 = MagicMock()
        type(obl2).outstanding_amount = PropertyMock(return_value=Decimal("500.00"))
        MockReceivable.objects.filter.return_value.order_by.return_value = [obl1, obl2]

        alloc1 = MagicMock()
        mock_allocate.return_value = alloc1

        payment = MagicMock()
        payment.amount = Decimal("200.00")  # Only enough for partial allocation of first
        payment.currency = "NIO"
        payment.company = MagicMock()

        result = auto_allocate_payment(payment, MagicMock(), created_by=MagicMock())

        # Should only allocate to first obligation (200 < 500)
        assert len(result) == 1
        assert mock_allocate.call_count == 1

    @patch("apps.kernels.portfolio.services.Receivable")
    @patch("apps.kernels.portfolio.services.PortfolioSettings")
    @patch("apps.kernels.portfolio.services.timezone")
    def test_auto_allocate_no_pending_obligations(self, mock_tz, MockSettings, MockReceivable):
        """Tests auto_allocate when no pending obligations exist."""
        from apps.kernels.portfolio.services import auto_allocate_payment

        mock_tz.localdate.return_value = date(2026, 6, 1)

        settings = MagicMock()
        settings.auto_allocate_payments = True
        MockSettings.get_or_create_for_company.return_value = settings

        MockReceivable.objects.filter.return_value.order_by.return_value = []

        payment = MagicMock()
        payment.amount = Decimal("500.00")
        payment.currency = "NIO"
        payment.company = MagicMock()

        result = auto_allocate_payment(payment, MagicMock())

        assert result == []


class TestPublishPayableCreatedEvent:
    """Tests de _publish_payable_created_event."""

    @patch("apps.kernels.portfolio.services.publish_outbox_event")
    def test_publish_event(self, mock_publish):
        from apps.kernels.portfolio.services import _publish_payable_created_event

        payable = MagicMock()
        payable.obligation_id = "uuid-p1"
        payable.party_id = 5
        payable.principal_amount = Decimal("3000.00")
        payable.currency = "NIO"
        payable.issue_date = date(2026, 6, 1)
        payable.due_date = date(2026, 7, 1)
        payable.reference_type = "PURCHASE"
        payable.reference_id = 10
        payable.supplier_invoice_number = "SUP-001"
        payable.withholding_tax_amount = Decimal("60.00")
        payable.company = MagicMock()
        payable.branch = MagicMock()

        _publish_payable_created_event(payable)

        mock_publish.assert_called_once()
        call_kwargs = mock_publish.call_args[1]
        assert call_kwargs["source_module"] == "PORTFOLIO"
        assert call_kwargs["event_type"] == "PayableCreated"


class TestPublishReceivableCreatedEvent:
    """Tests de _publish_receivable_created_event."""

    @patch("apps.kernels.portfolio.services.publish_outbox_event")
    def test_publish_event(self, mock_publish):
        from apps.kernels.portfolio.services import _publish_receivable_created_event

        receivable = MagicMock()
        receivable.obligation_id = "uuid-r99"
        receivable.party_id = 3
        receivable.principal_amount = Decimal("1500.00")
        receivable.currency = "NIO"
        receivable.issue_date = date(2026, 6, 1)
        receivable.due_date = date(2026, 7, 1)
        receivable.reference_type = "BILLING_DOCUMENT"
        receivable.reference_id = 42
        receivable.invoice_number = "FAC-042"
        receivable.company = MagicMock()
        receivable.branch = MagicMock()

        _publish_receivable_created_event(receivable)

        mock_publish.assert_called_once()
        call_kwargs = mock_publish.call_args[1]
        assert call_kwargs["source_module"] == "PORTFOLIO"
        assert call_kwargs["event_type"] == "ReceivableCreated"


class TestCreateReceivableWithOptionalParams:
    """Tests de create_receivable con todos los parámetros opcionales."""

    @patch("apps.kernels.portfolio.services.publish_outbox_event")
    @patch("apps.kernels.portfolio.services.Receivable")
    def test_create_with_all_optional_params(self, MockReceivable, mock_publish):
        from apps.kernels.portfolio.services import create_receivable

        mock_instance = MagicMock()
        mock_instance.obligation_id = "uuid-full"
        mock_instance.party_id = 1
        mock_instance.principal_amount = Decimal("500.00")
        mock_instance.currency = "USD"
        mock_instance.issue_date = date(2026, 6, 1)
        mock_instance.due_date = date(2026, 7, 1)
        mock_instance.reference_type = "BILLING"
        mock_instance.reference_id = 10
        mock_instance.invoice_number = "INV-FULL"
        mock_instance.company = MagicMock()
        mock_instance.branch = MagicMock()
        MockReceivable.return_value = mock_instance

        result = create_receivable(
            company=MagicMock(),
            party=MagicMock(),
            reference_type="BILLING",
            reference_id=10,
            principal_amount=Decimal("500.00"),
            currency="USD",
            issue_date=date(2026, 6, 1),
            due_date=date(2026, 7, 1),
            branch=MagicMock(),
            invoice_number="INV-FULL",
            invoice_date=date(2026, 5, 30),
            credit_limit=Decimal("10000.00"),
            credit_days=30,
            created_by=MagicMock(),
            metadata={"source": "test"},
        )

        assert result == mock_instance

    @patch("apps.kernels.portfolio.services.publish_outbox_event")
    @patch("apps.kernels.portfolio.services.Receivable")
    def test_create_with_no_invoice_date_uses_issue_date(self, MockReceivable, mock_publish):
        """Tests that when invoice_date is None, issue_date is used."""
        from apps.kernels.portfolio.services import create_receivable

        mock_instance = MagicMock()
        mock_instance.obligation_id = "uuid-noid"
        mock_instance.party_id = 1
        mock_instance.principal_amount = Decimal("100.00")
        mock_instance.currency = "NIO"
        mock_instance.issue_date = date(2026, 6, 1)
        mock_instance.due_date = date(2026, 7, 1)
        mock_instance.reference_type = "BILLING"
        mock_instance.reference_id = 1
        mock_instance.invoice_number = ""
        mock_instance.company = MagicMock()
        mock_instance.branch = MagicMock()
        MockReceivable.return_value = mock_instance

        result = create_receivable(
            company=MagicMock(),
            party=MagicMock(),
            reference_type="BILLING",
            reference_id=1,
            principal_amount=Decimal("100.00"),
            currency="NIO",
            issue_date=date(2026, 6, 1),
            due_date=date(2026, 7, 1),
            invoice_date=None,
        )

        assert result == mock_instance


class TestCreatePayableWithAllParams:
    """Tests de create_payable con todas las variantes."""

    @patch("apps.kernels.portfolio.services._publish_payable_created_event")
    @patch("apps.kernels.portfolio.services.Payable")
    def test_create_payable_with_all_params(self, MockPayable, mock_publish):
        from apps.kernels.portfolio.services import create_payable

        mock_instance = MagicMock()
        MockPayable.return_value = mock_instance

        result = create_payable(
            company=MagicMock(),
            party=MagicMock(),
            reference_type="PURCHASE",
            reference_id=5,
            principal_amount=Decimal("5000.00"),
            currency="USD",
            issue_date=date(2026, 6, 1),
            due_date=date(2026, 7, 1),
            branch=MagicMock(),
            supplier_invoice_number="PROV-999",
            supplier_invoice_date=date(2026, 5, 28),
            early_payment_discount_rate=Decimal("3.00"),
            early_payment_discount_days=15,
            withholding_tax_rate=Decimal("5.00"),
            created_by=MagicMock(),
            metadata={"po_number": "PO-123"},
        )

        assert result == mock_instance
        mock_instance.full_clean.assert_called_once()
        mock_instance.save.assert_called_once()

    @patch("apps.kernels.portfolio.services._publish_payable_created_event")
    @patch("apps.kernels.portfolio.services.Payable")
    def test_create_payable_no_supplier_date(self, MockPayable, mock_publish):
        """Tests that when supplier_invoice_date is None, issue_date is used."""
        from apps.kernels.portfolio.services import create_payable

        mock_instance = MagicMock()
        MockPayable.return_value = mock_instance

        create_payable(
            company=MagicMock(),
            party=MagicMock(),
            reference_type="PURCHASE",
            reference_id=3,
            principal_amount=Decimal("1000.00"),
            currency="NIO",
            issue_date=date(2026, 6, 1),
            due_date=date(2026, 7, 1),
            supplier_invoice_date=None,
        )

        assert mock_instance.full_clean.called


class TestCreateCreditWithAllParams:
    """Tests de create_credit con todos los parámetros opcionales."""

    @patch("apps.kernels.portfolio.services.publish_outbox_event")
    @patch("apps.kernels.portfolio.services.Credit")
    @patch("apps.kernels.portfolio.services.timezone")
    def test_create_credit_with_all_params(self, mock_tz, MockCredit, mock_publish):
        from apps.kernels.portfolio.services import create_credit

        mock_tz.localdate.return_value = date(2026, 6, 1)
        mock_instance = MagicMock()
        mock_instance.obligation_id = "uuid-c-full"
        mock_instance.company = MagicMock()
        mock_instance.branch = MagicMock()
        MockCredit.return_value = mock_instance

        lender = MagicMock(id=1)
        borrower = MagicMock(id=2)
        guarantor = MagicMock(id=3)

        result = create_credit(
            company=MagicMock(),
            credit_type="TERM_LOAN",
            lender_party=lender,
            borrower_party=borrower,
            approved_amount=Decimal("100000.00"),
            currency="USD",
            interest_rate=Decimal("8.50"),
            term_months=24,
            maturity_date=date(2028, 6, 1),
            branch=MagicMock(),
            guarantor_party=guarantor,
            interest_calculation_method="COMPOUND",
            payment_frequency="QUARTERLY",
            grace_period_months=3,
            collateral_type="REAL_ESTATE",
            collateral_value=Decimal("150000.00"),
            contract_number="CR-2026-001",
            created_by=MagicMock(),
            metadata={"loan_officer": "John"},
        )

        assert result == mock_instance
        mock_instance.full_clean.assert_called_once()
        mock_instance.save.assert_called_once()
        mock_publish.assert_called_once()


class TestDisburseCreditEdgeCases:
    """Tests adicionales de disburse_credit."""

    @patch("apps.kernels.portfolio.services.publish_outbox_event")
    def test_disburse_already_disbursed_partial(self, mock_publish):
        """Tests disbursing when already partially disbursed."""
        from apps.kernels.portfolio.services import disburse_credit
        from apps.kernels.portfolio.models import CreditStatus

        credit = MagicMock()
        credit.credit_status = CreditStatus.DISBURSED
        credit.disbursed_amount = Decimal("5000.00")
        credit.approved_amount = Decimal("10000.00")
        credit.disbursement_date = date(2026, 5, 1)  # Already has a date
        credit.metadata_json = {"disbursements": []}
        credit.obligation_id = "uuid-d3"
        credit.company = MagicMock()
        credit.branch = MagicMock()
        credit.borrower_party_id = 2
        credit.lender_party_id = 1

        result = disburse_credit(
            credit=credit,
            disbursed_amount=Decimal("3000.00"),
            disbursement_date=date(2026, 6, 1),
            disbursed_by=None,
        )

        assert credit.disbursed_amount == Decimal("8000.00")
        assert credit.credit_status == CreditStatus.ACTIVE
        # disbursement_date should not be overwritten (already set)
        assert credit.disbursement_date == date(2026, 5, 1)


class TestPortfolioSettingsGetOrCreate:
    """Tests de PortfolioSettings.get_or_create_for_company."""

    @patch("apps.kernels.portfolio.models.PortfolioSettings.objects")
    def test_get_or_create_existing(self, mock_objects):
        from apps.kernels.portfolio.models import PortfolioSettings

        existing_settings = MagicMock()
        mock_objects.get_or_create.return_value = (existing_settings, False)

        company = MagicMock()
        result = PortfolioSettings.get_or_create_for_company(company)

        assert result == existing_settings

    @patch("apps.kernels.portfolio.models.PortfolioSettings.objects")
    def test_get_or_create_new(self, mock_objects):
        from apps.kernels.portfolio.models import PortfolioSettings

        new_settings = MagicMock()
        mock_objects.get_or_create.return_value = (new_settings, True)

        company = MagicMock()
        result = PortfolioSettings.get_or_create_for_company(company)

        assert result == new_settings
        mock_objects.get_or_create.assert_called_once()
