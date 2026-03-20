from __future__ import annotations

import hashlib
import hmac
import json
from dataclasses import dataclass
from datetime import datetime, timezone as dt_timezone
from typing import Any

from django.conf import settings

from apps.modulos.iam.models import OrgUnit

from .certification import collect_phase6_env_manifest, collect_phase6_operational_health, certify_adapter_b_run
from .fiscal_adapters import FiscalMode, get_fiscal_adapter, resolve_adapter_b_http_config, resolve_fiscal_runtime_config


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


def build_phase9_evidence(*, payload: dict[str, Any], secret: str = "") -> dict[str, Any]:
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


def _provider_mode() -> str:
    return str(getattr(settings, "FISCAL_ADAPTER_B_PROVIDER", "EMULATED") or "EMULATED").strip().upper()


def collect_phase9_env_manifest(*, company_id: int, branch_id: int) -> dict[str, Any]:
    company, branch = _resolve_scope(company_id=company_id, branch_id=branch_id)
    phase6 = collect_phase6_env_manifest(company_id=company_id, branch_id=branch_id)

    runtime_cfg = resolve_fiscal_runtime_config(company=company, branch=branch)
    adapter = get_fiscal_adapter(company=company, branch=branch)
    http_cfg = resolve_adapter_b_http_config()

    provider_payload = {
        "provider_mode": _provider_mode(),
        "runtime_mode": str(runtime_cfg.mode or ""),
        "runtime_adapter_code": str(runtime_cfg.adapter_code or ""),
        "resolved_adapter_class": str(adapter.__class__.__name__),
        "resolved_adapter_code": str(getattr(adapter, "adapter_code", "") or ""),
        "print_required": bool(runtime_cfg.print_required),
        "strict_integrity": bool(runtime_cfg.strict_integrity),
        "contingency_max_attempts": int(runtime_cfg.contingency_max_attempts),
        "http_base_url_configured": bool(str(http_cfg.base_url or "").strip()),
        "http_api_key_configured": bool(str(http_cfg.api_key or "").strip()),
        "http_timeout_seconds": int(http_cfg.timeout_seconds),
        "http_verify_tls": bool(http_cfg.verify_tls),
        "emulated_fallback_enabled": bool(
            getattr(settings, "FISCAL_ADAPTER_B_ALLOW_EMULATED_FALLBACK", True)
        ),
    }
    provider_payload["hash"] = _json_hash(provider_payload)

    manifest = {
        "schema_version": 1,
        "generated_at": datetime.now(dt_timezone.utc).isoformat(),
        "pilot_scope": {
            "company_id": int(company.id),
            "branch_id": int(branch.id),
        },
        "phase6": {
            "parity_fingerprint": str(phase6.get("parity_fingerprint") or ""),
            "branch_fiscal_config_hash": str((phase6.get("branch_fiscal_config") or {}).get("hash") or ""),
            "migrations_hash": str((phase6.get("migrations") or {}).get("hash") or ""),
            "required_permissions_hash": str((phase6.get("required_permissions") or {}).get("hash") or ""),
        },
        "provider_config": provider_payload,
    }
    manifest["parity_fingerprint"] = _json_hash(
        {
            "phase6": manifest["phase6"],
            "provider_config_hash": provider_payload["hash"],
        }
    )
    return manifest


def compare_phase9_env_manifests(*, left: dict[str, Any], right: dict[str, Any]) -> list[dict[str, str]]:
    checks = [
        ("phase6.parity_fingerprint", (left.get("phase6") or {}).get("parity_fingerprint"), (right.get("phase6") or {}).get("parity_fingerprint")),
        ("provider_config.hash", (left.get("provider_config") or {}).get("hash"), (right.get("provider_config") or {}).get("hash")),
        ("provider_config.provider_mode", (left.get("provider_config") or {}).get("provider_mode"), (right.get("provider_config") or {}).get("provider_mode")),
        ("provider_config.runtime_mode", (left.get("provider_config") or {}).get("runtime_mode"), (right.get("provider_config") or {}).get("runtime_mode")),
        (
            "provider_config.resolved_adapter_class",
            (left.get("provider_config") or {}).get("resolved_adapter_class"),
            (right.get("provider_config") or {}).get("resolved_adapter_class"),
        ),
        ("parity_fingerprint", left.get("parity_fingerprint"), right.get("parity_fingerprint")),
    ]
    mismatches: list[dict[str, str]] = []
    for field, lval, rval in checks:
        if lval != rval:
            mismatches.append({"field": field, "left": str(lval), "right": str(rval)})
    return mismatches


