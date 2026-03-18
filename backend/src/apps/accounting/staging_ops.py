from __future__ import annotations

import hashlib
import hmac
import json
from datetime import date, datetime
from datetime import timezone as dt_timezone
from typing import Any

from django.conf import settings
from django.db.models import Q

from apps.iam.models import OrgUnit
from modulos.facturacion.certification import collect_phase6_env_manifest, collect_phase6_operational_health
from modulos.facturacion.models import BranchFiscalConfig, FiscalMode

from .certification_phase7 import collect_phase7_env_manifest, collect_phase7_operational_health
from .certification_phase7b import collect_phase7b_operational_health
from .models import ChartOfAccount, CompanyAccountingConfig, PostingRuleSet

DEFAULT_STAGING_THRESHOLDS = {
    "inbox_failed": 0,
    "outbox_failed": 0,
    "missing_lines": 0,
    "stale_revaluation": 0,
    "open_intercompany": 0,
    "disputed": 0,
}


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
        signature = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
        return digest, signature, "hmac-sha256"
    return digest, digest, "sha256"


def build_staging_ops_evidence(*, payload: dict[str, Any], secret: str = "") -> dict[str, Any]:
    digest, signature, signature_type = _signed_hash(payload, secret=secret)
    return {
        **payload,
        "evidence_hash": digest,
        "signature": signature,
        "signature_type": signature_type,
    }


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


def _resolve_thresholds(
    *,
    inbox_failed: int = 0,
    outbox_failed: int = 0,
    missing_lines: int = 0,
    stale_revaluation: int = 0,
    open_intercompany: int = 0,
    disputed: int = 0,
) -> dict[str, int]:
    return {
        "inbox_failed": max(0, int(inbox_failed)),
        "outbox_failed": max(0, int(outbox_failed)),
        "missing_lines": max(0, int(missing_lines)),
        "stale_revaluation": max(0, int(stale_revaluation)),
        "open_intercompany": max(0, int(open_intercompany)),
        "disputed": max(0, int(disputed)),
    }


def _build_health_checks(
    *,
    phase6_health: dict[str, int],
    phase7_health: dict[str, int],
    phase7b_health: dict[str, int],
    thresholds: dict[str, int],
) -> list[dict[str, Any]]:
    checks = [
        {
            "name": "inbox_failed_within_threshold",
            "passed": max(
                int(phase6_health.get("inbox_failed_count") or 0),
                int(phase7_health.get("inbox_failed_count") or 0),
                int(phase7b_health.get("inbox_failed_count") or 0),
            )
            <= int(thresholds["inbox_failed"]),
            "detail": {
                "phase6": int(phase6_health.get("inbox_failed_count") or 0),
                "phase7a": int(phase7_health.get("inbox_failed_count") or 0),
                "phase7b": int(phase7b_health.get("inbox_failed_count") or 0),
                "max_allowed": int(thresholds["inbox_failed"]),
            },
        },
        {
            "name": "outbox_failed_within_threshold",
            "passed": max(
                int(phase6_health.get("outbox_failed_count") or 0),
                int(phase7_health.get("outbox_failed_count") or 0),
                int(phase7b_health.get("outbox_failed_count") or 0),
            )
            <= int(thresholds["outbox_failed"]),
            "detail": {
                "phase6": int(phase6_health.get("outbox_failed_count") or 0),
                "phase7a": int(phase7_health.get("outbox_failed_count") or 0),
                "phase7b": int(phase7b_health.get("outbox_failed_count") or 0),
                "max_allowed": int(thresholds["outbox_failed"]),
            },
        },
        {
            "name": "missing_lines_within_threshold",
            "passed": int(phase7_health.get("missing_lines_count") or 0) <= int(thresholds["missing_lines"]),
            "detail": {
                "count": int(phase7_health.get("missing_lines_count") or 0),
                "max_allowed": int(thresholds["missing_lines"]),
            },
        },
        {
            "name": "stale_revaluation_within_threshold",
            "passed": int(phase7_health.get("stale_revaluation_count") or 0) <= int(thresholds["stale_revaluation"]),
            "detail": {
                "count": int(phase7_health.get("stale_revaluation_count") or 0),
                "max_allowed": int(thresholds["stale_revaluation"]),
            },
        },
        {
            "name": "open_intercompany_within_threshold",
            "passed": int(phase7b_health.get("open_intercompany_count") or 0) <= int(thresholds["open_intercompany"]),
            "detail": {
                "count": int(phase7b_health.get("open_intercompany_count") or 0),
                "max_allowed": int(thresholds["open_intercompany"]),
            },
        },
        {
            "name": "disputed_intercompany_within_threshold",
            "passed": int(phase7b_health.get("disputed_intercompany_count") or 0) <= int(thresholds["disputed"]),
            "detail": {
                "count": int(phase7b_health.get("disputed_intercompany_count") or 0),
                "max_allowed": int(thresholds["disputed"]),
            },
        },
    ]
    return checks


