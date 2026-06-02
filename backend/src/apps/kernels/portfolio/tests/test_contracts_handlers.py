"""
Portfolio Kernel - Contracts & Handlers Tests for Coverage

Tests unitarios para contracts.py y handlers.py.
Mock-based — validación completa con DB real es Frente 2 (Codex).
"""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


# ============================================================================
# CONTRACTS TESTS
# ============================================================================


class TestValidateEventPayload:
    """Tests de validate_event_payload."""

    def test_valid_receivable_created(self):
        from apps.kernels.portfolio.contracts import validate_event_payload

        payload = {
            "receivable_id": "uuid-1",
            "party_id": 1,
            "principal_amount": "1000.00",
            "currency": "NIO",
            "issue_date": "2026-06-01",
            "due_date": "2026-07-01",
            "reference_type": "BILLING",
            "reference_id": 10,
        }
        is_valid, error = validate_event_payload("ReceivableCreated", payload)
        assert is_valid is True
        assert error == ""

    def test_invalid_receivable_missing_fields(self):
        from apps.kernels.portfolio.contracts import validate_event_payload

        payload = {
            "receivable_id": "uuid-1",
            "party_id": 1,
            # Missing other required fields
        }
        is_valid, error = validate_event_payload("ReceivableCreated", payload)
        assert is_valid is False
        assert "Missing required fields" in error

    def test_unknown_event_type_passes(self):
        from apps.kernels.portfolio.contracts import validate_event_payload

        is_valid, error = validate_event_payload("UnknownEventType", {})
        assert is_valid is True
        assert error == ""

    def test_valid_credit_disbursed(self):
        from apps.kernels.portfolio.contracts import validate_event_payload

        payload = {
            "credit_id": "uuid-c1",
            "disbursed_amount": "5000.00",
            "total_disbursed": "5000.00",
            "disbursement_date": "2026-06-01",
            "borrower_party_id": 2,
            "lender_party_id": 1,
        }
        is_valid, error = validate_event_payload("CreditDisbursed", payload)
        assert is_valid is True

    def test_valid_interest_accrued(self):
        from apps.kernels.portfolio.contracts import validate_event_payload

        payload = {
            "credit_id": "uuid-c1",
            "accrual_id": "acc-1",
            "accrued_interest": "100.00",
            "principal_balance": "8000.00",
            "accrual_date": "2026-06-30",
            "borrower_party_id": 2,
        }
        is_valid, error = validate_event_payload("InterestAccrued", payload)
        assert is_valid is True

    def test_valid_payable_created(self):
        from apps.kernels.portfolio.contracts import validate_event_payload

        payload = {
            "payable_id": "uuid-p1",
            "party_id": 3,
            "principal_amount": "2000.00",
            "currency": "NIO",
            "issue_date": "2026-06-01",
            "due_date": "2026-07-01",
            "reference_type": "PROCUREMENT",
            "reference_id": 5,
        }
        is_valid, error = validate_event_payload("PayableCreated", payload)
        assert is_valid is True

    def test_valid_receivable_allocated(self):
        from apps.kernels.portfolio.contracts import validate_event_payload

        payload = {
            "allocation_id": "alloc-1",
            "payment_id": "pay-1",
            "receivable_id": "uuid-r1",
            "allocated_amount": "500.00",
            "principal_applied": "500.00",
            "party_id": 1,
        }
        is_valid, error = validate_event_payload("ReceivableAllocated", payload)
        assert is_valid is True


class TestPortfolioEconomicEventsContract:
    """Tests de PORTFOLIO_ECONOMIC_EVENTS."""

    def test_events_set_contains_required(self):
        from apps.kernels.portfolio.contracts import PORTFOLIO_ECONOMIC_EVENTS

        assert ("PORTFOLIO", "ReceivableCreated") in PORTFOLIO_ECONOMIC_EVENTS
        assert ("PORTFOLIO", "PayableCreated") in PORTFOLIO_ECONOMIC_EVENTS
        assert ("PORTFOLIO", "CreditApproved") in PORTFOLIO_ECONOMIC_EVENTS
        assert ("PORTFOLIO", "InterestAccrued") in PORTFOLIO_ECONOMIC_EVENTS


# ============================================================================
# HANDLERS TESTS
# ============================================================================


