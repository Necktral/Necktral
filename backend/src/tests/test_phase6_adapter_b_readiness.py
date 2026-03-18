from __future__ import annotations

import uuid
from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.iam.models import OrgUnit, UserMembership
from apps.integration.models import OutboxEvent
from apps.rbac.models import Permission, Role, RoleAssignment, RolePermission
from modulos.facturacion.fiscal_adapters import get_fiscal_adapter
from modulos.facturacion.models import BillingDocument, DocStatus, DocType, FiscalMode, FiscalPrintJob, FiscalStatus
from modulos.facturacion.services import process_fiscal_print_jobs

User = get_user_model()


def _mk_org():
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name="H")
    company = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.COMPANY, name="C", parent=holding)
    branch = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.BRANCH, name="B", parent=company)
    return company, branch


def _client_with_perms(*, company: OrgUnit, branch: OrgUnit, perm_codes: list[str]) -> tuple[APIClient, Any]:
    username = f"u_{uuid.uuid4().hex[:10]}"
    user = User.objects.create_user(username=username, email=f"{username}@test.com", password="pass12345")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    role = Role.objects.create(name=f"role_{uuid.uuid4().hex[:8]}", is_active=True)
    for code in perm_codes:
        perm, _ = Permission.objects.get_or_create(code=code, defaults={"description": code, "is_active": True})
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
    return client, user


def _billing_perms() -> list[str]:
    return [
        "billing.fiscal.config.read",
        "billing.fiscal.config.update",
        "billing.doc.create",
        "billing.doc.read",
        "billing.doc.issue",
        "billing.doc.void",
        "billing.doc.print",
        "billing.doc.contingency",
        "billing.doc.contingency.resolve",
    ]


def _create_doc(client: APIClient) -> int:
    create = client.post(
        "/api/billing/docs/",
        {
            "doc_type": "INVOICE",
            "series": "B",
            "currency": "NIO",
            "customer_name": "Cliente B",
            "is_fiscal": True,
            "lines": [
                {
                    "description": "Servicio",
                    "quantity": "1.0000",
                    "unit_price": "100.000000",
                    "tax_rate": "0.1500",
                }
            ],
        },
        format="json",
    )
    assert create.status_code == 201
    return int(create.data["id"])


@pytest.mark.django_db
def test_phase6_branch_config_issue_and_print_worker_happy_path():
    company, branch = _mk_org()
    client, _ = _client_with_perms(company=company, branch=branch, perm_codes=_billing_perms())

    cfg = client.put(
        "/api/billing/fiscal/branch-config/",
        {
            "fiscal_mode": "B",
            "adapter_code": "EMULATED_B",
            "print_required": True,
            "strict_integrity": True,
            "contingency_max_attempts": 5,
            "is_active": True,
        },
        format="json",
    )
    assert cfg.status_code == 200
    assert cfg.data["fiscal_mode"] == "B"

    doc_id = _create_doc(client)
    issue = client.post(
        f"/api/billing/docs/{doc_id}/issue/",
        {"print_after_issue": True, "idempotency_key": "phase6-issue-print-1"},
        format="json",
    )
    assert issue.status_code == 200
    assert issue.data["fiscal_mode"] == "B"
    assert issue.data["fiscal_status"] == "ISSUED"
    assert issue.data["fiscal_reference"]
    assert issue.data["print_job_id"] > 0

    call_command("process_fiscal_print_jobs", limit=20)
    detail = client.get(f"/api/billing/docs/{doc_id}/")
    assert detail.status_code == 200
    assert detail.data["fiscal"]["status"] == "PRINTED"
    assert detail.data["fiscal"]["attempts"] >= 1

    outbox_types = set(OutboxEvent.objects.filter(source_module="BILLING").values_list("event_type", flat=True))
    assert "BILLING.FiscalNumberReserved" in outbox_types
    assert "BILLING.FiscalDocumentIssued" in outbox_types
    assert "BILLING.FiscalPrintRequested" in outbox_types
    assert "BILLING.FiscalPrinted" in outbox_types


@pytest.mark.django_db
def test_phase6_print_worker_retries_and_contingency_after_max_attempts():
    company, branch = _mk_org()
    client, _ = _client_with_perms(company=company, branch=branch, perm_codes=_billing_perms())

    cfg = client.put(
        "/api/billing/fiscal/branch-config/",
        {
            "fiscal_mode": "B",
            "adapter_code": "EMULATED_B",
            "print_required": True,
            "strict_integrity": True,
            "contingency_max_attempts": 2,
            "is_active": True,
        },
        format="json",
    )
    assert cfg.status_code == 200

    doc_id = _create_doc(client)
    issue = client.post(
        f"/api/billing/docs/{doc_id}/issue/",
        {"print_after_issue": True, "idempotency_key": "phase6-issue-print-2"},
        format="json",
    )
    assert issue.status_code == 200

    doc = BillingDocument.objects.get(id=doc_id)
    doc.fiscal_metadata_json = {"force_print_failure": True}
    doc.save(update_fields=["fiscal_metadata_json"])

    summary_1 = process_fiscal_print_jobs(limit=20, now=timezone.now())
    assert summary_1.attempted >= 1
    doc.refresh_from_db()
    job = FiscalPrintJob.objects.filter(doc=doc).order_by("-id").first()
    assert job is not None
    assert doc.fiscal_status == FiscalStatus.FAILED_PRINT
    assert job.status == FiscalPrintJob.Status.RETRY

    summary_2 = process_fiscal_print_jobs(limit=20, now=timezone.now() + timedelta(hours=2))
    assert summary_2.attempted >= 1
    doc.refresh_from_db()
    job.refresh_from_db()
    assert doc.fiscal_status == FiscalStatus.CONTINGENCY
    assert job.status == FiscalPrintJob.Status.FAILED
    assert OutboxEvent.objects.filter(source_module="BILLING", event_type="BILLING.FiscalContingencyRecorded").exists()


