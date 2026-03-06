import pytest

import uuid

from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.iam.models import OrgUnit, UserMembership
from apps.rbac.models import Permission, Role, RoleAssignment, RolePermission


User = get_user_model()


def _mk_org():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


def _client_with_perms(*, company: OrgUnit, branch: OrgUnit, perm_codes: list[str]) -> APIClient:
    username = f"u_{uuid.uuid4().hex[:10]}"
    user = User.objects.create_user(username=username, email="fuel@test.com", password="pass12345")

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

    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client


@pytest.mark.django_db
def test_fuel_uom_preferences_get_put_and_inference():
    company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "fuel.uom_preferences.manage",
            "fuel.shift.open",
            "fuel.dispense.create",
        ],
    )

    # 1) Defaults (sin override de usuario): gasolina LITER, diesel GALLON
    resp = client.get("/api/fuel/uom-preferences/")
    assert resp.status_code == 200
    assert resp.data["gasoline_volume_uom"] in ("LITER", "GALLON")
    assert resp.data["diesel_volume_uom"] in ("LITER", "GALLON")

    # 2) Override por usuario: diesel => LITER
    resp = client.put("/api/fuel/uom-preferences/", {"diesel_volume_uom": "LITER"}, format="json")
    assert resp.status_code == 200
    assert resp.data["diesel_volume_uom"] == "LITER"

    # 3) Inference: si no mandamos volume_uom, toma la preferencia recordada
    resp = client.post("/api/fuel/shifts/open/", {"note": "turno pref"}, format="json")
    assert resp.status_code == 201
    shift_id = resp.data["id"]

    resp = client.post(
        "/api/fuel/dispenses/",
        {
            "shift_id": shift_id,
            "product": "DIESEL",
            "volume": "10.0000",
            "unit_price": "42.5000",
            "unit_price_uom": "PER_LITER",
            # volume_uom se omite a propósito
        },
        format="json",
    )
    assert resp.status_code == 201
    # Si diesel se resolvió en litros, gallons_equiv debe ser 10/3.7854... y liters debe ser 10.0000
    assert resp.data["liters"] == "10.0000"
    assert "gallons_equiv" in resp.data