class TestExtractEventData:
    """Tests de _extract_event_data."""

    def test_dict_payload_with_data(self):
        from apps.kernels.portfolio.handlers import _extract_event_data

        event = MagicMock()
        event.payload = {"data": {"key": "value"}}

        result = _extract_event_data(event)
        assert result == {"key": "value"}

    def test_dict_payload_without_data_key(self):
        from apps.kernels.portfolio.handlers import _extract_event_data

        event = MagicMock()
        event.payload = {"key": "value"}

        result = _extract_event_data(event)
        assert result == {"key": "value"}

    def test_non_dict_payload(self):
        from apps.kernels.portfolio.handlers import _extract_event_data

        event = MagicMock()
        event.payload = "not a dict"

        result = _extract_event_data(event)
        assert result == {}


class TestSafeDecimal:
    """Tests de _safe_decimal."""

    def test_valid_string(self):
        from apps.kernels.portfolio.handlers import _safe_decimal

        result = _safe_decimal("123.45")
        assert result == Decimal("123.45")

    def test_valid_int(self):
        from apps.kernels.portfolio.handlers import _safe_decimal

        result = _safe_decimal(100)
        assert result == Decimal("100")

    def test_none_value(self):
        from apps.kernels.portfolio.handlers import _safe_decimal

        result = _safe_decimal(None)
        assert result is None

    def test_invalid_value(self):
        from apps.kernels.portfolio.handlers import _safe_decimal

        result = _safe_decimal("not_a_number")
        assert result is None

    def test_empty_string(self):
        from apps.kernels.portfolio.handlers import _safe_decimal

        result = _safe_decimal("")
        assert result is None


class TestDispatchPortfolioEvent:
    """Tests de dispatch_portfolio_event."""

    def test_dispatch_known_event(self):
        from apps.kernels.portfolio.handlers import dispatch_portfolio_event

        event = MagicMock()
        event.source_module = "PROCUREMENT"
        event.event_type = "ProcurementDocumentPosted"

        with patch("apps.kernels.portfolio.handlers.handle_procurement_document_posted") as mock_handler:
            mock_handler.return_value = {"ok": True}
            result = dispatch_portfolio_event(event)
            assert result == {"ok": True}
            mock_handler.assert_called_once_with(event)

    def test_dispatch_billing_event(self):
        from apps.kernels.portfolio.handlers import dispatch_portfolio_event

        event = MagicMock()
        event.source_module = "BILLING"
        event.event_type = "DocumentIssued"

        with patch("apps.kernels.portfolio.handlers.handle_billing_document_issued") as mock_handler:
            mock_handler.return_value = {"ok": True}
            result = dispatch_portfolio_event(event)
            assert result == {"ok": True}

    def test_dispatch_unknown_event(self):
        from apps.kernels.portfolio.handlers import dispatch_portfolio_event

        event = MagicMock()
        event.source_module = "UNKNOWN"
        event.event_type = "Something"

        result = dispatch_portfolio_event(event)
        assert result is None


class TestMarkInboxHelpers:
    """Tests de helpers para InboxEvent."""

    def test_mark_inbox_processed(self):
        from apps.kernels.portfolio.handlers import _mark_inbox_processed

        inbox = MagicMock()
        _mark_inbox_processed(inbox, result_id="res-1")
        inbox.save.assert_called_once()

    def test_mark_inbox_skipped(self):
        from apps.kernels.portfolio.handlers import _mark_inbox_skipped

        inbox = MagicMock()
        _mark_inbox_skipped(inbox, reason="not applicable")
        inbox.save.assert_called_once()
        assert "SKIPPED" in inbox.last_error

    def test_mark_inbox_error(self):
        from apps.kernels.portfolio.handlers import _mark_inbox_error

        inbox = MagicMock()
        _mark_inbox_error(inbox, error="something went wrong")
        inbox.save.assert_called_once()


