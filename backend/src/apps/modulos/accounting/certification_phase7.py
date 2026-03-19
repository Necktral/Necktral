from __future__ import annotations

import hashlib
import hmac
import json
import os
import platform
import subprocess
from dataclasses import dataclass
from datetime import date
from datetime import datetime, timezone as dt_timezone
from pathlib import Path
from typing import Any

import django
from django.conf import settings
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder
from django.db.models import Count, F
from django.utils import timezone

from apps.modulos.iam.models import OrgUnit
from apps.modulos.integration.models import InboxEvent, OutboxEvent
from apps.modulos.rbac.models import Permission

from .models import CompanyAccountingConfig, JournalEntry, JournalEntryLine, RevaluationRun
from .phase7 import resolve_period_range, run_fx_revaluation, trial_balance_queryset
from .services import post_journal_drafts

PHASE7_REQUIRED_PERMISSIONS = [
    "accounting.coa.read",
    "accounting.coa.update",
    "accounting.fx_rate.read",
    "accounting.fx_rate.update",
    "accounting.report.read",
    "accounting.revaluation.run",
]


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(
        payload,
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
        default=_json_default,
    )


def _json_hash(payload: dict[str, Any]) -> str:
    raw = _json_dumps(payload)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _signed_hash(payload: dict[str, Any], *, secret: str = "") -> tuple[str, str, str]:
    raw = _json_dumps(payload).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    if secret:
        sig = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
        return digest, sig, "hmac-sha256"
    return digest, digest, "sha256"


def build_phase7_evidence(*, payload: dict[str, Any], secret: str = "") -> dict[str, Any]:
    digest, signature, signature_type = _signed_hash(payload, secret=secret)
    return {
        **payload,
        "evidence_hash": digest,
        "signature": signature,
        "signature_type": signature_type,
    }


def _resolve_company(*, company_id: int) -> OrgUnit:
    company = OrgUnit.objects.filter(
        id=int(company_id),
        unit_type=OrgUnit.UnitType.COMPANY,
        is_active=True,
    ).first()
    if company is None:
        raise ValueError(f"company inválida o inactiva: {company_id}")
    return company


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


def collect_phase7_env_manifest(*, company_id: int) -> dict[str, Any]:
    company = _resolve_company(company_id=company_id)
    migrations = list(MigrationRecorder(connection).migration_qs.values_list("app", "name").order_by("app", "name"))
    migration_ids = [f"{app}.{name}" for app, name in migrations]
    migrations_hash = hashlib.sha256("\n".join(migration_ids).encode("utf-8")).hexdigest()

    permissions_rows: list[dict[str, Any]] = []
    found_codes = set()
    for row in Permission.objects.filter(code__in=PHASE7_REQUIRED_PERMISSIONS).order_by("code"):
        found_codes.add(row.code)
        permissions_rows.append({"code": row.code, "is_active": bool(row.is_active)})
    for missing in sorted(set(PHASE7_REQUIRED_PERMISSIONS) - found_codes):
        permissions_rows.append({"code": missing, "is_active": False})
    perms_hash = _json_hash({"rows": permissions_rows})

    cfg = (
        CompanyAccountingConfig.objects.select_related(
            "fx_gain_account",
            "fx_loss_account",
            "retained_earnings_account",
        )
        .filter(company=company)
        .first()
    )
    fx_gain_account_code = ""
    fx_loss_account_code = ""
    retained_earnings_account_code = ""
    if cfg is not None and cfg.fx_gain_account_id:
        fx_gain = cfg.fx_gain_account
        if fx_gain is not None:
            fx_gain_account_code = str(fx_gain.code)
    if cfg is not None and cfg.fx_loss_account_id:
        fx_loss = cfg.fx_loss_account
        if fx_loss is not None:
            fx_loss_account_code = str(fx_loss.code)
    if cfg is not None and cfg.retained_earnings_account_id:
        retained = cfg.retained_earnings_account
        if retained is not None:
            retained_earnings_account_code = str(retained.code)
    config_payload = {
        "phase7_enabled": bool(cfg.phase7_enabled) if cfg else False,
        "functional_currency": str(cfg.functional_currency) if cfg else "NIO",
        "fx_gain_account_code": fx_gain_account_code,
        "fx_loss_account_code": fx_loss_account_code,
        "retained_earnings_account_code": retained_earnings_account_code,
    }
    config_hash = _json_hash(config_payload)

    coa_rows = list(
        company.acc_chart_accounts.order_by("code", "id").values(
            "code", "name", "account_type", "is_postable", "is_active", "is_revaluable", "parent__code"
        )
    )
    coa_hash = _json_hash({"rows": coa_rows})

    latest_reval = (
        RevaluationRun.objects.filter(company=company, status=RevaluationRun.Status.COMPLETED)
        .order_by("-year", "-month", "-completed_at", "-id")
        .values("run_id", "year", "month", "completed_at")
        .first()
    )
    reval_payload: dict[str, Any] = {
        "completed_runs_count": int(
            RevaluationRun.objects.filter(company=company, status=RevaluationRun.Status.COMPLETED).count()
        ),
        "latest": latest_reval or {},
    }
    reval_hash = _json_hash(reval_payload)

    app_version = str(settings.SENTRY_RELEASE or settings.REST_FRAMEWORK.get("VERSION", "") or "").strip()
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(dt_timezone.utc).isoformat(),
        "scope": {"company_id": int(company.id), "company_name": company.name},
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
        "migrations": {"count": len(migration_ids), "hash": migrations_hash, "items": migration_ids},
        "required_permissions": {"count": len(permissions_rows), "hash": perms_hash, "items": permissions_rows},
        "accounting_config": {**config_payload, "hash": config_hash},
        "chart_of_accounts": {"count": len(coa_rows), "hash": coa_hash, "items": coa_rows},
        "revaluation_state": {**reval_payload, "hash": reval_hash},
    }
    manifest["parity_fingerprint"] = _json_hash(
        {
            "environment": manifest["environment"],
            "database": manifest["database"],
            "migrations_hash": migrations_hash,
            "permissions_hash": perms_hash,
            "config_hash": config_hash,
            "coa_hash": coa_hash,
            "reval_hash": reval_hash,
        }
    )
    return manifest