def collect_phase9_operational_health(
    *,
    company_id: int,
    branch_id: int,
    consumer: str = "accounting.projector",
    stale_minutes: int = 30,
) -> dict[str, Any]:
    health = collect_phase6_operational_health(
        company_id=company_id,
        branch_id=branch_id,
        consumer=consumer,
        stale_minutes=stale_minutes,
    )
    health["provider_mode"] = _provider_mode()
    return health


def run_provider_integrity_check(*, company_id: int, branch_id: int, series: str = "B") -> tuple[bool, str, str]:
    company, branch = _resolve_scope(company_id=company_id, branch_id=branch_id)
    runtime_cfg = resolve_fiscal_runtime_config(company=company, branch=branch)
    if runtime_cfg.mode != FiscalMode.B:
        return False, f"modo fiscal actual no es B (mode={runtime_cfg.mode})", ""
    adapter = get_fiscal_adapter(company=company, branch=branch)
    adapter_name = str(adapter.__class__.__name__)
    try:
        ok = bool(adapter.validate_range_integrity(request=None, branch=branch, series=str(series or "B").upper()))
    except Exception as exc:  # noqa: BLE001
        return False, str(exc), adapter_name
    if not ok:
        return False, "provider respondió ok=false en validate_range_integrity", adapter_name
    return True, "", adapter_name


@dataclass(frozen=True)
class AdapterBProviderCertificationResult:
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
    provider_mode: str
    provider_adapter_class: str
    provider_check_ok: bool
    provider_check_error: str
    scenario_adapter_code: str
    blocked_path_mode: str


def certify_adapter_b_provider_run(
    *,
    company_id: int,
    branch_id: int,
    expect_blocked: bool = False,
    blocked_adapter_code: str = "EMULATED_B",
) -> AdapterBProviderCertificationResult:
    company, branch = _resolve_scope(company_id=company_id, branch_id=branch_id)
    runtime_cfg = resolve_fiscal_runtime_config(company=company, branch=branch)
    provider_mode = _provider_mode()

    default_happy_code = str(runtime_cfg.adapter_code or "").strip().upper()
    if not default_happy_code:
        default_happy_code = "PROVIDER_B" if provider_mode in ("HTTP", "REAL_HTTP") else "EMULATED_B"
    scenario_adapter_code = (
        str(blocked_adapter_code or "EMULATED_B").strip().upper()
        if expect_blocked
        else default_happy_code
    )

    provider_check_ok, provider_check_error, provider_adapter_class = run_provider_integrity_check(
        company_id=company_id,
        branch_id=branch_id,
        series="B",
    )

    result = certify_adapter_b_run(
        company_id=company_id,
        branch_id=branch_id,
        expect_blocked=expect_blocked,
        adapter_code=scenario_adapter_code,
    )

    passed = bool(result.passed)
    if not expect_blocked:
        passed = bool(passed and provider_check_ok)

    return AdapterBProviderCertificationResult(
        run_id=str(result.run_id),
        passed=bool(passed),
        blocked=bool(result.blocked),
        deterministic_replay=bool(result.deterministic_replay),
        close_run_status=str(result.close_run_status),
        first_manifest_hash=str(result.first_manifest_hash),
        second_manifest_hash=str(result.second_manifest_hash),
        first_counts=result.first_counts,
        second_counts=result.second_counts,
        pilot_scope=result.pilot_scope,
        job_counts=result.job_counts,
        contingency_counts=result.contingency_counts,
        cec_blocking_exceptions=int(result.cec_blocking_exceptions),
        go_live_passed=bool(passed),
        provider_mode=str(provider_mode),
        provider_adapter_class=provider_adapter_class,
        provider_check_ok=bool(provider_check_ok),
        provider_check_error=str(provider_check_error),
        scenario_adapter_code=scenario_adapter_code,
        blocked_path_mode="EMULATED_FALLBACK" if expect_blocked else "PROVIDER_OR_RUNTIME",
    )

