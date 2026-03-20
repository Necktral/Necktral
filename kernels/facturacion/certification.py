from __future__ import annotations

import hashlib
import hmac
import json
import os
import platform
import subprocess
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import django
from django.conf import settings
from django.contrib.auth import get_user_model
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder
from django.utils import timezone

from apps.modulos.cec.models import CECException, CloseRun
from apps.modulos.cec.services import execute_close_run
from apps.modulos.iam.models import OrgUnit
from apps.modulos.integration.models import InboxEvent, OutboxEvent
from apps.modulos.payments.models import CashMovement, CashSession
from apps.modulos.rbac.models import Permission

from .models import BillingDocument, BranchFiscalConfig, DocStatus, DocType, FiscalMode, FiscalPrintJob, FiscalStatus
from .services import create_draft, get_or_update_branch_fiscal_config, issue_doc, process_fiscal_print_jobs, queue_fiscal_print

OPEN_EXCEPTION_STATUSES = (CECException.Status.OPEN, CECException.Status.IN_PROGRESS)
PHASE6_REQUIRED_PERMISSIONS = [
    "billing.fiscal.config.read",
    "billing.fiscal.config.update",
    "billing.doc.print",
    "billing.doc.contingency",
    "billing.doc.contingency.resolve",
    "cec.close_run.read",
    "cec.close_run.create",
    "cec.close_run.update",
]


def _json_hash(payload: dict[str, Any]) -> str:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _signed_hash(payload: dict[str, Any], *, secret: str = "") -> tuple[str, str, str]:
    raw = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    if secret:
        sig = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
        return digest, sig, "hmac-sha256"
    return digest, digest, "sha256"


def build_phase6_evidence(*, payload: dict[str, Any], secret: str = "") -> dict[str, Any]:
    digest, signature, signature_type = _signed_hash(payload, secret=secret)
    return {
        **payload,
        "evidence_hash": digest,
        "signature": signature,
        "signature_type": signature_type,
    }


def _git_commit_sha() -> str:
    for env_key in ("GIT_COMMIT_SHA", "SOURCE_VERSION", "SENTRY_RELEASE"):
        val = str(os.getenv(env_key, "")).strip()
        if val:
            return val

    repo_root = Path(settings.BASE_DIR).parent.parent
    try:
        output = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            stderr=subprocess.DEVNULL,
            text=True,
        )
        return output.strip()
    except Exception:  # noqa: BLE001
        return ""


def _db_server_version() -> str:
    vendor = connection.vendor
    query = None
    if vendor == "postgresql":
        query = "SHOW server_version"
    elif vendor == "sqlite":
        query = "select sqlite_version()"
    elif vendor == "mysql":
        query = "select version()"

    if not query:
        return ""

    try:
        with connection.cursor() as cursor:
            cursor.execute(query)
            row = cursor.fetchone()
            if row and row[0]:
                return str(row[0])
    except Exception:  # noqa: BLE001
        return ""
    return ""


def _resolve_scope(*, company_id: int, branch_id: int) -> tuple[OrgUnit, OrgUnit]:
    company = OrgUnit.objects.filter(
        id=int(company_id),
        unit_type=OrgUnit.UnitType.COMPANY,
        is_active=True,
    ).first()
    if company is None:
        raise ValueError(f"company inválida o inactiva: {company_id}")

    branch = OrgUnit.objects.filter(
        id=int(branch_id),
        unit_type=OrgUnit.UnitType.BRANCH,
        parent=company,
        is_active=True,
    ).first()
    if branch is None:
        raise ValueError(f"branch inválida o inactiva para company={company_id}: {branch_id}")

    return company, branch