def compare_phase7_env_manifests(*, left: dict[str, Any], right: dict[str, Any]) -> list[dict[str, str]]:
    checks = [
        ("environment.app_version", left.get("environment", {}).get("app_version"), right.get("environment", {}).get("app_version")),
        (
            "environment.git_commit_sha",
            left.get("environment", {}).get("git_commit_sha"),
            right.get("environment", {}).get("git_commit_sha"),
        ),
        ("environment.timezone", left.get("environment", {}).get("timezone"), right.get("environment", {}).get("timezone")),
        ("database.engine", left.get("database", {}).get("engine"), right.get("database", {}).get("engine")),
        ("migrations.hash", left.get("migrations", {}).get("hash"), right.get("migrations", {}).get("hash")),
        (
            "required_permissions.hash",
            left.get("required_permissions", {}).get("hash"),
            right.get("required_permissions", {}).get("hash"),
        ),
        (
            "accounting_config.hash",
            left.get("accounting_config", {}).get("hash"),
            right.get("accounting_config", {}).get("hash"),
        ),
        ("chart_of_accounts.hash", left.get("chart_of_accounts", {}).get("hash"), right.get("chart_of_accounts", {}).get("hash")),
        ("parity_fingerprint", left.get("parity_fingerprint"), right.get("parity_fingerprint")),
    ]
    mismatches = []
    for key, lval, rval in checks:
        if lval != rval:
            mismatches.append({"field": key, "left": str(lval), "right": str(rval)})
    return mismatches


def collect_phase7_operational_health(*, company_id: int, consumer: str = "accounting.projector") -> dict[str, int]:
    company = _resolve_company(company_id=company_id)
    now = timezone.localdate()
    inbox_failed_count = InboxEvent.objects.filter(consumer=consumer, status=InboxEvent.Status.FAILED).count()
    outbox_failed_count = OutboxEvent.objects.filter(
        company=company,
        source_module__in=["ACCOUNTING", "CEC", "BILLING", "INVENTORY", "PAYMENTS", "PROCUREMENT"],
        status=OutboxEvent.Status.FAILED,
    ).count()
    unbalanced_entries_count = JournalEntry.objects.filter(company=company).exclude(debit_total=F("credit_total")).count()
    missing_lines_count = (
        JournalEntry.objects.filter(company=company, is_posted=True)
        .annotate(lines_count=Count("lines"))
        .filter(lines_count=0)
        .count()
    )
    stale_revaluation_count = 0
    cfg = CompanyAccountingConfig.objects.filter(company=company).first()
    if cfg and cfg.phase7_enabled:
        has_current_reval = RevaluationRun.objects.filter(
            company=company,
            year=int(now.year),
            month=int(now.month),
            status=RevaluationRun.Status.COMPLETED,
        ).exists()
        stale_revaluation_count = 0 if has_current_reval else 1
    return {
        "inbox_failed_count": int(inbox_failed_count),
        "outbox_failed_count": int(outbox_failed_count),
        "unbalanced_entries_count": int(unbalanced_entries_count),
        "missing_lines_count": int(missing_lines_count),
        "stale_revaluation_count": int(stale_revaluation_count),
    }


