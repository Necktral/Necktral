"""
Payments Kernel - Unit Tests (Gate 1→2)

Tests de contrato para el kernel de pagos.
Pueden fallar sin PostgreSQL real — validación completa es Frente 2.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestPaymentsEndpointContracts:
    """Verificar que los endpoints payments están registrados."""

    def test_urls_registered(self):
        """Todas las URLs del kernel están registradas."""
        from apps.kernels.payments.urls import urlpatterns

        paths = [p.pattern._route if hasattr(p.pattern, '_route') else str(p.pattern) for p in urlpatterns]
        assert "health/" in paths
        assert "intents/" in paths
        assert "cash-sessions/" in paths
        assert "cash-sessions/open/" in paths

    def test_payment_intent_url_has_reverse_capture(self):
        """Reverse-capture endpoint existe."""
        from apps.kernels.payments.urls import urlpatterns

        paths = [str(p.pattern) for p in urlpatterns]
        reverse_paths = [p for p in paths if "reverse-capture" in p]
        assert len(reverse_paths) == 1


class TestPaymentsModels:
    """Tests de estructura de modelos payments."""

    def test_payment_intent_model_exists(self):
        """PaymentIntent model importable."""
        from apps.kernels.payments.models import PaymentIntent
        assert PaymentIntent is not None

    def test_cash_session_model_exists(self):
        """CashSession model importable."""
        from apps.kernels.payments.models import CashSession
        assert CashSession is not None

    def test_cash_movement_model_exists(self):
        """CashMovement model importable."""
        from apps.kernels.payments.models import CashMovement
        assert CashMovement is not None
