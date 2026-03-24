from __future__ import annotations

import hashlib
import hmac
import json
import threading
from collections import Counter
from dataclasses import dataclass
from datetime import timedelta
from types import SimpleNamespace
from typing import Any

from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.utils.dateparse import parse_datetime

from apps.modulos.audit.writer import write_event
from apps.modulos.rbac.selectors import get_effective_permissions_for_scope

from .models import (
    DatasetCache,
    ReportDefinition,
    ReportExport,
    ReportMetricDefinition,
    ReportReadAudit,
    ReportRun,
    ReproducibilityLedger,
    SourceRegistry,
)
from .registry import REPORT_REGISTRY, REPORT_SPECS, ReportResult, ReportSpec
from .semantic_metrics import metric_expression_hash, semantic_metric_keys_for_dataset, SEMANTIC_METRIC_REGISTRY


@dataclass(frozen=True)
class ReportDomainError(Exception):
    code: str
    message: str
    http_status: int = 400
    details: dict[str, Any] | None = None


FAMILY_READ_PERMISSION: dict[str, str] = {
    "AUDIT": "reports.audit.read",
    "OBS": "reports.observability.read",
    "TRACE": "reports.trace.read",
    "CONTROL": "reports.control.read",
    "FIN": "reports.financial.read",
    "SEC": "reports.security.read",
}

KERNEL_PERMISSION_ALIASES: dict[str, tuple[str, ...]] = {
    "report.catalog.read": ("report.catalog.read", "reports.definition.read", "reports.view"),
    "report.dataset.read": ("report.dataset.read", "reports.run.read", "reports.run.create", "reports.view", "dashboard.widget.read"),
    "report.dataset.export": ("report.dataset.export", "reports.export"),
    "report.definition.manage": ("report.definition.manage", "reports.definition.create", "reports.definition.update"),
    "report.dashboard.read": ("report.dashboard.read", "dashboard.workspace.read"),
}


RETENTION_DAYS: dict[str, int] = {
    "ephemeral": 1,
    "short_term": 30,
    "operational_archive": 180,
    "compliance_archive": 365,
    "financial_archive": 365 * 5,
}


SENSITIVE_FIELD_TOKENS = ("email", "phone", "doc", "tax", "name", "user", "card", "token", "secret")
SENSITIVITY_ALLOWED_EXPORTS: dict[str, set[str]] = {
    ReportRun.SensitivityLevel.LOW: {"json", "jsonl", "csv", "xlsx"},
    ReportRun.SensitivityLevel.MEDIUM: {"json", "jsonl", "csv", "xlsx"},
    ReportRun.SensitivityLevel.HIGH: {"json", "xlsx", "pdf"},
    ReportRun.SensitivityLevel.RESTRICTED: {"pdf"},
}

ANALYTICS_PARAM_KEYS = {
    "filters",
    "group_by",
    "metrics",
    "sort",
    "cursor",
    "comparison",
    "drill_path",
}


_REPORTS_METRICS_LOCK = threading.Lock()
_REPORTS_RUN_STATUS_COUNT: Counter[str] = Counter()
_REPORTS_EXPORT_STATUS_COUNT: Counter[str] = Counter()
_REPORTS_RUN_FAMILY_DURATION_MS: Counter[str] = Counter()
_REPORTS_RUN_FAMILY_COUNT: Counter[str] = Counter()


def _get_request_id(request) -> str:
    return str(getattr(request, "request_id", "") or getattr(getattr(request, "ctx", None), "request_id", "") or "")


def _canon_json(payload: Any) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def _hash_hex(payload: Any) -> str:
    return hashlib.sha256(_canon_json(payload).encode("utf-8")).hexdigest()


def _sign_hash(value: str) -> str:
    key = str(getattr(settings, "AUDIT_HMAC_KEY", "") or "reports-dev-key")
    return hmac.new(key.encode("utf-8"), value.encode("utf-8"), hashlib.sha256).hexdigest()


def _scope_payload(*, company, branch, request) -> dict[str, Any]:
    data_scope = getattr(request, "data_scope", None) if request is not None else None
    payload = {
        "company_id": getattr(company, "id", None),
        "branch_id": getattr(branch, "id", None) if branch is not None else None,
    }
    if isinstance(data_scope, dict):
        payload["data_scope"] = dict(data_scope)
    return payload


def _effective_perms(*, user, company, branch) -> set[str]:
    return get_effective_permissions_for_scope(user, company=company, branch=branch, include_global=True)


def _require_permission(*, user, company, branch, permission_code: str) -> None:
    perms = _effective_perms(user=user, company=company, branch=branch)
    if permission_code not in perms and "*" not in perms:
        raise ReportDomainError(
            code="REPORT_FORBIDDEN",
            message="forbidden",
            http_status=403,
            details={"required_permission": permission_code},
        )


def _require_any_permission(*, user, company, branch, permission_codes: tuple[str, ...] | list[str]) -> str:
    perms = _effective_perms(user=user, company=company, branch=branch)
    if "*" in perms:
        return "*"
    normalized = tuple(str(code).strip() for code in permission_codes if str(code).strip())
    for code in normalized:
        if code in perms:
            return code
    raise ReportDomainError(
        code="REPORT_FORBIDDEN",
        message="forbidden",
        http_status=403,
        details={"required_permissions_any": list(normalized)},
    )


def _ensure_company_scope(*, request, company, branch=None) -> None:
    request_company = getattr(request, "company", None) if request is not None else None
    request_branch = getattr(request, "branch", None) if request is not None else None
    company_id = getattr(company, "id", None)
    branch_id = getattr(branch, "id", None) if branch is not None else None

    if request_company is None or getattr(request_company, "id", None) is None:
        raise ReportDomainError(
            code="REPORT_INVALID_SCOPE",
            message="missing effective company scope",
            http_status=403,
            details={"required_scope": {"company_id": company_id, "branch_id": branch_id}},
        )
    request_company_id = getattr(request_company, "id", None)
    if company_id is None or request_company_id is None:
        raise ReportDomainError(
            code="REPORT_INVALID_SCOPE",
            message="invalid company scope values",
            http_status=403,
            details={"required_scope": {"company_id": company_id, "branch_id": branch_id}},
        )

    if int(request_company_id) != int(company_id):
        raise ReportDomainError(
            code="REPORT_INVALID_SCOPE",
            message="company scope mismatch",
            http_status=403,
            details={
                "required_scope": {"company_id": company_id, "branch_id": branch_id},
                "effective_scope": {
                    "company_id": int(request_company_id),
                    "branch_id": getattr(request_branch, "id", None),
                },
            },
        )
    request_branch_id = getattr(request_branch, "id", None) if request_branch is not None else None
    if branch is not None and request_branch is not None and branch_id is not None and request_branch_id is not None and int(request_branch_id) != int(branch_id):
        raise ReportDomainError(
            code="REPORT_INVALID_SCOPE",
            message="branch scope mismatch",
            http_status=403,
            details={
                "required_scope": {"company_id": company_id, "branch_id": branch_id},
                "effective_scope": {
                    "company_id": int(request_company_id),
                    "branch_id": int(request_branch_id),
                },
            },
        )


