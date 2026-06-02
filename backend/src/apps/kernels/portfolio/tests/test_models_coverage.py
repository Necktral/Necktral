"""
Portfolio Kernel - Model Tests for Coverage

Tests unitarios para propiedades, validaciones y métodos de modelos.
No requiere PostgreSQL real — mock-based testing (Frente 1 → Frente 2).
"""
from __future__ import annotations

from datetime import date, timedelta
from decimal import Decimal
from unittest.mock import MagicMock, patch, PropertyMock

import pytest
from django.core.exceptions import ValidationError
from django.utils import timezone


class TestObligationProperties:
    """Tests de propiedades calculadas del modelo Obligation."""

    def _make_obligation_mock(self, **kwargs):
        """Helper: crea un mock que simula un Obligation con campos."""
        from apps.kernels.portfolio.models import Obligation, ObligationStatus

        defaults = {
            "principal_amount": Decimal("1000.00"),
            "interest_amount": Decimal("50.00"),
            "fee_amount": Decimal("10.00"),
            "penalty_amount": Decimal("5.00"),
            "allocated_amount": Decimal("200.00"),
            "status": ObligationStatus.PENDING,
            "due_date": date.today() - timedelta(days=10),
        }
        defaults.update(kwargs)

        # Use a real-ish approach: instantiate property logic manually
        obj = MagicMock()
        for k, v in defaults.items():
            setattr(obj, k, v)

        # Bind real property methods
        obj.total_amount = Obligation.total_amount.fget(obj)
        obj.outstanding_amount = Obligation.outstanding_amount.fget(obj)
        obj.is_overdue = Obligation.is_overdue.fget(obj)
        return obj

    def test_total_amount(self):
        """total_amount suma principal + interest + fee + penalty."""
        from apps.kernels.portfolio.models import Obligation

        obj = MagicMock()
        obj.principal_amount = Decimal("1000.00")
        obj.interest_amount = Decimal("50.00")
        obj.fee_amount = Decimal("10.00")
        obj.penalty_amount = Decimal("5.00")

        result = Obligation.total_amount.fget(obj)
        assert result == Decimal("1065.00")

    def test_outstanding_amount(self):
        """outstanding_amount = total - allocated."""
        from apps.kernels.portfolio.models import Obligation

        obj = MagicMock()
        obj.principal_amount = Decimal("1000.00")
        obj.interest_amount = Decimal("50.00")
        obj.fee_amount = Decimal("10.00")
        obj.penalty_amount = Decimal("5.00")
        obj.allocated_amount = Decimal("200.00")

        # total_amount property
        type(obj).total_amount = PropertyMock(return_value=Decimal("1065.00"))
        result = Obligation.outstanding_amount.fget(obj)
        assert result == Decimal("865.00")

    def test_is_overdue_when_paid(self):
        """No está vencida si está PAID."""
        from apps.kernels.portfolio.models import Obligation, ObligationStatus

        obj = MagicMock()
        obj.status = ObligationStatus.PAID
        obj.due_date = date.today() - timedelta(days=100)

        result = Obligation.is_overdue.fget(obj)
        assert result is False

    def test_is_overdue_when_written_off(self):
        """No está vencida si está WRITTEN_OFF."""
        from apps.kernels.portfolio.models import Obligation, ObligationStatus

        obj = MagicMock()
        obj.status = ObligationStatus.WRITTEN_OFF
        obj.due_date = date.today() - timedelta(days=100)

        result = Obligation.is_overdue.fget(obj)
        assert result is False

    def test_is_overdue_when_cancelled(self):
        """No está vencida si está CANCELLED."""
        from apps.kernels.portfolio.models import Obligation, ObligationStatus

        obj = MagicMock()
        obj.status = ObligationStatus.CANCELLED
        obj.due_date = date.today() - timedelta(days=100)

        result = Obligation.is_overdue.fget(obj)
        assert result is False

    def test_is_overdue_true_when_pending_past_due(self):
        """Está vencida si está PENDING y due_date < hoy."""
        from apps.kernels.portfolio.models import Obligation, ObligationStatus

        obj = MagicMock()
        obj.status = ObligationStatus.PENDING
        obj.due_date = date.today() - timedelta(days=5)

        result = Obligation.is_overdue.fget(obj)
        assert result is True

    def test_is_overdue_false_when_pending_future(self):
        """No está vencida si due_date >= hoy."""
        from apps.kernels.portfolio.models import Obligation, ObligationStatus

        obj = MagicMock()
        obj.status = ObligationStatus.PENDING
        obj.due_date = date.today() + timedelta(days=5)

        result = Obligation.is_overdue.fget(obj)
        assert result is False

    def test_calculate_days_overdue_not_overdue(self):
        """days_overdue = 0 si no está vencida."""
        from apps.kernels.portfolio.models import Obligation, ObligationStatus

        obj = MagicMock()
        obj.status = ObligationStatus.PENDING
        obj.due_date = date.today() + timedelta(days=5)
        type(obj).is_overdue = PropertyMock(return_value=False)

        result = Obligation.calculate_days_overdue(obj)
        assert result == 0

    def test_calculate_days_overdue_when_overdue(self):
        """days_overdue = días desde due_date si está vencida."""
        from apps.kernels.portfolio.models import Obligation, ObligationStatus

        obj = MagicMock()
        obj.status = ObligationStatus.PENDING
        obj.due_date = date.today() - timedelta(days=15)
        type(obj).is_overdue = PropertyMock(return_value=True)

        result = Obligation.calculate_days_overdue(obj)
        assert result == 15


