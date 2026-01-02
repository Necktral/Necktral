from __future__ import annotations

from django.contrib.auth import get_user_model
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.audit.writer import write_event
from apps.common.permissions import rbac_permission
from apps.iam.models import OrgUnit
from apps.rbac.models import RoleAssignment

from .models import Employee, EmploymentAssignment, JobPosition
from .serializers import (
    AssignmentCreateSerializer,
    EmployeeCreateSerializer,
    EmployeeUpdateSerializer,
    PositionCreateSerializer,
    PositionRoleMapUpdateSerializer,
    PositionUpdateSerializer,
)
from .services import end_assignment, reconcile_employee_roles, set_position_role_maps
class EmployeeAssignmentEndView(APIView):
    """
    Acción idempotente: si la asignación ya está finalizada, responde 200.
    """
    permission_classes = [rbac_permission("hr.assignment.end")]

    def post(self, request, employee_id: int, assignment_id: int):
        company: OrgUnit = request.company
        emp = get_object_or_404(Employee, id=employee_id, company=company)
        assignment = get_object_or_404(EmploymentAssignment, id=assignment_id, employee=emp)

        end_assignment(assignment=assignment, request=request, actor=request.user)
        return Response({"ok": True}, status=status.HTTP_200_OK)

User = get_user_model()

class PositionListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("hr.position.create")()]
        return [rbac_permission("hr.position.read")()]

    def get(self, request):
        company: OrgUnit = request.company
        qs = JobPosition.objects.filter(company=company).order_by("name")
        data = [
            {"id": p.id, "name": p.name, "code": p.code, "is_active": p.is_active}
            for p in qs
        ]
        return Response(data, status=status.HTTP_200_OK)

    def post(self, request):
        company: OrgUnit = request.company
        serializer = PositionCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        v = serializer.validated_data
        pos = JobPosition.objects.create(company=company, name=v["name"], code=v.get("code", ""))
        write_event(
            request=request,
            module="HR",
            event_type="HR_POSITION_CREATED",
            reason_code="OK",
            actor_user=request.user,
            subject_type="POSITION",
            subject_id=str(pos.id),
            metadata={"position_name": pos.name},
        )
        return Response({"id": pos.id}, status=status.HTTP_201_CREATED)

class PositionDetailView(APIView):
    permission_classes = [rbac_permission("hr.position.update")]

    def patch(self, request, position_id: int):
        company: OrgUnit = request.company
        pos = get_object_or_404(JobPosition, id=position_id, company=company)
        serializer = PositionUpdateSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        before = {"name": pos.name, "code": pos.code, "is_active": pos.is_active}
        v = serializer.validated_data
        if "name" in v:
            pos.name = v["name"]
        if "code" in v:
            pos.code = v["code"]
        if "is_active" in v:
            pos.is_active = bool(v["is_active"])
        pos.save()
        after = {"name": pos.name, "code": pos.code, "is_active": pos.is_active}
        write_event(
            request=request,
            module="HR",
            event_type="HR_POSITION_UPDATED",
            reason_code="OK",
            actor_user=request.user,
            subject_type="POSITION",
            subject_id=str(pos.id),
            before_snapshot=before,
            after_snapshot=after,
        )
        return Response({"ok": True}, status=status.HTTP_200_OK)

class PositionRoleMapUpdateView(APIView):
    permission_classes = [rbac_permission("hr.position.roles.update")]

    def put(self, request, position_id: int):
        company: OrgUnit = request.company
        pos = get_object_or_404(JobPosition, id=position_id, company=company)
        serializer = PositionRoleMapUpdateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        maps = serializer.validated_data.get("maps", [])
        normalized = []
        for m in maps:
            if not isinstance(m, dict):
                return Response({"maps": "Cada item debe ser un objeto"}, status=status.HTTP_400_BAD_REQUEST)
            if "role_id" not in m:
                return Response({"maps": "Falta role_id"}, status=status.HTTP_400_BAD_REQUEST)
            try:
                role_id = int(m["role_id"])
            except Exception:
                return Response({"maps": "role_id inválido"}, status=status.HTTP_400_BAD_REQUEST)

            scope_mode = str(m.get("scope_mode", "BRANCH")).upper().strip()
            if scope_mode not in ("BRANCH", "COMPANY"):
                return Response({"maps": f"scope_mode inválido: {scope_mode}"}, status=status.HTTP_400_BAD_REQUEST)
            normalized.append({"role_id": role_id, "scope_mode": scope_mode})

        # dedupe estable
        seen = set()
        deduped = []
        for x in normalized:
            k = (x["role_id"], x["scope_mode"])
            if k in seen:
                continue
            seen.add(k)
            deduped.append(x)
        set_position_role_maps(position=pos, maps=deduped, request=request, actor=request.user)
        return Response({"ok": True}, status=status.HTTP_200_OK)

