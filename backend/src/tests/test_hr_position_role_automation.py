import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.hr.models import EmploymentAssignment
from apps.hr.services import end_assignment
from apps.iam.models import OrgUnit, UserMembership
from apps.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


@pytest.mark.django_db
def test_hr_position_role_automation_end_to_end():
    # Org tree
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="HOLDING", code="H", is_active=True)
    company = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.COMPANY, parent=holding, name="ACME", code="AC", is_active=True
    )
    branch = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.BRANCH, parent=company, name="ACME-1", code="AC1", is_active=True
    )

    # Admin user (actor)
    admin = User.objects.create_user(username="admin", password="pass12345", email="admin@example.com")
    UserMembership.objects.create(user=admin, org_unit=company, is_active=True)

    # RBAC: admin role with HR permissions (so endpoints pass permission checks)
    admin_role = Role.objects.create(name="test_admin", is_active=True)
    for code in [
        "hr.position.read",
        "hr.position.create",
        "hr.position.roles.update",
        "hr.employee.read",
        "hr.employee.create",
        "hr.employee.update",
        "hr.assignment.create",
    ]:
        p = Permission.objects.create(code=code, is_active=True)
        RolePermission.objects.create(role=admin_role, permission=p)
    RoleAssignment.objects.create(user=admin, role=admin_role, org_unit=company, is_active=True)

    # Role to be granted via PositionRoleMap (POSITION origin)
    mapped_role = Role.objects.create(name="sales_rep", is_active=True)

    # Login
    client = APIClient()
    login = client.post("/api/auth/login/", {"username": "admin", "password": "pass12345"}, format="json")
    assert login.status_code == 200
    token = login.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

    # 1) Create position
    r_pos = client.post(
        "/api/hr/positions/",
        {"name": "Vendedor", "code": "VEN"},
        format="json",
        HTTP_X_COMPANY_ID=str(company.id),
    )
    assert r_pos.status_code == 201
    position_id = r_pos.data["id"]

    # 2) Map position -> role (BRANCH scope)
    r_map = client.put(
        f"/api/hr/positions/{position_id}/roles/",
        {"maps": [{"role_id": mapped_role.id, "scope_mode": "BRANCH"}]},
        format="json",
        HTTP_X_COMPANY_ID=str(company.id),
    )
    assert r_map.status_code == 200

    # 3) Create employee linked to a real user
    employee_user = User.objects.create_user(username="emp", password="pass12345", email="emp@example.com")
    r_emp = client.post(
        "/api/hr/employees/",
        {"first_name": "Juan", "last_name": "Perez", "linked_user_id": employee_user.id},
        format="json",
        HTTP_X_COMPANY_ID=str(company.id),
    )
    assert r_emp.status_code == 201
    employee_id = r_emp.data["id"]

    # 4) Create employment assignment at branch => should reconcile POSITION role assignment
    r_asg = client.post(
        f"/api/hr/employees/{employee_id}/assignments/",
        {"position_id": position_id, "branch_id": branch.id},
        format="json",
        HTTP_X_COMPANY_ID=str(company.id),
    )
    assert r_asg.status_code == 201
    assignment_id = r_asg.data["id"]

    assert RoleAssignment.objects.filter(
        user=employee_user,
        role=mapped_role,
        org_unit=branch,
        origin=RoleAssignment.Origin.POSITION,
        is_active=True,
    ).exists()

    # membership on branch should exist to make branch-scope usable
    assert UserMembership.objects.filter(user=employee_user, org_unit=branch, is_active=True).exists()

    # audit events exist (signals that contracts allow HR event types)
    assert AuditEvent.objects.filter(event_type="HR_POSITION_CREATED").exists()
    assert AuditEvent.objects.filter(event_type="HR_POSITION_ROLEMAP_UPDATED").exists()
    assert AuditEvent.objects.filter(event_type="HR_EMPLOYEE_CREATED").exists()
    assert AuditEvent.objects.filter(event_type="HR_ASSIGNMENT_CREATED").exists()
    assert AuditEvent.objects.filter(event_type="HR_RECONCILE_APPLIED").exists()

    # 5) End assignment => should deactivate POSITION role assignment
    assignment = EmploymentAssignment.objects.get(id=assignment_id)
    end_assignment(assignment=assignment)

    assert not RoleAssignment.objects.filter(
        user=employee_user,
        role=mapped_role,
        org_unit=branch,
        origin=RoleAssignment.Origin.POSITION,
        is_active=True,
    ).exists()

    assert AuditEvent.objects.filter(event_type="HR_ASSIGNMENT_ENDED").exists()