def collect_phase6_env_manifest(*, company_id: int, branch_id: int) -> dict[str, Any]:
    company, branch = _resolve_scope(company_id=company_id, branch_id=branch_id)

    migrations = list(
        MigrationRecorder(connection)
        .migration_qs.values_list("app", "name")
        .order_by("app", "name")
    )
    migration_ids = [f"{app}.{name}" for app, name in migrations]
    migrations_hash = hashlib.sha256("\n".join(migration_ids).encode("utf-8")).hexdigest()
    phase6_migration = "facturacion.0002_phase6_adapter_b"

    permissions_rows: list[dict[str, Any]] = []
    found_codes = set()
    for row in Permission.objects.filter(code__in=PHASE6_REQUIRED_PERMISSIONS).order_by("code"):
        found_codes.add(row.code)
        permissions_rows.append(
            {
                "code": row.code,
                "is_active": bool(row.is_active),
            }
        )
    for missing in sorted(set(PHASE6_REQUIRED_PERMISSIONS) - found_codes):
        permissions_rows.append({"code": missing, "is_active": False})
    permissions_hash = _json_hash({"rows": permissions_rows})

    cfg_qs = BranchFiscalConfig.objects.filter(company=company, branch=branch).order_by("-updated_at", "-id")
    cfg_rows: list[dict[str, Any]] = []
    for cfg in cfg_qs:
        cfg_rows.append(
            {
                "company_id": int(cfg.company_id),
                "branch_id": int(cfg.branch_id),
                "fiscal_mode": cfg.fiscal_mode,
                "adapter_code": cfg.adapter_code or "",
                "print_required": bool(cfg.print_required),
                "strict_integrity": bool(cfg.strict_integrity),
                "contingency_max_attempts": int(cfg.contingency_max_attempts),
                "is_active": bool(cfg.is_active),
                "updated_at": cfg.updated_at.isoformat(),
            }
        )
    fiscal_config_hash = _json_hash({"rows": cfg_rows})

    app_version = str(settings.SENTRY_RELEASE or settings.REST_FRAMEWORK.get("VERSION", "") or "").strip()
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(dt_timezone.utc).isoformat(),
        "pilot_scope": {
            "company_id": int(company.id),
            "company_name": company.name,
            "branch_id": int(branch.id),
            "branch_name": branch.name,
        },
        "environment": {
            "app_version": app_version,
            "git_commit_sha": _git_commit_sha(),
            "django_version": django.get_version(),
            "python_version": platform.python_version(),
            "timezone": settings.TIME_ZONE,
            "use_tz": bool(settings.USE_TZ),
            "language_code": settings.LANGUAGE_CODE,
        },
        "database": {
            "engine": settings.DATABASES["default"]["ENGINE"],
            "vendor": connection.vendor,
            "server_version": _db_server_version(),
        },
        "migrations": {
            "count": len(migration_ids),
            "hash": migrations_hash,
            "phase6_migration_applied": phase6_migration in migration_ids,
            "phase6_migration": phase6_migration,
            "items": migration_ids,
        },
        "required_permissions": {
            "count": len(permissions_rows),
            "hash": permissions_hash,
            "items": permissions_rows,
        },
        "branch_fiscal_config": {
            "count": len(cfg_rows),
            "hash": fiscal_config_hash,
            "items": cfg_rows,
        },
    }
    manifest["parity_fingerprint"] = _json_hash(
        {
            "environment": manifest["environment"],
            "database": manifest["database"],
            "migrations_hash": migrations_hash,
            "permissions_hash": permissions_hash,
            "fiscal_config_hash": fiscal_config_hash,
        }
    )
    return manifest


def compare_phase6_env_manifests(*, left: dict[str, Any], right: dict[str, Any]) -> list[dict[str, str]]:
    checks = [
        ("environment.app_version", left.get("environment", {}).get("app_version"), right.get("environment", {}).get("app_version")),
        (
            "environment.git_commit_sha",
            left.get("environment", {}).get("git_commit_sha"),
            right.get("environment", {}).get("git_commit_sha"),
        ),
        ("environment.timezone", left.get("environment", {}).get("timezone"), right.get("environment", {}).get("timezone")),
        ("environment.use_tz", left.get("environment", {}).get("use_tz"), right.get("environment", {}).get("use_tz")),
        (
            "environment.language_code",
            left.get("environment", {}).get("language_code"),
            right.get("environment", {}).get("language_code"),
        ),
        ("database.engine", left.get("database", {}).get("engine"), right.get("database", {}).get("engine")),
        ("migrations.hash", left.get("migrations", {}).get("hash"), right.get("migrations", {}).get("hash")),
        (
            "migrations.phase6_migration_applied",
            left.get("migrations", {}).get("phase6_migration_applied"),
            right.get("migrations", {}).get("phase6_migration_applied"),
        ),
        (
            "required_permissions.hash",
            left.get("required_permissions", {}).get("hash"),
            right.get("required_permissions", {}).get("hash"),
        ),
        (
            "branch_fiscal_config.hash",
            left.get("branch_fiscal_config", {}).get("hash"),
            right.get("branch_fiscal_config", {}).get("hash"),
        ),
        ("parity_fingerprint", left.get("parity_fingerprint"), right.get("parity_fingerprint")),
    ]
    mismatches = []
    for key, lval, rval in checks:
        if lval != rval:
            mismatches.append(
                {
                    "field": key,
                    "left": str(lval),
                    "right": str(rval),
                }
            )
    return mismatches