def _parse_dt(value: Any) -> Any:
    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value
    parsed = parse_datetime(str(value))
    if parsed is None:
        return None
    if timezone.is_naive(parsed):
        return timezone.make_aware(parsed, timezone.get_current_timezone())
    return parsed


def _retention_until(retention_policy: str) -> Any:
    days = int(RETENTION_DAYS.get(retention_policy, 30))
    return timezone.now() + timedelta(days=days)


def _masked_value(value: Any) -> Any:
    if value is None:
        return None
    raw = str(value)
    if len(raw) <= 4:
        return "***"
    return f"{raw[:2]}***{raw[-2:]}"


def _contains_v3_analytics_params(params: dict[str, Any]) -> bool:
    return bool(ANALYTICS_PARAM_KEYS.intersection(params.keys()))


def _assert_v3_analytics_params_enabled(params: dict[str, Any]) -> None:
    if not _contains_v3_analytics_params(params):
        return
    if not bool(getattr(settings, "FF_REPORTS_V3_QUERY", False)):
        raise ReportDomainError(
            code="REPORT_INVALID_PARAMS",
            message="reports v3 query disabled",
            http_status=422,
            details={"feature_flag": "FF_REPORTS_V3_QUERY"},
        )
    group_by = params.get("group_by")
    metrics = params.get("metrics")
    drill_path = params.get("drill_path")
    if isinstance(group_by, list) and len(group_by) > 12:
        raise ReportDomainError(
            code="REPORT_INVALID_PARAMS",
            message="group_by max length is 12",
            http_status=422,
        )
    if isinstance(metrics, list) and len(metrics) > 24:
        raise ReportDomainError(
            code="REPORT_INVALID_PARAMS",
            message="metrics max length is 24",
            http_status=422,
        )
    if isinstance(drill_path, list) and len(drill_path) > 12:
        raise ReportDomainError(
            code="REPORT_INVALID_PARAMS",
            message="drill_path max length is 12",
            http_status=422,
        )


def _mask_sensitive_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    masked: list[dict[str, Any]] = []
    for row in rows:
        out = {}
        for key, value in row.items():
            key_l = str(key).lower()
            if any(token in key_l for token in SENSITIVE_FIELD_TOKENS):
                out[key] = _masked_value(value)
            else:
                out[key] = value
        masked.append(out)
    return masked


def _record_run_metric(*, run: ReportRun, final_status: str, duration_ms: int) -> None:
    family = str(getattr(run.definition, "report_family", "") or "UNKNOWN")
    with _REPORTS_METRICS_LOCK:
        _REPORTS_RUN_STATUS_COUNT[str(final_status)] += 1
        _REPORTS_RUN_FAMILY_DURATION_MS[family] += int(max(duration_ms, 0))
        _REPORTS_RUN_FAMILY_COUNT[family] += 1


def _record_export_metric(*, export: ReportExport) -> None:
    with _REPORTS_METRICS_LOCK:
        _REPORTS_EXPORT_STATUS_COUNT[str(export.status)] += 1


def reports_metrics_snapshot() -> dict[str, Any]:
    with _REPORTS_METRICS_LOCK:
        by_family: dict[str, dict[str, int]] = {}
        for family, count in _REPORTS_RUN_FAMILY_COUNT.items():
            total = int(_REPORTS_RUN_FAMILY_DURATION_MS.get(family, 0))
            by_family[family] = {
                "count": int(count),
                "latency_ms_avg": int(total / count) if count else 0,
                "latency_ms_total": total,
            }
        return {
            "run_status_counts": dict(_REPORTS_RUN_STATUS_COUNT),
            "export_status_counts": dict(_REPORTS_EXPORT_STATUS_COUNT),
            "run_latency_by_family": by_family,
        }


def _family_permission(spec: ReportSpec) -> str | None:
    return FAMILY_READ_PERMISSION.get(spec.family)


def _build_time_window(*, definition: ReportDefinition, params: dict[str, Any], time_window: dict[str, Any] | None) -> dict[str, Any]:
    tw = dict(time_window or {})
    start = _parse_dt(tw.get("start") or params.get("since"))
    end = _parse_dt(tw.get("end") or params.get("until"))
    if start and end and end < start:
        raise ReportDomainError(
            code="REPORT_INVALID_PARAMS",
            message="invalid time window",
            http_status=422,
            details={"time_window": "end_before_start"},
        )
    if start and end:
        days = (end - start).days
        if days > int(definition.max_window_days):
            raise ReportDomainError(
                code="REPORT_INVALID_PARAMS",
                message="time window exceeds max_window_days",
                http_status=422,
                details={"max_window_days": int(definition.max_window_days)},
            )
    return {
        "start": start.isoformat() if start else "",
        "end": end.isoformat() if end else "",
    }


def _source_manifest(*, spec: ReportSpec) -> dict[str, Any]:
    return {
        "source_types": list(spec.source_types),
        "truth_level": spec.truth_level,
        "report_code": spec.code,
        "report_version": spec.report_version,
    }


def _seed_sources(*, company) -> None:
    defaults = [
        ("AUDIT_EVENTS", "AUDIT", "AUDIT_EVENTS", "audit_control"),
        ("OBS_METRICS", "COMMON", "METRICS", "observability"),
        ("OUTBOX_EVENTS", "INTEGRATION", "DOMAIN_EVENTS", "operational"),
        ("SYNC_EVENTS", "SYNC_ENGINE", "SYNC_EVENTS", "operational"),
        ("ACCOUNTS_EVENTS", "ACCOUNTS", "READ_MODELS", "operational"),
        ("IAM_SCOPE", "IAM", "READ_MODELS", "audit_control"),
        ("ORG_SCOPE", "ORG", "READ_MODELS", "operational"),
        ("HR_SCOPE", "HR", "READ_MODELS", "operational"),
        ("RBAC_SCOPE", "RBAC", "READ_MODELS", "audit_control"),
        ("ACCOUNTING_SCOPE", "ACCOUNTING", "READ_MODELS", "certified_financial"),
        ("PAYMENTS_SCOPE", "PAYMENTS", "READ_MODELS", "operational"),
        ("CEC_SCOPE", "CEC", "READ_MODELS", "audit_control"),
        ("REPORTS_SCOPE", "REPORTS", "READ_MODELS", "audit_control"),
        ("AUTH_KERNEL_SCOPE", "AUTH_KERNEL", "READ_MODELS", "audit_control"),
        ("BILLING_KERNEL_SCOPE", "FACTURACION", "READ_MODELS", "operational"),
        ("INVENTORY_KERNEL_SCOPE", "INVENTARIOS", "READ_MODELS", "operational"),
        ("PROCUREMENT_KERNEL_SCOPE", "COMPRAS", "READ_MODELS", "operational"),
        ("FUEL_KERNEL_SCOPE", "ESTACION_SERVICIOS", "READ_MODELS", "operational"),
    ]
    for source_code, producer, source_type, truth_level in defaults:
        SourceRegistry.objects.get_or_create(
            company=company,
            source_code=source_code,
            defaults={
                "source_type": source_type,
                "producer_module": producer,
                "truth_level": truth_level,
                "supports_scope": True,
                "supports_request_id": True,
                "supports_correlation": source_type in {"DOMAIN_EVENTS", "SYNC_EVENTS"},
                "supports_replay": source_type in {"DOMAIN_EVENTS", "SYNC_EVENTS"},
                "scope_fields": ["company_id", "branch_id"],
                "correlation_fields": ["request_id", "correlation_id", "causation_id"],
                "retention_policy": "short_term",
                "pii_policy": "minimal",
            },
        )


