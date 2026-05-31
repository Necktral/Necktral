"""
Portfolio Kernel - Unit Tests (Gate 1→2)

Tests de contrato para el kernel financiero.
Pueden fallar sin PostgreSQL real — validación completa es Frente 2.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestPortfolioEndpointContracts:
    """Verificar que los endpoints portfolio están registrados."""

    def test_urls_registered(self):
        """Todas las URLs del kernel están registradas."""
        from apps.kernels.portfolio.urls import urlpatterns

        assert len(urlpatterns) > 0

    def test_portfolio_models_importable(self):
        """Modelos críticos son importables."""
        from apps.kernels.portfolio.models import (
            Obligation,
            Receivable,
            Payable,
            Credit,
            PaymentAllocation,
            InterestAccrual,
        )
        assert Obligation is not None
        assert Receivable is not None
        assert Payable is not None
        assert Credit is not None


class TestPortfolioContracts:
    """Tests de contratos de negocio portfolio."""

    def test_obligation_status_choices(self):
        """ObligationStatus tiene los estados esperados."""
        from apps.kernels.portfolio.models import ObligationStatus

        expected = {"PENDING", "PARTIAL", "PAID", "OVERDUE", "WRITTEN_OFF", "DISPUTED", "RESTRUCTURED", "CANCELLED"}
        actual = {choice[0] for choice in ObligationStatus.choices}
        assert expected == actual

    def test_obligation_type_choices(self):
        """ObligationType tiene los tipos esperados."""
        from apps.kernels.portfolio.models import ObligationType

        expected = {"RECEIVABLE", "PAYABLE", "CREDIT", "LOAN"}
        actual = {choice[0] for choice in ObligationType.choices}
        assert expected == actual
