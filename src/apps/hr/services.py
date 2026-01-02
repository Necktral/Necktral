from __future__ import annotations

from dataclasses import dataclass

from django.db import transaction
from django.utils import timezone

from apps.audit.writer import write_event
from apps.iam.models import OrgUnit, UserMembership
from apps.rbac.models import RoleAssignment

from .models import Employee, EmploymentAssignment, JobPosition, PositionRoleMap

@dataclass(frozen=True)
class ReconcileResult:
    created: int
    reactivated: int
    deactivated: int

def _company_branches(company: OrgUnit) -> list[int]:
    return list(
        OrgUnit.objects.filter(parent=company, unit_type=OrgUnit.UnitType.BRANCH).values_list("id", flat=True)
    )

def _ensure_membership(user, org_unit: OrgUnit) -> None:
    UserMembership.objects.get_or_create(user=user, org_unit=org_unit, defaults={"is_active": True})

def reconcile_employee_roles(*, employee: Employee, request=None, actor=None) -> ReconcileResult:
    """
    Regla: SOLO toca RoleAssignment con origin=POSITION dentro del scope de la company del empleado.
    MANUAL y SYSTEM quedan intactos.
    """
    if employee.linked_user is None:
        return ReconcileResult(created=0, reactivated=0, deactivated=0)

    company = employee.company
    user = employee.linked_user

    branch_ids = _company_branches(company)
    scoped_orgunit_ids = [company.id] + branch_ids

    # 1) Desired grants desde assignments activos + maps activos
    desired: set[tuple[int, int]] = set()  # (role_id, org_unit_id)

    active_assignments = (
        EmploymentAssignment.objects.filter(employee=employee, is_active=True)
        .select_related("position", "branch")
        .all()
    )

    # Pre-cargar maps de puestos involucrados
    pos_ids = {a.position_id for a in active_assignments}
    maps = PositionRoleMap.objects.filter(position_id__in=list(pos_ids), is_active=True).select_related("role", "position")

    maps_by_position: dict[int, list[PositionRoleMap]] = {}
    for m in maps:
        maps_by_position.setdefault(m.position_id, []).append(m)

    for a in active_assignments:
        for m in maps_by_position.get(a.position_id, []):
            pass  # Aquí iría la lógica de grants
    created = reactivated = deactivated = 0

    with transaction.atomic():
        existing_qs = RoleAssignment.objects.filter(
            user=user,
            org_unit_id__in=scoped_orgunit_ids,
            origin=RoleAssignment.Origin.POSITION,
        )
        existing = {(ra.role_id, ra.org_unit_id): ra for ra in existing_qs.select_for_update()}

        # create/reactivate desired
        for (role_id, org_unit_id) in desired:
            pass  # Aquí iría la lógica de creación/reactivación
        # deactivate obsolete POSITION grants
        for (k, ra) in existing.items():
            pass  # Aquí iría la lógica de desactivación
        # memberships: agregar, no remover (robustez)
        for (_, org_unit_id) in desired:
            pass  # Aquí iría la lógica de membresía

    # audit
    write_event(
        request=request,
        module="HR",
        event_type="HR_RECONCILE_APPLIED",
        reason_code="OK",
        actor_user=actor,
        subject_type="EMPLOYEE",
        subject_id=str(employee.id),
        metadata={
            "created": created,
            "reactivated": reactivated,
            "deactivated": deactivated,
        },
    )

    return ReconcileResult(created=created, reactivated=reactivated, deactivated=deactivated)

def end_assignment(*, assignment: EmploymentAssignment, request=None, actor=None) -> None:
    if not assignment.is_active:
        return
    assignment.is_active = False
    assignment.ended_at = timezone.now()
    assignment.save(update_fields=["is_active", "ended_at"])

    write_event(
        request=request,
        module="HR",
        event_type="HR_ASSIGNMENT_ENDED",
        reason_code="OK",
        actor_user=actor,
        subject_type="EMPLOYEE",
        subject_id=str(assignment.employee_id),
        metadata={"assignment_id": assignment.id},
    )

    reconcile_employee_roles(employee=assignment.employee, request=request, actor=actor)

def set_position_role_maps(*, position: JobPosition, maps: list[dict], request=None, actor=None) -> None:
    """
    maps = [{"role_id": 1, "scope_mode":"BRANCH"}, ...]
    Reemplazo controlado: desactiva los existentes y activa/crea los nuevos.
    """
    with transaction.atomic():
        PositionRoleMap.objects.filter(position=position).update(is_active=False)

        for m in maps:
            pass  # Aquí iría la lógica de activación/creación
    write_event(
        request=request,
        module="HR",
        event_type="HR_POSITION_ROLEMAP_UPDATED",
        reason_code="OK",
        actor_user=actor,
        subject_type="POSITION",
        subject_id=str(position.id),
        metadata={"maps_count": len(maps)},
    )

    # Reconciliar empleados afectados (limitado a employees con linked_user)
    employee_ids = (
        EmploymentAssignment.objects.filter(position=position, is_active=True, employee__linked_user__isnull=False)
        .values_list("employee_id", flat=True)
        .distinct()
    )
    for eid in employee_ids:
        reconcile_employee_roles(employee=Employee.objects.get(id=eid), request=request, actor=actor)
