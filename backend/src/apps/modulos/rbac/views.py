from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework import status

from apps.modulos.common.pagination import get_limit_offset, paginate_queryset
from apps.modulos.common.permissions import rbac_permission
from apps.modulos.iam.models import OrgUnit
from .models import Role, Permission, RoleAssignment, RolePermission
from .selectors import get_effective_permissions, get_effective_permissions_for_scope


def _validation_error_detail(exc: DjangoValidationError):
    """Extract safe error messages from DjangoValidationError without exposing stack traces."""
    if hasattr(exc, "message_dict"):
        return exc.message_dict
    if hasattr(exc, "messages"):
        return {"non_field_errors": exc.messages}
    return {"non_field_errors": [str(exc.message)]}

# --- Listado de roles y permisos (read-only, protegidos) ---


class RoleListView(APIView):
    """
    GET /api/rbac/roles/?include_inactive=1
    """

    permission_classes = [rbac_permission("rbac.roles.read")]
    throttle_scope = "heavy_reads"

    def get(self, request):
        include_inactive = request.query_params.get("include_inactive") == "1"
        qs = Role.objects.all().order_by("name")
        if not include_inactive:
            qs = qs.filter(is_active=True)

        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)

        results = [
            {
                "id": r.id,
                "name": r.name,
                "description": getattr(r, "description", "") or "",
                "is_active": bool(getattr(r, "is_active", True)),
            }
            for r in rows
        ]
        return Response(
            {"count": total, "limit": limit, "offset": offset, "results": results},
            status=status.HTTP_200_OK,
        )


class PermissionListView(APIView):
    """
    GET /api/rbac/permissions/?include_inactive=1
    """

    permission_classes = [rbac_permission("rbac.permissions.read")]
    throttle_scope = "heavy_reads"

    def get(self, request):
        include_inactive = request.query_params.get("include_inactive") == "1"
        qs = Permission.objects.all().order_by("code")
        if not include_inactive:
            qs = qs.filter(is_active=True)

        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)

        results = [
            {
                "id": p.id,
                "code": p.code,
                "description": getattr(p, "description", "") or "",
                "is_active": bool(getattr(p, "is_active", True)),
            }
            for p in rows
        ]
        return Response(
            {"count": total, "limit": limit, "offset": offset, "results": results},
            status=status.HTTP_200_OK,
        )


class RoleDetailView(APIView):
    """
    GET /api/rbac/roles/<id>/
    Detalle de rol con sus permisos asignados.
    """

    permission_classes = [rbac_permission("rbac.roles.read")]
    throttle_scope = "heavy_reads"

    def get(self, request, role_id):
        try:
            role = Role.objects.get(pk=role_id)
        except Role.DoesNotExist:
            return Response({"detail": "Role not found."}, status=status.HTTP_404_NOT_FOUND)

        permissions = (
            RolePermission.objects.filter(role=role)
            .select_related("permission")
            .order_by("permission__code")
        )
        perm_list = [
            {"id": rp.permission.id, "code": rp.permission.code, "description": rp.permission.description}
            for rp in permissions
        ]

        return Response({
            "id": role.id,
            "name": role.name,
            "description": role.description,
            "is_active": role.is_active,
            "permissions": perm_list,
        })