class TestObligationAgingBucket:
    """Tests de calculate_aging_bucket."""

    def _call_bucket(self, days_overdue):
        from apps.kernels.portfolio.models import Obligation

        obj = MagicMock()
        obj.calculate_days_overdue = MagicMock(return_value=days_overdue)
        return Obligation.calculate_aging_bucket(obj)

    def test_current(self):
        assert self._call_bucket(0) == "CURRENT"

    def test_0_30(self):
        assert self._call_bucket(15) == "0-30"

    def test_31_60(self):
        assert self._call_bucket(45) == "31-60"

    def test_61_90(self):
        assert self._call_bucket(75) == "61-90"

    def test_91_120(self):
        assert self._call_bucket(100) == "91-120"

    def test_120_plus(self):
        assert self._call_bucket(200) == "120+"


class TestObligationUpdateAging:
    """Tests de update_aging."""

    def test_update_aging_sets_fields(self):
        from apps.kernels.portfolio.models import Obligation, ObligationStatus

        obj = MagicMock()
        obj.status = ObligationStatus.PENDING
        obj.calculate_days_overdue = MagicMock(return_value=45)
        obj.calculate_aging_bucket = MagicMock(return_value="31-60")
        type(obj).is_overdue = PropertyMock(return_value=True)

        Obligation.update_aging(obj)

        assert obj.days_overdue == 45
        assert obj.aging_bucket == "31-60"
        assert obj.status == ObligationStatus.OVERDUE

    def test_update_aging_no_status_change_when_partial(self):
        from apps.kernels.portfolio.models import Obligation, ObligationStatus

        obj = MagicMock()
        obj.status = ObligationStatus.PARTIAL
        obj.calculate_days_overdue = MagicMock(return_value=10)
        obj.calculate_aging_bucket = MagicMock(return_value="0-30")
        type(obj).is_overdue = PropertyMock(return_value=True)

        Obligation.update_aging(obj)

        # Status remains PARTIAL (only PENDING → OVERDUE)
        assert obj.status == ObligationStatus.PARTIAL


class TestObligationClean:
    """Tests de Obligation.clean validation."""

    def test_clean_allocated_exceeds_total(self):
        from apps.kernels.portfolio.models import Obligation

        obj = MagicMock()
        obj.principal_amount = Decimal("100.00")
        obj.interest_amount = Decimal("0.00")
        obj.fee_amount = Decimal("0.00")
        obj.penalty_amount = Decimal("0.00")
        obj.allocated_amount = Decimal("200.00")
        obj.due_date = date.today() + timedelta(days=30)
        obj.issue_date = date.today()
        type(obj).total_amount = PropertyMock(return_value=Decimal("100.00"))

        # Mock super().clean()
        with patch("django.db.models.Model.clean"):
            with pytest.raises(ValidationError) as exc_info:
                Obligation.clean(obj)
            assert "allocated_amount" in exc_info.value.message_dict

    def test_clean_due_date_before_issue_date(self):
        from apps.kernels.portfolio.models import Obligation

        obj = MagicMock()
        obj.principal_amount = Decimal("100.00")
        obj.interest_amount = Decimal("0.00")
        obj.fee_amount = Decimal("0.00")
        obj.penalty_amount = Decimal("0.00")
        obj.allocated_amount = Decimal("0.00")
        obj.due_date = date.today() - timedelta(days=10)
        obj.issue_date = date.today()
        type(obj).total_amount = PropertyMock(return_value=Decimal("100.00"))

        with patch("django.db.models.Model.clean"):
            with pytest.raises(ValidationError) as exc_info:
                Obligation.clean(obj)
            assert "due_date" in exc_info.value.message_dict

    def test_clean_passes_when_valid(self):
        from apps.kernels.portfolio.models import Obligation

        obj = MagicMock()
        obj.principal_amount = Decimal("100.00")
        obj.interest_amount = Decimal("0.00")
        obj.fee_amount = Decimal("0.00")
        obj.penalty_amount = Decimal("0.00")
        obj.allocated_amount = Decimal("50.00")
        obj.issue_date = date.today()
        obj.due_date = date.today() + timedelta(days=30)
        type(obj).total_amount = PropertyMock(return_value=Decimal("100.00"))

        with patch("django.db.models.Model.clean"):
            # Should not raise
            Obligation.clean(obj)