@pytest.mark.django_db
def test_phase6_void_from_failed_print_returns_conflict_409():
    company, branch = _mk_org()
    client, _ = _client_with_perms(company=company, branch=branch, perm_codes=_billing_perms())

    cfg = client.put(
        "/api/billing/fiscal/branch-config/",
        {
            "fiscal_mode": "B",
            "adapter_code": "EMULATED_B",
            "print_required": True,
            "strict_integrity": True,
            "contingency_max_attempts": 5,
            "is_active": True,
        },
        format="json",
    )
    assert cfg.status_code == 200

    doc_id = _create_doc(client)
    issue = client.post(f"/api/billing/docs/{doc_id}/issue/", {"print_after_issue": False}, format="json")
    assert issue.status_code == 200

    BillingDocument.objects.filter(id=doc_id).update(fiscal_status=FiscalStatus.FAILED_PRINT)
    void = client.post(f"/api/billing/docs/{doc_id}/void/", {"reason": "VOID_FROM_FAILED_PRINT"}, format="json")
    assert void.status_code == 409
    assert void.data["error"]["code"] == "CONFLICT"


@pytest.mark.django_db
def test_phase6_contingency_resolve_retry_print_endpoint():
    company, branch = _mk_org()
    client, _ = _client_with_perms(company=company, branch=branch, perm_codes=_billing_perms())

    cfg = client.put(
        "/api/billing/fiscal/branch-config/",
        {
            "fiscal_mode": "B",
            "adapter_code": "EMULATED_B",
            "print_required": True,
            "strict_integrity": True,
            "contingency_max_attempts": 5,
            "is_active": True,
        },
        format="json",
    )
    assert cfg.status_code == 200

    doc_id = _create_doc(client)
    issue = client.post(f"/api/billing/docs/{doc_id}/issue/", {"print_after_issue": False}, format="json")
    assert issue.status_code == 200

    contingency = client.post(
        f"/api/billing/docs/{doc_id}/contingency/",
        {"reason": "MANUAL_CONTINGENCY"},
        format="json",
    )
    assert contingency.status_code == 200
    assert contingency.data["fiscal_status"] == "CONTINGENCY"

    resolve = client.post(
        f"/api/billing/docs/{doc_id}/contingency/resolve/",
        {"action": "RETRY_PRINT", "idempotency_key": "contingency-retry-1"},
        format="json",
    )
    assert resolve.status_code == 200
    assert resolve.data["action"] == "RETRY_PRINT"
    assert resolve.data["job_id"] > 0


@pytest.mark.django_db
def test_phase6_cec_gate_blocks_on_fiscal_b_failed_print():
    company, branch = _mk_org()
    client, user = _client_with_perms(
        company=company,
        branch=branch,
        perm_codes=_billing_perms() + ["cec.close_run.read", "cec.close_run.create", "cec.close_run.update"],
    )

    cfg = client.put(
        "/api/billing/fiscal/branch-config/",
        {
            "fiscal_mode": "B",
            "adapter_code": "EMULATED_B",
            "print_required": True,
            "strict_integrity": True,
            "contingency_max_attempts": 5,
            "is_active": True,
        },
        format="json",
    )
    assert cfg.status_code == 200

    now = timezone.now()
    BillingDocument.objects.create(
        company=company,
        branch=branch,
        doc_type=DocType.INVOICE,
        status=DocStatus.ISSUED,
        series="B",
        number=999,
        currency="NIO",
        customer_name="CEC B",
        subtotal=Decimal("100.00"),
        tax_total=Decimal("15.00"),
        total=Decimal("115.00"),
        is_fiscal=True,
        fiscal_mode_resolved=FiscalMode.B,
        fiscal_status=FiscalStatus.FAILED_PRINT,
        issued_at=now - timedelta(minutes=5),
        created_by=user,
    )

    run_resp = client.post("/api/cec/close-runs/", {"run_type": "DAILY"}, format="json")
    assert run_resp.status_code == 201
    run_id = run_resp.data["run_id"]

    execute = client.post(
        f"/api/cec/close-runs/{run_id}/execute/",
        {
            "window_start": (now - timedelta(hours=1)).isoformat(),
            "window_end": (now + timedelta(hours=1)).isoformat(),
            "strict": True,
        },
        format="json",
    )
    assert execute.status_code == 200
    assert execute.data["status"] == "REOPENED_EXCEPTION"
    assert execute.data["blocking_exceptions_count"] >= 1

    summary = client.get(f"/api/cec/close-runs/{run_id}/summary/")
    assert summary.status_code == 200
    codes = {row["code"] for row in summary.data["exceptions"]}
    assert "FISCAL_B_PRINT_FAILED" in codes


@pytest.mark.django_db
@override_settings(FISCAL_ADAPTER_MODE="B")
def test_phase6_adapter_resolution_fallback_and_branch_override():
    company, branch = _mk_org()
    adapter_default = get_fiscal_adapter(company=company, branch=branch)
    assert adapter_default.mode == FiscalMode.B

    from modulos.facturacion.models import BranchFiscalConfig

    BranchFiscalConfig.objects.create(
        company=company,
        branch=branch,
        fiscal_mode=FiscalMode.NOOP,
        adapter_code="NOOP",
        print_required=False,
        strict_integrity=True,
        contingency_max_attempts=5,
        is_active=True,
    )
    adapter_override = get_fiscal_adapter(company=company, branch=branch)
    assert adapter_override.mode == FiscalMode.NOOP
