from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from rest_framework.exceptions import AuthenticationFailed, NotAuthenticated


def utc_timestamp_iso() -> str:
    # ISO-8601 en UTC; incluye microsegundos cuando aplica
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _as_object(details: Any) -> dict:
    if details is None:
        return {}
    if isinstance(details, dict):
        return details
    if isinstance(details, list):
        return {"non_field_errors": [str(x) for x in details]}
    return {"detail": str(details)}


def _validation_details(details: Any) -> dict:
    # DRF serializer errors suelen ser dict(field -> [messages]) o list
    if isinstance(details, dict):
        if "detail" in details and len(details.keys()) == 1:
            # mensaje simple
            return {"fields": {}, "non_field_errors": [str(details.get("detail") or "")]}

        fields: dict[str, list[str]] = {}
        non_field_errors: list[str] = []

        for key, value in details.items():
            if key in ("non_field_errors", "__all__"):
                if isinstance(value, list):
                    non_field_errors.extend([str(x) for x in value])
                else:
                    non_field_errors.append(str(value))
                continue

            if isinstance(value, list):
                fields[str(key)] = [str(x) for x in value]
            else:
                fields[str(key)] = [str(value)]

        return {"fields": fields, "non_field_errors": non_field_errors}

    if isinstance(details, list):
        return {"fields": {}, "non_field_errors": [str(x) for x in details]}

    return {"fields": {}, "non_field_errors": [str(details)]}


def retryable_for(status_code: int) -> bool:
    return int(status_code) in (429, 503)


def error_code_for(*, status_code: int, exc: Exception | None = None, request=None) -> str:
    if request is not None:
        override = getattr(request, "error_code_override", None)
        if override:
            return str(override)
    sc = int(status_code)

    if sc == 401:
        if isinstance(exc, NotAuthenticated):
            return "AUTH_UNAUTHENTICATED"
        if isinstance(exc, AuthenticationFailed):
            # Best-effort: mantener códigos estables sin parsear demasiado
            msg = str(getattr(exc, "detail", "") or "").lower()
            if "expired" in msg or "expir" in msg:
                return "AUTH_TOKEN_EXPIRED"
            return "AUTH_INVALID_TOKEN"
        return "AUTH_UNAUTHENTICATED"

    if sc == 403:
        # Distinguir RBAC vs Scope por señales del request
        if request is not None and getattr(request, "required_permission", False):
            return "RBAC_FORBIDDEN"
        if request is not None and getattr(request, "required_scope", False):
            return "SCOPE_FORBIDDEN"
        return "RBAC_FORBIDDEN"

    if sc == 404:
        return "NOT_FOUND"
    if sc == 409:
        return "CONFLICT"
    if sc == 429:
        return "RATE_LIMITED"
    if sc == 422:
        return "VALIDATION_ERROR"
    if sc == 400:
        return "BAD_REQUEST"
    if sc == 503:
        return "SERVICE_UNAVAILABLE"
    if sc >= 500:
        return "INTERNAL_ERROR"

    return "ERROR"


def message_for(*, code: str, details: Any) -> str:
    # Mensajes breves para UI
    if code == "VALIDATION_ERROR":
        obj = _as_object(details)
        detail = obj.get("detail")
        if isinstance(detail, str) and detail.strip():
            return detail
        return "Validación fallida."

    obj = _as_object(details)
    detail = obj.get("detail")
    if isinstance(detail, str) and detail.strip():
        return detail

    if code in (
        "RBAC_FORBIDDEN",
        "SCOPE_FORBIDDEN",
        "AUTH_UNAUTHENTICATED",
        "AUTH_INVALID_TOKEN",
        "AUTH_TOKEN_EXPIRED",
    ):
        return "Acceso denegado."

    return "Solicitud inválida."


def details_for(*, code: str, details: Any, request=None) -> dict:
    if code == "VALIDATION_ERROR":
        obj = _validation_details(details)
        _inject_context(obj, request)
        return obj

    obj = _as_object(details)

    if code == "RBAC_FORBIDDEN":
        required_permission = getattr(request, "required_permission", "") if request is not None else ""
        if required_permission:
            obj.setdefault("missing_permissions", [required_permission])

    if code == "SCOPE_FORBIDDEN":
        required_scope = getattr(request, "required_scope", None) if request is not None else None
        if required_scope is not None:
            obj.setdefault("required_scope", required_scope)

        effective_company = getattr(request, "company", None) if request is not None else None
        effective_branch = getattr(request, "branch", None) if request is not None else None
        obj.setdefault(
            "effective_scope",
            {
                "company_id": getattr(effective_company, "id", None),
                "branch_id": getattr(effective_branch, "id", None),
            },
        )
    _inject_context(obj, request)
    return obj


def _inject_context(target: dict, request=None) -> None:
    if request is None:
        return

    ctx = getattr(request, "ctx", None)
    if ctx is None:
        ctx = getattr(getattr(request, "_request", None), "ctx", None)

    if ctx is not None:
        target.setdefault(
            "context",
            {
                "company_id": getattr(ctx, "company_id", None),
                "branch_id": getattr(ctx, "branch_id", None),
                "data_company_id": getattr(ctx, "data_company_id", None),
                "data_branch_id": getattr(ctx, "data_branch_id", None),
            },
        )
        return

    company = getattr(request, "company", None)
    branch = getattr(request, "branch", None)
    if company or branch:
        target.setdefault(
            "context",
            {
                "company_id": getattr(company, "id", None),
                "branch_id": getattr(branch, "id", None),
            },
        )


def build_error_envelope(*, request, status_code: int, exc: Exception | None = None, details: Any = None) -> dict:
    code = error_code_for(status_code=int(status_code), exc=exc, request=request)
    return {
        "error": {
            "code": code,
            "http_status": int(status_code),
            "message": message_for(code=code, details=details),
            "details": details_for(code=code, details=details, request=request),
            "request_id": getattr(request, "request_id", "") if request is not None else "",
            "timestamp": utc_timestamp_iso(),
            "retryable": retryable_for(int(status_code)),
        }
    }
