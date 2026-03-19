from __future__ import annotations

import uuid
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.core.management import call_command
from rest_framework.test import APIClient

from apps.audit.models import AuditEvent
from apps.iam.models import OrgUnit, UserMembership
from apps.rbac.models import Permission, Role, RoleAssignment, RolePermission
from apps.reports.models import ReportExport, ReportReadAudit, ReportRun

User = get_user_model()
REPORTS_BASE = "/api/backend/reports"


def _mk_org_tree(label: str) -> tuple[OrgUnit, OrgUnit, OrgUnit]:
    holding = OrgUnit.objects.create(unit_type=OrgUnit.UnitType.HOLDING, name=f"H-{label}", code=f"H-{label}")
    company = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.COMPANY,
        name=f"C-{label}",
        code=f"C-{label}",
        parent=holding,
    )
    branch = OrgUnit.objects.create(
        unit_type=OrgUnit.UnitType.BRANCH,
        name=f"B-{label}",
        code=f"B-{label}",
        parent=company,
    )
    return holding, company, branch


def _mk_user(*, label: str, password: str = "Pass12345!") -> Any:
    return User.objects.create_user(username=f"user_{label}", email=f"{label}@test.com", password=password)


def _grant_local_permission(*, user: Any, company: OrgUnit, branch: OrgUnit, permission_code: str) -> None:
    role = Role.objects.create(name=f"role-{uuid.uuid4().hex[:8]}", is_active=True)
    perm, _ = Permission.objects.get_or_create(
        code=permission_code,
        defaults={"description": permission_code, "is_active": True},
    )
    RolePermission.objects.get_or_create(role=role, permission=perm)
    RoleAssignment.objects.create(user=user, role=role, org_unit=company, is_active=True)
    RoleAssignment.objects.create(user=user, role=role, org_unit=branch, is_active=True)


def _login_client(*, user: Any, password: str, company: OrgUnit, branch: OrgUnit) -> APIClient:
    client = APIClient()
    resp = client.post("/api/backend/auth/login/", {"username": user.username, "password": password}, format="json")
    assert resp.status_code == 200
    access = resp.data.get("access")
    assert isinstance(access, str) and access
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {access}",
        HTTP_X_COMPANY_ID=str(company.id),
        HTTP_X_BRANCH_ID=str(branch.id),
    )
    return client


