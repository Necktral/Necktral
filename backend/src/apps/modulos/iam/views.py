from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.common.pagination import get_limit_offset, paginate_queryset
from apps.modulos.common.permissions import rbac_permission

from .models import AdminGrant, CompanyLink, OrgUnit, UserMembership
from .selectors import (
    build_acl_snapshot,
    get_accessible_branches,
    get_accessible_companies,
)


class ContextEchoView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "context_read"

    def get(self, request):
        company = getattr(request, "company", None)
        branch = getattr(request, "branch", None)
        return Response(
            {
                "company_id": getattr(company, "id", None),
                "branch_id": getattr(branch, "id", None),
            }
        )


class ACLSnapshotView(APIView):
    """
    GET /api/iam/acl/
    Snapshot completo de control de acceso para el usuario autenticado.
    Incluye companies, branches, permisos efectivos y admin capabilities.
    """

    permission_classes = [IsAuthenticated]
    throttle_scope = "context_read"

    def get(self, request):
        payload = build_acl_snapshot(request.user)
        return Response(payload)


class OrgUnitListView(APIView):
    """
    GET /api/iam/org-units/?unit_type=COMPANY&parent_id=1
    Listar OrgUnits accesibles (filtrado por tipo y parent).
    """

    permission_classes = [rbac_permission("iam.org_units.read")]
    throttle_scope = "heavy_reads"

    def get(self, request):
        qs = OrgUnit.objects.filter(is_active=True).order_by("unit_type", "name")

        unit_type = request.query_params.get("unit_type")
        if unit_type:
            qs = qs.filter(unit_type=unit_type)

        parent_id = request.query_params.get("parent_id")
        if parent_id:
            qs = qs.filter(parent_id=parent_id)

        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)

        results = [
            {
                "id": ou.id,
                "unit_type": ou.unit_type,
                "name": ou.name,
                "code": ou.code,
                "parent_id": ou.parent_id,
                "is_active": ou.is_active,
            }
            for ou in rows
        ]
        return Response({"count": total, "limit": limit, "offset": offset, "results": results})


class MyCompaniesView(APIView):
    """
    GET /api/iam/my-companies/
    Companies accesibles por el usuario autenticado.
    """

    permission_classes = [IsAuthenticated]
    throttle_scope = "context_read"

    def get(self, request):
        companies = get_accessible_companies(request.user)
        results = [
            {"id": c.id, "name": c.name, "code": c.code}
            for c in companies
        ]
        return Response({"results": results})


class MyBranchesView(APIView):
    """
    GET /api/iam/my-branches/?company_id=1
    Branches accesibles por el usuario en una company específica.
    """

    permission_classes = [IsAuthenticated]
    throttle_scope = "context_read"

    def get(self, request):
        company_id = request.query_params.get("company_id")
        if not company_id:
            return Response({"detail": "company_id query param required."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            company = OrgUnit.objects.get(pk=company_id, unit_type=OrgUnit.UnitType.COMPANY, is_active=True)
        except OrgUnit.DoesNotExist:
            return Response({"detail": "Company not found."}, status=status.HTTP_404_NOT_FOUND)

        branches = get_accessible_branches(request.user, company)
        results = [
            {"id": b.id, "name": b.name, "code": b.code}
            for b in branches
        ]
        return Response({"results": results})


class MembershipListView(APIView):
    """
    GET /api/iam/memberships/
    Membresías del usuario autenticado.
    """

    permission_classes = [IsAuthenticated]
    throttle_scope = "context_read"

    def get(self, request):
        memberships = (
            UserMembership.objects.filter(user=request.user, is_active=True)
            .select_related("org_unit")
            .order_by("org_unit__unit_type", "org_unit__name")
        )
        results = [
            {
                "id": m.id,
                "org_unit_id": m.org_unit_id,
                "org_unit_name": m.org_unit.name,
                "org_unit_type": m.org_unit.unit_type,
                "joined_at": m.joined_at.isoformat() if m.joined_at else None,
            }
            for m in memberships
        ]
        return Response({"results": results})


class AdminGrantListView(APIView):
    """
    GET /api/iam/admin-grants/
    Capacidades admin del usuario autenticado.
    """

    permission_classes = [IsAuthenticated]
    throttle_scope = "context_read"

    def get(self, request):
        grants = (
            AdminGrant.objects.filter(user=request.user, is_active=True)
            .select_related("org_unit")
            .order_by("org_unit__name", "capability")
        )
        results = [
            {
                "id": g.id,
                "org_unit_id": g.org_unit_id,
                "org_unit_name": g.org_unit.name,
                "capability": g.capability,
                "applies_to_subtree": g.applies_to_subtree,
                "granted_at": g.granted_at.isoformat() if g.granted_at else None,
            }
            for g in grants
        ]
        return Response({"results": results})


class CompanyLinkListView(APIView):
    """
    GET /api/iam/company-links/
    Links intercompany visibles desde la company activa.
    """

    permission_classes = [rbac_permission("iam.company_links.read")]
    throttle_scope = "heavy_reads"

    def get(self, request):
        company = getattr(request, "company", None)
        if company is None:
            return Response({"detail": "Company context required."}, status=status.HTTP_400_BAD_REQUEST)

        qs = CompanyLink.objects.filter(
            from_company=company, is_active=True
        ).select_related("to_company").order_by("-created_at")

        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)

        results = [
            {
                "id": link.id,
                "to_company_id": link.to_company_id,
                "to_company_name": link.to_company.name,
                "link_type": link.link_type,
                "status": link.status,
                "created_at": link.created_at.isoformat(),
            }
            for link in rows
        ]
        return Response({"count": total, "limit": limit, "offset": offset, "results": results})
