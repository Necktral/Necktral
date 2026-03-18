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
from typing import Any

import django
from django.conf import settings
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder
from django.db.models import Q
from django.utils import timezone

from apps.iam.models import CompanyLink, LinkGrant, OrgUnit
from apps.integration.services import dispatch_outbox_events
from apps.rbac.models import Permission

from .certification_phase7 import collect_phase7_operational_health
from .certification_phase7b import collect_phase7b_operational_health
from .models import CompanyAccountingConfig, FxRate, IntercompanyDisputeReason
from .phase7 import run_fx_revaluation
from .phase7b import Phase7BValidationError, run_consolidation, run_intercompany_cycle
from .services import post_journal_drafts

PHASE12_REQUIRED_PERMISSIONS = [
    "accounting.report.read",
    "accounting.revaluation.run",
    "accounting.intercompany.write",
    "accounting.intercompany.reconcile",
    "accounting.intercompany.dispute",
    "accounting.intercompany.settle",
    "accounting.consolidation.run",
]

FX_BLOCKED_POLICY_ALERT = "ALERT"
FX_BLOCKED_POLICY_BLOCK = "BLOCK"
FX_BLOCKED_POLICIES = {FX_BLOCKED_POLICY_ALERT, FX_BLOCKED_POLICY_BLOCK}


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
    return hashlib.sha256(_json_dumps(payload).encode("utf-8")).hexdigest()


def _signed_hash(payload: dict[str, Any], *, secret: str = "") -> tuple[str, str, str]:
    raw = _json_dumps(payload).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    if secret:
        sig = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
        return digest, sig, "hmac-sha256"
    return digest, digest, "sha256"


def build_phase12_evidence(*, payload: dict[str, Any], secret: str = "") -> dict[str, Any]:
    digest, signature, signature_type = _signed_hash(payload, secret=secret)
    return {
        **payload,
        "evidence_hash": digest,
        "signature": signature,
        "signature_type": signature_type,
    }


def normalize_fx_blocked_policy(value: str | None) -> str:
    policy = str(value or FX_BLOCKED_POLICY_ALERT).strip().upper()
    if policy not in FX_BLOCKED_POLICIES:
        raise ValueError(f"fx_blocked_policy inválida: {policy}. Use ALERT o BLOCK.")
    return policy


def _resolve_company(*, company_id: int) -> OrgUnit:
    company = OrgUnit.objects.filter(id=int(company_id), unit_type=OrgUnit.UnitType.COMPANY, is_active=True).first()
    if company is None:
        raise ValueError(f"company inválida o inactiva: {company_id}")
    return company


def _resolve_branch(*, company: OrgUnit, branch_id: int) -> OrgUnit:
    branch = OrgUnit.objects.filter(
        id=int(branch_id),
        unit_type=OrgUnit.UnitType.BRANCH,
        parent=company,
        is_active=True,
    ).first()
    if branch is None:
        raise ValueError(f"branch inválida o inactiva para company={company.id}: {branch_id}")
    return branch


def _git_commit_sha() -> str:
    for env_key in ("GIT_COMMIT_SHA", "SOURCE_VERSION", "SENTRY_RELEASE"):
        val = str(os.getenv(env_key, "")).strip()
        if val:
            return val
    repo_root = settings.BASE_DIR.parent.parent
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