class TestPayableProperties:
    """Tests de propiedades de Payable."""

    def test_net_payable_amount(self):
        from apps.kernels.portfolio.models import Payable

        obj = MagicMock()
        obj.withholding_tax_amount = Decimal("15.00")
        type(obj).outstanding_amount = PropertyMock(return_value=Decimal("100.00"))

        result = Payable.net_payable_amount.fget(obj)
        assert result == Decimal("85.00")

    @patch("django.utils.timezone.localdate")
    def test_discount_available_within_date(self, mock_localdate):
        from apps.kernels.portfolio.models import Payable

        mock_localdate.return_value = date(2026, 6, 1)

        obj = MagicMock()
        obj.early_payment_discount_date = date(2026, 6, 10)
        obj.early_payment_discount_rate = Decimal("2.00")
        type(obj).outstanding_amount = PropertyMock(return_value=Decimal("1000.00"))

        result = Payable.discount_available.fget(obj)
        assert result == Decimal("20.00")

    @patch("django.utils.timezone.localdate")
    def test_discount_available_past_date(self, mock_localdate):
        from apps.kernels.portfolio.models import Payable

        mock_localdate.return_value = date(2026, 6, 15)

        obj = MagicMock()
        obj.early_payment_discount_date = date(2026, 6, 10)
        obj.early_payment_discount_rate = Decimal("2.00")
        type(obj).outstanding_amount = PropertyMock(return_value=Decimal("1000.00"))

        result = Payable.discount_available.fget(obj)
        assert result == Decimal("0.00")

    def test_discount_available_no_date(self):
        from apps.kernels.portfolio.models import Payable

        obj = MagicMock()
        obj.early_payment_discount_date = None

        result = Payable.discount_available.fget(obj)
        assert result == Decimal("0.00")


class TestCreditProperties:
    """Tests de propiedades de Credit."""

    def test_loan_to_value_with_collateral(self):
        from apps.kernels.portfolio.models import Credit

        obj = MagicMock()
        obj.approved_amount = Decimal("80000.00")
        obj.collateral_value = Decimal("100000.00")

        result = Credit.loan_to_value_ratio.fget(obj)
        assert result == Decimal("80.00")

    def test_loan_to_value_no_collateral(self):
        from apps.kernels.portfolio.models import Credit

        obj = MagicMock()
        obj.collateral_value = None

        result = Credit.loan_to_value_ratio.fget(obj)
        assert result is None

    def test_loan_to_value_zero_collateral(self):
        from apps.kernels.portfolio.models import Credit

        obj = MagicMock()
        obj.collateral_value = Decimal("0.00")

        result = Credit.loan_to_value_ratio.fget(obj)
        assert result is None


class TestCreditClean:
    """Tests de Credit.clean."""

    def test_clean_same_lender_borrower(self):
        from apps.kernels.portfolio.models import Credit

        obj = MagicMock()
        obj.lender_party_id = 1
        obj.borrower_party_id = 1
        # Need to mock parent clean
        obj.principal_amount = Decimal("100.00")
        obj.interest_amount = Decimal("0.00")
        obj.fee_amount = Decimal("0.00")
        obj.penalty_amount = Decimal("0.00")
        obj.allocated_amount = Decimal("0.00")
        obj.issue_date = date.today()
        obj.due_date = date.today() + timedelta(days=30)
        type(obj).total_amount = PropertyMock(return_value=Decimal("100.00"))

        with patch("apps.kernels.portfolio.models.Obligation.clean"):
            with pytest.raises(ValidationError) as exc_info:
                Credit.clean(obj)
            assert "borrower_party" in exc_info.value.message_dict


