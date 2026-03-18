from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


@dataclass(frozen=True)
class SyncRejectError(Exception):
    """
    Rechazo controlado (NO es un crash).
    Se usa para devolver REJECTED con reason_code contractual.

    reason_code: código contractual (ej. INVENTORY_NEGATIVE_STOCK_BLOCKED)
    details: metadata mínima para auditoría / diagnóstico (sin datos sensibles).
    """

    reason_code: str
    details: Mapping[str, Any] | None = None

    def __str__(self) -> str:
        return self.reason_code