def collect_phase12_env_manifest(*, company_id: int, branch_id: int) -> dict[str, Any]:
    company = _resolve_company(company_id=company_id)
    branch = _resolve_branch(company=company, branch_id=branch_id)

    migrations = list(MigrationRecorder(connection).migration_qs.values_list("app", "name").order_by("app", "name"))
    migration_ids = [f"{app}.{name}" for app, name in migrations]
    migrations_hash = hashlib.sha256("\n".join(migration_ids).encode("utf-8")).hexdigest()

    permission_rows: list[dict[str, Any]] = []
    found_codes = set()
    for row in Permission.objects.filter(code__in=PHASE12_REQUIRED_PERMISSIONS).order_by("code"):
        found_codes.add(row.code)
        permission_rows.append({"code": row.code, "is_active": bool(row.is_active)})
    for missing in sorted(set(PHASE12_REQUIRED_PERMISSIONS) - found_codes):
        permission_rows.append({"code": missing, "is_active": False})
    permissions_hash = _json_hash({"rows": permission_rows})

    cfg = CompanyAccountingConfig.objects.select_related(
        "fx_gain_account",
        "fx_loss_account",
        "retained_earnings_account",
    ).filter(company=company).first()
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
        "functional_currency": str(cfg.functional_currency) if cfg else "NIO",
        "phase7_enabled": bool(cfg.phase7_enabled) if cfg else False,
        "fx_gain_account_code": fx_gain_account_code,
        "fx_loss_account_code": fx_loss_account_code,
        "retained_earnings_account_code": retained_earnings_account_code,
    }
    config_hash = _json_hash(config_payload)

    link_rows = list(
        CompanyLink.objects.filter(is_active=True, status=CompanyLink.Status.ACTIVE)
        .filter(Q(from_company=company) | Q(to_company=company))
        .values("from_company_id", "to_company_id", "status", "is_active")
        .order_by("from_company_id", "to_company_id")
    )
    links_hash = _json_hash({"rows": link_rows})

    write_grants_rows = list(
        LinkGrant.objects.filter(
            Q(link__from_company=company) | Q(link__to_company=company),
            is_active=True,
            access_mode=LinkGrant.AccessMode.WRITE,
        )
        .values("link__from_company_id", "link__to_company_id", "permission__code", "scope_org_unit_id")
        .order_by("link__from_company_id", "link__to_company_id", "permission__code")
    )
    write_grants_hash = _json_hash({"rows": write_grants_rows})

    reason_rows = list(
        IntercompanyDisputeReason.objects.filter(company=company, is_active=True)
        .values("code", "version", "severity", "requires_evidence", "is_active")
        .order_by("code", "-version")
    )
    reasons_hash = _json_hash({"rows": reason_rows})

    latest_fx = (
        FxRate.objects.filter(company=company)
        .order_by("-rate_date", "-id")
        .values("rate_date", "from_currency", "to_currency", "rate_type", "rate")
        .first()
    )
    fx_state: dict[str, Any] = {
        "rates_count": int(FxRate.objects.filter(company=company).count()),
        "latest_rate": latest_fx or {},
    }
    fx_state_hash = _json_hash(fx_state)

    app_version = str(settings.SENTRY_RELEASE or settings.REST_FRAMEWORK.get("VERSION", "") or "").strip()
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(dt_timezone.utc).isoformat(),
        "scope": {
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
        "migrations": {"count": int(len(migration_ids)), "hash": migrations_hash, "items": migration_ids},
        "required_permissions": {"count": int(len(permission_rows)), "hash": permissions_hash, "items": permission_rows},
        "accounting_config": {**config_payload, "hash": config_hash},
        "company_links": {"count": int(len(link_rows)), "hash": links_hash, "items": link_rows},
        "write_grants": {"count": int(len(write_grants_rows)), "hash": write_grants_hash, "items": write_grants_rows},
        "dispute_reasons": {"count": int(len(reason_rows)), "hash": reasons_hash, "items": reason_rows},
        "fx_state": {**fx_state, "hash": fx_state_hash},
    }
    manifest["parity_fingerprint"] = _json_hash(
        {
            "environment": manifest["environment"],
            "database": manifest["database"],
            "migrations_hash": migrations_hash,
            "permissions_hash": permissions_hash,
            "accounting_config_hash": config_hash,
            "company_links_hash": links_hash,
            "write_grants_hash": write_grants_hash,
            "dispute_reasons_hash": reasons_hash,
            "fx_state_hash": fx_state_hash,
        }
    )
    return manifest