def _trial_balance_hash(*, company: OrgUnit, year: int, month: int) -> str:
    date_from, date_to = resolve_period_range(year=year, month=month) or (None, None)
    qs = trial_balance_queryset(company=company, date_from=date_from, date_to=date_to)
    rows = [
        {
            "account_code": str(row["account__code"]),
            "debit_total": str(row["debit_total"]),
            "credit_total": str(row["credit_total"]),
        }
        for row in qs
    ]
    return _json_hash({"rows": rows, "year": year, "month": month})


@dataclass(frozen=True)
class Phase7CertificationResult:
    run_id: str
    revaluation_run_id: str
    passed: bool
    blocked: bool
    deterministic_replay: bool
    posting_first: dict[str, Any]
    posting_second: dict[str, Any]
    first_counts: dict[str, int]
    second_counts: dict[str, int]
    first_manifest_hash: str
    second_manifest_hash: str
    close_run_status: str
    go_live_passed: bool


def _counts_for_run(*, company: OrgUnit, run_id: str) -> dict[str, int]:
    entries_qs = JournalEntry.objects.filter(company=company, draft__close_run_id=str(run_id))
    return {
        "journal_entries": int(entries_qs.count()),
        "journal_entry_lines": int(JournalEntryLine.objects.filter(journal_entry__in=entries_qs).count()),
        "missing_lines": int(entries_qs.annotate(lines_count=Count("lines")).filter(lines_count=0).count()),
    }


def certify_phase7_gl_run(
    *,
    company_id: int,
    run_id: str,
    year: int,
    month: int,
    expect_blocked: bool = False,
) -> Phase7CertificationResult:
    company = _resolve_company(company_id=company_id)
    first_post = post_journal_drafts(
        company_id=int(company.id),
        run_id=str(run_id),
        limit=5000,
        require_approved=False,
        auto_approve=False,
    )
    first_counts = _counts_for_run(company=company, run_id=str(run_id))
    first_hash = _trial_balance_hash(company=company, year=int(year), month=int(month))

    reval_first = run_fx_revaluation(
        company_id=int(company.id),
        year=int(year),
        month=int(month),
        strict=True,
    )
    blocked = str(reval_first.status) == "BLOCKED"
    if expect_blocked and not blocked:
        raise ValueError("Se esperaba bloqueo de revaluación y no ocurrió.")
    if not expect_blocked and blocked:
        raise ValueError("Se esperaba revaluación exitosa y quedó bloqueada.")

    second_post = post_journal_drafts(
        company_id=int(company.id),
        run_id=str(run_id),
        limit=5000,
        require_approved=False,
        auto_approve=False,
    )
    second_counts = _counts_for_run(company=company, run_id=str(run_id))
    second_hash = _trial_balance_hash(company=company, year=int(year), month=int(month))
    reval_second = run_fx_revaluation(
        company_id=int(company.id),
        year=int(year),
        month=int(month),
        strict=True,
    )

    deterministic = (
        first_counts == second_counts
        and first_hash == second_hash
        and int(second_post.posted) == 0
        and bool(reval_second.idempotent)
    )
    passed = bool(deterministic and (blocked == bool(expect_blocked)))
    posting_first = {
        "attempted": int(first_post.attempted),
        "approved": int(first_post.approved),
        "posted": int(first_post.posted),
        "skipped": int(first_post.skipped),
        "failed": int(first_post.failed),
        "errors": first_post.errors,
    }
    posting_second = {
        "attempted": int(second_post.attempted),
        "approved": int(second_post.approved),
        "posted": int(second_post.posted),
        "skipped": int(second_post.skipped),
        "failed": int(second_post.failed),
        "errors": second_post.errors,
    }

    return Phase7CertificationResult(
        run_id=str(run_id),
        revaluation_run_id=str(reval_first.run_id),
        passed=bool(passed),
        blocked=bool(blocked),
        deterministic_replay=bool(deterministic),
        posting_first=posting_first,
        posting_second=posting_second,
        first_counts=first_counts,
        second_counts=second_counts,
        first_manifest_hash=first_hash,
        second_manifest_hash=second_hash,
        close_run_status="PACKAGED" if not blocked else "REOPENED_EXCEPTION",
        go_live_passed=bool(passed),
    )