def collect_phase6_operational_health(
    *,
    company_id: int,
    branch_id: int,
    consumer: str = "accounting.projector",
    stale_minutes: int = 30,
) -> dict[str, int]:
    now = timezone.now()
    stale_cutoff = now - timedelta(minutes=max(1, int(stale_minutes)))

    inbox_failed_count = InboxEvent.objects.filter(
        consumer=consumer,
        status=InboxEvent.Status.FAILED,
    ).count()
    outbox_failed_count = OutboxEvent.objects.filter(
        company_id=int(company_id),
        branch_id=int(branch_id),
        source_module__in=["BILLING", "CEC", "ACCOUNTING", "INVENTORY", "PAYMENTS"],
        status=OutboxEvent.Status.FAILED,
    ).count()
    failed_jobs_count = FiscalPrintJob.objects.filter(
        company_id=int(company_id),
        branch_id=int(branch_id),
        status=FiscalPrintJob.Status.FAILED,
    ).count()
    retry_overdue_count = FiscalPrintJob.objects.filter(
        company_id=int(company_id),
        branch_id=int(branch_id),
        status=FiscalPrintJob.Status.RETRY,
        next_attempt_at__isnull=False,
        next_attempt_at__lte=now,
    ).count()
    stale_pending_count = FiscalPrintJob.objects.filter(
        company_id=int(company_id),
        branch_id=int(branch_id),
        status=FiscalPrintJob.Status.PENDING,
        created_at__lte=stale_cutoff,
    ).count()
    contingency_open_count = BillingDocument.objects.filter(
        company_id=int(company_id),
        branch_id=int(branch_id),
        status=DocStatus.ISSUED,
        fiscal_mode_resolved=FiscalMode.B,
        fiscal_status=FiscalStatus.CONTINGENCY,
    ).count()
    cec_blocking_open_count = CECException.objects.filter(
        company_id=int(company_id),
        branch_id=int(branch_id),
        status__in=OPEN_EXCEPTION_STATUSES,
        is_blocking=True,
        source_module="CEC",
    ).count()
    return {
        "inbox_failed_count": int(inbox_failed_count),
        "outbox_failed_count": int(outbox_failed_count),
        "failed_jobs_count": int(failed_jobs_count),
        "retry_overdue_count": int(retry_overdue_count),
        "stale_pending_count": int(stale_pending_count),
        "contingency_open_count": int(contingency_open_count),
        "cec_blocking_open_count": int(cec_blocking_open_count),
    }


@dataclass(frozen=True)
class AdapterBCertificationResult:
    run_id: str
    passed: bool
    blocked: bool
    deterministic_replay: bool
    close_run_status: str
    first_manifest_hash: str
    second_manifest_hash: str
    first_counts: dict[str, int]
    second_counts: dict[str, int]
    pilot_scope: dict[str, int]
    job_counts: dict[str, int]
    contingency_counts: dict[str, int]
    cec_blocking_exceptions: int
    go_live_passed: bool


def _system_request(*, company: OrgUnit, branch: OrgUnit, user, request_id: str, data: dict | None = None):
    return SimpleNamespace(
        company=company,
        branch=branch,
        user=user,
        request_id=request_id,
        data=(data or {}),
        META={},
        headers={},
        path="/management/certify_adapter_b_run",
        method="SYSTEM",
    )


def _ensure_system_user(*, company_id: int, branch_id: int):
    User = get_user_model()
    username = f"phase6_certifier_c{company_id}_b{branch_id}"
    user = User.objects.filter(username=username).first()
    if user:
        return user
    email = f"{username}@system.local"
    return User.objects.create_user(username=username, email=email, password=uuid.uuid4().hex)


