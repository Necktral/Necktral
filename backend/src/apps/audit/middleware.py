"""Middleware de auditoría para denegaciones (precedente).

Contrato:
- Si una request termina en 401/403/429, se emite un evento AUTH_ACCESS_DENIED (salvo exclusiones).
- Usa required_permission/required_scope cuando estén presentes (inyectados por RBAC/contexto).

Objetivo:
- Tener un rastro consistente de intentos de acceso fallidos sin duplicar eventos.
"""

from __future__ import annotations

from django.utils.deprecation import MiddlewareMixin

from apps.audit.contracts import validate_reason_code
from apps.audit.deny_aggregator import aggregate_deny
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

        # Evitar duplicado si el exception handler ya escribió o suprimió el evento
        if getattr(request, "_audit_access_denied_written", False) or getattr(
            request, "_audit_access_denied_suppressed", False
        ):
            return response

        reason_code = None
        override = getattr(request, "audit_reason_code_override", None)
        if override:
            try:
                validate_reason_code(str(override))
                reason_code = str(override)
            except Exception:
                reason_code = None

        # Mapping contractual (códigos estándar para consumo externo)
        if reason_code is None:
            if status_code == 401:
                reason_code = "AUTH_UNAUTHENTICATED"
            elif status_code == 403:
                if getattr(request, "required_permission", ""):
                    reason_code = "RBAC_FORBIDDEN"
                elif getattr(request, "required_scope", None):
                    reason_code = "SCOPE_FORBIDDEN"
                else:
                    reason_code = "RBAC_FORBIDDEN"
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

        ctx = getattr(request, "ctx", None)
        if ctx is not None:
            metadata["ctx"] = {
                "request_id": getattr(ctx, "request_id", "") or "",
                "company_id": getattr(ctx, "company_id", None),
                "branch_id": getattr(ctx, "branch_id", None),
                "data_company_id": getattr(ctx, "data_company_id", None),
                "data_branch_id": getattr(ctx, "data_branch_id", None),
            }

        ip = request.META.get("HTTP_X_FORWARDED_FOR")
        if ip:
            ip = ip.split(",")[0].strip()
        else:
            ip = request.META.get("REMOTE_ADDR", "")

        user_id = str(getattr(actor, "id", "")) if actor else ""
        cache_key = f"deny:{ip}:{user_id}:{path}:{status_code}"
        agg = aggregate_deny(key=cache_key, ttl_seconds=60, every=50)

        if agg is None:
            setattr(request, "_audit_access_denied_suppressed", True)
            return response

        metadata["count"] = agg.count
        metadata["window_seconds"] = agg.window_seconds

        write_event(
            request=request,
            event_type="AUTH_ACCESS_DENIED",
            reason_code=reason_code,
            actor_user=actor,
            subject_type=subject_type,
            subject_id=subject_id,
            metadata=metadata,
        )

        setattr(request, "_audit_access_denied_written", True)

        return response
