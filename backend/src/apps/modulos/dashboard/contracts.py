from __future__ import annotations

from typing import Any

from django.utils import timezone

CONTRACT_VERSION = "3.0.0"


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
    if warnings:
        meta["warnings"] = list(warnings)
    if meta_extra:
        meta.update(meta_extra)
    return {
        "meta": meta,
        "summary": summary,
        "results": results,
        "pagination": pagination or {},
    }