class TestHandleProcurementDocumentPosted:
    """Tests de handle_procurement_document_posted."""

    @patch("apps.kernels.portfolio.handlers.create_payable")
    @patch("apps.kernels.portfolio.handlers.Party")
    @patch("apps.kernels.portfolio.handlers.PortfolioSettings")
    @patch("apps.kernels.portfolio.handlers.create_or_get_inbox_event")
    def test_already_processed(self, mock_inbox, mock_settings, mock_party, mock_create):
        from apps.kernels.portfolio.handlers import handle_procurement_document_posted

        inbox = MagicMock()
        inbox.status = "PROCESSED"
        mock_inbox.return_value = (inbox, False)

        event = MagicMock()
        result = handle_procurement_document_posted(event)
        assert result["already_processed"] is True
        mock_create.assert_not_called()

    @patch("apps.kernels.portfolio.handlers._mark_inbox_skipped")
    @patch("apps.kernels.portfolio.handlers._extract_event_data")
    @patch("apps.kernels.portfolio.handlers.PortfolioSettings")
    @patch("apps.kernels.portfolio.handlers.create_or_get_inbox_event")
    def test_sync_disabled(self, mock_inbox, mock_settings, mock_extract, mock_skip):
        from apps.kernels.portfolio.handlers import handle_procurement_document_posted

        inbox = MagicMock()
        inbox.status = "RECEIVED"
        mock_inbox.return_value = (inbox, True)

        settings = MagicMock()
        settings.sync_with_procurement = False
        mock_settings.get_or_create_for_company.return_value = settings
        mock_extract.return_value = {}

        event = MagicMock()
        event.company = MagicMock()
        event.branch = MagicMock()

        result = handle_procurement_document_posted(event)
        assert result["skipped"] is True
        assert "sync_with_procurement" in result["reason"]

    @patch("apps.kernels.portfolio.handlers._mark_inbox_skipped")
    @patch("apps.kernels.portfolio.handlers._extract_event_data")
    @patch("apps.kernels.portfolio.handlers.PortfolioSettings")
    @patch("apps.kernels.portfolio.handlers.create_or_get_inbox_event")
    def test_no_supplier_party_id(self, mock_inbox, mock_settings, mock_extract, mock_skip):
        from apps.kernels.portfolio.handlers import handle_procurement_document_posted

        inbox = MagicMock()
        inbox.status = "RECEIVED"
        mock_inbox.return_value = (inbox, True)

        settings = MagicMock()
        settings.sync_with_procurement = True
        mock_settings.get_or_create_for_company.return_value = settings
        mock_extract.return_value = {"total": "1000"}

        event = MagicMock()
        event.company = MagicMock()
        event.branch = MagicMock()

        result = handle_procurement_document_posted(event)
        assert result["skipped"] is True
        assert "no supplier_party_id" in result["reason"]

    @patch("apps.kernels.portfolio.handlers._mark_inbox_error")
    @patch("apps.kernels.portfolio.handlers._extract_event_data")
    @patch("apps.kernels.portfolio.handlers.PortfolioSettings")
    @patch("apps.kernels.portfolio.handlers.create_or_get_inbox_event")
    def test_invalid_total(self, mock_inbox, mock_settings, mock_extract, mock_error):
        from apps.kernels.portfolio.handlers import handle_procurement_document_posted

        inbox = MagicMock()
        inbox.status = "RECEIVED"
        mock_inbox.return_value = (inbox, True)

        settings = MagicMock()
        settings.sync_with_procurement = True
        mock_settings.get_or_create_for_company.return_value = settings
        mock_extract.return_value = {"supplier_party_id": 1, "total": "invalid"}

        event = MagicMock()
        event.company = MagicMock()
        event.branch = MagicMock()

        result = handle_procurement_document_posted(event)
        assert result["ok"] is False
        assert "invalid total" in result["error"]

    @patch("apps.kernels.portfolio.handlers._mark_inbox_error")
    @patch("apps.kernels.portfolio.handlers.Party")
    @patch("apps.kernels.portfolio.handlers._extract_event_data")
    @patch("apps.kernels.portfolio.handlers.PortfolioSettings")
    @patch("apps.kernels.portfolio.handlers.create_or_get_inbox_event")
    def test_party_not_found(self, mock_inbox, mock_settings, mock_extract, mock_party, mock_error):
        from apps.kernels.portfolio.handlers import handle_procurement_document_posted

        inbox = MagicMock()
        inbox.status = "RECEIVED"
        mock_inbox.return_value = (inbox, True)

        settings = MagicMock()
        settings.sync_with_procurement = True
        mock_settings.get_or_create_for_company.return_value = settings
        mock_extract.return_value = {"supplier_party_id": 999, "total": "1000"}

        mock_party.objects.filter.return_value.first.return_value = None

        event = MagicMock()
        event.company = MagicMock()
        event.branch = MagicMock()

        result = handle_procurement_document_posted(event)
        assert result["ok"] is False
        assert "not found" in result["error"]


