from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db import transaction
from django.db.models import Prefetch
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.exceptions import ValidationError
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.modulos.audit.writer import write_event
from apps.modulos.common.api_exceptions import ConflictError
from apps.modulos.common.pagination import get_limit_offset, paginate_queryset
from apps.modulos.common.permissions import rbac_permission
from apps.modulos.common.throttling import MethodThrottleScopeMixin
from apps.modulos.iam.models import OrgUnit
from apps.modulos.parties.models import Party
from apps.modulos.rbac.models import RoleAssignment

from .models import Employee, EmploymentAssignment, JobPosition
from .serializers import (
    AssignmentCreateSerializer,
    EmployeeRevokeAccessSerializer,
    EmployeeCreateSerializer,
    ResetTempPasswordSerializer,
    EmployeeUpdateSerializer,
    PositionCreateSerializer,
    PositionRoleMapUpdateSerializer,
    PositionUpdateSerializer,
    EmployeeProvisionUserSerializer,
)
from .services import (
    end_assignment,
    link_employee_to_party,
    provision_user_for_employee,
    reconcile_employee_roles,
    revoke_employee_access,
    reset_temp_password_for_employee,
    set_position_role_maps,
    unlink_employee_party,
)


class EmployeeAssignmentEndView(APIView):
    """
    Acción idempotente: si la asignación ya está finalizada, responde 200.
    """

    permission_classes = [rbac_permission("hr.assignment.end")]
    throttle_scope = "admin_writes"

    def post(self, request, employee_id: int, assignment_id: int):
        company: OrgUnit = request.company
        emp = get_object_or_404(Employee, id=employee_id, company=company)
        assignment = get_object_or_404(EmploymentAssignment, id=assignment_id, employee=emp)

        end_assignment(assignment=assignment, request=request, actor=request.user)
        return Response({"ok": True}, status=status.HTTP_200_OK)


User = get_user_model()


def _django_validation_payload(exc: DjangoValidationError) -> dict:
    if hasattr(exc, "message_dict"):
        return exc.message_dict
    return {"detail": list(exc.messages)}


class PositionListCreateView(MethodThrottleScopeMixin, APIView):
    throttle_scope_by_method = {
        "GET": "heavy_reads",
        "POST": "admin_writes",
    }
    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("hr.position.create")()]
        return [rbac_permission("hr.position.read")()]

    def get(self, request):
        company: OrgUnit = request.company
        qs = JobPosition.objects.filter(company=company).order_by("name")
        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        data = [{"id": p.id, "name": p.name, "code": p.code, "is_active": p.is_active} for p in rows]
        return Response(
            {"count": total, "limit": limit, "offset": offset, "results": data},
            status=status.HTTP_200_OK,
        )

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
    throttle_scope = "admin_writes"

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
    throttle_scope = "admin_writes"

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


