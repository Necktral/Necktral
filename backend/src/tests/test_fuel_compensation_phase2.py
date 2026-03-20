from __future__ import annotations

import json
import uuid
from datetime import timedelta
from io import StringIO

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.integration.models import OutboxEvent
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission
from kernels.facturacion.models import BillingDocument, DocStatus
from kernels.inventarios.models import StockMovement
from kernels.estacion_servicios.models import FuelSale, FuelSaleStatus

User = get_user_model()


def _mk_org():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


def _client_with_perms(*, company: OrgUnit, branch: OrgUnit, perm_codes: list[str]) -> APIClient:
    username = f"u_{uuid.uuid4().hex[:10]}"
    user = User.objects.create_user(username=username, email="fuelc@test.com", password="pass12345")

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
    resp = client.post("/api/backend/auth/login/", {"username": username, "password": "pass12345"}, format="json")
    assert resp.status_code == 200
    access = resp.data.get("access") if isinstance(resp.data, dict) else None
    if isinstance(access, str) and access:
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        client.defaults["HTTP_AUTHORIZATION"] = f"Bearer {access}"
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client


def _mk_sale(*, client: APIClient):
    r = client.post("/api/fuel/shifts/open/", {"note": "turno"}, format="json")
    assert r.status_code == 201
    shift_id = int(r.data["id"])

    r = client.post(
        "/api/fuel/dispenses/",
        {
            "shift_id": shift_id,
            "product": "DIESEL",
            "liters": "10.0000",
            "unit_price": "42.5000",
        },
        format="json",
    )
    assert r.status_code == 201
    dispense_id = int(r.data["id"])

    r = client.post(
        "/api/fuel/sales/",
        {
            "shift_id": shift_id,
            "dispense_id": dispense_id,
            "sale_type": "PUBLIC",
            "payment_method": "CASH",
            "customer_name": "Cliente",
        },
        format="json",
    )
    assert r.status_code == 201
    return int(r.data["id"]), r.data


@pytest.mark.django_db
def test_fuel_cancel_compensating_then_retry_endpoint_success(monkeypatch):
    company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "fuel.shift.open",
            "fuel.dispense.create",
            "fuel.sale.create",
            "fuel.sale.void",
        ],
    )
    sale_id, _ = _mk_sale(client=client)

    from kernels.facturacion import services as billing_services

    original_void_doc = billing_services.void_doc
    call_count = {"n": 0}

    def _fail_first_void(*args, **kwargs):  # noqa: ANN002, ANN003
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("forced billing void failure")
        return original_void_doc(*args, **kwargs)

    monkeypatch.setattr(billing_services, "void_doc", _fail_first_void)

    cancel = client.post(f"/api/fuel/sales/{sale_id}/cancel/", {"reason": "test"}, format="json")
    assert cancel.status_code == 200
    assert cancel.data["status"] == FuelSaleStatus.COMPENSATING
    assert cancel.data["compensation_pending"] is True
    assert cancel.data["compensation_attempts"] == 1
    assert "billing_void" in (cancel.data.get("compensation_last_error") or "")
    assert cancel.data.get("compensation_next_retry_at")

    sale = FuelSale.objects.get(id=sale_id)
    assert sale.status == FuelSaleStatus.COMPENSATING
    assert sale.compensation_attempts == 1
    assert sale.compensation_next_retry_at is not None

    retry = client.post(f"/api/fuel/sales/{sale_id}/compensate/retry/", {"reason": "manual"}, format="json")
    assert retry.status_code == 200
    assert retry.data["status"] == FuelSaleStatus.CANCELLED
    assert retry.data["compensation_pending"] is False
    assert retry.data["compensation_attempts"] == 2
    assert retry.data.get("inventory_reversal_movement_id")

    sale.refresh_from_db()
    assert sale.status == FuelSaleStatus.CANCELLED
    assert sale.compensation_attempts == 2
    assert sale.compensation_next_retry_at is None
    assert sale.compensation_last_error == ""

    doc = BillingDocument.objects.get(id=int(retry.data["billing_doc_id"]))
    assert doc.status == DocStatus.VOIDED

    event_types = list(
        OutboxEvent.objects.filter(source_module="FUEL").values_list("event_type", flat=True)
    )
    assert "FuelSaleCancelRequested" in event_types
    assert "FuelSaleCompensating" in event_types
    assert "FuelSaleCompensationRetried" in event_types
    assert "FuelSaleCancelled" in event_types