@pytest.mark.django_db
def test_reports_end_to_end_definitions_runs_exports_read_audit_and_sources():
    _, company, branch = _mk_org_tree("e2e")
    user = _mk_user(label="e2e")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    perms = [
        "reports.definition.create",
        "reports.definition.read",
        "reports.run.create",
        "reports.run.read",
        "reports.export",
        "reports.audit.read",
        "reports.observability.read",
        "reports.trace.read",
    ]
    for code in perms:
        _grant_local_permission(user=user, company=company, branch=branch, permission_code=code)

    client = _login_client(user=user, password="Pass12345!", company=company, branch=branch)

    for code in ["AUDIT_EVENTS_BY_SCOPE", "OBS_ENDPOINT_ERRORS_SUMMARY", "TRACE_ENTITY_TIMELINE"]:
        resp = client.post(f"{REPORTS_BASE}/definitions/", {"code": code, "name": code}, format="json")
        assert resp.status_code == 201

    legacy_health = client.get("/api/reports/health/")
    assert legacy_health.status_code == 200
    assert legacy_health["Deprecation"] == "true"
    assert legacy_health["Sunset"]
    assert legacy_health["Link"] == '</api/backend/reports/>; rel="successor-version"'

    # Run AUDIT (high sensitivity)
    run_audit = client.post(
        f"{REPORTS_BASE}/runs/",
        {"code": "AUDIT_EVENTS_BY_SCOPE", "params": {"limit": 10}},
        format="json",
    )
    assert run_audit.status_code == 201
    execution_id = run_audit.data["execution_id"]

    # Export without reason is forbidden for high/restricted reports.
    forbidden = client.post(
        f"{REPORTS_BASE}/exports/",
        {"execution_id": execution_id, "format": "json"},
        format="json",
    )
    assert forbidden.status_code == 403
    assert forbidden.data["error"]["code"] == "REPORT_EXPORT_FORBIDDEN"

    exported = client.post(
        f"{REPORTS_BASE}/exports/",
        {"execution_id": execution_id, "format": "json", "reason": "internal investigation"},
        format="json",
    )
    assert exported.status_code == 201
    export_id = exported.data["export_id"]
    detail = client.get(f"{REPORTS_BASE}/exports/{export_id}/")
    assert detail.status_code == 200
    assert detail.data["status"] in {ReportExport.ExportStatus.READY, ReportExport.ExportStatus.PENDING_APPROVAL}

    # Sensitive read requires reason.
    denied_read = client.get(f"{REPORTS_BASE}/runs/{execution_id}/")
    assert denied_read.status_code == 403
    assert denied_read.data["error"]["code"] == "REPORT_FORBIDDEN"

    allowed_read = client.get(f"{REPORTS_BASE}/runs/{execution_id}/?reason=post_mortem")
    assert allowed_read.status_code == 200
    assert allowed_read.data["execution_id"] == execution_id

    read_audit_list = client.get(f"{REPORTS_BASE}/read-audit/")
    assert read_audit_list.status_code == 200
    assert read_audit_list.data["count"] >= 1
    assert ReportReadAudit.objects.filter(company=company, report_code="AUDIT_EVENTS_BY_SCOPE").exists()

    # sources endpoint available
    sources = client.get(f"{REPORTS_BASE}/sources/")
    assert sources.status_code == 200
    assert sources.data["count"] >= 1

    audited = set(AuditEvent.objects.filter(module="REPORTS").values_list("event_type", flat=True))
    assert "REPORT_DEFINITION_CREATED" in audited
    assert "REPORT_RUN_STARTED" in audited
    assert "REPORT_RUN_SUCCEEDED" in audited
    assert "REPORT_EXPORTED" in audited
    assert "REPORT_READ_AUDITED" in audited


@pytest.mark.django_db
def test_reports_family_permission_is_enforced_for_audit():
    _, company, branch = _mk_org_tree("family")
    user = _mk_user(label="family")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    # User can run reports in general but not audit family read permission.
    for code in ["reports.definition.create", "reports.run.create", "reports.run.read"]:
        _grant_local_permission(user=user, company=company, branch=branch, permission_code=code)

    client = _login_client(user=user, password="Pass12345!", company=company, branch=branch)
    resp = client.post(f"{REPORTS_BASE}/definitions/", {"code": "AUDIT_EVENTS_BY_SCOPE", "name": "Audit"}, format="json")
    assert resp.status_code == 201

    denied = client.post(f"{REPORTS_BASE}/runs/", {"code": "AUDIT_EVENTS_BY_SCOPE", "params": {}}, format="json")
    assert denied.status_code == 403
    assert denied.data["error"]["code"] == "REPORT_FORBIDDEN"


@pytest.mark.django_db
def test_reports_async_queue_processing():
    _, company, branch = _mk_org_tree("async")
    user = _mk_user(label="async")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    for code in ["reports.definition.create", "reports.run.create", "reports.run.read", "reports.trace.read"]:
        _grant_local_permission(user=user, company=company, branch=branch, permission_code=code)

    client = _login_client(user=user, password="Pass12345!", company=company, branch=branch)
    resp = client.post(f"{REPORTS_BASE}/definitions/", {"code": "TRACE_ENTITY_TIMELINE", "name": "Trace"}, format="json")
    assert resp.status_code == 201

    queued = client.post(
        f"{REPORTS_BASE}/runs/",
        {"code": "TRACE_ENTITY_TIMELINE", "params": {"limit": 20}, "run_async": True},
        format="json",
    )
    assert queued.status_code == 202
    execution_id = queued.data["execution_id"]

    run = ReportRun.objects.get(run_id=execution_id)
    assert run.status == ReportRun.Status.QUEUED

    call_command("process_report_queue", limit=5)

    run.refresh_from_db()
    assert run.status in {ReportRun.Status.SUCCEEDED, ReportRun.Status.FAILED}