def collect_staging_preflight_manifest(
    *,
    company_id: int,
    branch_id: int,
    consumer: str = "accounting.projector",
    stale_minutes: int = 30,
    inbox_failed: int = 0,
    outbox_failed: int = 0,
    missing_lines: int = 0,
    stale_revaluation: int = 0,
    open_intercompany: int = 0,
    disputed: int = 0,
) -> dict[str, Any]:
    company, branch = _resolve_scope(company_id=company_id, branch_id=branch_id)
    thresholds = _resolve_thresholds(
        inbox_failed=inbox_failed,
        outbox_failed=outbox_failed,
        missing_lines=missing_lines,
        stale_revaluation=stale_revaluation,
        open_intercompany=open_intercompany,
        disputed=disputed,
    )

    phase6_manifest = collect_phase6_env_manifest(company_id=int(company.id), branch_id=int(branch.id))
    phase7_manifest = collect_phase7_env_manifest(company_id=int(company.id))

    cfg = CompanyAccountingConfig.objects.filter(company=company).first()
    branch_cfg = (
        BranchFiscalConfig.objects.filter(company=company, branch=branch, is_active=True).order_by("-updated_at", "-id").first()
    )
    active_coa_count = int(ChartOfAccount.objects.filter(company=company, is_active=True).count())
    active_rules_count = int(
        PostingRuleSet.objects.filter(
            status=PostingRuleSet.Status.ACTIVE,
        )
        .filter(Q(scope_company=company) | Q(scope_company__isnull=True))
        .count()
    )

    phase6_health = collect_phase6_operational_health(
        company_id=int(company.id),
        branch_id=int(branch.id),
        consumer=consumer,
        stale_minutes=stale_minutes,
    )
    phase7_health = collect_phase7_operational_health(
        company_id=int(company.id),
        consumer=consumer,
    )
    phase7b_health = collect_phase7b_operational_health(
        company_id=int(company.id),
        consumer=consumer,
    )
    health_checks = _build_health_checks(
        phase6_health=phase6_health,
        phase7_health=phase7_health,
        phase7b_health=phase7b_health,
        thresholds=thresholds,
    )

    checks = [
        {
            "name": "phase6_migration_applied",
            "passed": bool(phase6_manifest.get("migrations", {}).get("phase6_migration_applied")),
            "detail": {"migration": phase6_manifest.get("migrations", {}).get("phase6_migration")},
        },
        {
            "name": "branch_fiscal_mode_b_active",
            "passed": bool(branch_cfg is not None and branch_cfg.fiscal_mode == FiscalMode.B),
            "detail": {
                "fiscal_mode": str(branch_cfg.fiscal_mode) if branch_cfg else "",
                "branch_config_id": int(branch_cfg.id) if branch_cfg else None,
            },
        },
        {
            "name": "phase7_enabled_for_company",
            "passed": bool(cfg is not None and cfg.phase7_enabled),
            "detail": {"phase7_enabled": bool(cfg.phase7_enabled) if cfg else False},
        },
        {
            "name": "active_chart_of_accounts_present",
            "passed": active_coa_count > 0,
            "detail": {"active_coa_count": int(active_coa_count)},
        },
        {
            "name": "active_posting_rules_present",
            "passed": active_rules_count > 0,
            "detail": {"active_rules_count": int(active_rules_count)},
        },
        {
            "name": "timezone_matches_operational_default",
            "passed": str(settings.TIME_ZONE) == "America/Managua",
            "detail": {"timezone": str(settings.TIME_ZONE)},
        },
    ]
    checks.extend(health_checks)
    preflight_passed = all(bool(row["passed"]) for row in checks)

    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(dt_timezone.utc).isoformat(),
        "pilot_scope": {
            "company_id": int(company.id),
            "company_name": company.name,
            "branch_id": int(branch.id),
            "branch_name": branch.name,
        },
        "consumer": str(consumer or "accounting.projector"),
        "stale_minutes": int(max(1, stale_minutes)),
        "thresholds": thresholds,
        "preflight_passed": bool(preflight_passed),
        "checks": checks,
        "phase6_manifest": phase6_manifest,
        "phase7_manifest": phase7_manifest,
        "health": {
            "phase6": phase6_health,
            "phase7a": phase7_health,
            "phase7b": phase7b_health,
        },
    }
    manifest["manifest_hash"] = _json_hash(
        {
            "scope": manifest["pilot_scope"],
            "thresholds": thresholds,
            "checks": checks,
            "phase6_fingerprint": phase6_manifest.get("parity_fingerprint"),
            "phase7_fingerprint": phase7_manifest.get("parity_fingerprint"),
            "health": manifest["health"],
        }
    )
    return manifest