@pytest.mark.django_db
def test_fuel_cancel_is_idempotent_after_cancelled():
    company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "fuel.shift.open",
            "fuel.dispense.create",
            "fuel.sale.create",
            "fuel.sale.void",
        ],
    )
    sale_id, _ = _mk_sale(client=client)

    first = client.post(f"/api/fuel/sales/{sale_id}/cancel/", {"reason": "test"}, format="json")
    assert first.status_code == 200
    assert first.data["status"] == FuelSaleStatus.CANCELLED
    rev_id = int(first.data["inventory_reversal_movement_id"])
    attempts = int(first.data["compensation_attempts"])

    second = client.post(f"/api/fuel/sales/{sale_id}/cancel/", {"reason": "test2"}, format="json")
    assert second.status_code == 200
    assert second.data["status"] == FuelSaleStatus.CANCELLED
    assert int(second.data["inventory_reversal_movement_id"]) == rev_id
    assert int(second.data["compensation_attempts"]) == attempts

    assert StockMovement.objects.filter(idempotency_key=f"fuel:sale:{sale_id}:reverse").count() == 1


@pytest.mark.django_db
def test_retry_endpoint_is_idempotent_when_sale_already_cancelled():
    company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "fuel.shift.open",
            "fuel.dispense.create",
            "fuel.sale.create",
            "fuel.sale.void",
        ],
    )
    sale_id, _ = _mk_sale(client=client)

    cancel = client.post(f"/api/fuel/sales/{sale_id}/cancel/", {"reason": "initial"}, format="json")
    assert cancel.status_code == 200
    assert cancel.data["status"] == FuelSaleStatus.CANCELLED
    attempts_before = int(cancel.data["compensation_attempts"])
    rev_id_before = int(cancel.data["inventory_reversal_movement_id"])

    retry = client.post(f"/api/fuel/sales/{sale_id}/compensate/retry/", {"reason": "manual"}, format="json")
    assert retry.status_code == 200
    assert retry.data["status"] == FuelSaleStatus.CANCELLED
    assert int(retry.data["compensation_attempts"]) == attempts_before
    assert int(retry.data["inventory_reversal_movement_id"]) == rev_id_before

    assert StockMovement.objects.filter(idempotency_key=f"fuel:sale:{sale_id}:reverse").count() == 1


@pytest.mark.django_db
def test_run_fuel_compensation_cycle_command_processes_pending(monkeypatch):
    company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "fuel.shift.open",
            "fuel.dispense.create",
            "fuel.sale.create",
            "fuel.sale.void",
        ],
    )
    sale_id, _ = _mk_sale(client=client)

    from kernels.facturacion import services as billing_services

    original_void_doc = billing_services.void_doc
    call_count = {"n": 0}

    def _fail_first_void(*args, **kwargs):  # noqa: ANN002, ANN003
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("forced billing void failure")
        return original_void_doc(*args, **kwargs)

    monkeypatch.setattr(billing_services, "void_doc", _fail_first_void)

    cancel = client.post(f"/api/fuel/sales/{sale_id}/cancel/", {"reason": "test"}, format="json")
    assert cancel.status_code == 200
    assert cancel.data["status"] == FuelSaleStatus.COMPENSATING
    FuelSale.objects.filter(id=sale_id).update(compensation_next_retry_at=timezone.now() - timedelta(seconds=1))

    out = StringIO()
    call_command(
        "run_fuel_compensation_cycle",
        company_id=company.id,
        branch_id=branch.id,
        stdout=out,
    )
    payload = json.loads(out.getvalue())
    assert payload["attempted"] >= 1
    assert payload.get("errors") == []

    sale = FuelSale.objects.get(id=sale_id)
    assert sale.compensation_attempts >= 2
    assert sale.status in (
        FuelSaleStatus.CANCELLED,
        FuelSaleStatus.COMPENSATING,
        FuelSaleStatus.COMPENSATION_FAILED,
    )
