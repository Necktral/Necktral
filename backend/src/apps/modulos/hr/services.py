"""Servicios de RRHH (precedente).

Precedente:
- La lógica de RRHH puede impactar autorización (RoleAssignment) y por eso debe ser transaccional,
  auditable y limitada por origen.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Set

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import get_random_string

from apps.modulos.audit.writer import write_event
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Role, RoleAssignment

from .models import Employee, EmploymentAssignment, JobPosition, PositionRoleMap

User = get_user_model()


def _make_temp_password(user_model=User) -> str:
    # Evita dependencias: usa util estándar ya usado en provisioning
    return get_random_string(length=12)


@dataclass(frozen=True)
class ReconcileResult:
    created: int
    reactivated: int
    deactivated: int


def _company_branches(company: OrgUnit) -> list[int]:
    return list(OrgUnit.objects.filter(parent=company, unit_type=OrgUnit.UnitType.BRANCH).values_list("id", flat=True))


def _ensure_membership(user, org_unit: OrgUnit) -> None:
    mem, created = UserMembership.objects.get_or_create(user=user, org_unit=org_unit, defaults={"is_active": True})
    if not created and not mem.is_active:
        mem.is_active = True
        mem.left_at = None
        mem.save(update_fields=["is_active", "left_at"])


def reconcile_employee_roles(*, employee: Employee, request=None, actor=None) -> ReconcileResult:
    """
    Regla: SOLO toca RoleAssignment con origin=POSITION dentro del scope de la company del empleado.
    MANUAL y SYSTEM quedan intactos.

    Precedente de seguridad:
    - No se “expanden” permisos fuera del scope de company+branches.
    - Cambios se realizan dentro de una transacción para evitar estados parciales.
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
    maps = PositionRoleMap.objects.filter(position_id__in=list(pos_ids), is_active=True).select_related(
        "role", "position"
    )

    maps_by_position: dict[int, list[PositionRoleMap]] = {}
    for m in maps:
        maps_by_position.setdefault(m.position_id, []).append(m)

    for a in active_assignments:
        for m in maps_by_position.get(a.position_id, []):
            if m.scope_mode == PositionRoleMap.ScopeMode.COMPANY:
                desired.add((m.role_id, company.id))
            elif m.scope_mode == PositionRoleMap.ScopeMode.BRANCH:
                if a.branch_id:
                    desired.add((m.role_id, a.branch_id))
    created = reactivated = deactivated = 0

    with transaction.atomic():
        existing_qs = RoleAssignment.objects.filter(
            user=user,
            org_unit_id__in=scoped_orgunit_ids,
            origin=RoleAssignment.Origin.POSITION,
        )
        existing = {(ra.role_id, ra.org_unit_id): ra for ra in existing_qs.select_for_update()}

        # create/reactivate desired
        for role_id, org_unit_id in desired:
            ra = existing.get((role_id, org_unit_id))
            if ra is None:
                RoleAssignment.objects.create(
                    user=user,
                    role_id=role_id,
                    org_unit_id=org_unit_id,
                    origin=RoleAssignment.Origin.POSITION,
                    origin_ref=f"employee:{employee.id}",
                    granted_by=actor,
                    is_active=True,
                )
                created += 1
            else:
                if not ra.is_active:
                    ra.is_active = True
                    ra.origin_ref = f"employee:{employee.id}"
                    if actor:
                        ra.granted_by = actor
                    ra.save(update_fields=["is_active", "origin_ref", "granted_by"])
                    reactivated += 1

        # deactivate obsolete POSITION grants
        for (role_id, org_unit_id), ra in existing.items():
            if (role_id, org_unit_id) in desired:
                continue
            if ra.is_active:
                ra.is_active = False
                ra.save(update_fields=["is_active"])
                deactivated += 1

        # memberships: agregar, no remover (robustez)
        #
        # Cambio: NO forzar membership a COMPANY siempre.
        # Base = asignaciones activas (branch o company si assignment sin branch)
        # + org units implicadas por role maps (desired)
        membership_ids: Set[int] = set()

        for a in active_assignments:
            if a.branch_id:
                membership_ids.add(a.branch_id)
            else:
                membership_ids.add(company.id)

        for _, org_unit_id in desired:
            membership_ids.add(org_unit_id)

        if membership_ids:
            org_map = OrgUnit.objects.in_bulk(list(membership_ids))
            for org_unit_id in membership_ids:
                ou = org_map.get(org_unit_id)
                if ou:
                    _ensure_membership(user, ou)

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
            role_id = int(m["role_id"])
            scope_mode = str(m.get("scope_mode", PositionRoleMap.ScopeMode.BRANCH)).upper().strip()
            if scope_mode not in PositionRoleMap.ScopeMode.values:
                raise ValueError(f"scope_mode inválido: {scope_mode}")
            if not Role.objects.filter(id=role_id).exists():
                raise ValueError(f"role_id no existe: {role_id}")

            obj, created = PositionRoleMap.objects.get_or_create(
                position=position,
                role_id=role_id,
                scope_mode=scope_mode,
                defaults={"is_active": True},
            )
            if not created and not obj.is_active:
                obj.is_active = True
                obj.save(update_fields=["is_active"])
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