def _run_counts(*, run: CloseRun, doc: BillingDocument) -> dict[str, int]:
    job_qs = FiscalPrintJob.objects.filter(doc=doc)
    counts = {
        "print_jobs_total": int(job_qs.count()),
        "print_jobs_pending": int(job_qs.filter(status=FiscalPrintJob.Status.PENDING).count()),
        "print_jobs_retry": int(job_qs.filter(status=FiscalPrintJob.Status.RETRY).count()),
        "print_jobs_printed": int(job_qs.filter(status=FiscalPrintJob.Status.PRINTED).count()),
        "print_jobs_failed": int(job_qs.filter(status=FiscalPrintJob.Status.FAILED).count()),
        "doc_print_attempt_count": int(doc.print_attempt_count),
        "cec_blocking_exceptions": int(
            CECException.objects.filter(
                close_run=run,
                status__in=OPEN_EXCEPTION_STATUSES,
                is_blocking=True,
            ).count()
        ),
        "cec_total_exceptions": int(
            CECException.objects.filter(
                close_run=run,
                status__in=OPEN_EXCEPTION_STATUSES,
            ).count()
        ),
        "contingency_docs_open": int(
            BillingDocument.objects.filter(
                company=doc.company,
                branch=doc.branch,
                status=DocStatus.ISSUED,
                fiscal_mode_resolved=FiscalMode.B,
                fiscal_status=FiscalStatus.CONTINGENCY,
            ).count()
        ),
    }

    billing_events_for_doc = OutboxEvent.objects.filter(
        source_module="BILLING",
        company=doc.company,
        branch=doc.branch,
        payload__data__doc_id=doc.id,
    ).count()
    counts["billing_events_for_doc"] = int(billing_events_for_doc)
    return counts


def _register_cash_for_document(*, doc: BillingDocument, actor, at_time) -> None:
    expected_amount = Decimal(str(doc.total))
    session = CashSession.objects.create(
        company=doc.company,
        branch=doc.branch,
        opened_by=actor,
        closed_by=actor,
        status=CashSession.Status.CLOSED,
        opened_at=at_time - timedelta(minutes=10),
        closed_at=at_time + timedelta(minutes=10),
        opening_amount=Decimal("0.00"),
        expected_amount=expected_amount,
        counted_amount=expected_amount,
        difference_amount=Decimal("0.00"),
        notes="phase6 certification synthetic cash session",
    )
    CashMovement.objects.create(
        session=session,
        movement_type=CashMovement.MovementType.INCOME,
        amount=expected_amount,
        reference=f"CERT-DOC-{doc.id}",
        reason="phase6 certification",
        created_by=actor,
        created_at=at_time,
        metadata={"doc_id": int(doc.id)},
    )


def _cert_manifest_hash(*, run: CloseRun, doc: BillingDocument, counts: dict[str, int]) -> str:
    payload = {
        "run_id": str(run.run_id),
        "close_run_status": run.status,
        "cec_output_manifest_hash": run.output_manifest_hash,
        "doc_id": int(doc.id),
        "doc_status": doc.status,
        "doc_fiscal_status": doc.fiscal_status,
        "doc_fiscal_reference": doc.fiscal_reference,
        "job_counts": counts,
    }
    return _json_hash(payload)


