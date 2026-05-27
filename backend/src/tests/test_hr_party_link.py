import uuid

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.modulos.audit.models import AuditEvent
from apps.modulos.hr import services as hr_services
from apps.modulos.hr.models import Employee
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.parties.models import Party, PartyRole
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _org_tree(*, suffix: str = ""):
    holding = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.HOLDING,
        name=f"Holding{suffix}",
        code=f"H{suffix}",
        is_active=True,
    )
    company = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.COMPANY,
        parent=holding,
        name=f"Company{suffix}",
        code=f"C{suffix}",
        is_active=True,
    )
    branch = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.BRANCH,
        parent=company,
        name=f"Branch{suffix}",
        code=f"B{suffix}",
        is_active=True,
    )
    return holding, company, branch


def _party(*, company, name: str = "Empleado Party") -> Party:
    return Party.objects.create(
        company=company,
        party_type=Party.PartyType.NATURAL,
        display_name=name,
        tax_id=f"RUC-{uuid.uuid4().hex[:8]}",
        national_id=f"CED-{uuid.uuid4().hex[:8]}",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
    )


def _employee(*, company, linked_user=None, name: str = "Juan") -> Employee:
    return Employee.objects.create(
        company=company,
        employee_code=f"E-{uuid.uuid4().hex[:8]}",
        first_name=name,
        last_name="Perez",
        phone="8888-0000",
        email=f"{uuid.uuid4().hex[:8]}@example.com",
        linked_user=linked_user,
    )


def _perm(code: str) -> Permission:
    p, _ = Permission.objects.get_or_create(code=code, defaults={"description": "", "is_active": True})
    if not p.is_active:
        p.is_active = True
        p.save(update_fields=["is_active"])
    return p