def provision_user_for_employee(
    *, employee: Employee, username: str, email: str | None, temp_password: str | None = None, request=None, actor=None
) -> dict:
    # Validaciones de negocio
    if employee.linked_user_id is not None:
        raise ValueError("El empleado ya tiene un usuario vinculado.")

    has_assignment = EmploymentAssignment.objects.filter(employee=employee, is_active=True).exists()
    if not has_assignment:
        raise ValueError("El empleado no tiene ninguna asignación activa. No se puede determinar el contexto.")

    if not temp_password:
        temp_password = get_random_string(length=12)

    normalized_email = (email or "").strip() or None

    with transaction.atomic():
        # Crear usuario
        if User.objects.filter(username=username).exists():
            raise ValueError(f"El username '{username}' ya existe.")

        if normalized_email and User.objects.filter(email=normalized_email).exists():
            raise ValueError(f"El email '{normalized_email}' ya existe.")

        user = User.objects.create_user(
            username=username,
            email=normalized_email,
            password=temp_password,
        )
        user.must_change_password = True
        user.is_active = True
        user.save(update_fields=["must_change_password", "is_active"])

        # Linkear
        employee.linked_user = user
        employee.save(update_fields=["linked_user"])

        # Reconciliar roles
        reconcile_employee_roles(employee=employee, request=request, actor=actor)

    write_event(
        request=request,
        module="HR",
        event_type="HR_EMPLOYEE_USER_PROVISIONED",
        reason_code="OK",
        actor_user=actor,
        subject_type="EMPLOYEE",
        subject_id=str(employee.id),
        metadata={"created_user_id": user.id, "username": user.username},
    )

    return {"user_id": user.id, "username": user.username, "temp_password": temp_password}


@transaction.atomic
def reset_temp_password_for_employee(
    *,
    employee: Employee,
    request=None,
    actor=None,
    temp_password: Optional[str] = None,
) -> dict:
    """
    Resetea contraseña provisional del usuario ligado a un empleado.
    Reglas:
      - Debe existir linked_user
      - Debe existir al menos 1 asignación activa (coherente con provisioning)
      - Fuerza must_change_password=True
      - Audita sin exponer la contraseña
    """
    if not employee.linked_user_id or not employee.linked_user:
        raise ValueError("EMPLOYEE_HAS_NO_LINKED_USER")

    has_active_assignment = EmploymentAssignment.objects.filter(employee=employee, is_active=True).exists()
    if not has_active_assignment:
        raise ValueError("EMPLOYEE_HAS_NO_ACTIVE_ASSIGNMENT")

    user = employee.linked_user
    pwd = (temp_password or "").strip() or _make_temp_password(User)

    user.set_password(pwd)
    user.must_change_password = True
    user.save(update_fields=["password", "must_change_password"])

    # Reconcile por consistencia (si el puesto cambió, o scopes cambiaron)
    reconcile_employee_roles(employee=employee, request=request, actor=actor)

    write_event(
        request=request,
        module="HR",
        event_type="HR_EMPLOYEE_TEMP_PASSWORD_RESET",
        reason_code="OK",
        actor_user=actor,
        subject_type="EMPLOYEE",
        subject_id=str(employee.id),
        metadata={
            "linked_user_id": user.id,
            "linked_username": user.username,
            "manual_password": bool((temp_password or "").strip()),
        },
    )

    return {"user_id": user.id, "username": user.username, "temp_password": pwd}


@transaction.atomic
def revoke_employee_access(
    *,
    employee: Employee,
    request=None,
    actor=None,
    disable_user: bool = False,
) -> dict:
    """
    B = revoke-access:
    - Desactiva RoleAssignments origin=POSITION en scope company + branches
    - Desactiva memberships del linked_user en scope company + branches
    - Opcional: user.is_active=False si el usuario ya no tiene memberships activas en ninguna otra org_unit
    - Audita HR_EMPLOYEE_ACCESS_REVOKED
    """
    if employee.linked_user is None:
        raise ValueError("EMPLOYEE_HAS_NO_LINKED_USER")

    user = employee.linked_user
    company = employee.company

    branch_ids = _company_branches(company)
    scoped_orgunit_ids = [company.id, *branch_ids]

    # 1) RoleAssignments origin=POSITION
    ra_qs = RoleAssignment.objects.filter(
        user=user,
        org_unit_id__in=scoped_orgunit_ids,
        origin=RoleAssignment.Origin.POSITION,
        is_active=True,
    )
    ra_deactivated = ra_qs.update(is_active=False)

    # 2) Memberships (company + branches)
    mem_qs = UserMembership.objects.filter(
        user=user,
        org_unit_id__in=scoped_orgunit_ids,
        is_active=True,
    )
    mem_deactivated = mem_qs.update(is_active=False, left_at=timezone.now())

    # 3) Opcional: user.is_active=False (solo si no queda activo en otro lado)
    user_disabled = False
    if disable_user:
        still_has_active_memberships = UserMembership.objects.filter(user=user, is_active=True).exists()
        if not still_has_active_memberships and user.is_active:
            user.is_active = False
            user.save(update_fields=["is_active"])
            user_disabled = True

    # 4) Auditoría
    write_event(
        request=request,
        module="HR",
        event_type="HR_EMPLOYEE_ACCESS_REVOKED",
        reason_code="OK",
        actor_user=actor,
        subject_type="EMPLOYEE",
        subject_id=str(employee.id),
        metadata={
            "company_id": company.id,
            "employee_id": employee.id,
            "linked_user_id": user.id,
            "role_assignments_deactivated": ra_deactivated,
            "memberships_deactivated": mem_deactivated,
            "user_disabled": user_disabled,
            "disable_user_requested": bool(disable_user),
        },
    )

    return {
        "ok": True,
        "employee_id": employee.id,
        "linked_user_id": user.id,
        "role_assignments_deactivated": ra_deactivated,
        "memberships_deactivated": mem_deactivated,
        "user_disabled": user_disabled,
    }