def _scope_level_from_scope(scope: dict[str, Any]) -> str:
    data_scope = dict(scope.get("data_scope") or {})
    if bool(data_scope.get("intercompany")):
        return ReportDefinition.ScopeLevel.INTERCOMPANY
    branch_id = scope.get("branch_id")
    return ReportDefinition.ScopeLevel.BRANCH if branch_id else ReportDefinition.ScopeLevel.COMPANY


def _freshness_mode_from_reproducibility(mode: str) -> str:
    if mode == ReportDefinition.ReproducibilityMode.LIVE:
        return ReportDefinition.FreshnessMode.LIVE
    if mode == ReportDefinition.ReproducibilityMode.SNAPSHOT:
        return ReportDefinition.FreshnessMode.SNAPSHOT
    return ReportDefinition.FreshnessMode.NEAR_REAL_TIME


def _materialization_policy_from_reproducibility(mode: str) -> str:
    if mode == ReportDefinition.ReproducibilityMode.LIVE:
        return ReportDefinition.MaterializationPolicy.LIVE_ONLY
    if mode == ReportDefinition.ReproducibilityMode.CERTIFIED:
        return ReportDefinition.MaterializationPolicy.SNAPSHOT_REQUIRED
    return ReportDefinition.MaterializationPolicy.CACHE_FIRST


def _sync_semantic_metrics_for_dataset(*, company, dataset_key: str, domain_owner: str) -> None:
    keys = semantic_metric_keys_for_dataset(dataset_key)
    for metric_key in keys:
        metric_spec = SEMANTIC_METRIC_REGISTRY.get(metric_key)
        if metric_spec is None:
            continue
        ReportMetricDefinition.objects.update_or_create(
            company=company,
            metric_key=metric_spec.metric_key,
            defaults={
                "name": metric_spec.name,
                "description": metric_spec.description,
                "domain_owner": domain_owner,
                "dataset_key": dataset_key,
                "expression": metric_spec.expression,
                "expression_hash": metric_expression_hash(metric_spec.expression),
                "unit": metric_spec.unit,
                "semantic_version": metric_spec.semantic_version,
                "formula_version": metric_spec.formula_version,
                "status": ReportMetricDefinition.MetricStatus.ACTIVE,
                "is_certified": bool(metric_spec.certified),
            },
        )


def _infer_dimensions_measures(*, rows: list[dict[str, Any]], parameters: dict[str, Any]) -> tuple[list[str], list[str]]:
    group_by = [str(x) for x in list(parameters.get("group_by") or []) if str(x)]
    metrics = [str(x) for x in list(parameters.get("metrics") or []) if str(x)]
    if group_by or metrics:
        return group_by, metrics
    if not rows:
        return [], []
    sample = rows[0]
    dimensions: list[str] = []
    measures: list[str] = []
    for key, value in sample.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            measures.append(str(key))
        else:
            dimensions.append(str(key))
    return dimensions, measures


def _compute_totals(*, rows: list[dict[str, Any]], measures: list[str]) -> dict[str, float]:
    if not rows or not measures:
        return {}
    totals: dict[str, float] = {}
    for name in measures:
        total = 0.0
        has_numeric = False
        for row in rows:
            value = row.get(name)
            if isinstance(value, (int, float)) and not isinstance(value, bool):
                total += float(value)
                has_numeric = True
        if has_numeric:
            totals[name] = round(total, 6)
    return totals


def _build_lineage_payload(*, run: ReportRun, request, actor, cache_hit: bool, consumer: str = "") -> dict[str, Any]:
    request_path = str(getattr(request, "path", "") or "")
    request_method = str(getattr(request, "method", "") or "")
    return {
        "actor_user_id": getattr(actor, "id", None),
        "request_id": _get_request_id(request),
        "request_path": request_path,
        "request_method": request_method,
        "consumer": consumer or ("dashboard_engine" if "/dashboard/" in request_path else "reports_api"),
        "cache_hit": bool(cache_hit),
        "source_manifest_hash": str(run.source_manifest_hash or ""),
        "output_manifest_hash": str(run.output_manifest_hash or ""),
        "generated_at": timezone.now().isoformat(),
    }


def _normalize_result_payload(
    *,
    run: ReportRun,
    payload: dict[str, Any],
    definition: ReportDefinition,
    parameters: dict[str, Any],
) -> dict[str, Any]:
    rows = list(payload.get("rows") or [])
    dimensions, measures = _infer_dimensions_measures(rows=rows, parameters=parameters)
    lineage = dict(run.lineage or {})
    return {
        # Compat v1
        "schema_version": int(payload.get("schema_version") or 1),
        "meta": dict(payload.get("meta") or {}),
        "rows": rows,
        "warnings": list(payload.get("warnings") or []),
        # Canonical dataset envelope v2
        "envelope_version": 2,
        "dataset_key": str(definition.dataset_key or definition.code),
        "semantic_version": str(definition.semantic_version or definition.version or "1.0.0"),
        "formula_version": str(definition.formula_version or ""),
        "metadata": {
            "title": definition.name,
            "description": definition.description,
            "scope": dict(run.effective_scope or {}),
            "filters": dict(parameters.get("filters") or {}),
            "generated_at": timezone.now().isoformat(),
            "freshness_mode": str(definition.freshness_mode or definition.freshness_class),
            "materialization_policy": str(definition.materialization_policy),
            "certification_status": str(definition.certification_status),
        },
        "dimensions": dimensions,
        "measures": measures,
        "totals": _compute_totals(rows=rows, measures=measures),
        "lineage": lineage,
        "render_hints": {
            "default_visual": "table",
            "default_group_by": dimensions[:3],
            "default_metrics": measures[:4],
        },
        "export_capabilities": dict(definition.export_capabilities or definition.export_policy or {}),
    }


