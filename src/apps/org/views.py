from __future__ import annotations

from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.writer import write_event
from apps.common.permissions import rbac_permission
from apps.iam.models import OrgUnit

from .models import BranchProfile, CompanyProfile
from .serializers import (
    BranchCreateSerializer,
    BranchUpdateSerializer,
    CompanyProfileUpdateSerializer,
)

class BranchListCreateView(APIView):
    """
    Permisos por método (robusto):
      - GET  -> org.branch.read
      - POST -> org.branch.create
    """

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
        data = []
        for b in qs:
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
        return Response({"results": data}, status=status.HTTP_200_OK)

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

    def patch(self, request, branch_id: int):
        company: OrgUnit = request.company
        branch = get_object_or_404(
            OrgUnit, id=branch_id, parent=company, unit_type=OrgUnit.UnitType.BRANCH
        )
        before = {"name": branch.name, "code": branch.code, "is_active": branch.is_active}
        serializer = BranchUpdateSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        v = serializer.validated_data
        changed = False
        if "name" in v:
            branch.name = v["name"]; changed = True
        if "code" in v:
            branch.code = v["code"]; changed = True
        if "is_active" in v:
            branch.is_active = bool(v["is_active"]); changed = True
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

class CompanyProfileView(APIView):
    permission_classes = [rbac_permission("org.company.update")]

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
