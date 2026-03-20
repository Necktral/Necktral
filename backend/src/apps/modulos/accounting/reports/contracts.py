from __future__ import annotations

from typing import Any

from django.utils import timezone

CONTRACT_VERSION = "2.0.0"
LEGACY_PREFIX = "/api/accounting/"


def is_legacy_route(request) -> bool:
    path = str(getattr(request, "path", "") or "")
    return path.startswith(LEGACY_PREFIX)


def _scope_payload(request) -> dict[str, int | None]:
    company = getattr(request, "company", None)
    branch = getattr(request, "branch", None)
    return {
        "company_id": int(company.id) if company is not None else None,
        "branch_id": int(branch.id) if branch is not None else None,
    }


def build_envelope(
    *,
    request,
    report_code: str,
    summary: dict[str, Any],
    results: Any,
    pagination: dict[str, int] | None = None,
    warnings: list[str] | None = None,
    meta_extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    meta: dict[str, Any] = {
        "contract_version": CONTRACT_VERSION,
        "report_code": str(report_code),
        "generated_at": timezone.now().isoformat(),
        "scope": _scope_payload(request),
    }
    if meta_extra:
        meta.update(meta_extra)
    if warnings:
        meta["warnings"] = list(warnings)
    return {
        "meta": meta,
        "summary": summary,
        "results": results,
        "pagination": pagination or {},
    }

