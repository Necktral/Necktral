from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.utils import timezone
from rest_framework.test import APIClient

from apps.modulos.accounting.models import EconomicEvent, JournalDraft
from apps.modulos.cec.models import CloseRun
from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.integration.models import OutboxEvent
from apps.modulos.integration.services import publish_outbox_event
from apps.modulos.rbac.models import Permission, Role, RoleAssignment, RolePermission

User = get_user_model()
_VALID_ACCOUNTING_STATUSES = {
    "DISABLED",
    "UNSUPPORTED",
    "PENDING_RULESET",
    "PENDING_RULE",
    "DRAFT_EXCEPTION",
    "DRAFT_VALIDATED",
    "POSTED",
}


def _mk_scope() -> tuple[OrgUnit, OrgUnit]:
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="Holding")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="Company", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="Branch", parent=company)
    return company, branch


def _mk_client(*, company: OrgUnit, branch: OrgUnit, perm_codes: list[str]) -> tuple[APIClient, Any]:
    username = f"proc_{uuid.uuid4().hex[:8]}"
    user = User.objects.create_user(username=username, email=f"{username}@test.local", password="pass12345")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    role = Role.objects.create(name=f"proc_role_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perm_codes:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
        RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)

    client = APIClient()
    login = client.post("/api/backend/auth/login/", {"username": username, "password": "pass12345"}, format="json")
    assert login.status_code == 200
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.data['access']}")
    client.defaults["HTTP_X_COMPANY_ID"] = str(company.id)
    client.defaults["HTTP_X_BRANCH_ID"] = str(branch.id)
    return client, user


def _mk_packaged_run(*, company: OrgUnit, branch: OrgUnit, user: Any) -> CloseRun:
    now = timezone.now()
    run = CloseRun.objects.create(
        company=company,
        branch=branch,
        run_type=CloseRun.RunType.DAILY,
        status=CloseRun.Status.PACKAGED,
        window_start=now - timedelta(hours=3),
        window_end=now + timedelta(hours=3),
        output_manifest_hash="f" * 64,
        summary_json={"schema_version": 1},
        created_by=user,
    )
    publish_outbox_event(
        source_module="CEC",
        event_type="CloseRunPackaged",
        payload={"run_id": str(run.run_id), "output_manifest_hash": run.output_manifest_hash},
        company=company,
        branch=branch,
        actor_user=user,
    )
    return run


def _procurement_perms() -> list[str]:
    return [
        "procurement.doc.create",
        "procurement.doc.read",
        "procurement.doc.post",
        "procurement.doc.void",
    ]


@pytest.mark.django_db
def test_phase10_procurement_api_create_post_void_and_outbox():
    company, branch = _mk_scope()
    client, _ = _mk_client(company=company, branch=branch, perm_codes=_procurement_perms())

    payload = {
        "doc_type": "SUPPLIER_INVOICE",
        "series": "P",
        "currency": "NIO",
        "supplier_name": "Proveedor 1",
        "supplier_ref": "PRV-001",
        "external_ref": "INV-EXT-1",
        "subtotal": "100.00",
        "tax_total": "15.00",
        "total": "115.00",
        "idempotency_key": "proc-001",
    }

    created = client.post("/api/procurement/docs/", payload, format="json")
    assert created.status_code == 201
    doc_id = int(created.data["id"])

    created_again = client.post("/api/procurement/docs/", payload, format="json")
    assert created_again.status_code == 201
    assert int(created_again.data["id"]) == doc_id

    detail = client.get(f"/api/procurement/docs/{doc_id}/")
    assert detail.status_code == 200
    assert detail.data["status"] == "DRAFT"
    assert int(detail.data["number"]) == 0
    assert detail.data["accounting_status"] == ""

    posted = client.post(f"/api/procurement/docs/{doc_id}/post/", {}, format="json")
    assert posted.status_code == 200
    assert posted.data["status"] == "POSTED"
    assert int(posted.data["number"]) > 0
    assert posted.data["accounting_status"] in _VALID_ACCOUNTING_STATUSES

    voided = client.post(
        f"/api/procurement/docs/{doc_id}/void/",
        {"reason": "VOID_FOR_TEST"},
        format="json",
    )
    assert voided.status_code == 200
    assert voided.data["status"] == "VOIDED"
    assert voided.data["accounting_status"] in _VALID_ACCOUNTING_STATUSES

    outbox_types = set(OutboxEvent.objects.filter(source_module="PROCUREMENT").values_list("event_type", flat=True))
    assert "ProcurementDocumentDrafted" in outbox_types
    assert "ProcurementDocumentPosted" in outbox_types
    assert "ProcurementDocumentVoided" in outbox_types


@pytest.mark.django_db
def test_phase10_procurement_shadow_projection_is_deterministic():
    company, branch = _mk_scope()
    client, user = _mk_client(company=company, branch=branch, perm_codes=_procurement_perms())
    call_command("seed_posting_rules_v1", company_id=company.id)

    created = client.post(
        "/api/procurement/docs/",
        {
            "doc_type": "SUPPLIER_INVOICE",
            "series": "P",
            "currency": "NIO",
            "supplier_name": "Proveedor 2",
            "supplier_ref": "PRV-002",
            "external_ref": "INV-EXT-2",
            "subtotal": "250.00",
            "tax_total": "37.50",
            "total": "287.50",
            "idempotency_key": "proc-002",
        },
        format="json",
    )
    assert created.status_code == 201
    doc_id = int(created.data["id"])

    posted = client.post(f"/api/procurement/docs/{doc_id}/post/", {}, format="json")
    assert posted.status_code == 200

    run = _mk_packaged_run(company=company, branch=branch, user=user)

    call_command("project_shadow_ledger", run_id=str(run.run_id))
    run.refresh_from_db()
    assert run.status == CloseRun.Status.PACKAGED

    event = (
        EconomicEvent.objects.filter(company=company, source_module="PROCUREMENT", event_type="ProcurementDocumentPosted")
        .order_by("-id")
        .first()
    )
    assert event is not None
    draft = JournalDraft.objects.filter(economic_event=event).first()
    assert draft is not None
    assert draft.state == JournalDraft.State.VALIDATED
    assert Decimal(draft.total_debit) == Decimal("287.50")
    assert Decimal(draft.total_credit) == Decimal("287.50")

    ee_count = EconomicEvent.objects.count()
    jd_count = JournalDraft.objects.count()
    call_command("project_shadow_ledger", run_id=str(run.run_id))
    assert EconomicEvent.objects.count() == ee_count
    assert JournalDraft.objects.count() == jd_count