def create_definition(
    *,
    request,
    actor,
    company,
    code: str,
    name: str,
    description: str = "",
    dataset_key: str = "",
    domain_owner: str = "",
    semantic_version: str = "",
    schema_version: int = 1,
    contract_version: int = 1,
    is_active: bool = True,
) -> ReportDefinition:
    _ensure_company_scope(request=request, company=company)
    if actor is not None and getattr(actor, "is_authenticated", False):
        _require_any_permission(
            user=actor,
            company=company,
            branch=getattr(request, "branch", None),
            permission_codes=KERNEL_PERMISSION_ALIASES["report.definition.manage"],
        )
    spec = REPORT_SPECS.get(code)
    if spec is None:
        raise ReportDomainError(
            code="REPORT_UNSUPPORTED_SOURCE",
            message=f"unknown_report_code:{code}",
            http_status=422,
        )

    _seed_sources(company=company)

    defaults = {
        "name": name,
        "description": description or "",
        "owner_domain": "REPORTS",
        "domain_owner": str(domain_owner or (code.split("_", 1)[0] if "_" in code else "REPORTS")).upper(),
        "status": ReportDefinition.DefinitionStatus.ACTIVE,
        "certification_status": ReportDefinition.CertificationStatus.CERTIFIED,
        "report_family": spec.family,
        "truth_level": spec.truth_level,
        "scope_level": _scope_level_from_scope(_scope_payload(company=company, branch=getattr(request, "branch", None), request=request)),
        "source_types": list(spec.source_types),
        "dataset_key": str(dataset_key or spec.dataset_code or code),
        "reproducibility_mode": spec.reproducibility_mode,
        "freshness_mode": _freshness_mode_from_reproducibility(spec.reproducibility_mode),
        "materialization_policy": _materialization_policy_from_reproducibility(spec.reproducibility_mode),
        "sensitivity_level": spec.sensitivity_level,
        "contains_pii": bool(spec.contains_pii),
        "reason_required": bool(spec.reason_required),
        "freshness_class": "live",
        "export_policy": {"allowed_formats": list(spec.export_formats)},
        "export_capabilities": {
            "formats": list(spec.export_formats),
            "supports_async_snapshot": spec.reproducibility_mode in {"SNAPSHOT", "CERTIFIED"},
        },
        "required_permissions": [*KERNEL_PERMISSION_ALIASES["report.dataset.read"], *([_family_permission(spec)] if _family_permission(spec) else [])],
        "semantic_metric_keys": semantic_metric_keys_for_dataset(str(spec.dataset_code or code)),
        "retention_policy": "short_term",
        "classification": "internal",
        "supports_async_snapshot": spec.reproducibility_mode in {"SNAPSHOT", "CERTIFIED"},
        "supports_future_modules": True,
        "version": spec.report_version,
        "semantic_version": str(semantic_version or spec.report_version),
        "dataset_version": str(spec.dataset_version or ""),
        "formula_version": str(spec.formula_version or ""),
        "schema_version": int(schema_version or 1),
        "contract_version": int(contract_version or 1),
        "is_active": bool(is_active),
    }
    with transaction.atomic():
        row, created = ReportDefinition.objects.get_or_create(company=company, code=code, defaults=defaults)
        if not created:
            row.name = name
            row.description = description or row.description
            row.is_active = bool(is_active)
            row.schema_version = int(schema_version or row.schema_version)
            row.contract_version = int(contract_version or row.contract_version)
            row.domain_owner = str(defaults["domain_owner"])
            row.dataset_key = str(defaults["dataset_key"])
            row.semantic_version = str(defaults["semantic_version"])
            row.formula_version = str(defaults["formula_version"])
            row.dataset_version = str(defaults["dataset_version"])
            row.scope_level = str(defaults["scope_level"])
            row.freshness_mode = str(defaults["freshness_mode"])
            row.materialization_policy = str(defaults["materialization_policy"])
            row.certification_status = str(defaults["certification_status"])
            row.required_permissions = defaults["required_permissions"]
            row.export_capabilities = defaults["export_capabilities"]
            row.semantic_metric_keys = defaults["semantic_metric_keys"]
            row.save(
                update_fields=[
                    "name",
                    "description",
                    "is_active",
                    "domain_owner",
                    "dataset_key",
                    "semantic_version",
                    "formula_version",
                    "dataset_version",
                    "scope_level",
                    "freshness_mode",
                    "materialization_policy",
                    "certification_status",
                    "required_permissions",
                    "export_capabilities",
                    "semantic_metric_keys",
                    "schema_version",
                    "contract_version",
                    "updated_at",
                ]
            )

        _sync_semantic_metrics_for_dataset(
            company=company,
            dataset_key=str(row.dataset_key or ""),
            domain_owner=str(row.domain_owner or "REPORTS"),
        )

        write_event(
            request=request,
            event_type="REPORT_DEFINITION_CREATED",
            reason_code="REPORTS_OK",
            actor_user=actor,
            subject_type="REPORT_DEFINITION",
            subject_id=str(row.report_id),
            metadata={"company_id": str(company.id), "code": code, "schema_version": row.schema_version},
            module="REPORTS",
        )

    return row


def _create_queue_dedupe_key(*, definition: ReportDefinition, scope: dict[str, Any], params_hash: str, as_of: Any) -> str:
    payload = {
        "code": definition.code,
        "scope": scope,
        "params_hash": params_hash,
        "as_of": str(as_of or ""),
    }
    return _hash_hex(payload)[:96]


def _resolve_allowed_formats(*, definition: ReportDefinition, spec: ReportSpec) -> set[str]:
    policy = dict(definition.export_policy or {})
    allowed = policy.get("allowed_formats") or spec.export_formats
    return {str(fmt).lower() for fmt in allowed}


def _build_freshness(*, definition: ReportDefinition) -> dict[str, Any]:
    return {"class": definition.freshness_class, "generated_at": timezone.now().isoformat()}


def _assert_reproducibility_integrity(*, run: ReportRun) -> None:
    if run.reproducibility_mode == ReportRun.ReproducibilityMode.LIVE:
        return
    if not str(run.source_manifest_hash or "").strip() or not str(run.output_manifest_hash or "").strip():
        raise ReportDomainError(
            code="REPORT_REPRODUCIBILITY_VIOLATION",
            message="missing reproducibility hashes",
            http_status=422,
            details={"execution_id": str(run.run_id)},
        )
    ledger = getattr(run, "reproducibility_ledger", None)
    if ledger is not None and ledger.verification_status == ReproducibilityLedger.VerificationStatus.MISMATCH:
        raise ReportDomainError(
            code="REPORT_REPRODUCIBILITY_VIOLATION",
            message="reproducibility ledger mismatch",
            http_status=422,
            details={"execution_id": str(run.run_id), "ledger_id": str(ledger.ledger_id)},
        )


