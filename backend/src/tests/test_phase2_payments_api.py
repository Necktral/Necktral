from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.modulos.audit.models import AuditEvent
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.integration.models import OutboxEvent
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _mk_org():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


def _client_with_perms(*, company: OrgUnit, branch: OrgUnit, perm_codes: list[str]) -> APIClient:
    username = f"u_{uuid.uuid4().hex[:10]}"
    user = User.objects.create_user(username=username, email="payments@test.com", password="pass12345")

    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perm_codes:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
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


@pytest.mark.django_db
def test_payments_intent_cash_session_and_outbox():
    company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "payments.intent.read",
            "payments.intent.create",
            "payments.cash_session.read",
            "payments.cash_session.open",
            "payments.cash_session.close",
            "payments.cash_movement.create",
        ],
    )

    idem_key = f"intent-{uuid.uuid4().hex[:8]}"
    r = client.post(
        "/api/payments/intents/",
        {"amount": "100.00", "currency": "NIO", "idempotency_key": idem_key, "external_ref": "INV-1"},
        format="json",
    )
    assert r.status_code == 201
    assert r.data["idempotent"] is False
    payment_id = r.data["payment_id"]

    r2 = client.post(
        "/api/payments/intents/",
        {"amount": "100.00", "currency": "NIO", "idempotency_key": idem_key, "external_ref": "INV-1"},
        format="json",
    )
    assert r2.status_code == 200
    assert r2.data["idempotent"] is True
    assert r2.data["payment_id"] == payment_id

    ropen = client.post("/api/payments/cash-sessions/open/", {"opening_amount": "50.00"}, format="json")
    assert ropen.status_code == 201
    session_id = ropen.data["id"]

    rmov = client.post(
        f"/api/payments/cash-sessions/{session_id}/movements/",
        {"movement_type": "INCOME", "amount": "25.00", "reference": "ticket-1"},
        format="json",
    )
    assert rmov.status_code == 201

    rclose = client.post(
        f"/api/payments/cash-sessions/{session_id}/close/",
        {"counted_amount": "75.00"},
        format="json",
    )
    assert rclose.status_code == 200
    assert rclose.data["status"] == "CLOSED"

    emitted = set(
        OutboxEvent.objects.filter(source_module="PAYMENTS").values_list("event_type", flat=True)
    )
    assert "PaymentIntentCreated" in emitted
    assert "CashSessionOpened" in emitted
    assert "CashMovementPosted" in emitted
    assert "CashSessionClosed" in emitted

    audited = set(
        AuditEvent.objects.filter(module="PAYMENTS").values_list("event_type", flat=True)
    )
    assert "PAYMENT_INTENT_CREATED" in audited
    assert "CASH_SESSION_OPENED" in audited
    assert "CASH_MOVEMENT_POSTED" in audited
    assert "CASH_SESSION_CLOSED" in audited