class EmployeeListCreateView(APIView):
    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("hr.employee.create")()]
        return [rbac_permission("hr.employee.read")()]

    def get(self, request):
        company: OrgUnit = request.company
        qs = Employee.objects.filter(company=company).order_by("first_name", "last_name")
        data = [
            {
                "id": e.id,
                "employee_code": e.employee_code,
                "first_name": e.first_name,
                "last_name": e.last_name,
                "phone": e.phone,
                "email": e.email,
                "is_active": e.is_active,
                "linked_user_id": e.linked_user_id,
            }
            for e in qs
        ]
        return Response(data, status=status.HTTP_200_OK)

    def post(self, request):
        company: OrgUnit = request.company
        serializer = EmployeeCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        v = serializer.validated_data
        linked_user = None
        if "linked_user_id" in v:
            linked_user = User.objects.filter(id=int(v["linked_user_id"])).first()
            if not linked_user:
                return Response({"linked_user_id": "Usuario no existe"}, status=status.HTTP_400_BAD_REQUEST)
        emp = Employee.objects.create(
            company=company,
            employee_code=v.get("employee_code", ""),
            first_name=v["first_name"],
            last_name=v.get("last_name", ""),
            phone=v.get("phone", ""),
            email=v.get("email", ""),
            linked_user=linked_user,
        )
        write_event(
            request=request,
            module="HR",
            event_type="HR_EMPLOYEE_CREATED",
            reason_code="OK",
            actor_user=request.user,
            subject_type="EMPLOYEE",
            subject_id=str(emp.id),
            metadata={"employee_name": emp.first_name},
        )
        if emp.linked_user_id:
            reconcile_employee_roles(employee=emp, request=request, actor=request.user)
        return Response({"id": emp.id}, status=status.HTTP_201_CREATED)

class EmployeeDetailView(APIView):
    permission_classes = [rbac_permission("hr.employee.update")]

    def patch(self, request, employee_id: int):
        company: OrgUnit = request.company
        emp = get_object_or_404(Employee, id=employee_id, company=company)
        serializer = EmployeeUpdateSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        before = {"employee_code": emp.employee_code, "first_name": emp.first_name, "last_name": emp.last_name, "phone": emp.phone, "email": emp.email, "is_active": emp.is_active, "linked_user_id": emp.linked_user_id}
        v = serializer.validated_data
        old_linked_user_id = emp.linked_user_id
        for f in ["employee_code", "first_name", "last_name", "phone", "email", "is_active"]:
            if f in v:
                setattr(emp, f, v[f])
        if "linked_user_id" in v:
            new_val = v["linked_user_id"]
            if new_val is None:
                emp.linked_user = None
            else:
                u = User.objects.filter(id=int(new_val)).first()
                if not u:
                    return Response({"linked_user_id": "Usuario no existe"}, status=status.HTTP_400_BAD_REQUEST)
                emp.linked_user = u
        emp.save()
        after = {"employee_code": emp.employee_code, "first_name": emp.first_name, "last_name": emp.last_name, "phone": emp.phone, "email": emp.email, "is_active": emp.is_active, "linked_user_id": emp.linked_user_id}
        write_event(
            request=request,
            module="HR",
            event_type="HR_EMPLOYEE_UPDATED",
            reason_code="OK",
            actor_user=request.user,
            subject_type="EMPLOYEE",
            subject_id=str(emp.id),
            before_snapshot=before,
            after_snapshot=after,
        )
        # si cambió el vínculo, limpiamos roles POSITION del usuario anterior dentro del scope de la company
        if old_linked_user_id and old_linked_user_id != emp.linked_user_id:
            branch_ids = list(
                OrgUnit.objects.filter(parent=company, unit_type=OrgUnit.UnitType.BRANCH).values_list("id", flat=True)
            )
            scoped_ids = [company.id] + branch_ids
            RoleAssignment.objects.filter(
                user_id=old_linked_user_id,
                org_unit_id__in=scoped_ids,
                origin=RoleAssignment.Origin.POSITION,
                is_active=True,
            ).update(is_active=False)
        if emp.linked_user_id:
            reconcile_employee_roles(employee=emp, request=request, actor=request.user)
        return Response({"ok": True}, status=status.HTTP_200_OK)

class EmployeeAssignmentCreateView(APIView):
    permission_classes = [rbac_permission("hr.assignment.create")]

    def post(self, request, employee_id: int):
        company: OrgUnit = request.company
        emp = get_object_or_404(Employee, id=employee_id, company=company)
        serializer = AssignmentCreateSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        v = serializer.validated_data
        position = get_object_or_404(JobPosition, id=int(v["position_id"]), company=company)
        branch = None
        if v.get("branch_id") is not None:
            branch = get_object_or_404(
                OrgUnit,
                id=int(v["branch_id"]),
                parent=company,
                unit_type=OrgUnit.UnitType.BRANCH,
            )
        a = EmploymentAssignment.objects.create(
            employee=emp,
            position=position,
            branch=branch,
        )
        write_event(
            request=request,
            module="HR",
            event_type="HR_ASSIGNMENT_CREATED",
            reason_code="OK",
            actor_user=request.user,
            subject_type="EMPLOYEE",
            subject_id=str(emp.id),
            metadata={"assignment_id": a.id},
        )
        if emp.linked_user_id:
            reconcile_employee_roles(employee=emp, request=request, actor=request.user)
        return Response({"id": a.id}, status=status.HTTP_201_CREATED)