def compare_phase12_env_manifests(*, left: dict[str, Any], right: dict[str, Any]) -> list[dict[str, str]]:
    checks = [
        ("environment.app_version", (left.get("environment") or {}).get("app_version"), (right.get("environment") or {}).get("app_version")),
        (
            "environment.git_commit_sha",
            (left.get("environment") or {}).get("git_commit_sha"),
            (right.get("environment") or {}).get("git_commit_sha"),
        ),
        ("environment.timezone", (left.get("environment") or {}).get("timezone"), (right.get("environment") or {}).get("timezone")),
        ("database.engine", (left.get("database") or {}).get("engine"), (right.get("database") or {}).get("engine")),
        ("migrations.hash", (left.get("migrations") or {}).get("hash"), (right.get("migrations") or {}).get("hash")),
        (
            "required_permissions.hash",
            (left.get("required_permissions") or {}).get("hash"),
            (right.get("required_permissions") or {}).get("hash"),
        ),
        (
            "accounting_config.hash",
            (left.get("accounting_config") or {}).get("hash"),
            (right.get("accounting_config") or {}).get("hash"),
        ),
        ("company_links.hash", (left.get("company_links") or {}).get("hash"), (right.get("company_links") or {}).get("hash")),
        ("write_grants.hash", (left.get("write_grants") or {}).get("hash"), (right.get("write_grants") or {}).get("hash")),
        ("dispute_reasons.hash", (left.get("dispute_reasons") or {}).get("hash"), (right.get("dispute_reasons") or {}).get("hash")),
        ("fx_state.hash", (left.get("fx_state") or {}).get("hash"), (right.get("fx_state") or {}).get("hash")),
        ("parity_fingerprint", left.get("parity_fingerprint"), right.get("parity_fingerprint")),
    ]
    mismatches: list[dict[str, str]] = []
    for field, lval, rval in checks:
        if lval != rval:
            mismatches.append({"field": field, "left": str(lval), "right": str(rval)})
    return mismatches


def collect_phase12_operational_health(*, company_id: int, consumer: str = "accounting.projector") -> dict[str, Any]:
    phase7 = collect_phase7_operational_health(company_id=company_id, consumer=consumer)
    phase7b = collect_phase7b_operational_health(company_id=company_id, consumer=consumer)
    return {
        "phase7a": phase7,
        "phase7b": phase7b,
        "inbox_failed_count": max(int(phase7.get("inbox_failed_count") or 0), int(phase7b.get("inbox_failed_count") or 0)),
        "outbox_failed_count": max(
            int(phase7.get("outbox_failed_count") or 0),
            int(phase7b.get("outbox_failed_count") or 0),
        ),
    }


def _period_key(*, year: int, month: int) -> str:
    return f"{int(year):04d}-{int(month):02d}"


def _scope_hash(*, company_id: int, parent_company_id: int, company_ids: list[int]) -> str:
    return _json_hash(
        {
            "company_id": int(company_id),
            "parent_company_id": int(parent_company_id),
            "company_ids": sorted({int(x) for x in company_ids}),
        }
    )


def _health_signature(health: dict[str, Any]) -> dict[str, int]:
    phase7 = dict(health.get("phase7a") or {})
    phase7b = dict(health.get("phase7b") or {})
    return {
        "inbox_failed_count": int(health.get("inbox_failed_count") or 0),
        "outbox_failed_count": int(health.get("outbox_failed_count") or 0),
        "missing_lines_count": int(phase7.get("missing_lines_count") or 0),
        "stale_revaluation_count": int(phase7.get("stale_revaluation_count") or 0),
        "unbalanced_entries_count": int(phase7.get("unbalanced_entries_count") or 0),
        "open_intercompany_count": int(phase7b.get("open_intercompany_count") or 0),
        "disputed_intercompany_count": int(phase7b.get("disputed_intercompany_count") or 0),
        "blocked_consolidation_count": int(phase7b.get("blocked_consolidation_count") or 0),
        "open_consolidation_exception_count": int(phase7b.get("open_consolidation_exception_count") or 0),
    }


