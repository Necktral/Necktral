from __future__ import annotations

from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.audit.writer import write_event
from apps.modulos.common.pagination import get_limit_offset, paginate_list, paginate_queryset
from apps.modulos.common.permissions import rbac_permission
from apps.modulos.common.throttling import MethodThrottleScopeMixin
from apps.modulos.iam.models import AdminGrant, OrgUnit, UserMembership
from apps.modulos.iam.selectors import get_accessible_companies
from apps.modulos.rbac.models import RoleAssignment

from .models import BranchProfile, CompanyProfile
from .bootstrap_services import bootstrap_organization_for_user
from .serializers import (
    BootstrapOrganizationSerializer,
    BranchCreateSerializer,
    BranchUpdateSerializer,
    CompanyCreateSerializer,
    CompanyProfileUpdateSerializer,
)


class BootstrapOrganizationView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_scope = "admin_writes"

    def post(self, request):
        serializer = BootstrapOrganizationSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        try:
            ids = bootstrap_organization_for_user(request.user, serializer.validated_data)
        except ValueError as exc:
            detail = str(exc)
            if "Bootstrap ya realizado" in detail:
                return Response({"detail": detail}, status=status.HTTP_409_CONFLICT)
            if "Falta role" in detail:
                return Response({"detail": detail}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            return Response({"detail": detail}, status=status.HTTP_400_BAD_REQUEST)

        write_event(
            request=request,
            event_type="IAM_BOOTSTRAP_ORG_CREATED",
            reason_code="OK",
            actor_user=request.user,
            subject_type="COMPANY",
            subject_id=str(ids["company_id"]),
            metadata=ids,
        )
        return Response(ids, status=status.HTTP_200_OK)


class CompanyListCreateView(MethodThrottleScopeMixin, APIView):
    """
    Holding → Companies (multi-company).
    Permisos por método:
      - GET  -> org.company.read
      - POST -> org.company.create
    """

    throttle_scope_by_method = {
        "GET": "heavy_reads",
        "POST": "admin_writes",
    }

    def get_permissions(self):
        if self.request.method == "GET":
            return [rbac_permission("org.company.read")()]
        if self.request.method == "POST":
            return [rbac_permission("org.company.create")()]
        return [rbac_permission("org.company.read")()]

    def get(self, request):
        companies = get_accessible_companies(request.user)
        limit, offset = get_limit_offset(request)
        total, rows = paginate_list(companies, limit=limit, offset=offset)
        out = []
        for c in rows:
            prof = getattr(c, "company_profile", None)
            out.append(
                {
                    "id": c.id,
                    "name": c.name,
                    "code": c.code,
                    "is_active": c.is_active,
                    "legal_name": getattr(prof, "legal_name", ""),
                    "tax_id": getattr(prof, "tax_id", ""),
                }
            )
        return Response(
            {"count": total, "limit": limit, "offset": offset, "results": out},
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        with transaction.atomic():
            current_company: OrgUnit | None = getattr(request, "company", None)

            holding: OrgUnit | None = None
            if current_company and current_company.unit_type == OrgUnit.UnitType.HOLDING:
                holding = current_company
            elif current_company and current_company.parent and current_company.parent.unit_type == OrgUnit.UnitType.HOLDING:
                holding = current_company.parent
            else:
                holding = OrgUnit.objects.filter(unit_type=OrgUnit.UnitType.HOLDING).order_by("id").first()

            if not holding:
                return Response({"detail": "No existe holding. Ejecuta bootstrap primero."}, status=status.HTTP_400_BAD_REQUEST)

            serializer = CompanyCreateSerializer(data=request.data)
            if not serializer.is_valid():
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
            v = serializer.validated_data

            # Dedupe por name dentro del holding (robusto)
            if OrgUnit.objects.filter(parent=holding, unit_type=OrgUnit.UnitType.COMPANY, name=v["name"]).exists():
                return Response(
                    {"name": "Ya existe una compañía con ese nombre en el holding"},
                    status=status.HTTP_409_CONFLICT,
                )

            new_company = OrgUnit.objects.create(
                unit_type=OrgUnit.UnitType.COMPANY,
                parent=holding,
                name=v["name"],
                code=v.get("code", ""),
                is_active=True,
            )
            CompanyProfile.objects.create(
                company=new_company,
                legal_name=v.get("legal_name", "") or v["name"],
                tax_id=v.get("tax_id", ""),
                address=v.get("address", ""),
                phone=v.get("phone", ""),
                email=v.get("email", ""),
            )

            # Dar acceso inmediato al creador (para selector/ACL)
            membership, _created = UserMembership.objects.get_or_create(
                user=request.user,
                org_unit=new_company,
                defaults={"is_active": True},
            )
            if not membership.is_active:
                membership.is_active = True
                membership.left_at = None
                membership.save()

            # Clonar roles del creador desde su compañía actual
            if current_company and current_company.unit_type == OrgUnit.UnitType.COMPANY:
                roles_to_clone = RoleAssignment.objects.filter(
                    user=request.user,
                    org_unit=current_company,
                    is_active=True,
                )
                for ra in roles_to_clone:
                    cloned_ra, _ = RoleAssignment.objects.get_or_create(
                        user=request.user,
                        role=ra.role,
                        org_unit=new_company,
                        defaults={
                            "is_active": True,
                            "granted_by": request.user,
                            "origin_ref": "org.company.create.clone",
                        },
                    )
                    if not cloned_ra.is_active:
                        cloned_ra.is_active = True
                        cloned_ra.granted_by = request.user
                        cloned_ra.origin_ref = "org.company.create.clone"
                        cloned_ra.save()

                grants_to_clone = AdminGrant.objects.filter(
                    user=request.user,
                    org_unit=current_company,
                    is_active=True,
                )
                for g in grants_to_clone:
                    cloned_g, _ = AdminGrant.objects.get_or_create(
                        user=request.user,
                        org_unit=new_company,
                        capability=g.capability,
                        defaults={
                            "is_active": True,
                            "applies_to_subtree": g.applies_to_subtree,
                            "granted_by": request.user,
                        },
                    )
                    if not cloned_g.is_active:
                        cloned_g.is_active = True
                        cloned_g.applies_to_subtree = g.applies_to_subtree
                        cloned_g.granted_by = request.user
                        cloned_g.save()

            write_event(
                request=request,
                module="ORG",
                event_type="ORG_COMPANY_CREATED",
                reason_code="OK",
                actor_user=request.user,
                subject_type="COMPANY",
                subject_id=str(new_company.id),
                metadata={"company_name": new_company.name, "holding_id": str(holding.id)},
            )
            return Response({"id": new_company.id}, status=status.HTTP_201_CREATED)


class BranchListCreateView(MethodThrottleScopeMixin, APIView):
    """
    Permisos por método (robusto):
      - GET  -> org.branch.read
      - POST -> org.branch.create
    """

    throttle_scope_by_method = {
        "GET": "heavy_reads",
        "POST": "admin_writes",
    }

    def get_permissions(self):
        if self.request.method == "GET":
            return [rbac_permission("org.branch.read")()]
        if self.request.method == "POST":
            return [rbac_permission("org.branch.create")()]
        # Fallback seguro: negar por defecto a quien no tenga al menos read
        return [rbac_permission("org.branch.read")()]

    def get(self, request):
        company: OrgUnit = request.company
        qs = OrgUnit.objects.filter(parent=company, unit_type=OrgUnit.UnitType.BRANCH).order_by("name")
        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        data = []
        for b in rows:
            prof = getattr(b, "branch_profile", None)
            data.append(
                {
                    "id": b.id,
                    "name": b.name,
                    "code": b.code,
                    "is_active": b.is_active,
                    "address": getattr(prof, "address", ""),
                    "phone": getattr(prof, "phone", ""),
                    "email": getattr(prof, "email", ""),
                }
            )
        return Response(
            {"count": total, "limit": limit, "offset": offset, "results": data},
            status=status.HTTP_200_OK,
        )

    def post(self, request):
        company: OrgUnit = request.company
        serializer = BranchCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        v = serializer.validated_data
        branch = OrgUnit.objects.create(
            unit_type=OrgUnit.UnitType.BRANCH,
            parent=company,
            name=v["name"],
            code=v.get("code", ""),
            is_active=True,
        )
        BranchProfile.objects.create(
            branch=branch,
            address=v.get("address", ""),
            phone=v.get("phone", ""),
            email=v.get("email", ""),
        )

        write_event(
            request=request,
            module="ORG",
            event_type="ORG_BRANCH_CREATED",
            reason_code="OK",
            actor_user=request.user,
            subject_type="BRANCH",
            subject_id=str(branch.id),
            metadata={"branch_name": branch.name},
        )
        return Response({"id": branch.id}, status=status.HTTP_201_CREATED)


class BranchDetailView(APIView):
    permission_classes = [rbac_permission("org.branch.update")]
    throttle_scope = "admin_writes"

    def patch(self, request, branch_id: int):
        company: OrgUnit = request.company
        branch = get_object_or_404(OrgUnit, id=branch_id, parent=company, unit_type=OrgUnit.UnitType.BRANCH)
        before = {"name": branch.name, "code": branch.code, "is_active": branch.is_active}
        serializer = BranchUpdateSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        v = serializer.validated_data
        changed = False
        if "name" in v:
            branch.name = v["name"]
            changed = True
        if "code" in v:
            branch.code = v["code"]
            changed = True
        if "is_active" in v:
            branch.is_active = bool(v["is_active"])
            changed = True
        if changed:
            branch.save()
        prof, _ = BranchProfile.objects.get_or_create(branch=branch)
        prof_changed = False
        for f in ["address", "phone", "email"]:
            if f in v:
                setattr(prof, f, v[f])
                prof_changed = True
        if prof_changed:
            prof.save()
        after = {"name": branch.name, "code": branch.code, "is_active": branch.is_active}
        write_event(
            request=request,
            module="ORG",
            event_type="ORG_BRANCH_UPDATED",
            reason_code="OK",
            actor_user=request.user,
            subject_type="BRANCH",
            subject_id=str(branch.id),
            before_snapshot=before,
            after_snapshot=after,
        )
        return Response({"ok": True}, status=status.HTTP_200_OK)


class CompanyProfileView(MethodThrottleScopeMixin, APIView):
    throttle_scope_by_method = {
        "GET": "heavy_reads",
        "PUT": "admin_writes",
    }
    def get_permissions(self):
        # Separar ver vs editar
        if self.request.method == "GET":
            return [rbac_permission("org.company.read")()]
        if self.request.method == "PUT":
            return [rbac_permission("org.company.update")()]
        return [rbac_permission("org.company.read")()]

    def get(self, request):
        company: OrgUnit = request.company
        prof, _ = CompanyProfile.objects.get_or_create(company=company)
        return Response(
            {
                "legal_name": prof.legal_name,
                "tax_id": prof.tax_id,
                "address": prof.address,
                "phone": prof.phone,
                "email": prof.email,
            },
            status=status.HTTP_200_OK,
        )

    def put(self, request):
        company: OrgUnit = request.company
        prof, _ = CompanyProfile.objects.get_or_create(company=company)
        serializer = CompanyProfileUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        before = {
            "legal_name": prof.legal_name,
            "tax_id": prof.tax_id,
            "address": prof.address,
            "phone": prof.phone,
            "email": prof.email,
        }
        v = serializer.validated_data
        for f in ["legal_name", "tax_id", "address", "phone", "email"]:
            if f in v:
                setattr(prof, f, v[f])
        prof.save()
        after = {
            "legal_name": prof.legal_name,
            "tax_id": prof.tax_id,
            "address": prof.address,
            "phone": prof.phone,
            "email": prof.email,
        }
        write_event(
            request=request,
            module="ORG",
            event_type="ORG_COMPANY_PROFILE_UPDATED",
            reason_code="OK",
            actor_user=request.user,
            subject_type="COMPANY",
            subject_id=str(company.id),
            before_snapshot=before,
            after_snapshot=after,
        )
        return Response({"ok": True}, status=status.HTTP_200_OK)