class TestPaymentAllocationClean:
    """Tests de PaymentAllocation.clean."""

    def test_clean_components_mismatch(self):
        from apps.kernels.portfolio.models import PaymentAllocation

        obj = MagicMock()
        obj.principal_applied = Decimal("50.00")
        obj.interest_applied = Decimal("10.00")
        obj.fee_applied = Decimal("5.00")
        obj.penalty_applied = Decimal("5.00")
        obj.allocated_amount = Decimal("100.00")  # != 70

        with patch("django.db.models.Model.clean"):
            with pytest.raises(ValidationError) as exc_info:
                PaymentAllocation.clean(obj)
            assert "allocated_amount" in exc_info.value.message_dict

    def test_clean_components_match(self):
        from apps.kernels.portfolio.models import PaymentAllocation

        obj = MagicMock()
        obj.principal_applied = Decimal("50.00")
        obj.interest_applied = Decimal("10.00")
        obj.fee_applied = Decimal("5.00")
        obj.penalty_applied = Decimal("5.00")
        obj.allocated_amount = Decimal("70.00")

        with patch("django.db.models.Model.clean"):
            PaymentAllocation.clean(obj)  # Should not raise

    def test_clean_all_zero_components(self):
        """When all components are zero, skip component check."""
        from apps.kernels.portfolio.models import PaymentAllocation

        obj = MagicMock()
        obj.principal_applied = Decimal("0.00")
        obj.interest_applied = Decimal("0.00")
        obj.fee_applied = Decimal("0.00")
        obj.penalty_applied = Decimal("0.00")
        obj.allocated_amount = Decimal("50.00")

        with patch("django.db.models.Model.clean"):
            PaymentAllocation.clean(obj)  # Should not raise - sum is 0


class TestModelStrMethods:
    """Tests de __str__ methods."""

    def test_obligation_str(self):
        from apps.kernels.portfolio.models import Obligation

        obj = MagicMock()
        obj.obligation_type = "RECEIVABLE"
        obj.obligation_id = "abc-123"
        obj.party = "Test Party"

        result = Obligation.__str__(obj)
        assert "RECEIVABLE" in result
        assert "abc-123" in result

    def test_receivable_str_with_invoice(self):
        from apps.kernels.portfolio.models import Receivable

        obj = MagicMock()
        obj.invoice_number = "FAC-001"
        obj.party = "Client A"
        obj.currency = "NIO"
        type(obj).outstanding_amount = PropertyMock(return_value=Decimal("500.00"))

        result = Receivable.__str__(obj)
        assert "CxC" in result
        assert "FAC-001" in result

    def test_receivable_str_no_invoice(self):
        from apps.kernels.portfolio.models import Receivable

        obj = MagicMock()
        obj.invoice_number = ""
        obj.party = "Client A"
        obj.currency = "NIO"
        type(obj).outstanding_amount = PropertyMock(return_value=Decimal("500.00"))

        result = Receivable.__str__(obj)
        assert "CxC" in result

    def test_payable_str_with_invoice(self):
        from apps.kernels.portfolio.models import Payable

        obj = MagicMock()
        obj.supplier_invoice_number = "PROV-001"
        obj.party = "Supplier A"
        obj.currency = "USD"
        type(obj).outstanding_amount = PropertyMock(return_value=Decimal("2000.00"))

        result = Payable.__str__(obj)
        assert "CxP" in result
        assert "PROV-001" in result

    def test_payable_str_no_invoice(self):
        from apps.kernels.portfolio.models import Payable

        obj = MagicMock()
        obj.supplier_invoice_number = ""
        obj.party = "Supplier A"
        obj.currency = "USD"
        type(obj).outstanding_amount = PropertyMock(return_value=Decimal("2000.00"))

        result = Payable.__str__(obj)
        assert "CxP" in result

    def test_credit_str(self):
        from apps.kernels.portfolio.models import Credit

        obj = MagicMock()
        obj.contract_number = "CR-001"
        obj.obligation_id = "uuid-here"
        obj.borrower_party = "Borrower X"
        obj.currency = "NIO"
        type(obj).outstanding_amount = PropertyMock(return_value=Decimal("50000.00"))

        result = Credit.__str__(obj)
        assert "Credit" in result
        assert "CR-001" in result

    def test_credit_str_no_contract(self):
        from apps.kernels.portfolio.models import Credit

        obj = MagicMock()
        obj.contract_number = ""
        obj.obligation_id = "uuid-here"
        obj.borrower_party = "Borrower X"
        obj.currency = "NIO"
        type(obj).outstanding_amount = PropertyMock(return_value=Decimal("50000.00"))

        result = Credit.__str__(obj)
        assert "Credit" in result
        assert "uuid-here" in result

    def test_payment_allocation_str(self):
        from apps.kernels.portfolio.models import PaymentAllocation

        obj = MagicMock()
        obj.allocation_id = "alloc-001"
        obj.allocated_amount = Decimal("500.00")
        obj.currency = "NIO"

        result = PaymentAllocation.__str__(obj)
        assert "Allocation" in result
        assert "alloc-001" in result

    def test_interest_accrual_str(self):
        from apps.kernels.portfolio.models import InterestAccrual

        obj = MagicMock()
        obj.accrual_date = date(2026, 5, 1)
        obj.accrued_interest = Decimal("125.50")
        obj.credit = "Credit X"

        result = InterestAccrual.__str__(obj)
        assert "Interest" in result

    def test_portfolio_settings_str(self):
        from apps.kernels.portfolio.models import PortfolioSettings

        obj = MagicMock()
        obj.company = "Company A"

        result = PortfolioSettings.__str__(obj)
        assert "Portfolio Settings" in result