def certify_adapter_b_run(
    *,
    company_id: int,
    branch_id: int,
    expect_blocked: bool = False,
    adapter_code: str = "EMULATED_B",
) -> AdapterBCertificationResult:
    company, branch = _resolve_scope(company_id=company_id, branch_id=branch_id)
    cert_user = _ensure_system_user(company_id=int(company.id), branch_id=int(branch.id))

    cfg_attempts = 2 if expect_blocked else 5
    normalized_adapter_code = str(adapter_code or "EMULATED_B").strip().upper() or "EMULATED_B"
    get_or_update_branch_fiscal_config(
        company=company,
        branch=branch,
        actor=cert_user,
        data={
            "fiscal_mode": FiscalMode.B,
            "adapter_code": normalized_adapter_code,
            "print_required": True,
            "strict_integrity": True,
            "contingency_max_attempts": cfg_attempts,
            "is_active": True,
        },
    )

    req_id = f"phase6-cert-{uuid.uuid4().hex[:12]}"
    request = _system_request(company=company, branch=branch, user=cert_user, request_id=req_id)

    doc_seed = uuid.uuid4().hex[:12]
    created = create_draft(
        request=request,
        actor=cert_user,
        doc_type=DocType.INVOICE,
        series="B",
        currency="NIO",
        customer_name=f"CERT-{doc_seed}",
        customer_ref=f"CERT-{doc_seed}",
        is_fiscal=True,
        lines=[
            {
                "description": "Certification adapter B",
                "quantity": "1.0000",
                "unit_price": "100.000000",
                "tax_rate": "0.1500",
            }
        ],
        idempotency_key=f"phase6-cert-draft-{doc_seed}",
    )
    print_idempotency_key = f"phase6-cert-print-{doc_seed}"
    issue_doc(
        request=request,
        actor=cert_user,
        doc_id=int(created.doc_id),
        apply_inventory=False,
        print_after_issue=True,
        idempotency_key=print_idempotency_key,
    )

    doc = BillingDocument.objects.get(id=int(created.doc_id))
    if expect_blocked:
        metadata = dict(doc.fiscal_metadata_json or {})
        metadata["force_print_failure"] = True
        doc.fiscal_metadata_json = metadata
        doc.save(update_fields=["fiscal_metadata_json"])

    replay_1 = queue_fiscal_print(
        request=request,
        actor=cert_user,
        doc_id=int(doc.id),
        idempotency_key=print_idempotency_key,
    )

    now = timezone.now()
    max_attempts = max(2, int(cfg_attempts) + 1)
    for idx in range(max_attempts):
        process_fiscal_print_jobs(
            limit=50,
            now=now + timedelta(minutes=(idx + 1) * 70),
            company_id=int(company.id),
            branch_id=int(branch.id),
            actor=cert_user,
        )

    doc.refresh_from_db()
    run = CloseRun.objects.create(
        company=company,
        branch=branch,
        run_type=CloseRun.RunType.DAILY,
        status=CloseRun.Status.CREATED,
        created_by=cert_user,
    )
    _register_cash_for_document(doc=doc, actor=cert_user, at_time=now)
    execute_close_run(
        run=run,
        request=request,
        actor=cert_user,
        window_start=now - timedelta(hours=2),
        window_end=now + timedelta(hours=2),
        strict=True,
    )
    run.refresh_from_db()
    doc.refresh_from_db()

    blocked = run.status == CloseRun.Status.REOPENED_EXCEPTION
    if blocked != bool(expect_blocked):
        raise ValueError(
            f"Resultado de bloqueo inesperado: expect_blocked={int(expect_blocked)} status={run.status}"
        )

    first_counts = _run_counts(run=run, doc=doc)
    first_manifest_hash = _cert_manifest_hash(run=run, doc=doc, counts=first_counts)

    replay_2 = queue_fiscal_print(
        request=request,
        actor=cert_user,
        doc_id=int(doc.id),
        idempotency_key=print_idempotency_key,
    )
    replay_summary = process_fiscal_print_jobs(
        limit=50,
        now=now + timedelta(days=1),
        company_id=int(company.id),
        branch_id=int(branch.id),
        actor=cert_user,
    )
    doc.refresh_from_db()
    run.refresh_from_db()

    second_counts = _run_counts(run=run, doc=doc)
    second_manifest_hash = _cert_manifest_hash(run=run, doc=doc, counts=second_counts)

    deterministic_replay = (
        bool(replay_1.created is False)
        and bool(replay_2.created is False)
        and int(replay_summary.attempted) == 0
        and first_counts == second_counts
        and first_manifest_hash == second_manifest_hash
    )

    if expect_blocked:
        scenario_ok = (
            doc.fiscal_status == FiscalStatus.CONTINGENCY
            and run.status == CloseRun.Status.REOPENED_EXCEPTION
            and int(first_counts["cec_blocking_exceptions"]) > 0
        )
    else:
        scenario_ok = (
            doc.fiscal_status == FiscalStatus.PRINTED
            and run.status == CloseRun.Status.PACKAGED
            and int(first_counts["cec_blocking_exceptions"]) == 0
        )

    passed = bool(deterministic_replay and scenario_ok)
    return AdapterBCertificationResult(
        run_id=str(run.run_id),
        passed=passed,
        blocked=blocked,
        deterministic_replay=bool(deterministic_replay),
        close_run_status=run.status,
        first_manifest_hash=first_manifest_hash,
        second_manifest_hash=second_manifest_hash,
        first_counts=first_counts,
        second_counts=second_counts,
        pilot_scope={"company_id": int(company.id), "branch_id": int(branch.id)},
        job_counts={
            "total": int(first_counts["print_jobs_total"]),
            "printed": int(first_counts["print_jobs_printed"]),
            "retry": int(first_counts["print_jobs_retry"]),
            "failed": int(first_counts["print_jobs_failed"]),
            "pending": int(first_counts["print_jobs_pending"]),
        },
        contingency_counts={
            "open_contingency_docs": int(first_counts["contingency_docs_open"]),
        },
        cec_blocking_exceptions=int(first_counts["cec_blocking_exceptions"]),
        go_live_passed=passed,
    )