def _intercompany_signature(rows: list[dict[str, Any]]) -> list[dict[str, int]]:
    normalized: list[dict[str, int]] = []
    for row in rows:
        normalized.append(
            {
                "company_id": int(row.get("company_id") or 0),
                "processed": int(row.get("processed") or 0),
                "confirmed": int(row.get("confirmed") or 0),
                "differences": int(row.get("differences") or 0),
                "disputed": int(row.get("disputed") or 0),
                "closed": int(row.get("closed") or 0),
                "open_items": int(row.get("open_items") or 0),
            }
        )
    normalized.sort(key=lambda x: int(x.get("company_id") or 0))
    return normalized


def _canonical_manifest(report: dict[str, Any]) -> dict[str, Any]:
    checks = list(report.get("checks") or [])
    checks_signature = [
        {
            "name": str(item.get("name") or ""),
            "passed": bool(item.get("passed")),
        }
        for item in checks
    ]
    checks_signature.sort(key=lambda item: str(item["name"]))

    warnings_payload = [
        {
            "code": str(item.get("code") or ""),
            "severity": str(item.get("severity") or "WARN"),
        }
        for item in list(report.get("warnings") or [])
    ]
    warnings_payload.sort(key=lambda item: (str(item["code"]), str(item["severity"])))

    posting = dict(report.get("posting") or {})
    revaluation = dict(report.get("revaluation") or {})
    consolidation = dict(report.get("consolidation") or {})
    return {
        "schema_version": 2,
        "period_key": str(report.get("period_key") or ""),
        "scope_hash": str(report.get("scope_hash") or ""),
        "fx_policy_applied": str(report.get("fx_policy_applied") or FX_BLOCKED_POLICY_ALERT),
        "cycle_passed": bool(report.get("cycle_passed")),
        "risk_level": str(report.get("risk_level") or "HIGH"),
        "warnings": warnings_payload,
        "posting": {
            "failed": int(posting.get("failed") or 0),
        },
        "revaluation": {
            "status": str(revaluation.get("status") or ""),
            "issues_count": int(revaluation.get("issues_count") or 0),
            "fx_blocked_warning": bool(revaluation.get("fx_blocked_warning")),
        },
        "intercompany": _intercompany_signature(list(report.get("intercompany") or [])),
        "consolidation": {
            "status": str(consolidation.get("status") or ""),
            "manifest_hash": str(consolidation.get("manifest_hash") or ""),
            "issues_count": int(consolidation.get("issues_count") or 0),
        },
        "health": _health_signature(dict(report.get("health") or {})),
        "checks": checks_signature,
    }


def _derive_risk_level(*, cycle_passed: bool, warnings: list[dict[str, Any]]) -> str:
    if not cycle_passed:
        return "HIGH"
    if warnings:
        return "MEDIUM"
    return "LOW"


@dataclass(frozen=True)
class Phase12CycleResult:
    cycle_passed: bool
    report: dict[str, Any]
    manifest_hash: str