def _build_run_error_envelope(*, code: str, message: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "code": code,
        "message": message,
        "details": details or {},
        "retryable": code in {"REPORT_UNSUPPORTED_SOURCE"},
        "timestamp": timezone.now().isoformat(),
    }


def _load_cache(*, definition: ReportDefinition, company, scope_hash: str, params_hash: str) -> DatasetCache | None:
    if definition.reproducibility_mode == ReportDefinition.ReproducibilityMode.LIVE:
        return None
    if not definition.dataset_version:
        return None
    return (
        DatasetCache.objects.filter(
            company=company,
            dataset_code=definition.code,
            dataset_version=definition.dataset_version,
            scope_hash=scope_hash,
            params_hash=params_hash,
            expires_at__gt=timezone.now(),
        )
        .order_by("-created_at")
        .first()
    )


def _save_cache(*, definition: ReportDefinition, company, scope_hash: str, params_hash: str, source_manifest_hash: str, payload: dict[str, Any]):
    if definition.reproducibility_mode == ReportDefinition.ReproducibilityMode.LIVE:
        return
    if not definition.dataset_version:
        return
    ttl = _retention_until(definition.retention_policy)
    DatasetCache.objects.update_or_create(
        company=company,
        dataset_code=definition.code,
        dataset_version=definition.dataset_version,
        scope_hash=scope_hash,
        params_hash=params_hash,
        defaults={
            "source_manifest_hash": source_manifest_hash,
            "payload": payload,
            "expires_at": ttl,
        },
    )


def _write_repro_ledger(*, run: ReportRun, actor, input_manifest_hash: str, output_manifest_hash: str):
    if run.reproducibility_mode not in {
        ReportDefinition.ReproducibilityMode.SNAPSHOT,
        ReportDefinition.ReproducibilityMode.CERTIFIED,
    }:
        return
    signature = _sign_hash(f"{input_manifest_hash}:{output_manifest_hash}")
    ReproducibilityLedger.objects.update_or_create(
        execution=run,
        defaults={
            "company": run.company,
            "report_code": run.definition.code,
            "report_version": run.report_version,
            "formula_version": run.formula_version,
            "dataset_version": run.dataset_version,
            "effective_scope": run.effective_scope,
            "as_of": run.as_of,
            "time_window": run.time_window,
            "input_manifest_hash": input_manifest_hash,
            "output_manifest_hash": output_manifest_hash,
            "signature": signature,
            "verification_status": ReproducibilityLedger.VerificationStatus.VERIFIED,
            "generated_by": actor,
        },
    )


def _run_request_from_row(run: ReportRun):
    branch = None
    if run.branch_id:
        from apps.modulos.iam.models import OrgUnit

        branch = OrgUnit.objects.filter(id=run.branch_id).first()
    return SimpleNamespace(
        request_id=run.request_id,
        META={},
        method="SYSTEM",
        path="/api/backend/reports/runs/",
        company=run.company,
        branch=branch,
    )


def _record_read_audit(
    *,
    request,
    actor,
    action: str,
    report_code: str,
    execution: ReportRun | None,
    sensitivity_level: str,
    reason: str = "",
):
    audit_company = getattr(request, "company", None) if request is not None else None
    if audit_company is None and execution is not None:
        audit_company = execution.company
    if audit_company is None:
        raise ReportDomainError(code="REPORT_INVALID_SCOPE", message="missing company scope for read-audit", http_status=403)

    scope = _scope_payload(company=audit_company, branch=getattr(request, "branch", None), request=request)
    row = ReportReadAudit.objects.create(
        company=audit_company,
        branch_id=getattr(getattr(request, "branch", None), "id", None),
        actor_user=actor,
        action=action,
        report_code=report_code,
        execution=execution,
        scope=scope,
        sensitivity_level=sensitivity_level,
        reason=reason or "",
        request_id=_get_request_id(request),
        ip_server_seen=(request.META.get("REMOTE_ADDR") if request is not None else None),
        user_agent=(request.META.get("HTTP_USER_AGENT", "") if request is not None else ""),
    )
    write_event(
        request=request,
        event_type="REPORT_READ_AUDITED",
        reason_code="REPORTS_OK",
        actor_user=actor,
        subject_type="REPORT_RUN" if execution is not None else "REPORT_DEFINITION",
        subject_id=str(execution.run_id) if execution is not None else "",
        metadata={
            "company_id": str(row.company_id),
            "action": action,
            "report_code": report_code,
            "read_audit_id": str(row.read_audit_id),
            "reason": reason or "",
        },
        module="REPORTS",
    )
    return row


