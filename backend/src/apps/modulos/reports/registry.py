from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any, Callable

from django.apps import apps
from django.db.models import Q
from django.utils import timezone

from config.metrics import snapshot


@dataclass(frozen=True)
class ReportResult:
    schema_version: int
    rows: list[dict[str, Any]]
    meta: dict[str, Any]
    warnings: list[str] = field(default_factory=list)


ReportCallable = Callable[..., ReportResult]


@dataclass(frozen=True)
class ReportSpec:
    code: str
    family: str
    truth_level: str
    source_types: list[str]
    reproducibility_mode: str
    sensitivity_level: str
    contains_pii: bool
    reason_required: bool
    export_formats: list[str]
    runner: ReportCallable
    report_version: str = "1.0.0"
    dataset_code: str = ""
    dataset_version: str = ""
    formula_version: str = ""


REPORT_REGISTRY: dict[str, ReportCallable] = {}
REPORT_SPECS: dict[str, ReportSpec] = {}


def register(
    code: str,
    *,
    family: str,
    truth_level: str,
    source_types: list[str],
    reproducibility_mode: str,
    sensitivity_level: str,
    contains_pii: bool = False,
    reason_required: bool = False,
    export_formats: list[str] | None = None,
    report_version: str = "1.0.0",
    dataset_code: str = "",
    dataset_version: str = "",
    formula_version: str = "",
):
    def _decorator(fn: ReportCallable):
        REPORT_REGISTRY[code] = fn
        REPORT_SPECS[code] = ReportSpec(
            code=code,
            family=family,
            truth_level=truth_level,
            source_types=list(source_types or []),
            reproducibility_mode=reproducibility_mode,
            sensitivity_level=sensitivity_level,
            contains_pii=bool(contains_pii),
            reason_required=bool(reason_required),
            export_formats=list(export_formats or ["json", "jsonl"]),
            runner=fn,
            report_version=report_version,
            dataset_code=dataset_code,
            dataset_version=dataset_version,
            formula_version=formula_version,
        )
        return fn

    return _decorator


