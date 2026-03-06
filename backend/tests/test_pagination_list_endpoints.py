import uuid

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.hr.models import Employee, EmploymentAssignment, JobPosition
from apps.iam.models import OrgUnit, UserMembership
from apps.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _mk_user_with_company_access(*, username: str, company: OrgUnit, perm_codes: list[str]) -> APIClient:
    user = User.objects.create_user(username=username, password="pass12345")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)

    role = Role.objects.create(name=f"role_{username}_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perm_codes:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"is_active": True, "description": ""})
        if not perm.is_active:
            perm.is_active = True
            perm.save(update_fields=["is_active"])
        RolePermission.objects.get_or_create(role=role, permission=perm)

    RoleAssignment.objects.get_or_create(user=user, role=role, org_unit=company, defaults={"is_active": True})

    client = APIClient()
    login = client.post("/api/auth/login/", {"username": username, "password": "pass12345"}, format="json")
    assert login.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    return client


@pytest.mark.django_db
def test_org_companies_pagination_limit_offset():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    c1 = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="A", parent=holding)
    c2 = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="B", parent=holding)
    c3 = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)

    client = _mk_user_with_company_access(
        username="u_org_pag",
        company=c1,
        perm_codes=["org.company.read"],
    )
    UserMembership.objects.create(user=User.objects.get(username="u_org_pag"), org_unit=c2, is_active=True)
    UserMembership.objects.create(user=User.objects.get(username="u_org_pag"), org_unit=c3, is_active=True)

    r = client.get(
        "/api/org/companies/?limit=1&offset=1",
        HTTP_X_COMPANY_ID=str(c1.id),
    )
    assert r.status_code == 200
    assert r.data["count"] == 3
    assert r.data["limit"] == 1
    assert r.data["offset"] == 1
    assert len(r.data["results"]) == 1
    assert r.data["results"][0]["name"] == "B"


@pytest.mark.django_db
def test_org_branches_pagination_limit_offset():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C1", parent=holding)
    OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="A", parent=company)
    OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="C", parent=company)

    client = _mk_user_with_company_access(
        username="u_branch_pag",
        company=company,
        perm_codes=["org.branch.read"],
    )

    r = client.get(
        "/api/org/branches/?limit=2&offset=1",
        HTTP_X_COMPANY_ID=str(company.id),
    )
    assert r.status_code == 200
    assert r.data["count"] == 3
    assert r.data["limit"] == 2
    assert r.data["offset"] == 1
    assert len(r.data["results"]) == 2
    assert r.data["results"][0]["name"] == "B"


@pytest.mark.django_db
def test_hr_employees_pagination_limit_offset():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C1", parent=holding)

    Employee.objects.create(company=company, first_name="Ana", last_name="A")
    Employee.objects.create(company=company, first_name="Beto", last_name="B")
    Employee.objects.create(company=company, first_name="Caro", last_name="C")

    client = _mk_user_with_company_access(
        username="u_emp_pag",
        company=company,
        perm_codes=["hr.employee.read"],
    )

    r = client.get(
        "/api/hr/employees/?limit=1&offset=1",
        HTTP_X_COMPANY_ID=str(company.id),
    )
    assert r.status_code == 200
    assert r.data["count"] == 3
    assert r.data["limit"] == 1
    assert r.data["offset"] == 1
    assert len(r.data["results"]) == 1
    assert r.data["results"][0]["first_name"] == "Beto"


@pytest.mark.django_db
def test_hr_assignments_pagination_limit_offset():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C1", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B1", parent=company)

    employee = Employee.objects.create(company=company, first_name="Ana", last_name="A")
    position = JobPosition.objects.create(company=company, name="P1", code="")
    now = timezone.now()
    EmploymentAssignment.objects.create(
        employee=employee,
        position=position,
        branch=branch,
        is_active=True,
        started_at=now,
    )
    EmploymentAssignment.objects.create(
        employee=employee,
        position=position,
        branch=branch,
        is_active=False,
        started_at=now - timezone.timedelta(days=1),
        ended_at=now,
    )

    client = _mk_user_with_company_access(
        username="u_asg_pag",
        company=company,
        perm_codes=["hr.assignment.read"],
    )

    r = client.get(
        f"/api/hr/employees/{employee.id}/assignments/?limit=1&offset=0",
        HTTP_X_COMPANY_ID=str(company.id),
    )
    assert r.status_code == 200
    assert r.data["count"] == 2
    assert r.data["limit"] == 1
    assert r.data["offset"] == 0
    assert len(r.data["results"]) == 1
    assert r.data["results"][0]["is_active"] is True


@pytest.mark.django_db
def test_rbac_roles_permissions_pagination_limit_offset():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C1", parent=holding)

    Role.objects.create(name="A", is_active=True)
    Role.objects.create(name="B", is_active=True)
    Role.objects.create(name="C", is_active=True)

    Permission.objects.create(code="a.read", is_active=True)
    Permission.objects.create(code="b.read", is_active=True)
    Permission.objects.create(code="c.read", is_active=True)

    client = _mk_user_with_company_access(
        username="u_rbac_pag",
        company=company,
        perm_codes=["rbac.roles.read", "rbac.permissions.read"],
    )

    r_roles = client.get("/api/rbac/roles/?limit=1&offset=1", HTTP_X_COMPANY_ID=str(company.id))
    assert r_roles.status_code == 200
    assert r_roles.data["count"] == 4
    assert r_roles.data["limit"] == 1
    assert r_roles.data["offset"] == 1
    assert len(r_roles.data["results"]) == 1
    assert r_roles.data["results"][0]["name"] == "B"

    r_perms = client.get(
        "/api/rbac/permissions/?limit=1&offset=2",
        HTTP_X_COMPANY_ID=str(company.id),
    )
    assert r_perms.status_code == 200
    assert r_perms.data["count"] == 5
    assert r_perms.data["limit"] == 1
    assert r_perms.data["offset"] == 2
    assert len(r_perms.data["results"]) == 1
    assert r_perms.data["results"][0]["code"] == "c.read"
