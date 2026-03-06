import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from apps.iam.models import OrgUnit
from apps.hr.models import Employee, JobPosition, EmploymentAssignment

User = get_user_model()


@pytest.mark.django_db
def test_provision_user_success():
    # Setup
    company = OrgUnit.objects.create(name="ACME", unit_type=OrgUnit.UnitType.COMPANY)
    emp = Employee.objects.create(company=company, first_name="Juan", last_name="Perez", email="juan@test.com")
    pos = JobPosition.objects.create(company=company, name="Desarrollador")
    EmploymentAssignment.objects.create(employee=emp, position=pos)

    # User to act
    admin = User.objects.create_superuser("admin", "admin@test.com", "pass")

    # Membership
    from apps.iam.models import UserMembership

    UserMembership.objects.create(user=admin, org_unit=company, is_active=True)

    client = APIClient()
    # Login to get token
    resp_login = client.post("/api/auth/login/", {"username": "admin", "password": "pass"})
    token = resp_login.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}", HTTP_X_COMPANY_ID=str(company.id))

    # Grant permission
    from apps.rbac.models import Permission, Role, RoleAssignment, RolePermission

    perm_update, _ = Permission.objects.get_or_create(code="hr.employee.update")
    perm_create_user, _ = Permission.objects.get_or_create(code="iam.users.create")
    role = Role.objects.create(name="HR Admin")
    RolePermission.objects.create(role=role, permission=perm_update)
    RolePermission.objects.create(role=role, permission=perm_create_user)
    # Assign role in the company context
    RoleAssignment.objects.create(user=admin, role=role, org_unit=company, origin="MANUAL")

    # Call endpoint
    url = f"/api/hr/employees/{emp.id}/provision-user/"
    payload = {"username": "juan.perez", "email": "juan@test.com"}

    response = client.post(url, payload, format="json")

    assert response.status_code == 201
    assert response.data["username"] == "juan.perez"
    assert "temp_password" in response.data

    emp.refresh_from_db()
    assert emp.linked_user is not None
    assert emp.linked_user.username == "juan.perez"
    assert emp.linked_user.must_change_password is True


@pytest.mark.django_db
def test_provision_user_no_assignment_fails():
    company = OrgUnit.objects.create(name="ACME2", unit_type=OrgUnit.UnitType.COMPANY)
    emp = Employee.objects.create(company=company, first_name="Pedro", last_name="Gol")

    admin = User.objects.create_superuser("admin2", "admin2@test.com", "pass")

    # Membership
    from apps.iam.models import UserMembership

    UserMembership.objects.create(user=admin, org_unit=company, is_active=True)

    client = APIClient()
    # Login
    resp_login = client.post("/api/auth/login/", {"username": "admin2", "password": "pass"})
    token = resp_login.data["access"]
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}", HTTP_X_COMPANY_ID=str(company.id))

    # Ensure perm
    from apps.rbac.models import Permission, Role, RolePermission, RoleAssignment

    perm_update, _ = Permission.objects.get_or_create(code="hr.employee.update")
    perm_create_user, _ = Permission.objects.get_or_create(code="iam.users.create")
    role = Role.objects.create(name="HR Admin 2")
    RolePermission.objects.create(role=role, permission=perm_update)
    RolePermission.objects.create(role=role, permission=perm_create_user)
    RoleAssignment.objects.create(user=admin, role=role, org_unit=company, origin="MANUAL")

    url = f"/api/hr/employees/{emp.id}/provision-user/"
    payload = {"username": "pedro", "email": "pedro@test.com"}

    response = client.post(url, payload, format="json")
    assert response.status_code == 422
    assert "no tiene ninguna asignación activa" in response.data["error"]["message"]
