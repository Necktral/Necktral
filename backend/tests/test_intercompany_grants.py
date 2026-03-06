import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.iam.models import OrgUnit, UserMembership, CompanyLink, LinkGrant
from apps.rbac.models import Permission, Role, RolePermission, RoleAssignment

User = get_user_model()


@pytest.mark.django_db
def test_intercompany_without_grant_denies_even_if_user_has_local_permission():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")

    company_a = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="A", parent=holding)
    company_b = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="B", parent=holding)

    # Usuario opera como B
    user = User.objects.create_user(username="u_b", password="pass12345")
    UserMembership.objects.create(user=user, org_unit=company_b, is_active=True)

    # Permiso local en B
    role = Role.objects.create(name="warehouse", is_active=True)
    perm = Permission.objects.create(code="inventory.read", is_active=True)
    RolePermission.objects.create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company_b, is_active=True)

    client = APIClient()
    login = client.post("/api/auth/login/", {"username": "u_b", "password": "pass12345"}, format="json")
    assert login.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    # Intenta leer datos de A desde contexto B
    r = client.get(
        "/api/rbac/demo/inventory-read/",
        HTTP_X_COMPANY_ID=str(company_b.id),
        HTTP_X_DATA_COMPANY_ID=str(company_a.id),
    )
    assert r.status_code == 403

    ev = AuditEvent.objects.filter(
        event_type="AUTH_ACCESS_DENIED",
        path="/api/rbac/demo/inventory-read/",
        method="GET",
    ).latest("timestamp_server")

    assert ev.metadata.get("required_permission") == "inventory.read"
    assert ev.metadata.get("effective_scope", {}).get("company_id") == company_b.id
    assert ev.metadata.get("data_scope", {}).get("company_id") == company_a.id

    inter = ev.metadata.get("intercompany", {})
    assert inter.get("from_company_id") == company_a.id
    assert inter.get("to_company_id") == company_b.id
    assert inter.get("grant_found") is False


@pytest.mark.django_db
def test_intercompany_with_grant_allows_read():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")

    company_a = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="A", parent=holding)
    company_b = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="B", parent=holding)

    user = User.objects.create_user(username="u_b2", password="pass12345")
    UserMembership.objects.create(user=user, org_unit=company_b, is_active=True)

    # Permiso local en B (requisito deliberado: el grant extiende alcance, no reemplaza RBAC)
    role = Role.objects.create(name="warehouse", is_active=True)
    perm = Permission.objects.create(code="inventory.read", is_active=True)
    RolePermission.objects.create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company_b, is_active=True)

    # Link A -> B y grant READ inventory.read (company-wide)
    link = CompanyLink.objects.create(
        from_company=company_a,
        to_company=company_b,
        link_type=CompanyLink.LinkType.ALLIANCE,
        status=CompanyLink.Status.ACTIVE,
        is_active=True,
    )
    LinkGrant.objects.create(
        link=link,
        permission=perm,
        access_mode=LinkGrant.AccessMode.READ,
        scope_org_unit=None,  # toda A
        is_active=True,
    )

    client = APIClient()
    login = client.post("/api/auth/login/", {"username": "u_b2", "password": "pass12345"}, format="json")
    assert login.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    r = client.get(
        "/api/rbac/demo/inventory-read/",
        HTTP_X_COMPANY_ID=str(company_b.id),
        HTTP_X_DATA_COMPANY_ID=str(company_a.id),
    )
    assert r.status_code == 200
    assert r.data["ok"] is True
