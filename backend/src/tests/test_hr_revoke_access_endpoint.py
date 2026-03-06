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
def test_hr_revoke_access_deactivates_memberships_and_position_roles_and_audits():
    # Org
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B1", parent=company)

    # Admin actor with perms
    admin = User.objects.create_user(
        username="admin_revoke",
        password="pass12345",
        email=f"admin_revoke_{uuid.uuid4().hex[:8]}@test.com",
    )
    UserMembership.objects.create(user=admin, org_unit=company, is_active=True)

    role = Role.objects.create(name=f"r_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in ["iam.users.create", "hr.employee.update"]:
        RolePermission.objects.get_or_create(role=role, permission=_perm(code))
    RoleAssignment.objects.create(user=admin, role=role, org_unit=company, is_active=True)

    # Employee + linked user + assignment + PositionRoleMap => creates POSITION RoleAssignment + branch membership
    linked = User.objects.create_user(username="emp_revoke_u", password="x")
    emp = Employee.objects.create(
        company=company,
        employee_code="E1",
        first_name="Juan",
        last_name="Perez",
        linked_user=linked,
    )

    mapped_role = Role.objects.create(name="sales_rep_revoke", is_active=True)
    pos = JobPosition.objects.create(company=company, name="Vendedor", code="VEN", is_active=True)
    PositionRoleMap.objects.create(position=pos, role=mapped_role, scope_mode=PositionRoleMap.ScopeMode.BRANCH, is_active=True)
    EmploymentAssignment.objects.create(employee=emp, position=pos, branch=branch, is_active=True)

    reconcile_employee_roles(employee=emp, request=None, actor=admin)

    assert RoleAssignment.objects.filter(
        user=linked,
        role=mapped_role,
        org_unit=branch,
        origin=RoleAssignment.Origin.POSITION,
        is_active=True,
    ).exists()
    assert UserMembership.objects.filter(user=linked, org_unit=branch, is_active=True).exists()

    # Call endpoint
    client = APIClient()
    login = client.post("/api/auth/login/", {"username": "admin_revoke", "password": "pass12345"}, format="json")
    assert login.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    path = f"/api/hr/employees/{emp.id}/revoke-access/"
    r = client.post(path, {"disable_user": False}, format="json", HTTP_X_COMPANY_ID=str(company.id))
    assert r.status_code == 200
    assert r.data["ok"] is True

    # Verify deactivated
    assert not UserMembership.objects.filter(user=linked, org_unit=branch, is_active=True).exists()
    ra = RoleAssignment.objects.get(user=linked, role=mapped_role, org_unit=branch, origin=RoleAssignment.Origin.POSITION)
    ra.refresh_from_db()
    assert ra.is_active is False

    # Audit exists
    ev = AuditEvent.objects.filter(event_type="HR_EMPLOYEE_ACCESS_REVOKED", path=path, method="POST").latest("timestamp_server")
    assert ev.reason_code == "OK"
    assert ev.metadata.get("employee_id") == emp.id


@pytest.mark.django_db
def test_hr_revoke_access_409_when_no_linked_user():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)

    admin = User.objects.create_user(username="admin_revoke2", password="pass12345")
    UserMembership.objects.create(user=admin, org_unit=company, is_active=True)

    role = Role.objects.create(name=f"r_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in ["iam.users.create", "hr.employee.update"]:
        RolePermission.objects.get_or_create(role=role, permission=_perm(code))
    RoleAssignment.objects.create(user=admin, role=role, org_unit=company, is_active=True)

    emp = Employee.objects.create(company=company, employee_code="E1", first_name="Juan", last_name="Perez")

    client = APIClient()
    login = client.post("/api/auth/login/", {"username": "admin_revoke2", "password": "pass12345"}, format="json")
    assert login.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    r = client.post(
        f"/api/hr/employees/{emp.id}/revoke-access/",
        {"disable_user": False},
        format="json",
        HTTP_X_COMPANY_ID=str(company.id),
    )
    assert r.status_code == 409
