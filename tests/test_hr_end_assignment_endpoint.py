import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.hr.models import Employee, EmploymentAssignment, JobPosition, PositionRoleMap
from apps.hr.services import reconcile_employee_roles
from apps.iam.models import OrgUnit, UserMembership
from apps.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _perm(code: str) -> Permission:
    p, _ = Permission.objects.get_or_create(code=code, defaults={"description": "", "is_active": True})
    if not p.is_active:
        p.is_active = True
        p.save(update_fields=["is_active"])
    return p


@pytest.mark.django_db
def test_end_assignment_endpoint_deactivates_assignment_and_position_roles():
    # Org
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B1", parent=company)

    # Admin actor (tiene permiso hr.assignment.end)
    admin = User.objects.create_user(username="admin_end", password="pass12345")
    UserMembership.objects.create(user=admin, org_unit=company, is_active=True)

    role = Role.objects.create(name=f"r_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in ["hr.assignment.end"]:
        RolePermission.objects.get_or_create(role=role, permission=_perm(code))
    RoleAssignment.objects.create(user=admin, role=role, org_unit=company, is_active=True)

    # Employee + linked user
    emp_user = User.objects.create_user(username="emp_u", password="pass12345")
    emp = Employee.objects.create(company=company, employee_code="E1", first_name="Juan", last_name="Perez", linked_user=emp_user, is_active=True)

    # Position + mapping -> role (branch scope)
    mapped_role = Role.objects.create(name="sales_rep", is_active=True)
    pos = JobPosition.objects.create(company=company, name="Vendedor", code="VEN", is_active=True)
    PositionRoleMap.objects.create(position=pos, role=mapped_role, scope_mode=PositionRoleMap.ScopeMode.BRANCH, is_active=True)

    # Active assignment in branch
    a = EmploymentAssignment.objects.create(employee=emp, position=pos, branch=branch, is_active=True)

    # Pre-reconcile: crea RoleAssignment origin=POSITION (para que luego se desactive)
    reconcile_employee_roles(employee=emp, request=None, actor=admin)
    ra = RoleAssignment.objects.get(user=emp_user, role=mapped_role, org_unit=branch, origin=RoleAssignment.Origin.POSITION)
    assert ra.is_active is True

    # Call endpoint
    client = APIClient()
    login = client.post("/api/auth/login/", {"username": "admin_end", "password": "pass12345"}, format="json")
    assert login.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    path = f"/api/hr/employees/{emp.id}/assignments/{a.id}/end/"
    r = client.post(path, {}, format="json", HTTP_X_COMPANY_ID=str(company.id))
    assert r.status_code == 200
    assert r.data["ok"] is True

    # Assignment ended
    a.refresh_from_db()
    assert a.is_active is False
    assert a.ended_at is not None

    # Position-origin role assignment deactivated
    ra.refresh_from_db()
    assert ra.is_active is False

    # Audit event from request path
    ev = AuditEvent.objects.filter(event_type="HR_ASSIGNMENT_ENDED", path=path, method="POST").latest("timestamp_server")
    assert ev.reason_code == "OK"
    assert ev.metadata.get("assignment_id") == a.id

    # Reconcile event on same request path: debe reflejar desactivación
    ev2 = AuditEvent.objects.filter(event_type="HR_RECONCILE_APPLIED", path=path, method="POST").latest("timestamp_server")
    assert int(ev2.metadata.get("deactivated", 0)) >= 1