class RolePermissionManageView(APIView):
    """
    POST   /api/rbac/roles/<id>/permissions/   — Añadir permiso al rol.
    DELETE /api/rbac/roles/<id>/permissions/   — Quitar permiso del rol.
    """

    permission_classes = [rbac_permission("rbac.roles.write")]
    throttle_scope = "heavy_reads"

    def post(self, request, role_id):
        try:
            role = Role.objects.get(pk=role_id)
        except Role.DoesNotExist:
            return Response({"detail": "Role not found."}, status=status.HTTP_404_NOT_FOUND)

        permission_code = request.data.get("permission_code")
        if not permission_code:
            return Response({"detail": "permission_code required."}, status=status.HTTP_400_BAD_REQUEST)

        try:
            perm = Permission.objects.get(code=permission_code, is_active=True)
        except Permission.DoesNotExist:
            return Response({"detail": f"Permission '{permission_code}' not found."}, status=status.HTTP_404_NOT_FOUND)

        _, created = RolePermission.objects.get_or_create(role=role, permission=perm)
        return Response(
            {"role_id": role.id, "permission_code": perm.code, "created": created},
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    def delete(self, request, role_id):
        try:
            role = Role.objects.get(pk=role_id)
        except Role.DoesNotExist:
            return Response({"detail": "Role not found."}, status=status.HTTP_404_NOT_FOUND)

        permission_code = request.data.get("permission_code")
        if not permission_code:
            return Response({"detail": "permission_code required."}, status=status.HTTP_400_BAD_REQUEST)

        deleted, _ = RolePermission.objects.filter(role=role, permission__code=permission_code).delete()
        if not deleted:
            return Response({"detail": "Permission not assigned to role."}, status=status.HTTP_404_NOT_FOUND)
        return Response(status=status.HTTP_204_NO_CONTENT)


class RoleAssignmentListView(APIView):
    """
    GET  /api/rbac/assignments/?user_id=X&org_unit_id=Y
    POST /api/rbac/assignments/  — Asignar rol a usuario en scope.
    """

    permission_classes = [rbac_permission("rbac.assignments.read")]
    throttle_scope = "heavy_reads"

    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("rbac.assignments.write")()]
        return super().get_permissions()

    def get(self, request):
        qs = RoleAssignment.objects.filter(is_active=True).select_related("role", "org_unit").order_by("-granted_at")

        user_id = request.query_params.get("user_id")
        if user_id:
            qs = qs.filter(user_id=user_id)

        org_unit_id = request.query_params.get("org_unit_id")
        if org_unit_id:
            qs = qs.filter(org_unit_id=org_unit_id)

        role_name = request.query_params.get("role")
        if role_name:
            qs = qs.filter(role__name=role_name)

        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)

        results = [
            {
                "id": ra.id,
                "user_id": ra.user_id,
                "role_id": ra.role_id,
                "role_name": ra.role.name,
                "org_unit_id": ra.org_unit_id,
                "org_unit_name": ra.org_unit.name,
                "org_unit_type": ra.org_unit.unit_type,
                "origin": ra.origin,
                "origin_ref": ra.origin_ref,
                "is_active": ra.is_active,
                "granted_at": ra.granted_at.isoformat() if ra.granted_at else None,
            }
            for ra in rows
        ]
        return Response({"count": total, "limit": limit, "offset": offset, "results": results})

    def post(self, request):
        user_id = request.data.get("user_id")
        role_id = request.data.get("role_id")
        org_unit_id = request.data.get("org_unit_id")
        origin = request.data.get("origin", RoleAssignment.Origin.MANUAL)

        if not all([user_id, role_id, org_unit_id]):
            return Response(
                {"detail": "user_id, role_id, and org_unit_id are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            role = Role.objects.get(pk=role_id, is_active=True)
        except Role.DoesNotExist:
            return Response({"detail": "Role not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            org_unit = OrgUnit.objects.get(pk=org_unit_id, is_active=True)
        except OrgUnit.DoesNotExist:
            return Response({"detail": "OrgUnit not found."}, status=status.HTTP_404_NOT_FOUND)

        try:
            ra = RoleAssignment(
                user_id=user_id,
                role=role,
                org_unit=org_unit,
                origin=origin,
                granted_by=request.user,
            )
            ra.full_clean()
            ra.save()
        except DjangoValidationError as exc:
            return Response(
                {"detail": _validation_error_detail(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        return Response(
            {
                "id": ra.id,
                "user_id": ra.user_id,
                "role_name": role.name,
                "org_unit_name": org_unit.name,
                "origin": ra.origin,
                "granted_at": ra.granted_at.isoformat(),
            },
            status=status.HTTP_201_CREATED,
        )


class RoleAssignmentRevokeView(APIView):
    """
    POST /api/rbac/assignments/<id>/revoke/
    Revoca una asignación de rol (soft delete).
    """

    permission_classes = [rbac_permission("rbac.assignments.write")]
    throttle_scope = "heavy_reads"

    def post(self, request, assignment_id):
        try:
            ra = RoleAssignment.objects.get(pk=assignment_id, is_active=True)
        except RoleAssignment.DoesNotExist:
            return Response({"detail": "Assignment not found or already revoked."}, status=status.HTTP_404_NOT_FOUND)

        ra.is_active = False
        ra.save(update_fields=["is_active"])
        return Response({"id": ra.id, "is_active": False, "revoked": True})


class EffectivePermissionsView(APIView):
    """
    GET /api/rbac/effective-permissions/
    Permisos efectivos del usuario autenticado en el contexto activo (company/branch).
    """

    permission_classes = [rbac_permission("rbac.permissions.read")]
    throttle_scope = "context_read"

    def get(self, request):
        company = getattr(request, "company", None)
        branch = getattr(request, "branch", None)

        if company is None:
            # Fallback a permisos globales
            perms = get_effective_permissions(request.user)
        else:
            perms = sorted(list(get_effective_permissions_for_scope(
                request.user, company=company, branch=branch, include_global=True,
            )))

        return Response({
            "user_id": request.user.id,
            "company_id": getattr(company, "id", None),
            "branch_id": getattr(branch, "id", None),
            "permissions": perms,
        })


# --- Demo contractual ---
class InventoryReadDemoView(APIView):
    """
    Endpoint demo para validar 403 contractual con required_permission.
    Luego puedes mover este patrón a endpoints reales.
    """

    permission_classes = [rbac_permission("inventory.read")]
    throttle_scope = "heavy_reads"

    def get(self, request):
        return Response({"ok": True, "required_permission": "inventory.read"})