class EmployeeListCreateView(MethodThrottleScopeMixin, APIView):
    throttle_scope_by_method = {
        "GET": "heavy_reads",
        "POST": "admin_writes",
    }
    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("hr.employee.create")()]
        return [rbac_permission("hr.employee.read")()]

    def get(self, request):
        company = request.company
        active_asg_qs = (
            EmploymentAssignment.objects.filter(is_active=True)
            .select_related("position", "branch")
            .order_by("-started_at", "-id")
        )
        base_qs = Employee.objects.filter(company=company).order_by("id")
        limit, offset = get_limit_offset(request)
        total = base_qs.count()
        qs = base_qs.select_related("linked_user", "party").prefetch_related(
            Prefetch("assignments", queryset=active_asg_qs, to_attr="active_assignments")
        )
        rows = qs[offset : offset + limit]
        out = []
        for e in rows:
            actives = getattr(e, "active_assignments", []) or []
            out.append(
                {
                    "id": e.id,
                    "employee_code": e.employee_code or "",
                    "first_name": e.first_name,
                    "last_name": e.last_name or "",
                    "phone": e.phone or "",
                    "email": e.email or "",
                    "is_active": e.is_active,
                    "party_id": e.party_id,
                    "party_display_name": e.party.display_name if e.party_id and e.party else None,
                    "party_tax_id": e.party.tax_id if e.party_id and e.party else "",
                    "party_national_id": e.party.national_id if e.party_id and e.party else "",
                    "linked_user_id": e.linked_user_id,
                    "linked_username": (e.linked_user.username if e.linked_user_id and e.linked_user else None),
                    "has_active_assignment": bool(actives),
                    "active_assignments": [
                        {
                            "id": a.id,
                            "position_id": a.position_id,
                            "position_name": a.position.name if a.position_id and a.position else "",
                            "branch_id": a.branch_id,
                            "branch_name": a.branch.name if a.branch_id and a.branch else None,
                            "started_at": a.started_at.isoformat() if a.started_at else None,
                        }
                        for a in actives
                    ],
                }
            )
        return Response({"count": total, "limit": limit, "offset": offset, "results": out})

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
        party = None
        if "party_id" in v:
            party = Party.objects.filter(id=int(v["party_id"]), company=company).first()
            if party is None:
                return Response({"party_id": "Party no existe en esta company."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            with transaction.atomic():
                emp = Employee.objects.create(
                    company=company,
                    employee_code=v.get("employee_code", ""),
                    first_name=v["first_name"],
                    last_name=v.get("last_name", ""),
                    phone=v.get("phone", ""),
                    email=v.get("email", ""),
                    is_active=bool(v.get("is_active", True)),
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
                if party is not None:
                    link_employee_to_party(employee=emp, party=party, request=request, actor=request.user)
                if emp.linked_user_id:
                    reconcile_employee_roles(employee=emp, request=request, actor=request.user)
        except DjangoValidationError as exc:
            return Response(_django_validation_payload(exc), status=status.HTTP_400_BAD_REQUEST)
        return Response({"id": emp.id}, status=status.HTTP_201_CREATED)


class EmployeeDetailView(APIView):
    permission_classes = [rbac_permission("hr.employee.update")]
    throttle_scope = "admin_writes"

    def patch(self, request, employee_id: int):
        company: OrgUnit = request.company
        emp = get_object_or_404(Employee, id=employee_id, company=company)
        serializer = EmployeeUpdateSerializer(data=request.data, partial=True)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        before = {
            "employee_code": emp.employee_code,
            "party_id": emp.party_id,
            "first_name": emp.first_name,
            "last_name": emp.last_name,
            "phone": emp.phone,
            "email": emp.email,
            "is_active": emp.is_active,
            "linked_user_id": emp.linked_user_id,
        }
        v = serializer.validated_data
        old_linked_user_id = emp.linked_user_id
        party_requested = "party_id" in v
        party = None
        if party_requested and v["party_id"] is not None:
            party = Party.objects.filter(id=int(v["party_id"]), company=company).first()
            if party is None:
                return Response({"party_id": "Party no existe en esta company."}, status=status.HTTP_400_BAD_REQUEST)
        try:
            with transaction.atomic():
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
                after = {
                    "employee_code": emp.employee_code,
                    "party_id": emp.party_id,
                    "first_name": emp.first_name,
                    "last_name": emp.last_name,
                    "phone": emp.phone,
                    "email": emp.email,
                    "is_active": emp.is_active,
                    "linked_user_id": emp.linked_user_id,
                }
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
                if party_requested:
                    if party is None:
                        unlink_employee_party(employee=emp, request=request, actor=request.user)
                    else:
                        link_employee_to_party(employee=emp, party=party, request=request, actor=request.user)
                # si cambió el vínculo, limpiamos roles POSITION del usuario anterior dentro del scope de la company
                if old_linked_user_id and old_linked_user_id != emp.linked_user_id:
                    branch_ids = list(
                        OrgUnit.objects.filter(parent=company, unit_type=OrgUnit.UnitType.BRANCH).values_list(
                            "id", flat=True
                        )
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
        except DjangoValidationError as exc:
            return Response(_django_validation_payload(exc), status=status.HTTP_400_BAD_REQUEST)
        return Response({"ok": True}, status=status.HTTP_200_OK)



# Vista combinada para listar y crear asignaciones de empleado
class EmployeeAssignmentListCreateView(MethodThrottleScopeMixin, APIView):
    throttle_scope_by_method = {
        "GET": "heavy_reads",
        "POST": "admin_writes",
    }
    def get_permissions(self):
        if self.request.method == "POST":
            return [rbac_permission("hr.assignment.create")()]
        return [rbac_permission("hr.assignment.read")()]

    def get(self, request, employee_id: int):
        company: OrgUnit = request.company
        emp = get_object_or_404(Employee, id=employee_id, company=company)
        qs = (
            EmploymentAssignment.objects.filter(employee=emp)
            .select_related("position", "branch")
            .order_by("-is_active", "-started_at", "-id")
        )
        limit, offset = get_limit_offset(request)
        total, rows = paginate_queryset(qs, limit=limit, offset=offset)
        data = []
        for a in rows:
            data.append(
                {
                    "id": a.id,
                    "is_active": a.is_active,
                    "position_id": a.position_id,
                    "position_name": a.position.name if a.position_id and a.position else "",
                    "branch_id": a.branch_id,
                    "branch_name": a.branch.name if a.branch_id and a.branch else None,
                    "started_at": a.started_at.isoformat() if a.started_at else None,
                    "ended_at": a.ended_at.isoformat() if a.ended_at else None,
                }
            )
        return Response(
            {"count": total, "limit": limit, "offset": offset, "results": data},
            status=status.HTTP_200_OK,
        )

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
            created_by=request.user,
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


class EmployeeProvisionUserView(APIView):
    permission_classes = [
        rbac_permission("iam.users.create"),
        rbac_permission("hr.employee.update"),
    ]
    throttle_scope = "admin_writes"

    def post(self, request, employee_id: int):
        company: OrgUnit = request.company
        emp = get_object_or_404(Employee, id=employee_id, company=company)

        serializer = EmployeeProvisionUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            result = provision_user_for_employee(
                employee=emp,
                username=serializer.validated_data["username"],
                email=serializer.validated_data["email"],
                temp_password=serializer.validated_data.get("temp_password"),
                request=request,
                actor=request.user,
            )
            return Response(result, status=status.HTTP_201_CREATED)

        except ValueError as e:
            msg = str(e)
            if "ya tiene un usuario vinculado" in msg:
                raise ConflictError(detail=msg)
            # Both "no active assignment" and username conflict fall here as 400
            raise ValidationError({"detail": msg})


class EmployeeResetTempPasswordView(APIView):
    """
    POST /hr/employees/<id>/reset-temp-password/
    Requiere: iam.users.create + hr.employee.update (mismo estándar que provision)
    """

    permission_classes = [rbac_permission("iam.users.create"), rbac_permission("hr.employee.update")]
    throttle_scope = "admin_writes"

    def post(self, request, employee_id: int):
        company = request.company
        emp = Employee.objects.filter(id=employee_id, company=company).select_related("linked_user").first()
        if not emp:
            return Response({"detail": "Not found"}, status=status.HTTP_404_NOT_FOUND)

        ser = ResetTempPasswordSerializer(data=request.data or {})
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            out = reset_temp_password_for_employee(
                employee=emp,
                request=request,
                actor=request.user,
                temp_password=ser.validated_data.get("temp_password") or None,
            )
        except ValueError as e:
            code = str(e)
            if code == "EMPLOYEE_HAS_NO_LINKED_USER":
                return Response({"detail": "Employee has no linked user"}, status=status.HTTP_409_CONFLICT)
            if code == "EMPLOYEE_HAS_NO_ACTIVE_ASSIGNMENT":
                return Response({"detail": "Employee has no active assignment"}, status=status.HTTP_409_CONFLICT)
            return Response({"detail": "Invalid state"}, status=status.HTTP_409_CONFLICT)

        return Response(out, status=status.HTTP_200_OK)


class EmployeeRevokeAccessView(APIView):
    """
    POST /hr/employees/<id>/revoke-access/
    Requiere: iam.users.create + hr.employee.update (mismo estándar que provision/reset)
    """

    permission_classes = [rbac_permission("iam.users.create"), rbac_permission("hr.employee.update")]
    throttle_scope = "admin_writes"

    def post(self, request, employee_id: int):
        company = request.company
        employee = Employee.objects.select_related("linked_user").filter(company=company, id=employee_id).first()
        if employee is None:
            return Response({"detail": "Empleado no encontrado."}, status=status.HTTP_404_NOT_FOUND)

        s = EmployeeRevokeAccessSerializer(data=request.data or {})
        s.is_valid(raise_exception=True)

        try:
            out = revoke_employee_access(
                employee=employee,
                request=request,
                actor=request.user,
                disable_user=bool(s.validated_data.get("disable_user", False)),
            )
        except ValueError as e:
            if str(e) == "EMPLOYEE_HAS_NO_LINKED_USER":
                return Response({"detail": "El empleado no tiene usuario ligado."}, status=status.HTTP_409_CONFLICT)
            return Response({"detail": "Estado inválido."}, status=status.HTTP_409_CONFLICT)

        return Response(out, status=status.HTTP_200_OK)
