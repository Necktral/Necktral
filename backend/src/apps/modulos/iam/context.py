from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class RequestContext:
    request_id: str
    company_id: Optional[int]
    branch_id: Optional[int]
    data_company_id: Optional[int]
    data_branch_id: Optional[int]


def attach_request_context(
    request,
    *,
    company=None,
    branch=None,
    data_company=None,
    data_branch=None,
) -> None:
    """Adjunta contexto operativo en request.ctx.

    Contrato:
    - No reemplaza request.company/request.branch (ya usados en otras capas).
    - Usa request.request_id si existe; si no, lo deja en blanco.
    """

    request_id = getattr(request, "request_id", "") or ""

    ctx = RequestContext(
        request_id=request_id,
        company_id=getattr(company, "id", None),
        branch_id=getattr(branch, "id", None),
        data_company_id=getattr(data_company, "id", None),
        data_branch_id=getattr(data_branch, "id", None),
    )

    setattr(request, "ctx", ctx)

    raw = getattr(request, "_request", None)
    if raw is not None:
        setattr(raw, "ctx", ctx)
