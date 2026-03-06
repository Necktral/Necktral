import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.iam.models import OrgUnit, UserMembership
from apps.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


@pytest.mark.django_db
def test_permission_in_c1_does_not_apply_in_c2():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    c1 = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C1", parent=holding)
    c2 = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C2", parent=holding)

    user = User.objects.create_user(username="u_multi", password="pass12345")

    # Membresía a ambas empresas (para que el fallo sea por permiso, no por membresía)
    UserMembership.objects.create(user=user, org_unit=c1, is_active=True)
    UserMembership.objects.create(user=user, org_unit=c2, is_active=True)

    role = Role.objects.create(name="warehouse", is_active=True)
    perm = Permission.objects.create(code="inventory.read", is_active=True)
    RolePermission.objects.create(role=role, permission=perm)

    # Rol solo en C1
    RoleAssignment.objects.create(user=user, role=role, org_unit=c1, is_active=True)

    client = APIClient()
    login = client.post("/api/auth/login/", {"username": "u_multi", "password": "pass12345"}, format="json")
    assert login.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")

    # En C1 pasa
    r1 = client.get("/api/rbac/demo/inventory-read/", HTTP_X_COMPANY_ID=str(c1.id))
    assert r1.status_code == 200

    # En C2 falla por permiso
    r2 = client.get("/api/rbac/demo/inventory-read/", HTTP_X_COMPANY_ID=str(c2.id))
    assert r2.status_code == 403

    ev = AuditEvent.objects.filter(
        event_type="AUTH_ACCESS_DENIED",
        path="/api/rbac/demo/inventory-read/",
        method="GET",
    ).latest("timestamp_server")

    assert ev.metadata.get("required_permission") == "inventory.read"
    assert ev.metadata.get("effective_scope", {}).get("company_id") == c2.id
    assert ev.metadata.get("required_scope", {}).get("company_id") == c2.id