def run_phase12_monthly_close(
    *,
    company_id: int,
    parent_company_id: int,
    company_ids: list[int],
    year: int,
    month: int,
    consumer: str = "accounting.projector",
    posting_limit: int = 500,
    intercompany_limit: int = 200,
    dispatch_limit: int = 200,
    max_inbox_failed: int = 0,
    max_outbox_failed: int = 0,
    max_missing_lines: int = 0,
    max_stale_revaluation: int = 0,
    max_open_intercompany: int = 0,
    max_disputed_intercompany: int = 0,
    max_blocked_consolidation: int = 0,
    max_open_consolidation_exception: int = 0,
    fx_blocked_policy: str = FX_BLOCKED_POLICY_ALERT,
) -> Phase12CycleResult:
    policy = normalize_fx_blocked_policy(fx_blocked_policy)
    scope_company_ids = sorted({int(company_id), *{int(x) for x in company_ids}})
    period_key = _period_key(year=year, month=month)
    scope_hash = _scope_hash(company_id=company_id, parent_company_id=parent_company_id, company_ids=scope_company_ids)

    dispatch_before = dispatch_outbox_events(limit=int(dispatch_limit))
    posting = post_journal_drafts(
        company_id=int(company_id),
        run_id="",
        limit=int(posting_limit),
        require_approved=False,
        auto_approve=False,
    )

    revaluation_error = ""
    fx_blocked_warning = False
    warnings: list[dict[str, Any]] = []
    try:
        revaluation = run_fx_revaluation(
            company_id=int(company_id),
            year=int(year),
            month=int(month),
            strict=False,
        )
    except Exception as exc:  # noqa: BLE001
        revaluation = None
        revaluation_error = str(exc)

    revaluation_payload = (
        {
            "run_id": str(revaluation.run_id),
            "status": str(revaluation.status),
            "idempotent": bool(revaluation.idempotent),
            "entries_created": int(revaluation.entries_created),
            "issues_count": int(revaluation.issues_count),
            "fx_blocked_warning": False,
        }
        if revaluation is not None
        else {
            "run_id": "",
            "status": "FAILED",
            "error": revaluation_error,
            "idempotent": False,
            "entries_created": 0,
            "issues_count": 1,
            "fx_blocked_warning": False,
        }
    )
    fx_status = str(revaluation_payload.get("status") or "")
    if fx_status == "BLOCKED":
        fx_blocked_warning = True
        warnings.append(
            {
                "code": "FX_REVALUATION_BLOCKED",
                "severity": "WARN",
                "message": "Revaluación FX bloqueada; permitida por política ALERT.",
                "detail": {
                    "period_key": period_key,
                    "run_id": str(revaluation_payload.get("run_id") or ""),
                },
            }
        )
    revaluation_payload["fx_blocked_warning"] = bool(fx_blocked_warning)
    if fx_status == "COMPLETED":
        fx_policy_passed = True
    elif fx_status == "BLOCKED":
        fx_policy_passed = bool(policy == FX_BLOCKED_POLICY_ALERT)
    else:
        fx_policy_passed = False

    intercompany_reports: list[dict[str, Any]] = []
    intercompany_errors: list[str] = []
    for cid in scope_company_ids:
        try:
            cycle = run_intercompany_cycle(
                company_id=int(cid),
                limit=int(intercompany_limit),
                strict=False,
                actor_user=None,
            )
            intercompany_reports.append(
                {
                    "company_id": int(cid),
                    "processed": int(cycle.processed),
                    "confirmed": int(cycle.confirmed),
                    "differences": int(cycle.differences),
                    "disputed": int(cycle.disputed),
                    "closed": int(cycle.closed),
                    "open_items": int(cycle.open_items),
                    "report_hash": str(cycle.report_hash),
                }
            )
        except Exception as exc:  # noqa: BLE001
            intercompany_errors.append(f"company={cid}:{exc}")

    try:
        consolidation = run_consolidation(
            parent_company_id=int(parent_company_id),
            year=int(year),
            month=int(month),
            company_ids=scope_company_ids,
            strict=False,
            actor_user=None,
        )
        consolidation_error = ""
    except Phase7BValidationError as exc:
        consolidation = None
        consolidation_error = str(exc)

    consolidation_payload = (
        {
            "run_id": str(consolidation.run_id),
            "status": str(consolidation.status),
            "idempotent": bool(consolidation.idempotent),
            "manifest_hash": str(consolidation.manifest_hash),
            "issues_count": int(consolidation.issues_count),
        }
        if consolidation is not None
        else {"run_id": "", "status": "FAILED", "error": consolidation_error, "idempotent": False, "issues_count": 1}
    )

    dispatch_after = dispatch_outbox_events(limit=int(dispatch_limit), source_module="ACCOUNTING")
    health = collect_phase12_operational_health(company_id=int(company_id), consumer=consumer)
    phase7 = dict(health.get("phase7a") or {})
    phase7b = dict(health.get("phase7b") or {})

    checks = [
        {
            "name": "fx_revaluation_policy",
            "passed": bool(fx_policy_passed),
            "detail": {
                "status": fx_status,
                "policy": policy,
                "fx_blocked_warning": bool(fx_blocked_warning),
            },
        },
        {
            "name": "inbox_failed_within_threshold",
            "passed": int(health.get("inbox_failed_count") or 0) <= int(max_inbox_failed),
            "detail": {"count": int(health.get("inbox_failed_count") or 0), "max_allowed": int(max_inbox_failed)},
        },
        {
            "name": "outbox_failed_within_threshold",
            "passed": int(health.get("outbox_failed_count") or 0) <= int(max_outbox_failed),
            "detail": {"count": int(health.get("outbox_failed_count") or 0), "max_allowed": int(max_outbox_failed)},
        },
        {
            "name": "missing_lines_within_threshold",
            "passed": int(phase7.get("missing_lines_count") or 0) <= int(max_missing_lines),
            "detail": {"count": int(phase7.get("missing_lines_count") or 0), "max_allowed": int(max_missing_lines)},
        },
        {
            "name": "stale_revaluation_within_threshold",
            "passed": int(phase7.get("stale_revaluation_count") or 0) <= int(max_stale_revaluation),
            "detail": {
                "count": int(phase7.get("stale_revaluation_count") or 0),
                "max_allowed": int(max_stale_revaluation),
            },
        },
        {
            "name": "open_intercompany_within_threshold",
            "passed": int(phase7b.get("open_intercompany_count") or 0) <= int(max_open_intercompany),
            "detail": {
                "count": int(phase7b.get("open_intercompany_count") or 0),
                "max_allowed": int(max_open_intercompany),
            },
        },
        {
            "name": "disputed_intercompany_within_threshold",
            "passed": int(phase7b.get("disputed_intercompany_count") or 0) <= int(max_disputed_intercompany),
            "detail": {
                "count": int(phase7b.get("disputed_intercompany_count") or 0),
                "max_allowed": int(max_disputed_intercompany),
            },
        },
        {
            "name": "blocked_consolidation_within_threshold",
            "passed": int(phase7b.get("blocked_consolidation_count") or 0) <= int(max_blocked_consolidation),
            "detail": {
                "count": int(phase7b.get("blocked_consolidation_count") or 0),
                "max_allowed": int(max_blocked_consolidation),
            },
        },
        {
            "name": "open_consolidation_exception_within_threshold",
            "passed": int(phase7b.get("open_consolidation_exception_count") or 0) <= int(max_open_consolidation_exception),
            "detail": {
                "count": int(phase7b.get("open_consolidation_exception_count") or 0),
                "max_allowed": int(max_open_consolidation_exception),
            },
        },
        {
            "name": "intercompany_cycle_errors_empty",
            "passed": len(intercompany_errors) == 0,
            "detail": {"errors": intercompany_errors},
        },
        {
            "name": "consolidation_not_failed",
            "passed": consolidation_error == "" and str(consolidation_payload.get("status") or "") in ("COMPLETED", "BLOCKED"),
            "detail": {"error": consolidation_error, "status": str(consolidation_payload.get("status") or "")},
        },
        {
            "name": "posting_without_failures",
            "passed": int(posting.failed) == 0,
            "detail": {"failed": int(posting.failed)},
        },
    ]
    cycle_passed = all(bool(item["passed"]) for item in checks)

    report = {
        "schema_version": 2,
        "generated_at": timezone.now().isoformat(),
        "pilot_scope": {
            "company_id": int(company_id),
            "parent_company_id": int(parent_company_id),
            "company_ids": scope_company_ids,
        },
        "period": {"year": int(year), "month": int(month)},
        "period_key": period_key,
        "scope_hash": scope_hash,
        "consumer": consumer,
        "fx_policy_applied": policy,
        "cycle_passed": bool(cycle_passed),
        "dispatch_before": {
            "attempted": int(dispatch_before.attempted),
            "sent": int(dispatch_before.sent),
            "retried": int(dispatch_before.retried),
            "failed": int(dispatch_before.failed),
        },
        "posting": {
            "attempted": int(posting.attempted),
            "approved": int(posting.approved),
            "posted": int(posting.posted),
            "skipped": int(posting.skipped),
            "failed": int(posting.failed),
            "errors": posting.errors,
        },
        "revaluation": revaluation_payload,
        "intercompany": intercompany_reports,
        "consolidation": consolidation_payload,
        "dispatch_after": {
            "attempted": int(dispatch_after.attempted),
            "sent": int(dispatch_after.sent),
            "retried": int(dispatch_after.retried),
            "failed": int(dispatch_after.failed),
        },
        "health": health,
        "checks": checks,
        "warnings": warnings,
    }
    report["risk_level"] = _derive_risk_level(cycle_passed=bool(cycle_passed), warnings=warnings)
    canonical_manifest = _canonical_manifest(report)
    report["manifest_hash"] = _json_hash(canonical_manifest)
    report["canonical_manifest"] = canonical_manifest

    return Phase12CycleResult(
        cycle_passed=bool(cycle_passed),
        report=report,
        manifest_hash=str(report["manifest_hash"]),
    )