def _execute_run(*, run: ReportRun, request, actor, use_cache: bool = True) -> ReportRun:
    definition = run.definition
    spec = REPORT_SPECS[definition.code]
    params = dict(run.parameters or {})
    scope_hash = _hash_hex(run.effective_scope)

    write_event(
        request=request,
        event_type="REPORT_RUN_STARTED",
        reason_code="REPORTS_OK",
        actor_user=actor,
        subject_type="REPORT_RUN",
        subject_id=str(run.run_id),
        metadata={"company_id": str(run.company_id), "code": definition.code, "request_id": run.request_id},
        module="REPORTS",
    )

    start_ts = timezone.now()
    warnings: list[str] = []
    cached_payload: dict[str, Any] | None = None
    source_manifest_hash = ""
    cache_hit = False
    try:
        if use_cache:
            cache_row = _load_cache(
                definition=definition,
                company=run.company,
                scope_hash=scope_hash,
                params_hash=run.params_hash,
            )
            if cache_row is not None:
                cached_payload = dict(cache_row.payload or {})
                warnings.append("CACHE_HIT")
                source_manifest_hash = str(cache_row.source_manifest_hash or "")
                cache_hit = True

        if cached_payload is None:
            result: ReportResult = REPORT_REGISTRY[definition.code](
                company_id=run.company_id,
                branch_id=run.branch_id,
                parameters=params,
            )
            rows = list(result.rows or [])
            if len(rows) > int(definition.max_rows):
                rows = rows[: int(definition.max_rows)]
                warnings.append("MAX_ROWS_TRUNCATED")
            source_manifest = dict(result.meta.get("source_manifest") or _source_manifest(spec=spec))
            source_manifest_hash = _hash_hex(source_manifest)
            payload = {
                "schema_version": int(result.schema_version),
                "meta": dict(result.meta or {}),
                "rows": rows,
                "warnings": list(result.warnings or []) + warnings,
            }
            cached_payload = json.loads(_canon_json(payload))
            _save_cache(
                definition=definition,
                company=run.company,
                scope_hash=scope_hash,
                params_hash=run.params_hash,
                source_manifest_hash=source_manifest_hash,
                payload=payload,
            )

        normalized_payload = _normalize_result_payload(
            run=run,
            payload=cached_payload,
            definition=definition,
            parameters=params,
        )
        output_manifest_hash = _hash_hex(cached_payload)
        duration_ms = int((timezone.now() - start_ts).total_seconds() * 1000)
        run.status = ReportRun.Status.SUCCEEDED
        run.result = normalized_payload
        run.source_manifest = json.loads(
            _canon_json((cached_payload.get("meta") or {}).get("source_manifest") or _source_manifest(spec=spec))
        )
        run.source_manifest_hash = source_manifest_hash or _hash_hex(run.source_manifest)
        run.output_manifest_hash = output_manifest_hash
        run.duration_ms = duration_ms
        run.row_count = len(list(normalized_payload.get("rows") or []))
        run.warnings = list(normalized_payload.get("warnings") or [])
        run.freshness = _build_freshness(definition=definition)
        run.lineage = _build_lineage_payload(
            run=run,
            request=request,
            actor=actor,
            cache_hit=cache_hit,
            consumer=str((params or {}).get("consumer_surface") or ""),
        )
        run.finished_at = timezone.now()
        run.save(
            update_fields=[
                "status",
                "result",
                "source_manifest",
                "source_manifest_hash",
                "output_manifest_hash",
                "duration_ms",
                "row_count",
                "warnings",
                "freshness",
                "lineage",
                "finished_at",
            ]
        )

        _write_repro_ledger(
            run=run,
            actor=actor,
            input_manifest_hash=run.source_manifest_hash,
            output_manifest_hash=run.output_manifest_hash,
        )
        write_event(
            request=request,
            event_type="REPORT_RUN_SUCCEEDED",
            reason_code="REPORTS_OK",
            actor_user=actor,
            subject_type="REPORT_RUN",
            subject_id=str(run.run_id),
            metadata={"company_id": str(run.company_id), "code": definition.code, "row_count": run.row_count},
            module="REPORTS",
        )
        _record_run_metric(run=run, final_status=run.status, duration_ms=run.duration_ms)
        return run
    except Exception as exc:
        run.status = ReportRun.Status.FAILED
        run.error = str(exc)[:500]
        run.error_code = "REPORT_INVALID_PARAMS" if isinstance(exc, ReportDomainError) else "INTERNAL_ERROR"
        run.error_envelope = _build_run_error_envelope(code=run.error_code, message=str(exc)[:500])
        run.finished_at = timezone.now()
        run.save(update_fields=["status", "error", "error_code", "error_envelope", "finished_at"])
        write_event(
            request=request,
            event_type="REPORT_RUN_FAILED",
            reason_code="INTERNAL_ERROR",
            actor_user=actor,
            subject_type="REPORT_RUN",
            subject_id=str(run.run_id),
            metadata={"company_id": str(run.company_id), "code": definition.code, "error": str(exc)[:200]},
            module="REPORTS",
        )
        _record_run_metric(run=run, final_status=run.status, duration_ms=0)
        raise


def run_report(
    *,
    request,
    actor,
    company,
    branch,
    code: str,
    params: dict[str, Any] | None = None,
    as_of=None,
    time_window: dict[str, Any] | None = None,
    run_async: bool = False,
    priority: int = 5,
    use_cache: bool = True,
) -> ReportRun:
    _ensure_company_scope(request=request, company=company, branch=branch)
    definition = ReportDefinition.objects.filter(company=company, code=code, is_active=True).first()
    if definition is None:
        raise ReportDomainError(code="REPORT_NOT_FOUND", message="report not found", http_status=404)
    if code not in REPORT_REGISTRY or code not in REPORT_SPECS:
        raise ReportDomainError(code="REPORT_UNSUPPORTED_SOURCE", message="runtime not registered", http_status=422)

    spec = REPORT_SPECS[code]
    _require_any_permission(
        user=actor,
        company=company,
        branch=branch,
        permission_codes=KERNEL_PERMISSION_ALIASES["report.dataset.read"],
    )
    family_perm = _family_permission(spec)
    if family_perm:
        _require_any_permission(
            user=actor,
            company=company,
            branch=branch,
            permission_codes=(family_perm,),
        )

    merged_params = dict(params or {})
    _assert_v3_analytics_params_enabled(merged_params)
    tw = _build_time_window(definition=definition, params=merged_params, time_window=time_window)
    req_id = _get_request_id(request)
    scope = _scope_payload(company=company, branch=branch, request=request)
    params_hash = _hash_hex({"params": merged_params, "as_of": str(as_of or ""), "time_window": tw})
    dedupe_key = _create_queue_dedupe_key(definition=definition, scope=scope, params_hash=params_hash, as_of=as_of)

    with transaction.atomic():
        lineage_seed = {
            "actor_user_id": getattr(actor, "id", None),
            "request_id": req_id,
            "request_path": str(getattr(request, "path", "") or ""),
            "request_method": str(getattr(request, "method", "") or ""),
            "consumer": "dashboard_engine" if "/dashboard/" in str(getattr(request, "path", "") or "") else "reports_api",
            "workspace_code": str(merged_params.get("workspace_code") or ""),
            "widget_code": str(merged_params.get("widget_code") or ""),
            "created_at": timezone.now().isoformat(),
        }
        if run_async:
            existing = (
                ReportRun.objects.filter(
                    company=company,
                    dedupe_key=dedupe_key,
                    status__in=[ReportRun.Status.QUEUED, ReportRun.Status.RUNNING],
                )
                .order_by("-started_at")
                .first()
            )
            if existing is not None:
                setattr(existing, "_dedupe_reused", True)
                return existing
            pending = ReportRun.objects.filter(company=company, status__in=[ReportRun.Status.QUEUED, ReportRun.Status.RUNNING]).count()
            if pending >= int(definition.max_pending_jobs):
                raise ReportDomainError(
                    code="REPORT_INVALID_PARAMS",
                    message="pending jobs quota exceeded",
                    http_status=422,
                    details={"max_pending_jobs": int(definition.max_pending_jobs)},
                )
            run = ReportRun.objects.create(
                company=company,
                branch_id=getattr(branch, "id", None) if branch is not None else None,
                definition=definition,
                actor_user=actor,
                status=ReportRun.Status.QUEUED,
                request_id=req_id,
                report_version=spec.report_version,
                truth_level=spec.truth_level,
                reproducibility_mode=spec.reproducibility_mode,
                source_types=list(spec.source_types),
                effective_scope=scope,
                params_hash=params_hash,
                as_of=_parse_dt(as_of),
                time_window=tw,
                source_manifest=_source_manifest(spec=spec),
                dataset_version=spec.dataset_version,
                formula_version=spec.formula_version,
                freshness={"class": definition.freshness_class, "queued_at": timezone.now().isoformat()},
                classification=definition.classification,
                sensitivity_level=definition.sensitivity_level,
                is_async=True,
                priority=int(priority),
                dedupe_key=dedupe_key,
                queue_name="reports",
                parameters=merged_params,
                lineage=lineage_seed,
            )
            return run

        run = ReportRun.objects.create(
            company=company,
            branch_id=getattr(branch, "id", None) if branch is not None else None,
            definition=definition,
            actor_user=actor,
            status=ReportRun.Status.RUNNING,
            request_id=req_id,
            report_version=spec.report_version,
            truth_level=spec.truth_level,
            reproducibility_mode=spec.reproducibility_mode,
            source_types=list(spec.source_types),
            effective_scope=scope,
            params_hash=params_hash,
            as_of=_parse_dt(as_of),
            time_window=tw,
            source_manifest=_source_manifest(spec=spec),
            dataset_version=spec.dataset_version,
            formula_version=spec.formula_version,
            freshness={"class": definition.freshness_class},
            classification=definition.classification,
            sensitivity_level=definition.sensitivity_level,
            is_async=False,
            priority=int(priority),
            dedupe_key=dedupe_key,
            queue_name="reports",
            parameters=merged_params,
            lineage=lineage_seed,
        )
    return _execute_run(run=run, request=request, actor=actor, use_cache=bool(use_cache))