class TestHandleBillingDocumentIssued:
    """Tests de handle_billing_document_issued."""

    @patch("apps.kernels.portfolio.handlers.create_receivable")
    @patch("apps.kernels.portfolio.handlers.Party")
    @patch("apps.kernels.portfolio.handlers.PortfolioSettings")
    @patch("apps.kernels.portfolio.handlers.create_or_get_inbox_event")
    def test_already_processed(self, mock_inbox, mock_settings, mock_party, mock_create):
        from apps.kernels.portfolio.handlers import handle_billing_document_issued

        inbox = MagicMock()
        inbox.status = "PROCESSED"
        mock_inbox.return_value = (inbox, False)

        event = MagicMock()
        result = handle_billing_document_issued(event)
        assert result["already_processed"] is True

    @patch("apps.kernels.portfolio.handlers._mark_inbox_skipped")
    @patch("apps.kernels.portfolio.handlers._extract_event_data")
    @patch("apps.kernels.portfolio.handlers.PortfolioSettings")
    @patch("apps.kernels.portfolio.handlers.create_or_get_inbox_event")
    def test_sync_disabled(self, mock_inbox, mock_settings, mock_extract, mock_skip):
        from apps.kernels.portfolio.handlers import handle_billing_document_issued

        inbox = MagicMock()
        inbox.status = "RECEIVED"
        mock_inbox.return_value = (inbox, True)

        settings = MagicMock()
        settings.sync_with_billing = False
        mock_settings.get_or_create_for_company.return_value = settings
        mock_extract.return_value = {}

        event = MagicMock()
        event.company = MagicMock()
        event.branch = MagicMock()

        result = handle_billing_document_issued(event)
        assert result["skipped"] is True
        assert "sync_with_billing" in result["reason"]

    @patch("apps.kernels.portfolio.handlers._mark_inbox_skipped")
    @patch("apps.kernels.portfolio.handlers._extract_event_data")
    @patch("apps.kernels.portfolio.handlers.PortfolioSettings")
    @patch("apps.kernels.portfolio.handlers.create_or_get_inbox_event")
    def test_cash_sale_skipped(self, mock_inbox, mock_settings, mock_extract, mock_skip):
        from apps.kernels.portfolio.handlers import handle_billing_document_issued

        inbox = MagicMock()
        inbox.status = "RECEIVED"
        mock_inbox.return_value = (inbox, True)

        settings = MagicMock()
        settings.sync_with_billing = True
        mock_settings.get_or_create_for_company.return_value = settings
        mock_extract.return_value = {"payment_method": "CASH", "total": "500"}

        event = MagicMock()
        event.company = MagicMock()
        event.branch = MagicMock()

        result = handle_billing_document_issued(event)
        assert result["skipped"] is True
        assert "cash sale" in result["reason"]

    @patch("apps.kernels.portfolio.handlers._mark_inbox_skipped")
    @patch("apps.kernels.portfolio.handlers._extract_event_data")
    @patch("apps.kernels.portfolio.handlers.PortfolioSettings")
    @patch("apps.kernels.portfolio.handlers.create_or_get_inbox_event")
    def test_no_customer_party(self, mock_inbox, mock_settings, mock_extract, mock_skip):
        from apps.kernels.portfolio.handlers import handle_billing_document_issued

        inbox = MagicMock()
        inbox.status = "RECEIVED"
        mock_inbox.return_value = (inbox, True)

        settings = MagicMock()
        settings.sync_with_billing = True
        mock_settings.get_or_create_for_company.return_value = settings
        mock_extract.return_value = {"payment_method": "CREDIT", "total": "500"}

        event = MagicMock()
        event.company = MagicMock()
        event.branch = MagicMock()

        result = handle_billing_document_issued(event)
        assert result["skipped"] is True
        assert "no customer_party_id" in result["reason"]

    @patch("apps.kernels.portfolio.handlers._mark_inbox_error")
    @patch("apps.kernels.portfolio.handlers._extract_event_data")
    @patch("apps.kernels.portfolio.handlers.PortfolioSettings")
    @patch("apps.kernels.portfolio.handlers.create_or_get_inbox_event")
    def test_invalid_total(self, mock_inbox, mock_settings, mock_extract, mock_error):
        from apps.kernels.portfolio.handlers import handle_billing_document_issued

        inbox = MagicMock()
        inbox.status = "RECEIVED"
        mock_inbox.return_value = (inbox, True)

        settings = MagicMock()
        settings.sync_with_billing = True
        mock_settings.get_or_create_for_company.return_value = settings
        mock_extract.return_value = {
            "payment_method": "CREDIT",
            "customer_party_id": 5,
            "total": "invalid",
        }

        event = MagicMock()
        event.company = MagicMock()
        event.branch = MagicMock()

        result = handle_billing_document_issued(event)
        assert result["ok"] is False

    @patch("apps.kernels.portfolio.handlers._mark_inbox_error")
    @patch("apps.kernels.portfolio.handlers.Party")
    @patch("apps.kernels.portfolio.handlers._extract_event_data")
    @patch("apps.kernels.portfolio.handlers.PortfolioSettings")
    @patch("apps.kernels.portfolio.handlers.create_or_get_inbox_event")
    def test_customer_not_found(self, mock_inbox, mock_settings, mock_extract, mock_party, mock_error):
        from apps.kernels.portfolio.handlers import handle_billing_document_issued

        inbox = MagicMock()
        inbox.status = "RECEIVED"
        mock_inbox.return_value = (inbox, True)

        settings = MagicMock()
        settings.sync_with_billing = True
        mock_settings.get_or_create_for_company.return_value = settings
        mock_extract.return_value = {
            "payment_method": "CREDIT",
            "customer_party_id": 999,
            "total": "1000",
        }

        mock_party.objects.filter.return_value.first.return_value = None

        event = MagicMock()
        event.company = MagicMock()
        event.branch = MagicMock()

        result = handle_billing_document_issued(event)
        assert result["ok"] is False
        assert "not found" in result["error"]