@pytest.mark.django_db
def test_reports_retry_cancel_and_contractual_error_codes():
    _, company, branch = _mk_org_tree("contract")
    user = _mk_user(label="contract")
    UserMembership.objects.create(user=user, org_unit=company, is_active=True)
    UserMembership.objects.create(user=user, org_unit=branch, is_active=True)

    perms = [
        "reports.definition.create",
        "reports.run.create",
        "reports.run.read",
        "reports.trace.read",
        "reports.export",
    ]
    for code in perms:
        _grant_local_permission(user=user, company=company, branch=branch, permission_code=code)

    client = _login_client(user=user, password="Pass12345!", company=company, branch=branch)
    resp = client.post(f"{REPORTS_BASE}/definitions/", {"code": "TRACE_ENTITY_TIMELINE", "name": "Trace"}, format="json")
    assert resp.status_code == 201

    queued = client.post(
        f"{REPORTS_BASE}/runs/",
        {"code": "TRACE_ENTITY_TIMELINE", "params": {"limit": 20}, "run_async": True},
        format="json",
    )
    assert queued.status_code == 202
    execution_id = queued.data["execution_id"]

    cancel_resp = client.post(f"{REPORTS_BASE}/runs/{execution_id}/cancel/", {}, format="json")
    assert cancel_resp.status_code == 200
    assert cancel_resp.data["status"] == ReportRun.Status.CANCELED

    retry_resp = client.post(f"{REPORTS_BASE}/runs/{execution_id}/retry/", {"priority": 3}, format="json")
    assert retry_resp.status_code in {201, 202}
    retry_execution_id = retry_resp.data["execution_id"]
    assert retry_execution_id

    call_command("process_report_queue", limit=5)
    retry_run = ReportRun.objects.get(run_id=retry_execution_id)

    # REPORT_DATA_CLASSIFICATION_CONFLICT via restricted + non-pdf.
    retry_run.sensitivity_level = ReportRun.SensitivityLevel.RESTRICTED
    retry_run.status = ReportRun.Status.SUCCEEDED
    retry_run.result = {"rows": [{"id": 1}]}
    retry_run.source_manifest_hash = "a" * 64
    retry_run.output_manifest_hash = "b" * 64
    retry_run.save(
        update_fields=["sensitivity_level", "status", "result", "source_manifest_hash", "output_manifest_hash"]
    )
    conflict = client.post(
        f"{REPORTS_BASE}/exports/",
        {"execution_id": str(retry_run.run_id), "format": "json", "reason": "ops"},
        format="json",
    )
    assert conflict.status_code == 403
    assert conflict.data["error"]["code"] == "REPORT_DATA_CLASSIFICATION_CONFLICT"

    # REPORT_REPRODUCIBILITY_VIOLATION for SNAPSHOT run without hashes.
    retry_run.sensitivity_level = ReportRun.SensitivityLevel.MEDIUM
    retry_run.reproducibility_mode = ReportRun.ReproducibilityMode.SNAPSHOT
    retry_run.source_manifest_hash = ""
    retry_run.output_manifest_hash = ""
    retry_run.save(update_fields=["sensitivity_level", "reproducibility_mode", "source_manifest_hash", "output_manifest_hash"])
    repro_violation = client.post(
        f"{REPORTS_BASE}/exports/",
        {"execution_id": str(retry_run.run_id), "format": "json"},
        format="json",
    )
    assert repro_violation.status_code == 422
    assert repro_violation.data["error"]["code"] == "REPORT_REPRODUCIBILITY_VIOLATION"
