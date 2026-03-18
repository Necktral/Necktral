from __future__ import annotations

from django.conf import settings
from rest_framework.response import Response
from rest_framework.exceptions import (
    AuthenticationFailed,
    NotAuthenticated,
    PermissionDenied,
    Throttled,
    ValidationError,
)
from rest_framework.views import exception_handler as drf_exception_handler

from config.error_envelope import build_error_envelope
from apps.audit.writer import write_event


def _actor_user(request):
    if request is None:
        return None
    user = getattr(request, "user", None)
    if user is not None and getattr(user, "is_authenticated", False):
        return user
    return None


def _subject_for_request(request):
    actor = _actor_user(request)
    if actor is not None:
        return ("USER", str(actor.id), actor)
    # Sin usuario autenticado: tratamos como contexto de sesión
    return ("SESSION", "", None)


def custom_exception_handler(exc, context):
    """
    Ruta A (contractual EAU):
    - 401/403/429 -> AuditEvent AUTH_ACCESS_DENIED con reason_code estándar
    - Incluye required_permission si la view lo inyecta en request.required_permission
    """
    response = drf_exception_handler(exc, context)
    request = (context or {}).get("request")

    # Fallback prod-safe para excepciones no manejadas por DRF
    if response is None:
        if settings.DEBUG:
            return None
        envelope = build_error_envelope(request=request, status_code=500, exc=exc, details={"detail": "Error interno."})
        return Response(envelope, status=500)

    status_code = getattr(response, "status_code", None)

    # Contrato: validaciones deben responder como 422
    if isinstance(exc, ValidationError) and status_code == 400:
        response.status_code = 422
        status_code = 422

    # Solo auditamos estados de denegación (authz/authn/rate-limit)
    if status_code not in (401, 403, 429):
        # Igual normalizamos el formato de error
        if isinstance(getattr(response, "data", None), dict) and "error" in response.data:
            return response

        details = getattr(response, "data", None)
        if status_code is not None and int(status_code) >= 400:
            response.data = build_error_envelope(
                request=request,
                status_code=int(status_code),
                exc=exc,
                details=details,
            )
        return response

    # Mapping contractual (auditoría)
    if isinstance(exc, (NotAuthenticated, AuthenticationFailed)):
        # Diferenciar cuando sea posible para trazabilidad
        if isinstance(exc, NotAuthenticated):
            reason_code = "AUTH_UNAUTHENTICATED"
        else:
            msg = str(getattr(exc, "detail", "") or "").lower()
            reason_code = "AUTH_TOKEN_EXPIRED" if ("expired" in msg or "expir" in msg) else "AUTH_INVALID_TOKEN"
    elif isinstance(exc, PermissionDenied):
        if request is not None and getattr(request, "required_permission", ""):
            reason_code = "RBAC_FORBIDDEN"
        elif request is not None and getattr(request, "required_scope", None):
            reason_code = "SCOPE_FORBIDDEN"
        else:
            reason_code = "RBAC_FORBIDDEN"
    elif isinstance(exc, Throttled):
        reason_code = "RATE_LIMITED"
    else:
        # Fallback por status
        reason_code = "RATE_LIMITED" if status_code == 429 else "AUTH_UNAUTHENTICATED"

    # Detalle (sin filtrar secretos; DRF detail suele ser seguro)
    try:
        detail = getattr(exc, "detail", None)
        detail = str(detail) if detail is not None else ""
    except Exception:
        detail = ""

    required_perm = getattr(request, "required_permission", "") if request else ""
    required_scope = getattr(request, "required_scope", None) if request else None
    effective_company = getattr(request, "company", None) if request else None
    effective_branch = getattr(request, "branch", None) if request else None

    subject_type, subject_id, actor = _subject_for_request(request)

    metadata = {
        "status_code": status_code,
        "detail": detail,
        "effective_scope": {
            "company_id": getattr(effective_company, "id", None),
            "branch_id": getattr(effective_branch, "id", None),
        },
    }
    if required_perm:
        metadata["required_permission"] = required_perm
    if required_scope is not None:
        metadata["required_scope"] = required_scope

    write_event(
        request=request,
        event_type="AUTH_ACCESS_DENIED",
        reason_code=reason_code,
        actor_user=actor,
        subject_type=subject_type,
        subject_id=subject_id,
        metadata=metadata,
    )
    if request is not None:
        setattr(request, "_audit_access_denied_written", True)

    # Envelope contractual
    if isinstance(getattr(response, "data", None), dict) and "error" in response.data:
        return response

    details = getattr(response, "data", None)
    if status_code is not None and int(status_code) >= 400:
        response.data = build_error_envelope(
            request=request,
            status_code=int(status_code),
            exc=exc,
            details=details,
        )

    return response