class TestHandleProcurementSuccess:
    """Tests de handle_procurement_document_posted con éxito."""

    @patch("apps.kernels.portfolio.handlers.transaction")
    @patch("apps.kernels.portfolio.handlers._mark_inbox_processed")
    @patch("apps.kernels.portfolio.handlers.create_payable")
    @patch("apps.kernels.portfolio.handlers.Party")
    @patch("apps.kernels.portfolio.handlers._extract_event_data")
    @patch("apps.kernels.portfolio.handlers.PortfolioSettings")
    @patch("apps.kernels.portfolio.handlers.create_or_get_inbox_event")
    def test_success_creates_payable(self, mock_inbox, mock_settings, mock_extract, mock_party, mock_create, mock_mark, mock_tx):
        from apps.kernels.portfolio.handlers import handle_procurement_document_posted

        inbox = MagicMock()
        inbox.status = "RECEIVED"
        mock_inbox.return_value = (inbox, True)

        settings = MagicMock()
        settings.sync_with_procurement = True
        settings.settings_json = {"default_payable_credit_days": 45}
        mock_settings.get_or_create_for_company.return_value = settings

        mock_extract.return_value = {
            "supplier_party_id": 10,
            "total": "5000.00",
            "currency": "NIO",
            "doc_id": 42,
            "supplier_ref": "PROV-100",
            "series": "CP",
            "number": "00042",
        }

        party_obj = MagicMock()
        party_obj.id = 10
        mock_party.objects.filter.return_value.first.return_value = party_obj

        payable_obj = MagicMock()
        payable_obj.obligation_id = "uuid-payable-1"
        mock_create.return_value = payable_obj

        mock_tx.atomic.return_value.__enter__ = MagicMock()
        mock_tx.atomic.return_value.__exit__ = MagicMock(return_value=False)

        event = MagicMock()
        event.company = MagicMock()
        event.branch = MagicMock()
        event.event_id = "evt-1"

        result = handle_procurement_document_posted(event)
        assert result["ok"] is True
        assert result["payable_id"] == "uuid-payable-1"
        assert result["party_id"] == 10
        mock_create.assert_called_once()

    @patch("apps.kernels.portfolio.handlers._mark_inbox_error")
    @patch("apps.kernels.portfolio.handlers._extract_event_data")
    @patch("apps.kernels.portfolio.handlers.PortfolioSettings")
    @patch("apps.kernels.portfolio.handlers.create_or_get_inbox_event")
    def test_zero_total_amount(self, mock_inbox, mock_settings, mock_extract, mock_error):
        from apps.kernels.portfolio.handlers import handle_procurement_document_posted

        inbox = MagicMock()
        inbox.status = "RECEIVED"
        mock_inbox.return_value = (inbox, True)

        settings = MagicMock()
        settings.sync_with_procurement = True
        mock_settings.get_or_create_for_company.return_value = settings
        mock_extract.return_value = {"supplier_party_id": 1, "total": "0"}

        event = MagicMock()
        event.company = MagicMock()
        event.branch = MagicMock()

        result = handle_procurement_document_posted(event)
        assert result["ok"] is False
        assert "invalid total" in result["error"]


