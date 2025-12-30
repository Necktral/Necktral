from __future__ import annotations

from rest_framework.exceptions import (AuthenticationFailed, NotAuthenticated,
                                       PermissionDenied, Throttled)
from rest_framework.views import exception_handler as drf_exception_handler

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
    if response is None:
        return response

    request = (context or {}).get("request")
    status_code = getattr(response, "status_code", None)

    # Solo auditamos estados de denegación (authz/authn/rate-limit)
    if status_code not in (401, 403, 429):
        return response

    # Mapping contractual
    if isinstance(exc, (NotAuthenticated, AuthenticationFailed)):
        reason_code = "POLICY_SCOPE_DENIED"
    elif isinstance(exc, PermissionDenied):
        reason_code = "POLICY_PERMISSION_DENIED"
    elif isinstance(exc, Throttled):
        reason_code = "RATE_LIMITED"
    else:
        # Fallback por status
        reason_code = "RATE_LIMITED" if status_code == 429 else "POLICY_SCOPE_DENIED"

    # Detalle (sin filtrar secretos; DRF detail suele ser seguro)
    try:
        detail = getattr(exc, "detail", None)
        detail = str(detail) if detail is not None else ""
    except Exception:
        detail = ""

    required_perm = getattr(request, "required_permission", "") if request else ""

    subject_type, subject_id, actor = _subject_for_request(request)

    metadata = {
        "status_code": status_code,
        "detail": detail,
    }
    if required_perm:
        metadata["required_permission"] = required_perm


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

    return response