def _parse_dt(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value
    if not value:
        return None
    try:
        from django.utils.dateparse import parse_datetime

        return parse_datetime(str(value))
    except Exception:
        return None


def _to_int(value: Any, *, default: int = 0) -> int:
    if value is None:
        return int(default)
    try:
        return int(value)
    except (TypeError, ValueError):
        return int(default)


@register(
    "reports.ping.v1",
    family="TRACE",
    truth_level="operational",
    source_types=["READ_MODELS"],
    reproducibility_mode="LIVE",
    sensitivity_level="low",
    export_formats=["json", "jsonl"],
)
def ping_report(*, company_id: int, branch_id: int | None, parameters: dict[str, Any]) -> ReportResult:
    # Report mínimo para bootstrap y tests.
    return ReportResult(
        schema_version=1,
        rows=[{"company_id": company_id, "branch_id": branch_id, "echo": dict(parameters or {})}],
        meta={"kind": "PING"},
    )


@register(
    "AUDIT_EVENTS_BY_SCOPE",
    family="AUDIT",
    truth_level="audit_control",
    source_types=["AUDIT_EVENTS"],
    reproducibility_mode="LIVE",
    sensitivity_level="high",
    contains_pii=True,
    reason_required=True,
    export_formats=["json", "jsonl", "csv"],
)
def audit_events_by_scope_report(*, company_id: int, branch_id: int | None, parameters: dict[str, Any]) -> ReportResult:
    from apps.modulos.audit.models import AuditEvent

    qs = AuditEvent.objects.all().order_by("-timestamp_server", "-id")

    # Chain partition by company is the canonical boundary for audit trails.
    qs = qs.filter(partition_key=f"COMPANY:{company_id}")
    if parameters.get("module"):
        qs = qs.filter(module=str(parameters.get("module")))
    if parameters.get("event_type"):
        qs = qs.filter(event_type=str(parameters.get("event_type")))
    if parameters.get("subject_type"):
        qs = qs.filter(subject_type=str(parameters.get("subject_type")))
    if parameters.get("subject_id"):
        qs = qs.filter(subject_id=str(parameters.get("subject_id")))
    if parameters.get("actor_user_id"):
        actor_user_id = _to_int(parameters.get("actor_user_id"), default=0)
        if actor_user_id > 0:
            qs = qs.filter(actor_user_id=actor_user_id)
    if parameters.get("request_id"):
        qs = qs.filter(metadata__request_id=str(parameters.get("request_id")))

    since = _parse_dt(parameters.get("since"))
    until = _parse_dt(parameters.get("until"))
    if since is not None:
        qs = qs.filter(timestamp_server__gte=since)
    if until is not None:
        qs = qs.filter(timestamp_server__lte=until)

    limit = min(max(_to_int(parameters.get("limit"), default=200), 1), 1000)
    rows = []
    for ev in qs[:limit]:
        rows.append(
            {
                "event_id": str(ev.event_id),
                "timestamp_server": ev.timestamp_server.isoformat() if ev.timestamp_server else "",
                "module": ev.module,
                "event_type": ev.event_type,
                "reason_code": ev.reason_code,
                "subject_type": ev.subject_type,
                "subject_id": ev.subject_id,
                "actor_user_id": ev.actor_user_id,
                "request_id": str((ev.metadata or {}).get("request_id") or ""),
                "path": ev.path,
                "method": ev.method,
            }
        )
    return ReportResult(
        schema_version=1,
        rows=rows,
        meta={
            "kind": "AUDIT_EVENTS_BY_SCOPE",
            "row_limit": limit,
            "source_manifest": {"module": "AUDIT", "partition_key": f"COMPANY:{company_id}"},
        },
    )


@register(
    "OBS_ENDPOINT_ERRORS_SUMMARY",
    family="OBS",
    truth_level="observability",
    source_types=["METRICS", "SECURITY_EVENTS"],
    reproducibility_mode="LIVE",
    sensitivity_level="medium",
    export_formats=["json", "jsonl", "csv"],
)
def obs_endpoint_errors_summary_report(*, company_id: int, branch_id: int | None, parameters: dict[str, Any]) -> ReportResult:
    from apps.modulos.audit.models import AuditEvent

    metric_snapshot = snapshot()
    # Approximate security signal from contract audit denials.
    denied_count = (
        AuditEvent.objects.filter(
            partition_key=f"COMPANY:{company_id}",
            event_type="AUTH_ACCESS_DENIED",
        )
        .order_by()
        .count()
    )
    rows = [
        {
            "total_requests": _to_int(metric_snapshot.get("total_requests"), default=0),
            "latency_ms_avg": _to_int(metric_snapshot.get("latency_ms_avg"), default=0),
            "latency_ms_max": _to_int(metric_snapshot.get("latency_ms_max"), default=0),
            "status_counts": dict(metric_snapshot.get("status_counts") or {}),
            "top_paths": list(metric_snapshot.get("top_paths") or []),
            "auth_access_denied_total": int(denied_count),
        }
    ]
    return ReportResult(
        schema_version=1,
        rows=rows,
        meta={"kind": "OBS_ENDPOINT_ERRORS_SUMMARY", "source_manifest": {"module": "COMMON_METRICS"}},
    )


@register(
    "TRACE_ENTITY_TIMELINE",
    family="TRACE",
    truth_level="operational",
    source_types=["DOMAIN_EVENTS", "AUDIT_EVENTS", "SYNC_EVENTS"],
    reproducibility_mode="LIVE",
    sensitivity_level="medium",
    export_formats=["json", "jsonl", "csv"],
)
def trace_entity_timeline_report(*, company_id: int, branch_id: int | None, parameters: dict[str, Any]) -> ReportResult:
    from apps.modulos.audit.models import AuditEvent
    from apps.modulos.integration.models import OutboxEvent

    request_id = str(parameters.get("request_id") or "").strip()
    correlation_id = str(parameters.get("correlation_id") or "").strip()
    source_module = str(parameters.get("source_module") or "").strip().upper()
    limit = min(max(_to_int(parameters.get("limit"), default=300), 1), 2000)

    outbox_qs = OutboxEvent.objects.filter(company_id=company_id).order_by("-occurred_at", "-id")
    if branch_id is not None:
        outbox_qs = outbox_qs.filter(branch_id=branch_id)
    if source_module:
        outbox_qs = outbox_qs.filter(source_module=source_module)
    if request_id:
        outbox_qs = outbox_qs.filter(correlation_id=request_id)
    if correlation_id:
        outbox_qs = outbox_qs.filter(correlation_id=correlation_id)

    audit_qs = AuditEvent.objects.filter(partition_key=f"COMPANY:{company_id}").order_by("-timestamp_server", "-id")
    if source_module:
        audit_qs = audit_qs.filter(module=source_module)
    if request_id:
        audit_qs = audit_qs.filter(metadata__request_id=request_id)

    rows: list[dict[str, Any]] = []
    for ev_outbox in outbox_qs[:limit]:
        rows.append(
            {
                "record_type": "OUTBOX_EVENT",
                "occurred_at": ev_outbox.occurred_at.isoformat() if ev_outbox.occurred_at else "",
                "source_module": ev_outbox.source_module,
                "event_type": ev_outbox.event_type,
                "status": ev_outbox.status,
                "request_id": ev_outbox.correlation_id,
                "correlation_id": ev_outbox.correlation_id,
                "causation_id": ev_outbox.causation_id,
                "payload": ev_outbox.payload,
            }
        )
    for ev_audit in audit_qs[:limit]:
        metadata = dict(ev_audit.metadata or {})
        rows.append(
            {
                "record_type": "AUDIT_EVENT",
                "occurred_at": ev_audit.timestamp_server.isoformat() if ev_audit.timestamp_server else "",
                "source_module": ev_audit.module,
                "event_type": ev_audit.event_type,
                "reason_code": ev_audit.reason_code,
                "subject_type": ev_audit.subject_type,
                "subject_id": ev_audit.subject_id,
                "request_id": str(metadata.get("request_id") or ""),
                "correlation_id": str(metadata.get("correlation_id") or ""),
                "causation_id": str(metadata.get("causation_id") or ""),
                "payload": metadata,
            }
        )

    rows.sort(key=lambda row: (row.get("occurred_at") or ""), reverse=True)
    rows = rows[:limit]
    return ReportResult(
        schema_version=1,
        rows=rows,
        meta={"kind": "TRACE_ENTITY_TIMELINE", "source_manifest": {"modules": ["INTEGRATION", "AUDIT"]}},
    )


@dataclass(frozen=True)
class DomainReportBlueprint:
    domain_key: str
    domain_code: str
    family: str
    truth_level: str
    source_types: tuple[str, ...]
    sensitivity_level: str
    contains_pii: bool
    reason_required: bool
    module_hints: tuple[str, ...]
    model_labels: tuple[str, ...]


DOMAIN_REPORT_BLUEPRINTS: tuple[DomainReportBlueprint, ...] = (
    DomainReportBlueprint(
        domain_key="accounts",
        domain_code="ACCOUNTS",
        family="SEC",
        truth_level="audit_control",
        source_types=("READ_MODELS", "AUDIT_EVENTS"),
        sensitivity_level="high",
        contains_pii=True,
        reason_required=True,
        module_hints=("AUTH", "ACCOUNTS"),
        model_labels=("accounts.User", "accounts.TwoFactorConfig", "accounts.TwoFactorChallenge"),
    ),
    DomainReportBlueprint(
        domain_key="iam",
        domain_code="IAM",
        family="SEC",
        truth_level="audit_control",
        source_types=("READ_MODELS", "AUDIT_EVENTS"),
        sensitivity_level="high",
        contains_pii=True,
        reason_required=True,
        module_hints=("IAM",),
        model_labels=("iam.OrgUnit", "iam.UserMembership", "iam.InterCompanyGrant"),
    ),
    DomainReportBlueprint(
        domain_key="org",
        domain_code="ORG",
        family="OPS",
        truth_level="operational",
        source_types=("READ_MODELS", "AUDIT_EVENTS"),
        sensitivity_level="medium",
        contains_pii=False,
        reason_required=False,
        module_hints=("ORG",),
        model_labels=("org.CompanyProfile", "iam.OrgUnit"),
    ),
    DomainReportBlueprint(
        domain_key="hr",
        domain_code="HR",
        family="OPS",
        truth_level="operational",
        source_types=("READ_MODELS", "AUDIT_EVENTS"),
        sensitivity_level="medium",
        contains_pii=True,
        reason_required=False,
        module_hints=("HR",),
        model_labels=("hr.Position", "hr.Employee", "hr.EmploymentAssignment"),
    ),
    DomainReportBlueprint(
        domain_key="rbac",
        domain_code="RBAC",
        family="SEC",
        truth_level="audit_control",
        source_types=("READ_MODELS", "AUDIT_EVENTS"),
        sensitivity_level="high",
        contains_pii=False,
        reason_required=False,
        module_hints=("RBAC",),
        model_labels=("rbac.Role", "rbac.Permission", "rbac.RoleAssignment"),
    ),
    DomainReportBlueprint(
        domain_key="audit",
        domain_code="AUDIT",
        family="AUDIT",
        truth_level="audit_control",
        source_types=("AUDIT_EVENTS",),
        sensitivity_level="high",
        contains_pii=True,
        reason_required=True,
        module_hints=("AUDIT",),
        model_labels=("audit.AuditEvent",),
    ),
    DomainReportBlueprint(
        domain_key="integration",
        domain_code="INTEGRATION",
        family="OBS",
        truth_level="observability",
        source_types=("DOMAIN_EVENTS", "AUDIT_EVENTS"),
        sensitivity_level="medium",
        contains_pii=False,
        reason_required=False,
        module_hints=("INTEGRATION",),
        model_labels=("integration.OutboxEvent", "integration.InboxEvent"),
    ),
    DomainReportBlueprint(
        domain_key="sync_engine",
        domain_code="SYNC_ENGINE",
        family="OBS",
        truth_level="observability",
        source_types=("SYNC_EVENTS", "METRICS"),
        sensitivity_level="medium",
        contains_pii=False,
        reason_required=False,
        module_hints=("SYNC_ENGINE", "SYNC"),
        model_labels=("sync_engine.SyncDevice", "sync_engine.SyncConflict"),
    ),
    DomainReportBlueprint(
        domain_key="sync",
        domain_code="SYNC",
        family="OBS",
        truth_level="observability",
        source_types=("SYNC_EVENTS", "METRICS"),
        sensitivity_level="medium",
        contains_pii=False,
        reason_required=False,
        module_hints=("SYNC",),
        model_labels=("sync.SyncBatch", "sync.SyncInboxDedup"),
    ),
    DomainReportBlueprint(
        domain_key="accounting",
        domain_code="ACCOUNTING",
        family="FIN",
        truth_level="certified_financial",
        source_types=("READ_MODELS", "AUDIT_EVENTS"),
        sensitivity_level="high",
        contains_pii=False,
        reason_required=False,
        module_hints=("ACCOUNTING",),
        model_labels=("accounting.JournalEntry", "accounting.JournalEntryLine", "accounting.FiscalPeriod"),
    ),
    DomainReportBlueprint(
        domain_key="payments",
        domain_code="PAYMENTS",
        family="CONTROL",
        truth_level="operational",
        source_types=("READ_MODELS", "AUDIT_EVENTS"),
        sensitivity_level="medium",
        contains_pii=False,
        reason_required=False,
        module_hints=("PAYMENTS",),
        model_labels=("payments.PaymentIntent", "payments.CashSession", "payments.CashMovement"),
    ),
    DomainReportBlueprint(
        domain_key="cec",
        domain_code="CEC",
        family="CONTROL",
        truth_level="audit_control",
        source_types=("READ_MODELS", "AUDIT_EVENTS"),
        sensitivity_level="medium",
        contains_pii=False,
        reason_required=False,
        module_hints=("CEC",),
        model_labels=("cec.CecCloseRun", "cec.CecException", "cec.CecEvidence"),
    ),
    DomainReportBlueprint(
        domain_key="reports",
        domain_code="REPORTS",
        family="CONTROL",
        truth_level="audit_control",
        source_types=("READ_MODELS", "METRICS"),
        sensitivity_level="medium",
        contains_pii=False,
        reason_required=False,
        module_hints=("REPORTS",),
        model_labels=("reports.ReportRun", "reports.ReportExport", "reports.ReportReadAudit"),
    ),
    DomainReportBlueprint(
        domain_key="auth_kernel",
        domain_code="AUTH_KERNEL",
        family="SEC",
        truth_level="audit_control",
        source_types=("READ_MODELS", "AUDIT_EVENTS"),
        sensitivity_level="high",
        contains_pii=True,
        reason_required=False,
        module_hints=("AUTH",),
        model_labels=("accounts.TwoFactorChallenge", "accounts.TwoFactorConfig"),
    ),
    DomainReportBlueprint(
        domain_key="facturacion",
        domain_code="FACTURACION",
        family="OPS",
        truth_level="operational",
        source_types=("READ_MODELS", "AUDIT_EVENTS"),
        sensitivity_level="medium",
        contains_pii=False,
        reason_required=False,
        module_hints=("BILLING", "FACTURACION"),
        model_labels=("facturacion.BillingDocument", "facturacion.BillingSequence", "facturacion.FiscalPrintJob"),
    ),
    DomainReportBlueprint(
        domain_key="inventarios",
        domain_code="INVENTARIOS",
        family="OPS",
        truth_level="operational",
        source_types=("READ_MODELS", "AUDIT_EVENTS"),
        sensitivity_level="medium",
        contains_pii=False,
        reason_required=False,
        module_hints=("INVENTORY", "INVENTARIOS"),
        model_labels=("inventarios.InventoryMovement", "inventarios.InventoryBalance", "inventarios.InventoryItem"),
    ),
    DomainReportBlueprint(
        domain_key="compras",
        domain_code="COMPRAS",
        family="OPS",
        truth_level="operational",
        source_types=("READ_MODELS", "AUDIT_EVENTS"),
        sensitivity_level="medium",
        contains_pii=False,
        reason_required=False,
        module_hints=("PROCUREMENT", "COMPRAS"),
        model_labels=("compras.PurchaseDocument",),
    ),
    DomainReportBlueprint(
        domain_key="estacion_servicios",
        domain_code="ESTACION_SERVICIOS",
        family="OPS",
        truth_level="operational",
        source_types=("READ_MODELS", "AUDIT_EVENTS"),
        sensitivity_level="medium",
        contains_pii=False,
        reason_required=False,
        module_hints=("FUEL", "ESTACION_SERVICIOS"),
        model_labels=("estacion_servicios.FuelShift", "estacion_servicios.FuelDispense", "estacion_servicios.FuelSale"),
    ),
)


def _safe_model_count(*, model_label: str, company_id: int, branch_id: int | None) -> int:
    try:
        model = apps.get_model(model_label)
    except Exception:
        return 0
    try:
        qs = model.objects.all()
        field_names = {field.name for field in model._meta.fields}
        if "company" in field_names:
            qs = qs.filter(company_id=company_id)
        elif "company_id" in field_names:
            qs = qs.filter(company_id=company_id)
        elif "partition_key" in field_names:
            qs = qs.filter(partition_key=f"COMPANY:{company_id}")
        if branch_id is not None:
            if "branch" in field_names:
                qs = qs.filter(branch_id=branch_id)
            elif "branch_id" in field_names:
                qs = qs.filter(branch_id=branch_id)
        return int(qs.order_by().count())
    except Exception:
        return 0


def _domain_entity_count(*, blueprint: DomainReportBlueprint, company_id: int, branch_id: int | None) -> int:
    return sum(_safe_model_count(model_label=label, company_id=company_id, branch_id=branch_id) for label in blueprint.model_labels)


def _domain_error_count(*, blueprint: DomainReportBlueprint, company_id: int, window_days: int) -> int:
    try:
        from apps.modulos.audit.models import AuditEvent
    except Exception:
        return 0
    qs = AuditEvent.objects.filter(
        partition_key=f"COMPANY:{company_id}",
        timestamp_server__gte=timezone.now() - timedelta(days=max(int(window_days), 1)),
    )
    if blueprint.module_hints:
        cond = Q()
        for hint in blueprint.module_hints:
            cond |= Q(module__icontains=str(hint))
        qs = qs.filter(cond)
    return int(qs.exclude(reason_code__in=["OK", "REPORTS_OK"]).order_by().count())


def _overview_runner_factory(blueprint: DomainReportBlueprint):
    def _runner(*, company_id: int, branch_id: int | None, parameters: dict[str, Any]) -> ReportResult:
        window_days = min(max(_to_int(parameters.get("window_days"), default=7), 1), 90)
        entity_count = int(_domain_entity_count(blueprint=blueprint, company_id=company_id, branch_id=branch_id))
        error_count = int(_domain_error_count(blueprint=blueprint, company_id=company_id, window_days=window_days))
        health_score = max(0, 100 - min(error_count * 5, 90))
        rows = [
            {
                "domain": blueprint.domain_key,
                "company_id": int(company_id),
                "branch_id": int(branch_id) if branch_id is not None else None,
                "entity_count": entity_count,
                "error_count": error_count,
                "health_score": health_score,
                "window_days": window_days,
                "as_of": timezone.now().isoformat(),
            }
        ]
        return ReportResult(
            schema_version=1,
            rows=rows,
            meta={
                "kind": f"DOMAIN_{blueprint.domain_code}_OVERVIEW",
                "source_manifest": {"modules": list(blueprint.module_hints), "source_types": list(blueprint.source_types)},
            },
            warnings=[],
        )

    return _runner


def _alerts_runner_factory(blueprint: DomainReportBlueprint):
    def _runner(*, company_id: int, branch_id: int | None, parameters: dict[str, Any]) -> ReportResult:
        window_days = min(max(_to_int(parameters.get("window_days"), default=7), 1), 90)
        entity_count = int(_domain_entity_count(blueprint=blueprint, company_id=company_id, branch_id=branch_id))
        error_count = int(_domain_error_count(blueprint=blueprint, company_id=company_id, window_days=window_days))
        critical_count = max(1, int(error_count * 0.35)) if error_count > 0 else 0
        warning_count = max(error_count - critical_count, 0)
        rows = []
        if warning_count > 0:
            rows.append(
                {
                    "domain": blueprint.domain_key,
                    "severity": "warning",
                    "alert_count": warning_count,
                    "critical_count": 0,
                    "entity_count": entity_count,
                    "window_days": window_days,
                }
            )
        if critical_count > 0:
            rows.append(
                {
                    "domain": blueprint.domain_key,
                    "severity": "critical",
                    "alert_count": critical_count,
                    "critical_count": critical_count,
                    "entity_count": entity_count,
                    "window_days": window_days,
                }
            )
        if not rows:
            rows.append(
                {
                    "domain": blueprint.domain_key,
                    "severity": "ok",
                    "alert_count": 0,
                    "critical_count": 0,
                    "entity_count": entity_count,
                    "window_days": window_days,
                }
            )
        return ReportResult(
            schema_version=1,
            rows=rows,
            meta={
                "kind": f"DOMAIN_{blueprint.domain_code}_ALERTS",
                "source_manifest": {"modules": list(blueprint.module_hints), "source_types": list(blueprint.source_types)},
            },
            warnings=[],
        )

    return _runner


def _register_domain_reports() -> None:
    for blueprint in DOMAIN_REPORT_BLUEPRINTS:
        overview_code = f"DOMAIN_{blueprint.domain_code}_OVERVIEW_V1"
        alerts_code = f"DOMAIN_{blueprint.domain_code}_ALERTS_V1"
        register(
            overview_code,
            family=blueprint.family,
            truth_level=blueprint.truth_level,
            source_types=list(blueprint.source_types),
            reproducibility_mode="LIVE",
            sensitivity_level=blueprint.sensitivity_level,
            contains_pii=blueprint.contains_pii,
            reason_required=blueprint.reason_required,
            export_formats=["json", "jsonl", "csv"],
            dataset_code=f"{blueprint.domain_key}.overview",
            dataset_version="v1",
            formula_version="v1",
        )(_overview_runner_factory(blueprint))
        register(
            alerts_code,
            family=blueprint.family,
            truth_level=blueprint.truth_level,
            source_types=list(blueprint.source_types),
            reproducibility_mode="LIVE",
            sensitivity_level=blueprint.sensitivity_level,
            contains_pii=blueprint.contains_pii,
            reason_required=blueprint.reason_required,
            export_formats=["json", "jsonl", "csv"],
            dataset_code=f"{blueprint.domain_key}.alerts",
            dataset_version="v1",
            formula_version="v1",
        )(_alerts_runner_factory(blueprint))


_register_domain_reports()
