from __future__ import annotations

from apps.modulos.accounting.services import OPERATIONAL_ACCOUNTING_EVENTS, SUPPORTED_ECONOMIC_EVENTS


def test_supported_economic_events_matrix_v1_is_frozen():
    assert SUPPORTED_ECONOMIC_EVENTS == {
        ("BILLING", "DocumentIssued"),
        ("BILLING", "DocumentVoided"),
        ("INVENTORY", "InventoryMovementPosted"),
        ("INVENTORY", "InventoryAdjusted"),
        ("INVENTORY", "InventoryTransferCompleted"),
        ("PAYMENTS", "CashMovementPosted"),
        ("PAYMENTS", "CashSessionClosed"),
        ("PROCUREMENT", "ProcurementDocumentPosted"),
        ("PROCUREMENT", "ProcurementDocumentVoided"),
    }


def test_operational_accounting_events_matrix_v1_is_frozen():
    assert OPERATIONAL_ACCOUNTING_EVENTS == {
        ("BILLING", "DocumentIssued"),
        ("BILLING", "DocumentVoided"),
        ("INVENTORY", "InventoryMovementPosted"),
        ("INVENTORY", "InventoryAdjusted"),
        ("INVENTORY", "InventoryTransferCompleted"),
        ("PROCUREMENT", "ProcurementDocumentPosted"),
        ("PROCUREMENT", "ProcurementDocumentVoided"),
    }
