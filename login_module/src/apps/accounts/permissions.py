from __future__ import annotations

from rest_framework.permissions import BasePermission

ALLOWED_WHEN_MUST_CHANGE = {
    "/api/auth/me/",
    "/api/auth/me/acl/",
    "/api/auth/logout/",
    "/api/auth/refresh/",
    "/api/auth/password/",
}


class MustChangePasswordGate(BasePermission):
    message = "Debes cambiar tu contrasena antes de continuar."

    def has_permission(self, request, view) -> bool:
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return True

        if getattr(user, "must_change_password", False):
            path = (request.path or "").rstrip("/") + "/"
            return path in {p.rstrip("/") + "/" for p in ALLOWED_WHEN_MUST_CHANGE}

        return True
