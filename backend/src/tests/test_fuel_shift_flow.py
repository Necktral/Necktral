from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.iam.models import OrgUnit, UserMembership
from apps.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _mk_org():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


def _client_with_perms(*, company: OrgUnit, branch: OrgUnit, perm_codes: list[str]) -> APIClient:
    """Replica el patrón de test_rbac_list_endpoints: client autenticado + permisos."""

    username = f"u_{uuid.uuid4().hex[:10]}"
    user = User.objects.create_user(username=username, email="fuel@test.com", password="pass12345")

    # Memberships: asegurar acceso a COMPANY + BRANCH
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perm_codes:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": "", "is_active": True})
        if not perm.is_active:
            perm.is_active = True
            perm.save(update_fields=["is_active"])
        RolePermission.objects.get_or_create(role=role, permission=perm)

    # Asignar en COMPANY y BRANCH para evitar ambigüedades de scope
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)

    client = APIClient()
    resp = client.post("/api/auth/login/", {"username": username, "password": "pass12345"}, format="json")
    assert resp.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {resp.data['access']}")

    # Contexto multiempresa (middleware)
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)

    return client


@pytest.mark.django_db
def test_fuel_shift_dispense_sale_close_flow():
    company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "fuel.shift.open",
            "fuel.shift.close",
            "fuel.dispense.create",
            "fuel.sale.create",
        ],
    )

    # 1) abrir turno
    resp = client.post("/api/fuel/shifts/open/", {"note": "turno 1"}, format="json")
    assert resp.status_code == 201
    shift_id = resp.data["id"]

    # 2) despacho
    resp = client.post(
        "/api/fuel/dispenses/",
        {
            "shift_id": shift_id,
            "product": "DIESEL",
            # Legacy: liters (sigue soportado)
            "liters": "10.0000",
            "unit_price": "42.5000",
            "vehicle_plate": "M123-456",
            "external_ref": "PED-001",
        },
        format="json",
    )
    assert resp.status_code == 201
    dispense_id = resp.data["id"]
    assert resp.data["amount"] == "425.00"
    # El serializer siempre devuelve ambas unidades
    assert "liters" in resp.data
    assert "gallons_us" in resp.data

    # 3) venta
    resp = client.post(
        "/api/fuel/sales/",
        {
            "shift_id": shift_id,
            "dispense_id": dispense_id,
            "sale_type": "INTERNAL",
            "payment_method": "CASH",
            "customer_name": "CONSUMO INTERNO",
        },
        format="json",
    )
    assert resp.status_code == 201
    sale_id = resp.data["id"]

    # 4) cerrar turno
    resp = client.post(f"/api/fuel/shifts/{shift_id}/close/", {"note": "cierre"}, format="json")
    assert resp.status_code == 200
    assert resp.data["status"] == "CLOSED"

    # 5) auditoría: eventos mínimos
    types = list(AuditEvent.objects.filter(module="FUEL").values_list("event_type", flat=True))
    assert "FUEL_SHIFT_OPENED" in types
    assert "FUEL_DISPENSE_RECORDED" in types
    assert "FUEL_SALE_CREATED" in types
    assert "FUEL_SHIFT_CLOSED" in types

    # sanity
    assert sale_id is not None


@pytest.mark.django_db
def test_fuel_dispense_diesel_in_gallons_returns_both_units():
    company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "fuel.shift.open",
            "fuel.dispense.create",
        ],
    )

    # abrir turno
    resp = client.post("/api/fuel/shifts/open/", {"note": "turno galones"}, format="json")
    assert resp.status_code == 201
    shift_id = resp.data["id"]

    # despacho: 10 galones US de diesel
    resp = client.post(
        "/api/fuel/dispenses/",
        {
            "shift_id": shift_id,
            "product": "DIESEL",
            "volume": "10.0000",
            "unit_price": "42.5000",
            "volume_uom": "GALLON",
            "unit_price_uom": "PER_GALLON",
        },
        format="json",
    )
    assert resp.status_code == 201
    assert resp.data["amount"] == "425.00"
    # litros canónicos (10 * 3.785411784 = 37.85411784 -> 37.8541)
    assert resp.data["liters"] == "37.8541"
    # el serializer devuelve ambos siempre
    assert resp.data["gallons_us"] == "10.0000"


@pytest.mark.django_db
def test_fuel_open_shift_twice_denied_by_constraint():
    company, branch = _mk_org()
    client = _client_with_perms(company=company, branch=branch, perm_codes=["fuel.shift.open"])

    r1 = client.post(
        "/api/fuel/shifts/open/",
        {},
        format="json",
    )
    assert r1.status_code == 201

    r2 = client.post(
        "/api/fuel/shifts/open/",
        {},
        format="json",
    )
    assert r2.status_code == 422
    assert "turno abierto" in (r2.data.get("error", {}).get("message") or "").lower()
