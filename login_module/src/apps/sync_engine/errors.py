from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SyncRejectError(Exception):
    """Error controlado para rechazar un comando con un reason estable.

    Se usa dentro de handlers para rechazar payloads inválidos o reglas de negocio
    sin provocar SYNC_INTERNAL_ERROR.
    """

    reason: str
    details: dict

    def __str__(self) -> str:  # pragma: no cover
        return f"{self.reason}: {self.details}"
