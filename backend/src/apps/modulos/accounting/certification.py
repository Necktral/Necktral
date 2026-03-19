from __future__ import annotations

import hashlib
import hmac
import json
import os
import platform
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
from pathlib import Path
from typing import Any

import django
from django.conf import settings
from django.db import connection
from django.db.migrations.recorder import MigrationRecorder

from apps.modulos.cec.models import CECException, CloseRun

from .models import EconomicEvent, JournalDraft, PostingRuleSet
from .services import project_shadow_ledger_for_run

OPEN_EXCEPTION_STATUSES = (CECException.Status.OPEN, CECException.Status.IN_PROGRESS)


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


def collect_phase4_env_manifest(*, company_id: int | None = None) -> dict[str, Any]:
    migrations = list(
        MigrationRecorder(connection)
        .migration_qs.values_list("app", "name")
        .order_by("app", "name")
    )
    migration_ids = [f"{app}.{name}" for app, name in migrations]
    migrations_hash = hashlib.sha256("\n".join(migration_ids).encode("utf-8")).hexdigest()

    rules_qs = PostingRuleSet.objects.filter(code="shadow_ledger_v1", status=PostingRuleSet.Status.ACTIVE).order_by(
        "scope_company_id",
        "-version",
        "-id",
    )
    if company_id is not None:
        rules_qs = rules_qs.filter(scope_company_id=int(company_id))

    rules_rows: list[dict[str, Any]] = []
    for row in rules_qs:
        rules_rows.append(
            {
                "company_id": row.scope_company_id,
                "code": row.code,
                "version": int(row.version),
                "status": row.status,
                "fiscal_mode": row.fiscal_mode,
                "effective_from": row.effective_from.isoformat() if row.effective_from else "",
                "effective_to": row.effective_to.isoformat() if row.effective_to else "",
                "rules_hash": _json_hash(row.rules_json if isinstance(row.rules_json, dict) else {}),
            }
        )
    rules_hash = _json_hash({"rows": rules_rows})

    app_version = str(settings.SENTRY_RELEASE or settings.REST_FRAMEWORK.get("VERSION", "") or "").strip()
    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(dt_timezone.utc).isoformat(),
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
            "items": migration_ids,
        },
        "posting_rules_v1": {
            "count": len(rules_rows),
            "hash": rules_hash,
            "items": rules_rows,
        },
    }
    manifest["parity_fingerprint"] = _json_hash(
        {
            "environment": manifest["environment"],
            "database": manifest["database"],
            "migrations_hash": migrations_hash,
            "posting_rules_hash": rules_hash,
        }
    )
    return manifest


def compare_phase4_env_manifests(*, left: dict[str, Any], right: dict[str, Any]) -> list[dict[str, str]]:
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
            "posting_rules_v1.hash",
            left.get("posting_rules_v1", {}).get("hash"),
            right.get("posting_rules_v1", {}).get("hash"),
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


@dataclass(frozen=True)
class RunCertificationResult:
    run_id: str
    passed: bool
    blocked: bool
    replay_performed: bool
    deterministic_replay: bool
    close_run_status: str
    first_manifest_hash: str
    second_manifest_hash: str
    first_counts: dict[str, int]
    second_counts: dict[str, int]


def _counts_for_run(*, run: CloseRun) -> dict[str, int]:
    run_id = str(run.run_id)
    return {
        "economic_events": EconomicEvent.objects.filter(close_run_id=run_id).count(),
        "journal_drafts": JournalDraft.objects.filter(close_run_id=run_id).count(),
        "open_accounting_exceptions": CECException.objects.filter(
            close_run=run,
            source_module="ACCOUNTING",
            status__in=OPEN_EXCEPTION_STATUSES,
        ).count(),
    }


def _projection_manifest_hash(run: CloseRun, fallback: str = "") -> str:
    summary = run.summary_json if isinstance(run.summary_json, dict) else {}
    proj = summary.get("accounting_projection", {})
    if isinstance(proj, dict):
        val = str(proj.get("manifest_hash", "")).strip()
        if val:
            return val
    return fallback


def certify_shadow_ledger_run(*, run_id: str, company_id: int | None = None, expect_blocked: bool = False) -> RunCertificationResult:
    run_qs = CloseRun.objects.filter(run_id=run_id)
    if company_id is not None:
        run_qs = run_qs.filter(company_id=int(company_id))
    run = run_qs.first()
    if run is None:
        raise ValueError(f"CloseRun {run_id} no existe.")

    first = project_shadow_ledger_for_run(run_id=run_id, company_id=company_id)
    run.refresh_from_db()
    first_counts = _counts_for_run(run=run)
    first_manifest_hash = _projection_manifest_hash(run, fallback=first.manifest_hash)

    if first.blocked:
        if not expect_blocked:
            raise ValueError("Certificación fallida: proyección bloqueada y expect_blocked=False.")
        return RunCertificationResult(
            run_id=str(run.run_id),
            passed=True,
            blocked=True,
            replay_performed=False,
            deterministic_replay=True,
            close_run_status=run.status,
            first_manifest_hash=first_manifest_hash,
            second_manifest_hash=first_manifest_hash,
            first_counts=first_counts,
            second_counts=first_counts,
        )

    if expect_blocked:
        raise ValueError("Certificación fallida: se esperaba bloqueo y la corrida no bloqueó.")

    second = project_shadow_ledger_for_run(run_id=run_id, company_id=company_id)
    run.refresh_from_db()
    second_counts = _counts_for_run(run=run)
    second_manifest_hash = _projection_manifest_hash(run, fallback=second.manifest_hash)
    deterministic_replay = first_manifest_hash == second_manifest_hash and first_counts == second_counts

    return RunCertificationResult(
        run_id=str(run.run_id),
        passed=bool(deterministic_replay),
        blocked=False,
        replay_performed=True,
        deterministic_replay=bool(deterministic_replay),
        close_run_status=run.status,
        first_manifest_hash=first_manifest_hash,
        second_manifest_hash=second_manifest_hash,
        first_counts=first_counts,
        second_counts=second_counts,
    )


def build_phase4_evidence(*, payload: dict[str, Any], secret: str = "") -> dict[str, Any]:
    digest, signature, signature_type = _signed_hash(payload, secret=secret)
    return {
        **payload,
        "evidence_hash": digest,
        "signature": signature,
        "signature_type": signature_type,
    }
