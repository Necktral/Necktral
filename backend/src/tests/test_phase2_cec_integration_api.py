from __future__ import annotations

import uuid

import pytest
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient

from apps.iam.models import OrgUnit, UserMembership
from apps.integration.models import InboxEvent
from apps.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()


def _mk_org():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


def _client_with_perms(*, company: OrgUnit, branch: OrgUnit, perm_codes: list[str]) -> APIClient:
    username = f"u_{uuid.uuid4().hex[:10]}"
    user = User.objects.create_user(username=username, email="cec@test.com", password="pass12345")

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
def test_cec_and_integration_endpoints_flow():
    company, branch = _mk_org()
    client = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=[
            "cec.close_run.read",
            "cec.close_run.create",
            "cec.close_run.update",
            "cec.exception.read",
            "cec.exception.create",
            "cec.exception.resolve",
            "cec.evidence.create",
            "integration.outbox.read",
            "integration.outbox.publish",
            "integration.inbox.read",
            "integration.inbox.process",
        ],
    )

    r_run = client.post(
        "/api/cec/close-runs/",
        {"run_type": "DAILY", "input_manifest_hash": "a" * 64},
        format="json",
    )
    assert r_run.status_code == 201
    run_id = r_run.data["run_id"]

    r_adv = client.post(
        f"/api/cec/close-runs/{run_id}/advance/",
        {"status": "GATHERED", "output_manifest_hash": "b" * 64},
        format="json",
    )
    assert r_adv.status_code == 200
    assert r_adv.data["status"] == "GATHERED"

    r_ex = client.post(
        "/api/cec/exceptions/",
        {"source_module": "BILLING", "code": "DOC_GAP", "severity": "HIGH", "close_run_id": run_id},
        format="json",
    )
    assert r_ex.status_code == 201
    exception_id = r_ex.data["exception_id"]

    r_resolve = client.post(
        f"/api/cec/exceptions/{exception_id}/resolve/",
        {"resolution_note": "fixed"},
        format="json",
    )
    assert r_resolve.status_code == 200
    assert r_resolve.data["status"] == "RESOLVED"

    r_evidence = client.post(
        "/api/cec/evidence/",
        {
            "support_id": f"support-{uuid.uuid4().hex[:8]}",
            "sha256": "c" * 64,
            "mime_type": "application/pdf",
            "storage_ref": "s3://bucket/path.pdf",
            "close_run_id": run_id,
        },
        format="json",
    )
    assert r_evidence.status_code == 201

    r_outbox = client.get("/api/integration/outbox/?source_module=CEC")
    assert r_outbox.status_code == 200
    assert r_outbox.data["count"] >= 4
    event_id = r_outbox.data["results"][0]["event_id"]

    r_sent = client.post(f"/api/integration/outbox/{event_id}/sent/", {}, format="json")
    assert r_sent.status_code == 200
    assert r_sent.data["status"] == "SENT"

    inbox = InboxEvent.objects.create(
        event_id=uuid.uuid4(),
        consumer="accounting.projector",
        source_module="CEC",
        event_type="CloseRunCreated",
        payload={"run_id": run_id},
    )
    r_ack = client.post(f"/api/integration/inbox/{inbox.id}/ack/", {"status": "PROCESSED"}, format="json")
    assert r_ack.status_code == 200
    assert r_ack.data["status"] == "PROCESSED"