def _client_with_hr_permissions(company, *permission_codes: str):
    username = f"admin_hr_party_{uuid.uuid4().hex[:8]}"
    admin = User.objects.create_user(username=username, password="pass12345", email=f"{username}@example.com")
    UserMembership.objects.create(user=admin, org_unit=company, is_active=True)
    role = Role.objects.create(name=f"role_hr_party_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in permission_codes:
        RolePermission.objects.get_or_create(role=role, permission=_perm(code))
    RoleAssignment.objects.create(user=admin, role=role, org_unit=company, is_active=True)

    client = APIClient()
    login = client.post("/api/auth/login/", {"username": username, "password": "pass12345"}, format="json")
    assert login.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    return client


def _audit_failure(*args, **kwargs):
    raise RuntimeError("audit writer unavailable")


@pytest.mark.django_db
def test_employee_party_model_allows_nullable_and_rejects_cross_company_party():
    _holding, company, _branch = _org_tree(suffix="A")
    other_holding, other_company, _other_branch = _org_tree(suffix="B")
    same_company_party = _party(company=company, name="Empleado Misma Empresa")
    other_company_party = _party(company=other_company, name="Empleado Otra Empresa")

    employee_without_party = _employee(company=company, name="Sin Party")
    assert employee_without_party.party_id is None

    employee_with_party = _employee(company=company, name="Con Party")
    employee_with_party.party = same_company_party
    employee_with_party.save()
    assert employee_with_party.party_id == same_company_party.id

    employee_with_party.party = other_company_party
    with pytest.raises(ValidationError):
        employee_with_party.save()


@pytest.mark.django_db
def test_link_employee_to_party_creates_employee_role_and_company_scoped_audit():
    _holding, company, _branch = _org_tree()
    linked_user = User.objects.create_user(username=f"emp_{uuid.uuid4().hex[:8]}", password="x")
    employee = _employee(company=company, linked_user=linked_user)
    party = _party(company=company)

    linked = hr_services.link_employee_to_party(employee=employee, party=party)

    linked.refresh_from_db()
    assert linked.party_id == party.id
    assert linked.linked_user_id == linked_user.id
    assert PartyRole.objects.filter(party=party, role=PartyRole.Role.EMPLOYEE, is_active=True).count() == 1
    assert RoleAssignment.objects.count() == 0

    hr_event = AuditEvent.objects.get(event_type="HR_EMPLOYEE_PARTY_LINK_CHANGED")
    assert hr_event.partition_key == f"COMPANY:{company.id}"
    assert hr_event.metadata["company_id"] == str(company.id)
    assert hr_event.before_snapshot["party_id"] is None
    assert hr_event.after_snapshot["party_id"] == party.id
    assert not AuditEvent.objects.filter(partition_key="SYSTEM", event_type__startswith="HR_EMPLOYEE_PARTY").exists()


@pytest.mark.django_db
def test_link_employee_to_party_does_not_duplicate_existing_employee_party_role():
    _holding, company, _branch = _org_tree()
    employee = _employee(company=company)
    party = _party(company=company)
    PartyRole.objects.create(party=party, role=PartyRole.Role.EMPLOYEE)

    hr_services.link_employee_to_party(employee=employee, party=party)

    assert PartyRole.objects.filter(party=party, role=PartyRole.Role.EMPLOYEE, is_active=True).count() == 1
    assert AuditEvent.objects.filter(event_type="PARTY_ROLE_ASSIGNED").count() == 0


@pytest.mark.django_db
def test_link_employee_to_party_rejects_cross_company_party():
    _holding, company, _branch = _org_tree(suffix="A")
    _other_holding, other_company, _other_branch = _org_tree(suffix="B")
    employee = _employee(company=company)
    party = _party(company=other_company)

    with pytest.raises(ValidationError):
        hr_services.link_employee_to_party(employee=employee, party=party)

    employee.refresh_from_db()
    assert employee.party_id is None
    assert PartyRole.objects.filter(party=party, role=PartyRole.Role.EMPLOYEE).count() == 0
    assert AuditEvent.objects.count() == 0


@pytest.mark.django_db
def test_link_employee_to_party_rolls_back_party_role_when_hr_audit_fails(monkeypatch):
    _holding, company, _branch = _org_tree()
    employee = _employee(company=company)
    party = _party(company=company)
    monkeypatch.setattr(hr_services, "write_event", _audit_failure)

    with pytest.raises(RuntimeError):
        hr_services.link_employee_to_party(employee=employee, party=party)

    employee.refresh_from_db()
    assert employee.party_id is None
    assert PartyRole.objects.filter(party=party, role=PartyRole.Role.EMPLOYEE).count() == 0
    assert AuditEvent.objects.count() == 0


@pytest.mark.django_db
def test_unlink_employee_party_clears_employee_and_keeps_party_role_active():
    _holding, company, _branch = _org_tree()
    employee = _employee(company=company)
    party = _party(company=company)
    hr_services.link_employee_to_party(employee=employee, party=party)

    unlinked = hr_services.unlink_employee_party(employee=employee)

    unlinked.refresh_from_db()
    assert unlinked.party_id is None
    assert PartyRole.objects.filter(party=party, role=PartyRole.Role.EMPLOYEE, is_active=True).count() == 1
    assert AuditEvent.objects.filter(event_type="HR_EMPLOYEE_PARTY_LINK_CHANGED").count() == 2


@pytest.mark.django_db
def test_employee_api_create_list_patch_and_unlink_party():
    _holding, company, _branch = _org_tree()
    party_a = _party(company=company, name="Empleado A")
    party_b = _party(company=company, name="Empleado B")
    client = _client_with_hr_permissions(
        company,
        "hr.employee.create",
        "hr.employee.read",
        "hr.employee.update",
    )

    created = client.post(
        "/api/hr/employees/",
        {
            "employee_code": "E-API",
            "party_id": party_a.id,
            "first_name": "Ana",
            "last_name": "Lopez",
            "phone": "7777-0000",
            "email": "ana@example.com",
        },
        format="json",
        HTTP_X_COMPANY_ID=str(company.id),
    )
    assert created.status_code == 201
    employee_id = created.data["id"]
    employee = Employee.objects.get(id=employee_id)
    assert employee.party_id == party_a.id
    assert PartyRole.objects.filter(party=party_a, role=PartyRole.Role.EMPLOYEE, is_active=True).exists()

    listed = client.get("/api/hr/employees/", HTTP_X_COMPANY_ID=str(company.id))
    assert listed.status_code == 200
    row = next(item for item in listed.data["results"] if item["id"] == employee_id)
    assert row["party_id"] == party_a.id
    assert row["party_display_name"] == "Empleado A"
    assert row["party_tax_id"] == party_a.tax_id
    assert row["party_national_id"] == party_a.national_id

    relinked = client.patch(
        f"/api/hr/employees/{employee_id}/",
        {"party_id": party_b.id},
        format="json",
        HTTP_X_COMPANY_ID=str(company.id),
    )
    assert relinked.status_code == 200
    employee.refresh_from_db()
    assert employee.party_id == party_b.id
    assert PartyRole.objects.filter(party=party_b, role=PartyRole.Role.EMPLOYEE, is_active=True).exists()

    unlinked = client.patch(
        f"/api/hr/employees/{employee_id}/",
        {"party_id": None},
        format="json",
        HTTP_X_COMPANY_ID=str(company.id),
    )
    assert unlinked.status_code == 200
    employee.refresh_from_db()
    assert employee.party_id is None
    assert PartyRole.objects.filter(party=party_b, role=PartyRole.Role.EMPLOYEE, is_active=True).exists()


@pytest.mark.django_db
def test_employee_api_rejects_cross_company_party_without_partial_employee():
    _holding, company, _branch = _org_tree(suffix="A")
    _other_holding, other_company, _other_branch = _org_tree(suffix="B")
    other_party = _party(company=other_company)
    client = _client_with_hr_permissions(company, "hr.employee.create")

    response = client.post(
        "/api/hr/employees/",
        {"party_id": other_party.id, "first_name": "No Crear"},
        format="json",
        HTTP_X_COMPANY_ID=str(company.id),
    )

    assert response.status_code == 400
    assert Employee.objects.filter(company=company, first_name="No Crear").count() == 0
    assert PartyRole.objects.filter(party=other_party, role=PartyRole.Role.EMPLOYEE).count() == 0
