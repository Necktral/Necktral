import uuid

import pytest
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.iam.models import OrgUnit, UserMembership
from apps.org.models import BranchProfile, CompanyProfile
from apps.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _mk_user_with_company_access(*, username: str, company: OrgUnit, perm_codes: list[str]) -> tuple[APIClient, User]:
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
    return client, user


@pytest.mark.django_db
def test_org_create_branch_creates_profile_and_audit():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C1", parent=holding)

    # Importante: con el fix por método, POST requiere solo org.branch.create (no read)
    client, user = _mk_user_with_company_access(
        username="u_org_create",
        company=company,
        perm_codes=["org.branch.create"],
    )

    payload = {
        "name": "Sucursal Norte",
        "code": "SN",
        "address": "Av 1",
        "phone": "111",
        "email": "norte@c1.com",
    }

    r = client.post("/api/org/branches/", payload, format="json", HTTP_X_COMPANY_ID=str(company.id))
    assert r.status_code == 201
    branch_id = r.data["id"]

    branch = OrgUnit.objects.get(id=branch_id)
    assert branch.unit_type == OrgUnit.UnitType.BRANCH
    assert branch.parent_id == company.id
    assert branch.name == "Sucursal Norte"
    assert branch.code == "SN"

    prof = BranchProfile.objects.get(branch=branch)
    assert prof.address == "Av 1"
    assert prof.phone == "111"
    assert prof.email == "norte@c1.com"

    ev = AuditEvent.objects.filter(
        event_type="ORG_BRANCH_CREATED",
        module="ORG",
        path="/api/org/branches/",
        method="POST",
        subject_type="BRANCH",
        subject_id=str(branch.id),
    ).latest("timestamp_server")

    assert ev.reason_code == "OK"
    assert ev.actor_user_id == user.id
    assert ev.metadata.get("branch_name") == "Sucursal Norte"
    assert ev.event_hash is not None and len(ev.event_hash) == 64
    assert ev.signature is not None and len(ev.signature) == 64


@pytest.mark.django_db
def test_org_create_branch_denied_without_create_permission():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C1", parent=holding)

    # Solo read, NO create
    client, _ = _mk_user_with_company_access(
        username="u_org_read_only",
        company=company,
        perm_codes=["org.branch.read"],
    )

    r = client.post(
        "/api/org/branches/",
        {"name": "X"},
        format="json",
        HTTP_X_COMPANY_ID=str(company.id),
    )
    assert r.status_code == 403

    # Denegación auditada por middleware
    ev = AuditEvent.objects.filter(
        event_type="AUTH_ACCESS_DENIED",
        path="/api/org/branches/",
        method="POST",
    ).latest("timestamp_server")
    assert ev.reason_code == "RBAC_FORBIDDEN"
    assert ev.metadata.get("required_permission") == "org.branch.create"


@pytest.mark.django_db
def test_org_patch_branch_updates_and_audit():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C1", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B1", code="B1", parent=company)
    BranchProfile.objects.create(branch=branch, address="Old", phone="", email="")

    client, user = _mk_user_with_company_access(
        username="u_org_update",
        company=company,
        perm_codes=["org.branch.update"],
    )

    r = client.patch(
        f"/api/org/branches/{branch.id}/",
        {"name": "B1-NEW", "address": "New Addr"},
        format="json",
        HTTP_X_COMPANY_ID=str(company.id),
    )
    assert r.status_code == 200
    assert r.data["ok"] is True

    branch.refresh_from_db()
    assert branch.name == "B1-NEW"
    prof = BranchProfile.objects.get(branch=branch)
    assert prof.address == "New Addr"

    ev = AuditEvent.objects.filter(
        event_type="ORG_BRANCH_UPDATED",
        module="ORG",
        path=f"/api/org/branches/{branch.id}/",
        method="PATCH",
        subject_type="BRANCH",
        subject_id=str(branch.id),
    ).latest("timestamp_server")

    assert ev.reason_code == "OK"
    assert ev.actor_user_id == user.id
    assert ev.before_snapshot.get("name") == "B1"
    assert ev.after_snapshot.get("name") == "B1-NEW"
    assert ev.event_hash is not None and len(ev.event_hash) == 64
    assert ev.signature is not None and len(ev.signature) == 64


