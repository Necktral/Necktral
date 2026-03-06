from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
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
def test_fuel_get_list_and_detail_and_reports():
    company, branch = _mk_org()

    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            # write-path
            "fuel.shift.open",
            "fuel.shift.close",
            "fuel.dispense.create",
            "fuel.sale.create",
            "fuel.sale.void",
            # read-path
            "fuel.shift.read",
            "fuel.dispense.read",
            "fuel.sale.read",
            # reports
            "fuel.reports.view",
        ],
    )

    # 1) abrir turno
    resp = client.post("/api/fuel/shifts/open/", {"note": "turno read"}, format="json")
    assert resp.status_code == 201
    shift_id = resp.data["id"]

    # 2) despacho
    resp = client.post(
        "/api/fuel/dispenses/",
        {
            "shift_id": shift_id,
            "product": "DIESEL",
            "liters": "10.0000",
            "unit_price": "42.5000",
        },
        format="json",
    )
    assert resp.status_code == 201
    dispense_id = resp.data["id"]

    # 3) venta
    resp = client.post(
        "/api/fuel/sales/",
        {
            "shift_id": shift_id,
            "dispense_id": dispense_id,
            "sale_type": "INTERNAL",
            "payment_method": "CASH",
        },
        format="json",
    )
    assert resp.status_code == 201
    sale_id = resp.data["id"]

    # 4) anular venta (para que el cierre reporte cancelaciones)
    resp = client.post(f"/api/fuel/sales/{sale_id}/cancel/", {"reason": "test"}, format="json")
    assert resp.status_code == 200
    assert resp.data["status"] == "CANCELLED"

    # 5) GET shifts list/detail
    resp = client.get("/api/fuel/shifts/")
    assert resp.status_code == 200
    assert resp.data["count"] >= 1
    assert any(r["id"] == shift_id for r in resp.data["results"])

    resp = client.get(f"/api/fuel/shifts/{shift_id}/")
    assert resp.status_code == 200
    assert resp.data["id"] == shift_id

    # 6) GET dispenses list/detail
    resp = client.get(f"/api/fuel/dispenses/?shift_id={shift_id}")
    assert resp.status_code == 200
    assert resp.data["count"] == 1
    assert resp.data["results"][0]["id"] == dispense_id

    resp = client.get(f"/api/fuel/dispenses/{dispense_id}/")
    assert resp.status_code == 200
    assert resp.data["id"] == dispense_id

    # 7) GET sales list/detail
    resp = client.get(f"/api/fuel/sales/?shift_id={shift_id}")
    assert resp.status_code == 200
    assert resp.data["count"] == 1
    assert resp.data["results"][0]["id"] == sale_id

    resp = client.get(f"/api/fuel/sales/{sale_id}/")
    assert resp.status_code == 200
    assert resp.data["id"] == sale_id

    # 8) Reporte cierre de turno
    resp = client.get(f"/api/fuel/reports/shift-close/{shift_id}/")
    assert resp.status_code == 200
    assert resp.data["shift"]["id"] == shift_id
    # Debe existir totales por producto con DIESEL
    diesel_lines = [x for x in resp.data["totals_by_product"] if x["key"] == "DIESEL"]
    assert len(diesel_lines) == 1
    assert diesel_lines[0]["dispense_count"] == 1
    assert diesel_lines[0]["liters"] == "10.0000"
    assert resp.data["counts"]["sales_cancelled"] == 1

    # 9) Reporte cierre diario
    today = timezone.localdate()
    resp = client.get(f"/api/fuel/reports/daily-close/?date={today.isoformat()}")
    assert resp.status_code == 200
    assert resp.data["date"] == today.isoformat()
    assert resp.data["branch_id"] == branch.id


@pytest.mark.django_db
def test_fuel_read_endpoints_require_permissions():
    company, branch = _mk_org()

    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "fuel.shift.open",
        ],
    )

    resp = client.get("/api/fuel/shifts/")
    assert resp.status_code == 403

    resp = client.get("/api/fuel/dispenses/")
    assert resp.status_code == 403

    resp = client.get("/api/fuel/sales/")
    assert resp.status_code == 403

    resp = client.get("/api/fuel/reports/daily-close/?date=2026-01-26")
    assert resp.status_code == 403
