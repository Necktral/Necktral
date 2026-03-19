from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.utils import timezone
from rest_framework.test import APIClient

from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.integration.models import OutboxEvent
from apps.modulos.payments.models import CashSession
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _mk_org():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


def _client_with_perms(*, company: OrgUnit, branch: OrgUnit, perm_codes: list[str]) -> tuple[APIClient, Any]:
    username = f"u_{uuid.uuid4().hex[:10]}"
    user = User.objects.create_user(username=username, email="phase3_cec@test.com", password="pass12345")

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
    return client, user


@pytest.mark.django_db
def test_cec_execute_success_and_summary_endpoint():
    company, branch = _mk_org()
    client, _ = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["cec.close_run.read", "cec.close_run.create", "cec.close_run.update"],
    )

    run_resp = client.post("/api/cec/close-runs/", {"run_type": "DAILY"}, format="json")
    assert run_resp.status_code == 201
    run_id = run_resp.data["run_id"]

    now = timezone.now()
    execute_resp = client.post(
        f"/api/cec/close-runs/{run_id}/execute/",
        {
            "window_start": (now - timedelta(days=1)).isoformat(),
            "window_end": (now + timedelta(days=1)).isoformat(),
            "strict": True,
        },
        format="json",
    )
    assert execute_resp.status_code == 200
    assert execute_resp.data["status"] == "PACKAGED"
    assert execute_resp.data["blocking_exceptions_count"] == 0
    assert len(execute_resp.data["output_manifest_hash"]) == 64

    summary_resp = client.get(f"/api/cec/close-runs/{run_id}/summary/")
    assert summary_resp.status_code == 200
    assert summary_resp.data["status"] == "PACKAGED"
    assert summary_resp.data["consistency_score"] == 100
    assert isinstance(summary_resp.data["summary"], dict)
    assert isinstance(summary_resp.data["exceptions"], list)


@pytest.mark.django_db
def test_cec_execute_blocked_when_cash_difference_exists():
    company, branch = _mk_org()
    client, user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["cec.close_run.read", "cec.close_run.create", "cec.close_run.update", "cec.evidence.create"],
    )

    run_resp = client.post("/api/cec/close-runs/", {"run_type": "DAILY"}, format="json")
    assert run_resp.status_code == 201
    run_id = run_resp.data["run_id"]

    now = timezone.now()
    CashSession.objects.create(
        company=company,
        branch=branch,
        opened_by=user,
        closed_by=user,
        status=CashSession.Status.CLOSED,
        opened_at=now - timedelta(hours=4),
        closed_at=now - timedelta(hours=1),
        opening_amount=Decimal("100.00"),
        expected_amount=Decimal("180.00"),
        counted_amount=Decimal("170.00"),
        difference_amount=Decimal("-10.00"),
    )

    execute_resp = client.post(
        f"/api/cec/close-runs/{run_id}/execute/",
        {
            "window_start": (now - timedelta(days=1)).isoformat(),
            "window_end": (now + timedelta(days=1)).isoformat(),
            "strict": True,
        },
        format="json",
    )
    assert execute_resp.status_code == 200
    assert execute_resp.data["status"] == "REOPENED_EXCEPTION"
    assert execute_resp.data["blocking_exceptions_count"] >= 1

    outbox_types = set(
        OutboxEvent.objects.filter(source_module="CEC").values_list("event_type", flat=True)
    )
    assert "CloseRunExecuted" in outbox_types
    assert "CloseRunBlocked" in outbox_types


@pytest.mark.django_db
def test_cec_execute_with_strict_false_still_blocks_cash_difference():
    company, branch = _mk_org()
    client, user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["cec.close_run.read", "cec.close_run.create", "cec.close_run.update"],
    )

    run_resp = client.post("/api/cec/close-runs/", {"run_type": "DAILY"}, format="json")
    assert run_resp.status_code == 201
    run_id = run_resp.data["run_id"]

    now = timezone.now()
    CashSession.objects.create(
        company=company,
        branch=branch,
        opened_by=user,
        closed_by=user,
        status=CashSession.Status.CLOSED,
        opened_at=now - timedelta(hours=4),
        closed_at=now - timedelta(hours=1),
        opening_amount=Decimal("100.00"),
        expected_amount=Decimal("180.00"),
        counted_amount=Decimal("170.00"),
        difference_amount=Decimal("-10.00"),
    )

    execute_resp = client.post(
        f"/api/cec/close-runs/{run_id}/execute/",
        {
            "window_start": (now - timedelta(days=1)).isoformat(),
            "window_end": (now + timedelta(days=1)).isoformat(),
            "strict": False,
        },
        format="json",
    )
    assert execute_resp.status_code == 200
    assert execute_resp.data["status"] == "REOPENED_EXCEPTION"
    assert execute_resp.data["blocking_exceptions_count"] >= 1


@pytest.mark.django_db
def test_cec_advance_rejects_invalid_transition_with_409():
    company, branch = _mk_org()
    client, _ = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=["cec.close_run.create", "cec.close_run.update"],
    )
    run_resp = client.post("/api/cec/close-runs/", {"run_type": "DAILY"}, format="json")
    assert run_resp.status_code == 201
    run_id = run_resp.data["run_id"]

    invalid = client.post(
        f"/api/cec/close-runs/{run_id}/advance/",
        {"status": "PACKAGED"},
        format="json",
    )
    assert invalid.status_code == 409