def process_queued_runs(*, limit: int = 20) -> dict[str, int]:
    selected = list(
        ReportRun.objects.filter(status=ReportRun.Status.QUEUED)
        .select_related("company", "definition", "actor_user")
        .order_by("priority", "started_at")[: max(int(limit), 1)]
    )
    processed = 0
    failed = 0
    for run in selected:
        run.status = ReportRun.Status.RUNNING
        run.save(update_fields=["status"])
        req = _run_request_from_row(run)
        try:
            _execute_run(run=run, request=req, actor=run.actor_user, use_cache=True)
            processed += 1
        except Exception:
            failed += 1
    return {"processed": processed, "failed": failed}


def cancel_run(*, request, actor, company, run_id: str) -> ReportRun:
    _ensure_company_scope(request=request, company=company, branch=getattr(request, "branch", None))
    run = ReportRun.objects.filter(company=company, run_id=run_id).select_related("definition").first()
    if run is None:
        raise ReportDomainError(code="REPORT_NOT_FOUND", message="execution not found", http_status=404)
    if run.branch_id and getattr(request, "branch", None) is not None and int(getattr(request.branch, "id")) != int(run.branch_id):
        raise ReportDomainError(
            code="REPORT_INVALID_SCOPE",
            message="branch scope mismatch for cancel",
            http_status=403,
            details={"required_scope": {"company_id": int(company.id), "branch_id": int(run.branch_id)}},
        )
    if run.status in {ReportRun.Status.SUCCEEDED, ReportRun.Status.FAILED}:
        raise ReportDomainError(
            code="REPORT_INVALID_PARAMS",
            message="only queued/running executions can be canceled",
            http_status=422,
        )
    if run.status == ReportRun.Status.CANCELED:
        return run

    run.status = ReportRun.Status.CANCELED
    run.error_code = "REPORT_INVALID_PARAMS"
    run.error = "canceled_by_user"
    run.finished_at = timezone.now()
    run.save(update_fields=["status", "error_code", "error", "finished_at"])
    write_event(
        request=request,
        event_type="REPORT_RUN_FAILED",
        reason_code="REPORTS_OK",
        actor_user=actor,
        subject_type="REPORT_RUN",
        subject_id=str(run.run_id),
        metadata={"company_id": str(company.id), "code": run.definition.code, "status": run.status},
        module="REPORTS",
    )
    _record_run_metric(run=run, final_status=run.status, duration_ms=0)
    return run


def retry_run(*, request, actor, company, run_id: str, priority: int | None = None, use_cache: bool = True) -> ReportRun:
    _ensure_company_scope(request=request, company=company, branch=getattr(request, "branch", None))
    run = ReportRun.objects.filter(company=company, run_id=run_id).select_related("definition").first()
    if run is None:
        raise ReportDomainError(code="REPORT_NOT_FOUND", message="execution not found", http_status=404)
    if run.status not in {ReportRun.Status.FAILED, ReportRun.Status.CANCELED}:
        raise ReportDomainError(code="REPORT_INVALID_PARAMS", message="execution is not retryable", http_status=422)
    if run.branch_id and getattr(request, "branch", None) is not None and int(getattr(request.branch, "id")) != int(run.branch_id):
        raise ReportDomainError(
            code="REPORT_INVALID_SCOPE",
            message="branch scope mismatch for retry",
            http_status=403,
            details={"required_scope": {"company_id": int(company.id), "branch_id": int(run.branch_id)}},
        )
    return run_report(
        request=request,
        actor=actor,
        company=company,
        branch=getattr(request, "branch", None),
        code=run.definition.code,
        params=dict(run.parameters or {}),
        as_of=run.as_of,
        time_window=dict(run.time_window or {}),
        run_async=True,
        priority=int(priority if priority is not None else run.priority),
        use_cache=bool(use_cache),
    )


def invalidate_dataset_cache(
    *,
    company,
    dataset_code: str,
    dataset_version: str = "",
    source_manifest_hash: str = "",
) -> int:
    qs = DatasetCache.objects.filter(company=company, dataset_code=dataset_code)
    if str(dataset_version).strip():
        qs = qs.filter(dataset_version=str(dataset_version).strip())
    if str(source_manifest_hash).strip():
        qs = qs.filter(source_manifest_hash=str(source_manifest_hash).strip())
    deleted, _ = qs.delete()
    return int(deleted)


def _build_watermark(*, actor, run: ReportRun, request) -> str:
    return (
        f"user={getattr(actor, 'id', None)}|ts={timezone.now().isoformat()}|"
        f"scope={run.company_id}:{run.branch_id}|request_id={_get_request_id(request)}"
    )


def _serialize_export_content(*, run: ReportRun, rows: list[dict[str, Any]], fmt: str, watermark: str) -> dict[str, Any]:
    payload = {
        "execution_id": str(run.run_id),
        "report_code": run.definition.code,
        "report_version": run.report_version,
        "classification": run.classification,
        "sensitivity_level": run.sensitivity_level,
        "watermark": watermark,
        "format": fmt,
        "rows": rows,
    }
    return payload