@pytest.mark.django_db
def test_org_get_company_profile_requires_read_not_update():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C1", parent=holding)
    CompanyProfile.objects.create(company=company, legal_name="C1", tax_id="", address="", phone="", email="")

    client, _ = _mk_user_with_company_access(
        username="u_org_company_read",
        company=company,
        perm_codes=["org.company.read"],
    )

    r = client.get("/api/org/company/profile/", HTTP_X_COMPANY_ID=str(company.id))
    assert r.status_code == 200
    assert r.data["legal_name"] == "C1"


@pytest.mark.django_db
def test_org_put_company_profile_updates_and_audit():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C1", parent=holding)
    CompanyProfile.objects.create(company=company, legal_name="", tax_id="", address="", phone="", email="")

    client, user = _mk_user_with_company_access(
        username="u_org_company_update",
        company=company,
        perm_codes=["org.company.update"],
    )

    payload = {
        "legal_name": "C1 SA",
        "tax_id": "J-123",
        "address": "Av Central",
        "phone": "555",
        "email": "admin@c1.com",
    }

    r = client.put("/api/org/company/profile/", payload, format="json", HTTP_X_COMPANY_ID=str(company.id))
    assert r.status_code == 200
    assert r.data["ok"] is True

    prof = CompanyProfile.objects.get(company=company)
    assert prof.legal_name == "C1 SA"
    assert prof.tax_id == "J-123"
    assert prof.address == "Av Central"
    assert prof.phone == "555"
    assert prof.email == "admin@c1.com"

    ev = AuditEvent.objects.filter(
        event_type="ORG_COMPANY_PROFILE_UPDATED",
        module="ORG",
        path="/api/org/company/profile/",
        method="PUT",
        subject_type="COMPANY",
        subject_id=str(company.id),
    ).latest("timestamp_server")

    assert ev.reason_code == "OK"
    assert ev.actor_user_id == user.id
    assert ev.after_snapshot.get("legal_name") == "C1 SA"
    assert ev.event_hash is not None and len(ev.event_hash) == 64
    assert ev.signature is not None and len(ev.signature) == 64


@pytest.mark.django_db
def test_org_list_companies_and_create_company_audit():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company1 = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C1", parent=holding)
    CompanyProfile.objects.create(company=company1, legal_name="C1 SA", tax_id="", address="", phone="", email="")

    # Permisos mínimos: read para listar, create para crear
    client, user = _mk_user_with_company_access(
        username="u_org_company_create",
        company=company1,
        perm_codes=["org.company.read", "org.company.create"],
    )

    r0 = client.get("/api/org/companies/", HTTP_X_COMPANY_ID=str(company1.id))
    assert r0.status_code == 200
    assert len(r0.data["results"]) == 1

    payload = {
        "name": "C2",
        "code": "C2",
        "legal_name": "C2 SA",
        "tax_id": "J-222",
        "address": "Av 2",
        "phone": "222",
        "email": "admin@c2.com",
    }

    ts_before = timezone.now()
    r1 = client.post("/api/org/companies/", payload, format="json", HTTP_X_COMPANY_ID=str(company1.id))
    assert r1.status_code == 201
    new_id = r1.data["id"]

    c2 = OrgUnit.objects.get(id=new_id)
    assert c2.unit_type == OrgUnit.UnitType.COMPANY
    assert c2.parent_id == holding.id
    assert c2.name == "C2"

    prof2 = CompanyProfile.objects.get(company=c2)
    assert prof2.legal_name == "C2 SA"

    # Membership del creador en la nueva empresa
    assert UserMembership.objects.filter(user=user, org_unit=c2, is_active=True).exists()

    ev = AuditEvent.objects.filter(
        event_type="ORG_COMPANY_CREATED",
        module="ORG",
        path="/api/org/companies/",
        method="POST",
        subject_type="COMPANY",
        subject_id=str(c2.id),
    ).latest("timestamp_server")
    assert ev.timestamp_server >= ts_before
    assert ev.reason_code == "OK"
    assert ev.actor_user_id == user.id
    assert ev.metadata.get("company_name") == "C2"
    assert ev.event_hash is not None and len(ev.event_hash) == 64
    assert ev.signature is not None and len(ev.signature) == 64
