from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.common.permissions import rbac_permission
from .models import Role, Permission

# --- Listado de roles y permisos (read-only, protegidos) ---


class RoleListView(APIView):
    """
    GET /api/rbac/roles/?include_inactive=1
    """

    permission_classes = [rbac_permission("rbac.roles.read")]

    def get(self, request):
        include_inactive = request.query_params.get("include_inactive") == "1"
        qs = Role.objects.all().order_by("name")
        if not include_inactive:
            qs = qs.filter(is_active=True)

        results = [
            {
                "id": r.id,
                "name": r.name,
                "description": getattr(r, "description", "") or "",
                "is_active": bool(getattr(r, "is_active", True)),
            }
            for r in qs
        ]
        return Response({"count": len(results), "results": results}, status=status.HTTP_200_OK)


class PermissionListView(APIView):
    """
    GET /api/rbac/permissions/?include_inactive=1
    """

    permission_classes = [rbac_permission("rbac.permissions.read")]

    def get(self, request):
        include_inactive = request.query_params.get("include_inactive") == "1"
        qs = Permission.objects.all().order_by("code")
        if not include_inactive:
            qs = qs.filter(is_active=True)

        results = [
            {
                "id": p.id,
                "code": p.code,
                "description": getattr(p, "description", "") or "",
                "is_active": bool(getattr(p, "is_active", True)),
            }
            for p in qs
        ]
        return Response({"count": len(results), "results": results}, status=status.HTTP_200_OK)


class InventoryReadDemoView(APIView):
    """
    Endpoint demo para validar 403 contractual con required_permission.
    Luego puedes mover este patrón a endpoints reales.
    """

    permission_classes = [rbac_permission("inventory.read")]

    def get(self, request):
        return Response({"ok": True, "required_permission": "inventory.read"})
