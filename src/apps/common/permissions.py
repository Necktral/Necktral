from __future__ import annotations

from django.conf import settings
from rest_framework.permissions import BasePermission

from apps.rbac.selectors import get_effective_permissions_for_scope


def _set_on_request_and_raw(request, key: str, value):
    try:
        setattr(request, key, value)
    except Exception:
        pass
    try:
        raw = getattr(request, "_request", None)
        if raw is not None:
            setattr(raw, key, value)
    except Exception:
        pass

def rbac_permission(required_permission: str):
    """
    Factory DRF-friendly:
        permission_classes = [rbac_permission("inventory.read")]

    Fase 3.3B:
      - Valida permisos por contexto activo (request.company/request.branch)
      - Usa RoleAssignment (scoped) + opcional UserRole (legacy) vía settings
      - Marca required_permission + required_scope para auditoría
    """

    class _RBACPermission(BasePermission):
        message = "No tienes permisos para realizar esta acción."

        def has_permission(self, request, view) -> bool:
            # 1) Siempre marcar required_permission (para auditoría)
            _set_on_request_and_raw(request, "required_permission", required_permission)

            user = getattr(request, "user", None)
            if user is None or not getattr(user, "is_authenticated", False):
                return False

            # 2) Contexto (inyectado por JWTAuthWithOrgContext)
            company = getattr(request, "company", None)
            branch = getattr(request, "branch", None)

            effective_scope = {
                "company_id": getattr(company, "id", None),
                "branch_id": getattr(branch, "id", None),
            }

            # Si no hay contexto, negar y dejar rastro (normalmente no ocurre porque auth lo exige)
            if company is None:
                _set_on_request_and_raw(request, "required_scope", effective_scope)
                return False

            include_global = bool(getattr(settings, "RBAC_INCLUDE_GLOBAL_USERROLES", True))

            perms = get_effective_permissions_for_scope(
                user,
                company=company,
                branch=branch,
                include_global=include_global,
            )

            allowed_local = required_permission in perms or ("*" in perms)
            if not allowed_local:
                if getattr(request, "required_scope", None) is None:
                    _set_on_request_and_raw(request, "required_scope", effective_scope)
                return False

            # --- Intercompany enforcement (solo READ en esta fase) ---
            data_company = getattr(request, "data_company", company) or company
            data_branch = getattr(request, "data_branch", None)

            if getattr(data_company, "id", None) != getattr(company, "id", None):
                from apps.iam.selectors import has_intercompany_grant

                grant_ok = has_intercompany_grant(
                    from_company=data_company,
                    to_company=company,
                    permission_code=required_permission,
                    mode="READ",
                    scope_branch=data_branch,
                )

                # enriquecer metadata para auditoría
                intercompany_meta = getattr(request, "intercompany", None) or {
                    "from_company_id": data_company.id,
                    "to_company_id": company.id,
                    "mode": "READ",
                }
                intercompany_meta["grant_found"] = bool(grant_ok)
                _set_on_request_and_raw(request, "intercompany", intercompany_meta)

                if not grant_ok:
                    # required_scope en este caso representa el data_scope que se intentó acceder
                    _set_on_request_and_raw(
                        request,
                        "required_scope",
                        {"company_id": data_company.id, "branch_id": getattr(data_branch, "id", None)},
                    )
                    return False

            return True

    return _RBACPermission