class TestObligationFieldDefaults:
    """Tests para asegurar cobertura de los campos con defaults en Obligation."""

    def test_model_field_defaults(self):
        """Importar y verificar que los modelos tienen los defaults correctos."""
        from apps.kernels.portfolio.models import (
            Obligation,
            Receivable,
            Payable,
            Credit,
            PaymentAllocation,
            InterestAccrual,
            PortfolioSettings,
            ObligationType,
            ObligationStatus,
            AccountingStatus,
            CreditType,
            CreditStatus,
            InterestCalculationMethod,
            PaymentFrequency,
            AllocationStatus,
        )

        # Verify TextChoices enums have expected values
        assert ObligationType.RECEIVABLE == "RECEIVABLE"
        assert ObligationType.PAYABLE == "PAYABLE"
        assert ObligationType.CREDIT == "CREDIT"
        assert ObligationType.LOAN == "LOAN"

        assert ObligationStatus.PENDING == "PENDING"
        assert ObligationStatus.PARTIAL == "PARTIAL"
        assert ObligationStatus.PAID == "PAID"
        assert ObligationStatus.OVERDUE == "OVERDUE"
        assert ObligationStatus.WRITTEN_OFF == "WRITTEN_OFF"
        assert ObligationStatus.DISPUTED == "DISPUTED"
        assert ObligationStatus.RESTRUCTURED == "RESTRUCTURED"
        assert ObligationStatus.CANCELLED == "CANCELLED"

        assert AccountingStatus.PENDING_RULESET == "PENDING_RULESET"
        assert AccountingStatus.PENDING_RULE == "PENDING_RULE"
        assert AccountingStatus.DRAFT_GENERATED == "DRAFT_GENERATED"
        assert AccountingStatus.DRAFT_EXCEPTION == "DRAFT_EXCEPTION"
        assert AccountingStatus.POSTED == "POSTED"

        assert CreditType.WORKING_CAPITAL == "WORKING_CAPITAL"
        assert CreditType.FACTORING == "FACTORING"

        assert CreditStatus.DRAFT == "DRAFT"
        assert CreditStatus.APPROVED == "APPROVED"
        assert CreditStatus.DISBURSED == "DISBURSED"
        assert CreditStatus.ACTIVE == "ACTIVE"
        assert CreditStatus.PAID_OFF == "PAID_OFF"
        assert CreditStatus.DEFAULTED == "DEFAULTED"

        assert InterestCalculationMethod.SIMPLE == "SIMPLE"
        assert InterestCalculationMethod.COMPOUND == "COMPOUND"
        assert InterestCalculationMethod.FLAT == "FLAT"

        assert PaymentFrequency.MONTHLY == "MONTHLY"
        assert PaymentFrequency.QUARTERLY == "QUARTERLY"
        assert PaymentFrequency.ANNUALLY == "ANNUALLY"

        assert AllocationStatus.PENDING == "PENDING"
        assert AllocationStatus.APPLIED == "APPLIED"
        assert AllocationStatus.REVERSED == "REVERSED"

    def test_model_meta_via_internal(self):
        """Tests _meta attributes of Django models."""
        from apps.kernels.portfolio.models import (
            Receivable,
            Payable,
            Credit,
            PaymentAllocation,
            InterestAccrual,
            PortfolioSettings,
        )

        assert Receivable._meta.db_table == "portfolio_receivable"
        assert Payable._meta.db_table == "portfolio_payable"
        assert Credit._meta.db_table == "portfolio_credit"
        assert PaymentAllocation._meta.db_table == "portfolio_payment_allocation"
        assert InterestAccrual._meta.db_table == "portfolio_interest_accrual"
        assert PortfolioSettings._meta.db_table == "portfolio_settings"

    def test_model_ordering(self):
        """Tests ordering configuration."""
        from apps.kernels.portfolio.models import (
            PaymentAllocation,
            InterestAccrual,
        )

        assert PaymentAllocation._meta.ordering == ["-allocation_date", "-created_at"]
        assert InterestAccrual._meta.ordering == ["-accrual_date"]


