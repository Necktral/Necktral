from __future__ import annotations

from django.utils.deprecation import MiddlewareMixin

from apps.audit.writer import write_event


class AuditAccessDeniedMiddleware(MiddlewareMixin):
    """
    Auditoría de denegaciones por respuesta HTTP:
    - 401/403/429 generan AUTH_ACCESS_DENIED si el handler no lo hizo ya.
    - Evita duplicar eventos (flag en request).
    - Excluye endpoints de auth donde ya auditas con AUTH_LOGIN_FAILURE, etc.
    """

    EXCLUDE_PATH_PREFIXES = (
        "/api/auth/login/",
        "/api/auth/refresh/",
        "/api/auth/logout/",
    )

    def process_response(self, request, response):
        status_code = getattr(response, "status_code", None)

        if status_code not in (401, 403, 429):
            return response

        path = getattr(request, "path", "") or ""

        # No duplicar eventos en endpoints donde ya existe auditoría específica
        for prefix in self.EXCLUDE_PATH_PREFIXES:
            if path.startswith(prefix):
                return response

        # Evitar duplicado si el exception handler ya escribió el evento
        if getattr(request, "_audit_access_denied_written", False):
            return response

        # Mapping contractual
        if status_code == 401:
            reason_code = "POLICY_SCOPE_DENIED"
        elif status_code == 403:
            reason_code = "POLICY_PERMISSION_DENIED"
        else:
            reason_code = "RATE_LIMITED"

        # Actor/subject
        user = getattr(request, "user", None)
        actor = user if (user is not None and getattr(user, "is_authenticated", False)) else None

        subject_type = "USER" if actor else "SESSION"
        subject_id = str(actor.id) if actor else ""

        required_perm = getattr(request, "required_permission", "")  # Fase RBAC


        metadata = {
            "status_code": status_code,
        }

        required_perm = getattr(request, "required_permission", "")
        if required_perm:
            metadata["required_permission"] = required_perm

        required_scope = getattr(request, "required_scope", None)
        if required_scope:
            metadata["required_scope"] = required_scope

        effective_company = getattr(request, "company", None)
        effective_branch = getattr(request, "branch", None)

        metadata["effective_scope"] = {
            "company_id": getattr(effective_company, "id", None),
            "branch_id": getattr(effective_branch, "id", None),
        }

        data_scope = getattr(request, "data_scope", None)
        if data_scope:
            metadata["data_scope"] = data_scope

        intercompany = getattr(request, "intercompany", None)
        if intercompany:
            metadata["intercompany"] = intercompany

        write_event(
            request=request,
            event_type="AUTH_ACCESS_DENIED",
            reason_code=reason_code,
            actor_user=actor,
            subject_type=subject_type,
            subject_id=subject_id,
            metadata=metadata,
        )

        # Marcar para evitar dobles escrituras si hay otro middleware
        setattr(request, "_audit_access_denied_written", True)

        return response