def collect_finance_operational_snapshot(
    *,
    company_id: int,
    branch_id: int,
    consumer: str = "accounting.projector",
    stale_minutes: int = 30,
    inbox_failed: int = 0,
    outbox_failed: int = 0,
    missing_lines: int = 0,
    stale_revaluation: int = 0,
    open_intercompany: int = 0,
    disputed: int = 0,
) -> dict[str, Any]:
    company, branch = _resolve_scope(company_id=company_id, branch_id=branch_id)
    thresholds = _resolve_thresholds(
        inbox_failed=inbox_failed,
        outbox_failed=outbox_failed,
        missing_lines=missing_lines,
        stale_revaluation=stale_revaluation,
        open_intercompany=open_intercompany,
        disputed=disputed,
    )

    phase6_health = collect_phase6_operational_health(
        company_id=int(company.id),
        branch_id=int(branch.id),
        consumer=consumer,
        stale_minutes=stale_minutes,
    )
    phase7_health = collect_phase7_operational_health(
        company_id=int(company.id),
        consumer=consumer,
    )
    phase7b_health = collect_phase7b_operational_health(
        company_id=int(company.id),
        consumer=consumer,
    )
    checks = _build_health_checks(
        phase6_health=phase6_health,
        phase7_health=phase7_health,
        phase7b_health=phase7b_health,
        thresholds=thresholds,
    )
    alerts = [
        {
            "name": row["name"],
            "detail": row["detail"],
        }
        for row in checks
        if not bool(row["passed"])
    ]
    snapshot_passed = len(alerts) == 0
    payload = {
        "schema_version": 1,
        "generated_at": datetime.now(dt_timezone.utc).isoformat(),
        "pilot_scope": {
            "company_id": int(company.id),
            "branch_id": int(branch.id),
        },
        "consumer": str(consumer or "accounting.projector"),
        "stale_minutes": int(max(1, stale_minutes)),
        "thresholds": thresholds,
        "snapshot_passed": bool(snapshot_passed),
        "checks": checks,
        "alerts": alerts,
        "health": {
            "phase6": phase6_health,
            "phase7a": phase7_health,
            "phase7b": phase7b_health,
        },
    }
    payload["manifest_hash"] = _json_hash(
        {
            "pilot_scope": payload["pilot_scope"],
            "thresholds": thresholds,
            "health": payload["health"],
            "checks": checks,
        }
    )
    return payload