@dataclass(frozen=True)
class Phase12DeterminismResult:
    passed: bool
    deterministic_replay: bool
    first_manifest_hash: str
    second_manifest_hash: str
    first_report: dict[str, Any]
    second_report: dict[str, Any]
    fx_policy_applied: str
    warnings: list[dict[str, Any]]


def certify_phase12_monthly_determinism(
    *,
    company_id: int,
    parent_company_id: int,
    company_ids: list[int],
    year: int,
    month: int,
    consumer: str = "accounting.projector",
    fx_blocked_policy: str = FX_BLOCKED_POLICY_ALERT,
) -> Phase12DeterminismResult:
    policy = normalize_fx_blocked_policy(fx_blocked_policy)
    first = run_phase12_monthly_close(
        company_id=company_id,
        parent_company_id=parent_company_id,
        company_ids=company_ids,
        year=year,
        month=month,
        consumer=consumer,
        max_inbox_failed=999999,
        max_outbox_failed=999999,
        max_missing_lines=999999,
        max_stale_revaluation=999999,
        max_open_intercompany=999999,
        max_disputed_intercompany=999999,
        max_blocked_consolidation=999999,
        max_open_consolidation_exception=999999,
        fx_blocked_policy=policy,
    )
    second = run_phase12_monthly_close(
        company_id=company_id,
        parent_company_id=parent_company_id,
        company_ids=company_ids,
        year=year,
        month=month,
        consumer=consumer,
        max_inbox_failed=999999,
        max_outbox_failed=999999,
        max_missing_lines=999999,
        max_stale_revaluation=999999,
        max_open_intercompany=999999,
        max_disputed_intercompany=999999,
        max_blocked_consolidation=999999,
        max_open_consolidation_exception=999999,
        fx_blocked_policy=policy,
    )

    second_post = dict((second.report or {}).get("posting") or {})
    second_reval = dict((second.report or {}).get("revaluation") or {})
    second_warnings = list((second.report or {}).get("warnings") or [])
    second_reval_status = str(second_reval.get("status") or "")
    if policy == FX_BLOCKED_POLICY_BLOCK:
        fx_ok = second_reval_status == "COMPLETED"
    else:
        fx_ok = second_reval_status in ("COMPLETED", "BLOCKED")
        if second_reval_status == "BLOCKED" and not bool(second_reval.get("fx_blocked_warning")):
            fx_ok = False

    deterministic = bool(
        str(first.manifest_hash) == str(second.manifest_hash)
        and int(second_post.get("posted") or 0) == 0
        and fx_ok
    )
    passed = bool(first.cycle_passed and second.cycle_passed and deterministic)
    return Phase12DeterminismResult(
        passed=bool(passed),
        deterministic_replay=bool(deterministic),
        first_manifest_hash=str(first.manifest_hash),
        second_manifest_hash=str(second.manifest_hash),
        first_report=first.report,
        second_report=second.report,
        fx_policy_applied=policy,
        warnings=second_warnings,
    )
