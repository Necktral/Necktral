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
    @pytest.mark.django_db
    def test_employee_list_includes_active_assignment_summary():
        holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
        company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
        branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B1", parent=company)

        admin = User.objects.create_user(
            username="admin_list_emp", password="pass12345", email=f"admin_list_emp_{uuid.uuid4().hex[:8]}@test.com"
        )
        UserMembership.objects.create(user=admin, org_unit=company, is_active=True)

        role = Role.objects.create(name=f"r_{uuid.uuid4().hex[:8]}", is_active=True)
        for code in ["hr.employee.read"]:
            RolePermission.objects.get_or_create(role=role, permission=_perm(code))
        RoleAssignment.objects.create(user=admin, role=role, org_unit=company, is_active=True)

        pos = JobPosition.objects.create(company=company, name="Vendedor", code="VEN", is_active=True)
        emp = Employee.objects.create(company=company, employee_code="E1", first_name="Juan", last_name="Perez", is_active=True)
        EmploymentAssignment.objects.create(employee=emp, position=pos, branch=branch, is_active=True)

        client = APIClient()
        login = client.post("/api/auth/login/", {"username": "admin_list_emp", "password": "pass12345"}, format="json")
        assert login.status_code == 200
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

        r = client.get("/api/hr/employees/", HTTP_X_COMPANY_ID=str(company.id))
        assert r.status_code == 200
        row = next(x for x in r.data if x["id"] == emp.id)
        assert row["has_active_assignment"] is True
        assert isinstance(row["active_assignments"], list)
        assert len(row["active_assignments"]) == 1
        a0 = row["active_assignments"][0]
        assert a0["position_name"] == "Vendedor"
        assert a0["branch_name"] == "B1"


    @pytest.mark.django_db
    def test_list_employee_assignments_endpoint_returns_rows():
        holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
        company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
        branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B1", parent=company)

        admin = User.objects.create_user(
            username="admin_list_asg", password="pass12345", email=f"admin_list_asg_{uuid.uuid4().hex[:8]}@test.com"
        )
        UserMembership.objects.create(user=admin, org_unit=company, is_active=True)

        role = Role.objects.create(name=f"r_{uuid.uuid4().hex[:8]}", is_active=True)
        for code in ["hr.assignment.read"]:
            RolePermission.objects.get_or_create(role=role, permission=_perm(code))
        RoleAssignment.objects.create(user=admin, role=role, org_unit=company, is_active=True)

        pos = JobPosition.objects.create(company=company, name="Vendedor", code="VEN", is_active=True)
        emp = Employee.objects.create(company=company, employee_code="E1", first_name="Juan", last_name="Perez", is_active=True)
        a = EmploymentAssignment.objects.create(employee=emp, position=pos, branch=branch, is_active=True)

        client = APIClient()
        login = client.post("/api/auth/login/", {"username": "admin_list_asg", "password": "pass12345"}, format="json")
        assert login.status_code == 200
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

        r = client.get(f"/api/hr/employees/{emp.id}/assignments/", HTTP_X_COMPANY_ID=str(company.id))
        assert r.status_code == 200
        assert isinstance(r.data, list)
        ids = [x["id"] for x in r.data]
        assert a.id in ids
    # Org
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B1", parent=company)

    # Admin actor (tiene permiso hr.assignment.end)
    admin = User.objects.create_user(
        username="admin_end", password="pass12345", email=f"admin_end_{uuid.uuid4().hex[:8]}@test.com"
    )
    UserMembership.objects.create(user=admin, org_unit=company, is_active=True)

    role = Role.objects.create(name=f"r_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in ["hr.assignment.end"]:
        RolePermission.objects.get_or_create(role=role, permission=_perm(code))
    RoleAssignment.objects.create(user=admin, role=role, org_unit=company, is_active=True)

    # Employee + linked user
    emp_user = User.objects.create_user(
        username="emp_u", password="pass12345", email=f"emp_u_{uuid.uuid4().hex[:8]}@test.com"
    )
    emp = Employee.objects.create(
        company=company, employee_code="E1", first_name="Juan", last_name="Perez", linked_user=emp_user, is_active=True
    )

    # Position + mapping -> role (branch scope)
    mapped_role = Role.objects.create(name="sales_rep", is_active=True)
    pos = JobPosition.objects.create(company=company, name="Vendedor", code="VEN", is_active=True)
    PositionRoleMap.objects.create(
        position=pos, role=mapped_role, scope_mode=PositionRoleMap.ScopeMode.BRANCH, is_active=True
    )

    # Active assignment in branch
    a = EmploymentAssignment.objects.create(employee=emp, position=pos, branch=branch, is_active=True)

    # Pre-reconcile: crea RoleAssignment origin=POSITION (para que luego se desactive)
    reconcile_employee_roles(employee=emp, request=None, actor=admin)
    ra = RoleAssignment.objects.get(
        user=emp_user, role=mapped_role, org_unit=branch, origin=RoleAssignment.Origin.POSITION
    )
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
    ev = AuditEvent.objects.filter(event_type="HR_ASSIGNMENT_ENDED", path=path, method="POST").latest(
        "timestamp_server"
    )
    assert ev.reason_code == "OK"
    assert ev.metadata.get("assignment_id") == a.id

    # Reconcile event on same request path: debe reflejar desactivación
    ev2 = AuditEvent.objects.filter(event_type="HR_RECONCILE_APPLIED", path=path, method="POST").latest(
        "timestamp_server"
    )
    assert int(ev2.metadata.get("deactivated", 0)) >= 1


@pytest.mark.django_db
def test_hr_reset_temp_password_success_and_audit():
    # Setup org
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B1", parent=company)

    # Admin con permisos (reusamos iam.users.create + hr.employee.update)
    admin = User.objects.create_user(
        username="admin_reset",
        password="pass12345",
        email=f"admin_reset_{uuid.uuid4().hex[:8]}@test.com",
    )
    UserMembership.objects.create(user=admin, org_unit=company, is_active=True)

    role = Role.objects.create(name=f"r_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in ["iam.users.create", "hr.employee.update", "hr.employee.read"]:
        RolePermission.objects.get_or_create(role=role, permission=_perm(code))
    RoleAssignment.objects.create(user=admin, role=role, org_unit=company, is_active=True)

    # Empleado con usuario ligado + asignación activa
    linked = User.objects.create_user(username="emp_u1", password="x")
    emp = Employee.objects.create(
        company=company,
        employee_code="E1",
        first_name="Juan",
        last_name="Perez",
        is_active=True,
        linked_user=linked,
    )
    pos = JobPosition.objects.create(company=company, name="Vendedor", code="VEN", is_active=True)
    EmploymentAssignment.objects.create(employee=emp, position=pos, branch=branch, is_active=True)

    client = APIClient()
    login = client.post("/api/auth/login/", {"username": "admin_reset", "password": "pass12345"}, format="json")
    assert login.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    r = client.post(
        f"/api/hr/employees/{emp.id}/reset-temp-password/",
        {},
        format="json",
        HTTP_X_COMPANY_ID=str(company.id),
    )
    assert r.status_code == 200
    assert r.data["user_id"] == linked.id
    assert r.data["username"] == "emp_u1"
    assert isinstance(r.data["temp_password"], str) and len(r.data["temp_password"]) >= 8

    linked.refresh_from_db()
    assert linked.must_change_password is True

    ev = AuditEvent.objects.filter(event_type="HR_EMPLOYEE_TEMP_PASSWORD_RESET", subject_id=str(emp.id)).latest(
        "timestamp_server"
    )
    assert ev.reason_code == "OK"
    assert ev.metadata.get("linked_user_id") == linked.id
    assert ev.metadata.get("linked_username") == "emp_u1"
    assert "temp_password" not in (ev.metadata or {})


@pytest.mark.django_db
def test_hr_reset_temp_password_409_when_no_linked_user():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)

    admin = User.objects.create_user(username="admin_reset2", password="pass12345")
    UserMembership.objects.create(user=admin, org_unit=company, is_active=True)

    role = Role.objects.create(name=f"r_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in ["iam.users.create", "hr.employee.update", "hr.employee.read"]:
        RolePermission.objects.get_or_create(role=role, permission=_perm(code))
    RoleAssignment.objects.create(user=admin, role=role, org_unit=company, is_active=True)

    emp = Employee.objects.create(
        company=company,
        employee_code="E1",
        first_name="Juan",
        last_name="Perez",
        is_active=True,
    )

    client = APIClient()
    login = client.post("/api/auth/login/", {"username": "admin_reset2", "password": "pass12345"}, format="json")
    assert login.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    r = client.post(
        f"/api/hr/employees/{emp.id}/reset-temp-password/",
        {},
        format="json",
        HTTP_X_COMPANY_ID=str(company.id),
    )
    assert r.status_code == 409