class TestHandleBillingSuccess:
    """Tests de handle_billing_document_issued con éxito."""

    @patch("apps.kernels.portfolio.handlers.transaction")
    @patch("apps.kernels.portfolio.handlers._mark_inbox_processed")
    @patch("apps.kernels.portfolio.handlers.create_receivable")
    @patch("apps.kernels.portfolio.handlers.Party")
    @patch("apps.kernels.portfolio.handlers._extract_event_data")
    @patch("apps.kernels.portfolio.handlers.PortfolioSettings")
    @patch("apps.kernels.portfolio.handlers.create_or_get_inbox_event")
    def test_success_creates_receivable(self, mock_inbox, mock_settings, mock_extract, mock_party, mock_create, mock_mark, mock_tx):
        from apps.kernels.portfolio.handlers import handle_billing_document_issued

        inbox = MagicMock()
        inbox.status = "RECEIVED"
        mock_inbox.return_value = (inbox, True)

        settings = MagicMock()
        settings.sync_with_billing = True
        settings.settings_json = {"default_receivable_credit_days": 30}
        mock_settings.get_or_create_for_company.return_value = settings

        mock_extract.return_value = {
            "payment_method": "CREDIT",
            "customer_party_id": 5,
            "total": "3000.00",
            "currency": "USD",
            "doc_id": 99,
            "series": "FA",
            "number": "00099",
            "is_fiscal": True,
        }

        party_obj = MagicMock()
        party_obj.id = 5
        mock_party.objects.filter.return_value.first.return_value = party_obj

        receivable_obj = MagicMock()
        receivable_obj.obligation_id = "uuid-recv-1"
        mock_create.return_value = receivable_obj

        mock_tx.atomic.return_value.__enter__ = MagicMock()
        mock_tx.atomic.return_value.__exit__ = MagicMock(return_value=False)

        event = MagicMock()
        event.company = MagicMock()
        event.branch = MagicMock()
        event.event_id = "evt-billing-1"

        result = handle_billing_document_issued(event)
        assert result["ok"] is True
        assert result["receivable_id"] == "uuid-recv-1"
        assert result["party_id"] == 5
        mock_create.assert_called_once()

    @patch("apps.kernels.portfolio.handlers._mark_inbox_skipped")
    @patch("apps.kernels.portfolio.handlers._extract_event_data")
    @patch("apps.kernels.portfolio.handlers.PortfolioSettings")
    @patch("apps.kernels.portfolio.handlers.create_or_get_inbox_event")
    def test_card_payment_skipped(self, mock_inbox, mock_settings, mock_extract, mock_skip):
        """CARD payment method should be skipped (cash sale)."""
        from apps.kernels.portfolio.handlers import handle_billing_document_issued

        inbox = MagicMock()
        inbox.status = "RECEIVED"
        mock_inbox.return_value = (inbox, True)

        settings = MagicMock()
        settings.sync_with_billing = True
        mock_settings.get_or_create_for_company.return_value = settings
        mock_extract.return_value = {"payment_method": "CARD", "total": "500"}

        event = MagicMock()
        event.company = MagicMock()
        event.branch = MagicMock()

        result = handle_billing_document_issued(event)
        assert result["skipped"] is True
        assert "cash sale" in result["reason"]

    @patch("apps.kernels.portfolio.handlers._mark_inbox_error")
    @patch("apps.kernels.portfolio.handlers._extract_event_data")
    @patch("apps.kernels.portfolio.handlers.PortfolioSettings")
    @patch("apps.kernels.portfolio.handlers.create_or_get_inbox_event")
    def test_zero_total_billing(self, mock_inbox, mock_settings, mock_extract, mock_error):
        from apps.kernels.portfolio.handlers import handle_billing_document_issued

        inbox = MagicMock()
        inbox.status = "RECEIVED"
        mock_inbox.return_value = (inbox, True)

        settings = MagicMock()
        settings.sync_with_billing = True
        mock_settings.get_or_create_for_company.return_value = settings
        mock_extract.return_value = {
            "payment_method": "CREDIT",
            "customer_party_id": 5,
            "total": "0",
        }

        event = MagicMock()
        event.company = MagicMock()
        event.branch = MagicMock()

        result = handle_billing_document_issued(event)
        assert result["ok"] is False
        assert "invalid total" in result["error"]


class TestAppsConfig:
    """Tests de apps.py."""

    def test_portfolio_config(self):
        from apps.kernels.portfolio.apps import PortfolioConfig

        assert PortfolioConfig.name == "apps.kernels.portfolio"
        assert PortfolioConfig.verbose_name == "Financial Portfolio"