class TestObligationSaveMethod:
    """Tests de Obligation.save que llama update_aging antes de super().save."""

    def test_save_calls_update_aging(self):
        """save() debe llamar update_aging y luego super().save."""
        from apps.kernels.portfolio.models import Obligation

        obj = MagicMock()
        obj.calculate_days_overdue = MagicMock(return_value=0)
        obj.calculate_aging_bucket = MagicMock(return_value="CURRENT")
        obj.status = "PENDING"
        type(obj).is_overdue = PropertyMock(return_value=False)

        with patch("django.db.models.Model.save") as mock_super_save:
            Obligation.save(obj)
            mock_super_save.assert_called_once()
            assert obj.days_overdue == 0
            assert obj.aging_bucket == "CURRENT"


class TestObligationAgingBucketBoundary:
    """Tests de boundary values para aging buckets."""

    def _call_bucket(self, days_overdue):
        from apps.kernels.portfolio.models import Obligation

        obj = MagicMock()
        obj.calculate_days_overdue = MagicMock(return_value=days_overdue)
        return Obligation.calculate_aging_bucket(obj)

    def test_boundary_30(self):
        assert self._call_bucket(30) == "0-30"

    def test_boundary_31(self):
        assert self._call_bucket(31) == "31-60"

    def test_boundary_60(self):
        assert self._call_bucket(60) == "31-60"

    def test_boundary_61(self):
        assert self._call_bucket(61) == "61-90"

    def test_boundary_90(self):
        assert self._call_bucket(90) == "61-90"

    def test_boundary_91(self):
        assert self._call_bucket(91) == "91-120"

    def test_boundary_120(self):
        assert self._call_bucket(120) == "91-120"

    def test_boundary_121(self):
        assert self._call_bucket(121) == "120+"

    def test_boundary_1(self):
        assert self._call_bucket(1) == "0-30"


class TestCreditCleanValid:
    """Tests de Credit.clean cuando lender != borrower (válido)."""

    def test_clean_different_parties_passes(self):
        from apps.kernels.portfolio.models import Credit

        obj = MagicMock()
        obj.lender_party_id = 1
        obj.borrower_party_id = 2
        obj.principal_amount = Decimal("100.00")
        obj.interest_amount = Decimal("0.00")
        obj.fee_amount = Decimal("0.00")
        obj.penalty_amount = Decimal("0.00")
        obj.allocated_amount = Decimal("0.00")
        obj.issue_date = date.today()
        obj.due_date = date.today() + timedelta(days=30)
        type(obj).total_amount = PropertyMock(return_value=Decimal("100.00"))

        with patch("apps.kernels.portfolio.models.Obligation.clean"):
            # Should not raise
            Credit.clean(obj)


class TestObligationUpdateAgingNotOverdue:
    """Tests de update_aging cuando no está overdue."""

    def test_update_aging_not_overdue_keeps_pending(self):
        from apps.kernels.portfolio.models import Obligation, ObligationStatus

        obj = MagicMock()
        obj.status = ObligationStatus.PENDING
        obj.calculate_days_overdue = MagicMock(return_value=0)
        obj.calculate_aging_bucket = MagicMock(return_value="CURRENT")
        type(obj).is_overdue = PropertyMock(return_value=False)

        Obligation.update_aging(obj)

        assert obj.days_overdue == 0
        assert obj.aging_bucket == "CURRENT"
        # Status should remain PENDING
        assert obj.status == ObligationStatus.PENDING