def create_export(
    *,
    request,
    actor,
    company,
    execution_id,
    fmt: str,
    template_version: str = "v1",
    reason: str = "",
    require_dual_approval: bool = False,
    approved_by_user_id: int | None = None,
) -> ReportExport:
    _ensure_company_scope(request=request, company=company)
    _require_any_permission(
        user=actor,
        company=company,
        branch=getattr(request, "branch", None),
        permission_codes=KERNEL_PERMISSION_ALIASES["report.dataset.export"],
    )
    run = ReportRun.objects.filter(company=company, run_id=execution_id).select_related("definition").first()
    if run is None:
        raise ReportDomainError(code="REPORT_NOT_FOUND", message="execution not found", http_status=404)
    if run.status != ReportRun.Status.SUCCEEDED:
        raise ReportDomainError(code="REPORT_INVALID_PARAMS", message="execution not succeeded", http_status=422)
    request_branch = getattr(request, "branch", None)
    if run.branch_id is not None and request_branch is not None and int(request_branch.id) != int(run.branch_id):
        raise ReportDomainError(
            code="REPORT_INVALID_SCOPE",
            message="branch scope mismatch for export",
            http_status=403,
            details={"required_scope": {"company_id": int(company.id), "branch_id": int(run.branch_id)}},
        )
    _assert_reproducibility_integrity(run=run)

    spec = REPORT_SPECS.get(run.definition.code)
    if spec is None:
        raise ReportDomainError(code="REPORT_UNSUPPORTED_SOURCE", message="missing report spec", http_status=422)

    sensitivity_allowed = set(SENSITIVITY_ALLOWED_EXPORTS.get(str(run.sensitivity_level), {"json"}))
    allowed_formats = _resolve_allowed_formats(definition=run.definition, spec=spec)
    fmt = str(fmt or "json").strip().lower()

    if fmt not in sensitivity_allowed:
        raise ReportDomainError(
            code="REPORT_DATA_CLASSIFICATION_CONFLICT",
            message="format not allowed for sensitivity level",
            http_status=403,
            details={
                "format": fmt,
                "sensitivity_level": str(run.sensitivity_level),
                "allowed_formats_by_sensitivity": sorted(sensitivity_allowed),
            },
        )
    if fmt not in allowed_formats:
        raise ReportDomainError(
            code="REPORT_EXPORT_FORBIDDEN",
            message="format not allowed by export policy",
            http_status=403,
            details={"format": fmt, "allowed_formats": sorted(allowed_formats)},
        )

    if run.sensitivity_level in {ReportRun.SensitivityLevel.HIGH, ReportRun.SensitivityLevel.RESTRICTED} and not str(reason or "").strip():
        raise ReportDomainError(
            code="REPORT_EXPORT_FORBIDDEN",
            message="reason required for sensitive export",
            http_status=403,
        )

    approved_by = None
    if approved_by_user_id:
        from django.contrib.auth import get_user_model

        User = get_user_model()
        approved_by = User.objects.filter(id=int(approved_by_user_id)).first()

    if run.sensitivity_level == ReportRun.SensitivityLevel.RESTRICTED and not bool(require_dual_approval):
        raise ReportDomainError(
            code="REPORT_DATA_CLASSIFICATION_CONFLICT",
            message="restricted reports require dual approval",
            http_status=403,
            details={"sensitivity_level": run.sensitivity_level, "required": "dual_approval"},
        )

    status = ReportExport.ExportStatus.PENDING_APPROVAL if require_dual_approval and approved_by is None else ReportExport.ExportStatus.READY
    rows = list((run.result or {}).get("rows") or [])
    if run.sensitivity_level in {ReportRun.SensitivityLevel.HIGH, ReportRun.SensitivityLevel.RESTRICTED}:
        perms = _effective_perms(user=actor, company=company, branch=getattr(request, "branch", None))
        if "reports.admin" not in perms and "*" not in perms:
            rows = _mask_sensitive_rows(rows)

    watermark = _build_watermark(actor=actor, run=run, request=request)
    content = _serialize_export_content(run=run, rows=rows, fmt=fmt, watermark=watermark)
    content_hash = _hash_hex(content)
    export = ReportExport.objects.create(
        company=company,
        execution=run,
        format=fmt,
        status=status,
        template_version=template_version or "v1",
        watermark_text=watermark,
        requested_reason=reason or "",
        exported_by=actor,
        approved_by=approved_by,
        download_scope=_scope_payload(company=company, branch=getattr(request, "branch", None), request=request),
        retention_until=_retention_until(run.definition.retention_policy),
        storage_ref=f"db://reports_export/{run.run_id}/{fmt}",
        content=content if status == ReportExport.ExportStatus.READY else {},
        content_hash=content_hash if status == ReportExport.ExportStatus.READY else "",
        exported_at=timezone.now() if status == ReportExport.ExportStatus.READY else None,
    )
    _record_export_metric(export=export)
    if status == ReportExport.ExportStatus.READY:
        _record_read_audit(
            request=request,
            actor=actor,
            action=ReportReadAudit.Action.EXPORT,
            report_code=run.definition.code,
            execution=run,
            sensitivity_level=run.sensitivity_level,
            reason=reason,
        )
        write_event(
            request=request,
            event_type="REPORT_EXPORTED",
            reason_code="REPORTS_OK",
            actor_user=actor,
            subject_type="REPORT_RUN",
            subject_id=str(run.run_id),
            metadata={
                "company_id": str(company.id),
                "execution_id": str(run.run_id),
                "format": fmt,
                "export_id": str(export.export_id),
            },
            module="REPORTS",
        )
    return export


def list_visible_sources(*, company):
    return SourceRegistry.objects.filter(company=company).order_by("source_type", "source_code")


def register_read_access(*, request, actor, run: ReportRun, reason: str = "") -> ReportReadAudit | None:
    if run.sensitivity_level not in {ReportRun.SensitivityLevel.HIGH, ReportRun.SensitivityLevel.RESTRICTED}:
        return None
    if run.definition.reason_required and not str(reason or "").strip():
        raise ReportDomainError(
            code="REPORT_FORBIDDEN",
            message="reason required for sensitive report read",
            http_status=403,
        )
    return _record_read_audit(
        request=request,
        actor=actor,
        action=ReportReadAudit.Action.READ,
        report_code=run.definition.code,
        execution=run,
        sensitivity_level=run.sensitivity_level,
        reason=reason,
    )


def masked_result_for_actor(*, request, actor, run: ReportRun) -> dict[str, Any]:
    result = dict(run.result or {})
    rows = list(result.get("rows") or [])
    if run.sensitivity_level in {ReportRun.SensitivityLevel.HIGH, ReportRun.SensitivityLevel.RESTRICTED}:
        perms = _effective_perms(user=actor, company=run.company, branch=getattr(request, "branch", None))
        if "reports.admin" not in perms and "*" not in perms:
            result["rows"] = _mask_sensitive_rows(rows)
    return result
