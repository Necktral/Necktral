import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.hr.models import Employee, JobPosition
from apps.iam.models import OrgUnit, UserMembership
from apps.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _mk_org():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C1", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B1", parent=company)
    return holding, company, branch


def _activate_perm(code: str) -> Permission:
    p, created = Permission.objects.get_or_create(code=code, defaults={"description": "", "is_active": True})
    if not created and not p.is_active:
        p.is_active = True
        p.save(update_fields=["is_active"])
    return p


def _client_for_user_with_perms(*, company: OrgUnit, perm_codes: list[str]) -> APIClient:
    username = f"u_{uuid.uuid4().hex[:10]}"
    user = User.objects.create_user(username=username, password="pass12345")

    UserMembership.objects.create(user=user, org_unit=company, is_active=True)

    role = Role.objects.create(name=f"r_{uuid.uuid4().hex[:10]}", is_active=True)
    for code in perm_codes:
        perm = _activate_perm(code)
        RolePermission.objects.get_or_create(role=role, permission=perm)

    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)

    client = APIClient()
    login = client.post("/api/auth/login/", {"username": username, "password": "pass12345"}, format="json")
    assert login.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    return client


@pytest.mark.django_db
def test_positions_post_denied_without_create_permission():
    _, company, _ = _mk_org()

    # Solo READ
    client = _client_for_user_with_perms(company=company, perm_codes=["hr.position.read"])

    r = client.post(
        "/api/hr/positions/",
        {"name": "Puesto X", "code": "PX"},
        format="json",
        HTTP_X_COMPANY_ID=str(company.id),
    )
    assert r.status_code == 403

    ev = AuditEvent.objects.filter(
        event_type="AUTH_ACCESS_DENIED",
        path="/api/hr/positions/",
        method="POST",
    ).latest("timestamp_server")

    assert ev.reason_code == "POLICY_PERMISSION_DENIED"
    assert ev.metadata.get("required_permission") == "hr.position.create"
    assert ev.metadata.get("required_scope", {}).get("company_id") == company.id
    assert ev.metadata.get("effective_scope", {}).get("company_id") == company.id


@pytest.mark.django_db
def test_positions_get_denied_without_read_permission():
    _, company, _ = _mk_org()

    # Solo CREATE (sin READ)
    client = _client_for_user_with_perms(company=company, perm_codes=["hr.position.create"])

    r = client.get(
        "/api/hr/positions/",
        HTTP_X_COMPANY_ID=str(company.id),
    )
    assert r.status_code == 403

    ev = AuditEvent.objects.filter(
        event_type="AUTH_ACCESS_DENIED",
        path="/api/hr/positions/",
        method="GET",
    ).latest("timestamp_server")

    assert ev.reason_code == "POLICY_PERMISSION_DENIED"
    assert ev.metadata.get("required_permission") == "hr.position.read"
    assert ev.metadata.get("required_scope", {}).get("company_id") == company.id


@pytest.mark.django_db
def test_employees_post_denied_without_employee_create_permission():
    _, company, _ = _mk_org()

    # Solo READ
    client = _client_for_user_with_perms(company=company, perm_codes=["hr.employee.read"])

    r = client.post(
        "/api/hr/employees/",
        {"first_name": "Ana", "last_name": "Lopez"},
        format="json",
        HTTP_X_COMPANY_ID=str(company.id),
    )
    assert r.status_code == 403

    ev = AuditEvent.objects.filter(
        event_type="AUTH_ACCESS_DENIED",
        path="/api/hr/employees/",
        method="POST",
    ).latest("timestamp_server")

    assert ev.metadata.get("required_permission") == "hr.employee.create"
    assert ev.metadata.get("required_scope", {}).get("company_id") == company.id


@pytest.mark.django_db
def test_assignment_post_denied_without_assignment_create_permission():
    _, company, branch = _mk_org()

    # Setup data (no depende de permisos)
    pos = JobPosition.objects.create(company=company, name="Vendedor", code="VEN", is_active=True)
    emp = Employee.objects.create(company=company, employee_code="E1", first_name="Juan", last_name="Perez", is_active=True)

    # Usuario sin hr.assignment.create
    client = _client_for_user_with_perms(company=company, perm_codes=["hr.employee.read"])

    r = client.post(
        f"/api/hr/employees/{emp.id}/assignments/",
        {"position_id": pos.id, "branch_id": branch.id},
        format="json",
        HTTP_X_COMPANY_ID=str(company.id),
    )
    assert r.status_code == 403

    ev = AuditEvent.objects.filter(
        event_type="AUTH_ACCESS_DENIED",
        path=f"/api/hr/employees/{emp.id}/assignments/",
        method="POST",
    ).latest("timestamp_server")

    assert ev.metadata.get("required_permission") == "hr.assignment.create"
    assert ev.metadata.get("required_scope", {}).get("company_id") == company.id
