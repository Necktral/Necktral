from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import date, datetime
from datetime import timezone as dt_timezone
from typing import Any

from django.utils import timezone

from modulos.facturacion.certification import collect_phase6_env_manifest, collect_phase6_operational_health

from .certification_phase7 import collect_phase7_env_manifest, collect_phase7_operational_health
from .certification_phase7b import collect_phase7b_operational_health


def _json_default(value: Any) -> str:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _json_dumps(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"), default=_json_default)


def _json_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(_json_dumps(payload).encode("utf-8")).hexdigest()


def _signed_hash(payload: dict[str, Any], *, secret: str = "") -> tuple[str, str, str]:
    raw = _json_dumps(payload).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    if secret:
        signature = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
        return digest, signature, "hmac-sha256"
    return digest, digest, "sha256"


def build_phase8_evidence(*, payload: dict[str, Any], secret: str = "") -> dict[str, Any]:
    digest, signature, signature_type = _signed_hash(payload, secret=secret)
    return {
        **payload,
        "evidence_hash": digest,
        "signature": signature,
        "signature_type": signature_type,
    }


def collect_phase8_env_manifest(
    *,
    company_id: int,
    branch_id: int,
    parent_company_id: int,
    company_ids: list[int],
) -> dict[str, Any]:
    phase6 = collect_phase6_env_manifest(company_id=company_id, branch_id=branch_id)
    phase7 = collect_phase7_env_manifest(company_id=company_id)

    normalized_company_ids = sorted({int(x) for x in company_ids})
    scope_payload = {
        "parent_company_id": int(parent_company_id),
        "company_ids": normalized_company_ids,
    }

    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(dt_timezone.utc).isoformat(),
        "pilot_scope": {
            "company_id": int(company_id),
            "branch_id": int(branch_id),
            "parent_company_id": int(parent_company_id),
            "company_ids": normalized_company_ids,
        },
        "phase6": {
            "parity_fingerprint": str(phase6.get("parity_fingerprint") or ""),
            "migrations_hash": str((phase6.get("migrations") or {}).get("hash") or ""),
            "required_permissions_hash": str((phase6.get("required_permissions") or {}).get("hash") or ""),
            "branch_fiscal_config_hash": str((phase6.get("branch_fiscal_config") or {}).get("hash") or ""),
            "app_version": str((phase6.get("environment") or {}).get("app_version") or ""),
            "git_commit_sha": str((phase6.get("environment") or {}).get("git_commit_sha") or ""),
        },
        "phase7": {
            "parity_fingerprint": str(phase7.get("parity_fingerprint") or ""),
            "migrations_hash": str((phase7.get("migrations") or {}).get("hash") or ""),
            "required_permissions_hash": str((phase7.get("required_permissions") or {}).get("hash") or ""),
            "accounting_config_hash": str((phase7.get("accounting_config") or {}).get("hash") or ""),
            "chart_of_accounts_hash": str((phase7.get("chart_of_accounts") or {}).get("hash") or ""),
            "app_version": str((phase7.get("environment") or {}).get("app_version") or ""),
            "git_commit_sha": str((phase7.get("environment") or {}).get("git_commit_sha") or ""),
        },
        "phase7b_scope": {
            **scope_payload,
            "scope_hash": _json_hash(scope_payload),
        },
    }
    manifest["parity_fingerprint"] = _json_hash(
        {
            "phase6": manifest["phase6"],
            "phase7": manifest["phase7"],
            "phase7b_scope": manifest["phase7b_scope"],
        }
    )
    return manifest


def compare_phase8_env_manifests(*, left: dict[str, Any], right: dict[str, Any]) -> list[dict[str, str]]:
    checks = [
        ("phase6.parity_fingerprint", (left.get("phase6") or {}).get("parity_fingerprint"), (right.get("phase6") or {}).get("parity_fingerprint")),
        ("phase7.parity_fingerprint", (left.get("phase7") or {}).get("parity_fingerprint"), (right.get("phase7") or {}).get("parity_fingerprint")),
        ("phase7b_scope.scope_hash", (left.get("phase7b_scope") or {}).get("scope_hash"), (right.get("phase7b_scope") or {}).get("scope_hash")),
        ("parity_fingerprint", left.get("parity_fingerprint"), right.get("parity_fingerprint")),
    ]
    mismatches: list[dict[str, str]] = []
    for field, lval, rval in checks:
        if lval != rval:
            mismatches.append({"field": field, "left": str(lval), "right": str(rval)})
    return mismatches


def collect_phase8_operational_health(
    *,
    company_id: int,
    branch_id: int,
    parent_company_id: int,
    consumer: str = "accounting.projector",
    stale_minutes: int = 30,
) -> dict[str, Any]:
    _ = parent_company_id
    phase6 = collect_phase6_operational_health(
        company_id=company_id,
        branch_id=branch_id,
        consumer=consumer,
        stale_minutes=stale_minutes,
    )
    phase7 = collect_phase7_operational_health(company_id=company_id, consumer=consumer)
    phase7b = collect_phase7b_operational_health(company_id=company_id, consumer=consumer)
    return {
        "phase6": phase6,
        "phase7a": phase7,
        "phase7b": phase7b,
        "generated_at": timezone.now().isoformat(),
    }


@dataclass(frozen=True)
class Phase8BurnInResult:
    cycle_passed: bool
    checks: list[dict[str, Any]]
    health: dict[str, Any]
    report: dict[str, Any]
