"""
Accounting Kernel - Unit Tests (Gate 1→2)

Tests de contrato para el kernel contable.
Pueden fallar sin PostgreSQL real — validación completa es Frente 2.
"""
from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestAccountingEndpointContracts:
    """Verificar que los endpoints accounting están registrados correctamente."""

    def test_urls_registered(self):
        """Todas las URLs del kernel están registradas."""
        from apps.kernels.accounting.urls import urlpatterns

        paths = [p.pattern._route if hasattr(p.pattern, '_route') else str(p.pattern) for p in urlpatterns]
        assert "health/" in paths
        assert "journal-drafts/" in paths
        assert "journal-entries/" in paths
        assert "periods/" in paths
        assert "chart-of-accounts/" in paths
        assert "reports/trial-balance/" in paths
        assert "reports/pnl/" in paths
        assert "reports/balance-sheet/" in paths
        assert "fx-rates/" in paths
        assert "consolidation/run/" in paths

    def test_intercompany_urls_registered(self):
        """URLs de intercompany están presentes."""
        from apps.kernels.accounting.urls import urlpatterns

        paths = [str(p.pattern) for p in urlpatterns]
        intercompany_paths = [p for p in paths if "intercompany" in p]
        assert len(intercompany_paths) >= 6  # transactions, confirm, reconcile, dispute, settle, close


class TestAccountingModels:
    """Tests de estructura de modelos accounting."""

    def test_journal_draft_model_exists(self):
        """JournalDraft model importable."""
        from apps.kernels.accounting.models import JournalDraft
        assert JournalDraft is not None

    def test_journal_entry_model_exists(self):
        """JournalEntry model importable."""
        from apps.kernels.accounting.models import JournalEntry
        assert JournalEntry is not None

    def test_economic_event_model_exists(self):
        """EconomicEvent model importable."""
        from apps.kernels.accounting.models import EconomicEvent
        assert EconomicEvent is not None
