from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.modulos.iam.models import OrgUnit


class ReportDefinition(models.Model):
    class ReportFamily(models.TextChoices):
        TRACE = "TRACE"
        AUDIT = "AUDIT"
        OPS = "OPS"
        OBS = "OBS"
        CONTROL = "CONTROL"
        FIN = "FIN"
        SEC = "SEC"

    class TruthLevel(models.TextChoices):
        OPERATIONAL = "operational"
        AUDIT_CONTROL = "audit_control"
        OBSERVABILITY = "observability"
        CERTIFIED_FINANCIAL = "certified_financial"

    class ReproducibilityMode(models.TextChoices):
        LIVE = "LIVE"
        SNAPSHOT = "SNAPSHOT"
        CERTIFIED = "CERTIFIED"

    class SensitivityLevel(models.TextChoices):
        LOW = "low"
        MEDIUM = "medium"
        HIGH = "high"
        RESTRICTED = "restricted"

    class DefinitionStatus(models.TextChoices):
        ACTIVE = "ACTIVE"
        DEPRECATED = "DEPRECATED"
        DISABLED = "DISABLED"

    class CertificationStatus(models.TextChoices):
        DRAFT = "DRAFT"
        CERTIFIED = "CERTIFIED"
        DEPRECATED = "DEPRECATED"
        RETIRED = "RETIRED"

    class ScopeLevel(models.TextChoices):
        COMPANY = "COMPANY"
        BRANCH = "BRANCH"
        INTERCOMPANY = "INTERCOMPANY"

    class FreshnessMode(models.TextChoices):
        LIVE = "live"
        NEAR_REAL_TIME = "near_real_time"
        SNAPSHOT = "snapshot"

    class MaterializationPolicy(models.TextChoices):
        LIVE_ONLY = "live_only"
        CACHE_FIRST = "cache_first"
        SNAPSHOT_REQUIRED = "snapshot_required"

    """
    Contrato:
    - code es estable y es el identificador público (no se recicla).
    - schema_version permite evolucionar parámetros/shape sin romper histórico.
    - is_active controla disponibilidad operativa sin borrar.
    """

    report_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    company = models.ForeignKey(OrgUnit, on_delete=models.CASCADE, related_name="report_definitions")
    # Código público (permite namespace con puntos): `reports.ping.v1`
    code = models.CharField(max_length=64)
    report_family = models.CharField(max_length=16, choices=ReportFamily.choices, default=ReportFamily.TRACE)
    name = models.CharField(max_length=160, default="")
    description = models.CharField(max_length=500, default="", blank=True)
    owner_domain = models.CharField(max_length=64, default="REPORTS")
    status = models.CharField(max_length=16, choices=DefinitionStatus.choices, default=DefinitionStatus.ACTIVE)
    truth_level = models.CharField(max_length=32, choices=TruthLevel.choices, default=TruthLevel.OPERATIONAL)
    source_types = models.JSONField(default=list, blank=True)
    input_contracts = models.JSONField(default=list, blank=True)
    filter_contract = models.JSONField(default=dict, blank=True)
    output_schema = models.JSONField(default=dict, blank=True)
    freshness_class = models.CharField(max_length=32, default="live")
    freshness_mode = models.CharField(max_length=24, choices=FreshnessMode.choices, default=FreshnessMode.LIVE)
    materialization_policy = models.CharField(
        max_length=24,
        choices=MaterializationPolicy.choices,
        default=MaterializationPolicy.CACHE_FIRST,
    )
    scope_level = models.CharField(max_length=16, choices=ScopeLevel.choices, default=ScopeLevel.BRANCH)
    reproducibility_mode = models.CharField(
        max_length=16,
        choices=ReproducibilityMode.choices,
        default=ReproducibilityMode.LIVE,
    )
    export_policy = models.JSONField(default=dict, blank=True)
    retention_policy = models.CharField(max_length=32, default="short_term")
    classification = models.CharField(max_length=32, default="internal")
    sensitivity_level = models.CharField(max_length=16, choices=SensitivityLevel.choices, default=SensitivityLevel.MEDIUM)
    contains_pii = models.BooleanField(default=False)
    reason_required = models.BooleanField(default=False)
    supports_async_snapshot = models.BooleanField(default=False)
    supports_future_modules = models.BooleanField(default=True)
    allow_intercompany = models.BooleanField(default=False)
    max_window_days = models.PositiveIntegerField(default=31)
    max_rows = models.PositiveIntegerField(default=5000)
    max_pending_jobs = models.PositiveIntegerField(default=20)
    dataset_version = models.CharField(max_length=64, default="", blank=True)
    formula_version = models.CharField(max_length=64, default="", blank=True)
    semantic_version = models.CharField(max_length=32, default="1.0.0")
    dataset_key = models.CharField(max_length=128, default="", blank=True)
    domain_owner = models.CharField(max_length=64, default="REPORTS")
    certification_status = models.CharField(
        max_length=16,
        choices=CertificationStatus.choices,
        default=CertificationStatus.CERTIFIED,
    )
    required_permissions = models.JSONField(default=list, blank=True)
    export_capabilities = models.JSONField(default=dict, blank=True)
    semantic_metric_keys = models.JSONField(default=list, blank=True)
    version = models.CharField(max_length=32, default="1.0.0")
    schema_version = models.PositiveIntegerField(default=1)
    contract_version = models.PositiveIntegerField(default=1)
    is_active = models.BooleanField(default=True)
    deprecated_at = models.DateTimeField(null=True, blank=True)
    replacement_report_code = models.CharField(max_length=64, default="", blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "code"], name="uniq_report_def_per_company"),
        ]
        indexes = [
            models.Index(fields=["company", "code"], name="ix_report_def_code"),
        ]

    def __str__(self) -> str:
        return f"{self.company_id}:{self.code}"


class ReportRun(models.Model):
    class TruthLevel(models.TextChoices):
        OPERATIONAL = "operational"
        AUDIT_CONTROL = "audit_control"
        OBSERVABILITY = "observability"
        CERTIFIED_FINANCIAL = "certified_financial"

    class ReproducibilityMode(models.TextChoices):
        LIVE = "LIVE"
        SNAPSHOT = "SNAPSHOT"
        CERTIFIED = "CERTIFIED"

    class SensitivityLevel(models.TextChoices):
        LOW = "low"
        MEDIUM = "medium"
        HIGH = "high"
        RESTRICTED = "restricted"

    class Status(models.TextChoices):
        QUEUED = "QUEUED"
        RUNNING = "RUNNING"
        SUCCEEDED = "SUCCEEDED"
        FAILED = "FAILED"
        CANCELED = "CANCELED"

    run_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    company = models.ForeignKey(OrgUnit, on_delete=models.CASCADE, related_name="report_runs")
    branch_id = models.IntegerField(null=True, blank=True)
    definition = models.ForeignKey(ReportDefinition, on_delete=models.PROTECT, related_name="runs")
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="report_runs"
    )
    status = models.CharField(max_length=16, choices=Status.choices, default=Status.RUNNING)
    request_id = models.CharField(max_length=64, default="", blank=True)
    report_version = models.CharField(max_length=32, default="1.0.0")
    truth_level = models.CharField(max_length=32, choices=TruthLevel.choices, default=TruthLevel.OPERATIONAL)
    reproducibility_mode = models.CharField(
        max_length=16,
        choices=ReproducibilityMode.choices,
        default=ReproducibilityMode.LIVE,
    )
    source_types = models.JSONField(default=list, blank=True)
    effective_scope = models.JSONField(default=dict, blank=True)
    params_hash = models.CharField(max_length=64, default="", blank=True)
    as_of = models.DateTimeField(null=True, blank=True)
    time_window = models.JSONField(default=dict, blank=True)
    source_manifest = models.JSONField(default=dict, blank=True)
    source_manifest_hash = models.CharField(max_length=64, default="", blank=True)
    output_manifest_hash = models.CharField(max_length=64, default="", blank=True)
    dataset_version = models.CharField(max_length=64, default="", blank=True)
    formula_version = models.CharField(max_length=64, default="", blank=True)
    freshness = models.JSONField(default=dict, blank=True)
    lineage = models.JSONField(default=dict, blank=True)
    warnings = models.JSONField(default=list, blank=True)
    duration_ms = models.PositiveIntegerField(default=0)
    row_count = models.PositiveIntegerField(default=0)
    classification = models.CharField(max_length=32, default="internal")
    sensitivity_level = models.CharField(max_length=16, choices=SensitivityLevel.choices, default=SensitivityLevel.MEDIUM)
    is_async = models.BooleanField(default=False)
    priority = models.PositiveIntegerField(default=5)
    dedupe_key = models.CharField(max_length=96, default="", blank=True)
    queue_name = models.CharField(max_length=32, default="default")
    parameters = models.JSONField(default=dict, blank=True)
    result = models.JSONField(default=dict, blank=True)
    error_code = models.CharField(max_length=64, default="", blank=True)
    error_envelope = models.JSONField(default=dict, blank=True)
    error = models.CharField(max_length=500, default="", blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["company", "started_at", "id"], name="ix_report_run_time"),
            models.Index(fields=["company", "definition", "started_at"], name="ix_report_run_def_time"),
            models.Index(fields=["company", "status", "priority", "started_at"], name="ix_report_run_queue"),
            models.Index(fields=["company", "dedupe_key"], name="ix_report_run_dedupe"),
        ]

    def __str__(self) -> str:
        return f"{self.company_id}:{self.definition_id}:{self.run_id}"

    @property
    def execution_id(self):
        return self.run_id


class ReportExport(models.Model):
    class ExportStatus(models.TextChoices):
        PENDING = "PENDING"
        READY = "READY"
        FAILED = "FAILED"
        BLOCKED = "BLOCKED"
        PENDING_APPROVAL = "PENDING_APPROVAL"

    export_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    company = models.ForeignKey(OrgUnit, on_delete=models.CASCADE, related_name="report_exports")
    execution = models.ForeignKey(ReportRun, on_delete=models.CASCADE, related_name="exports")
    format = models.CharField(max_length=16, default="json")
    status = models.CharField(max_length=24, choices=ExportStatus.choices, default=ExportStatus.PENDING)
    template_version = models.CharField(max_length=32, default="v1")
    watermark_text = models.CharField(max_length=300, default="", blank=True)
    requested_reason = models.CharField(max_length=300, default="", blank=True)
    exported_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="report_exports_created",
    )
    approved_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="report_exports_approved",
    )
    download_scope = models.JSONField(default=dict, blank=True)
    retention_until = models.DateTimeField(null=True, blank=True)
    audit_event_ref = models.CharField(max_length=64, default="", blank=True)
    storage_ref = models.CharField(max_length=300, default="", blank=True)
    content = models.JSONField(default=dict, blank=True)
    content_hash = models.CharField(max_length=64, default="", blank=True)
    error = models.CharField(max_length=500, default="", blank=True)
    requested_at = models.DateTimeField(auto_now_add=True)
    exported_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["company", "status", "requested_at"], name="ix_report_export_queue"),
        ]


class ReportReadAudit(models.Model):
    class Action(models.TextChoices):
        READ = "READ"
        EXPORT = "EXPORT"

    read_audit_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    company = models.ForeignKey(OrgUnit, on_delete=models.CASCADE, related_name="report_read_audits")
    branch_id = models.IntegerField(null=True, blank=True)
    actor_user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="report_read_audits",
    )
    action = models.CharField(max_length=16, choices=Action.choices, default=Action.READ)
    report_code = models.CharField(max_length=64)
    execution = models.ForeignKey(ReportRun, null=True, blank=True, on_delete=models.SET_NULL, related_name="read_audits")
    scope = models.JSONField(default=dict, blank=True)
    sensitivity_level = models.CharField(
        max_length=16, choices=ReportDefinition.SensitivityLevel.choices, default=ReportDefinition.SensitivityLevel.MEDIUM
    )
    reason = models.CharField(max_length=300, default="", blank=True)
    request_id = models.CharField(max_length=64, default="", blank=True)
    ip_server_seen = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(default="", blank=True)
    occurred_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [
            models.Index(fields=["company", "occurred_at"], name="ix_report_read_audit_time"),
            models.Index(fields=["company", "report_code", "occurred_at"], name="ix_report_read_audit_report"),
        ]


class SourceRegistry(models.Model):
    class SourceType(models.TextChoices):
        DOMAIN_EVENTS = "DOMAIN_EVENTS"
        AUDIT_EVENTS = "AUDIT_EVENTS"
        SYSTEM_LOGS = "SYSTEM_LOGS"
        METRICS = "METRICS"
        SYNC_EVENTS = "SYNC_EVENTS"
        SECURITY_EVENTS = "SECURITY_EVENTS"
        CERTIFIED_SNAPSHOTS = "CERTIFIED_SNAPSHOTS"
        READ_MODELS = "READ_MODELS"

    class SourceStatus(models.TextChoices):
        ACTIVE = "ACTIVE"
        DEPRECATED = "DEPRECATED"
        DISABLED = "DISABLED"

    source_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    company = models.ForeignKey(OrgUnit, null=True, blank=True, on_delete=models.CASCADE, related_name="report_sources")
    source_code = models.CharField(max_length=64)
    source_type = models.CharField(max_length=32, choices=SourceType.choices)
    producer_module = models.CharField(max_length=64)
    contract_version = models.CharField(max_length=32, default="1.0.0")
    schema_version = models.PositiveIntegerField(default=1)
    truth_level = models.CharField(
        max_length=32,
        choices=ReportDefinition.TruthLevel.choices,
        default=ReportDefinition.TruthLevel.OPERATIONAL,
    )
    supports_scope = models.BooleanField(default=True)
    supports_request_id = models.BooleanField(default=True)
    supports_correlation = models.BooleanField(default=False)
    supports_replay = models.BooleanField(default=False)
    scope_fields = models.JSONField(default=list, blank=True)
    correlation_fields = models.JSONField(default=list, blank=True)
    event_types = models.JSONField(default=list, blank=True)
    pii_policy = models.CharField(max_length=32, default="none")
    retention_policy = models.CharField(max_length=32, default="short_term")
    status = models.CharField(max_length=16, choices=SourceStatus.choices, default=SourceStatus.ACTIVE)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "source_code"], name="uniq_report_source_per_company"),
        ]
        indexes = [
            models.Index(fields=["source_type", "status"], name="ix_report_source_type"),
        ]


class DatasetVersion(models.Model):
    dataset_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    company = models.ForeignKey(OrgUnit, on_delete=models.CASCADE, related_name="report_dataset_versions")
    dataset_code = models.CharField(max_length=64)
    dataset_version = models.CharField(max_length=32)
    source_registry_refs = models.JSONField(default=list, blank=True)
    shape_contract = models.JSONField(default=dict, blank=True)
    join_contract = models.JSONField(default=dict, blank=True)
    privacy_contract = models.JSONField(default=dict, blank=True)
    quality_contract = models.JSONField(default=dict, blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "dataset_code", "dataset_version"], name="uniq_dataset_version_per_company"),
        ]


class ReportMetricDefinition(models.Model):
    class MetricStatus(models.TextChoices):
        ACTIVE = "ACTIVE"
        DEPRECATED = "DEPRECATED"
        RETIRED = "RETIRED"

    metric_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    company = models.ForeignKey(OrgUnit, on_delete=models.CASCADE, related_name="report_metric_definitions")
    metric_key = models.CharField(max_length=128)
    name = models.CharField(max_length=160)
    description = models.CharField(max_length=500, default="", blank=True)
    domain_owner = models.CharField(max_length=64, default="REPORTS")
    dataset_key = models.CharField(max_length=128, default="", blank=True)
    expression = models.TextField(default="", blank=True)
    expression_hash = models.CharField(max_length=64, default="", blank=True)
    unit = models.CharField(max_length=24, default="", blank=True)
    semantic_version = models.CharField(max_length=32, default="1.0.0")
    formula_version = models.CharField(max_length=64, default="", blank=True)
    status = models.CharField(max_length=16, choices=MetricStatus.choices, default=MetricStatus.ACTIVE)
    is_certified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["company", "metric_key"], name="uniq_report_metric_per_company"),
        ]
        indexes = [
            models.Index(fields=["company", "domain_owner"], name="ix_report_metric_domain"),
            models.Index(fields=["company", "dataset_key"], name="ix_report_metric_dataset"),
        ]


class DatasetCache(models.Model):
    cache_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    company = models.ForeignKey(OrgUnit, on_delete=models.CASCADE, related_name="report_dataset_cache")
    dataset_code = models.CharField(max_length=64)
    dataset_version = models.CharField(max_length=32)
    scope_hash = models.CharField(max_length=64)
    params_hash = models.CharField(max_length=64)
    source_manifest_hash = models.CharField(max_length=64, default="", blank=True)
    payload = models.JSONField(default=dict, blank=True)
    expires_at = models.DateTimeField(default=timezone.now)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["company", "dataset_code", "dataset_version", "scope_hash", "params_hash"],
                name="uniq_dataset_cache_key",
            ),
        ]
        indexes = [
            models.Index(fields=["company", "dataset_code", "expires_at"], name="ix_dataset_cache_exp"),
        ]


class ReproducibilityLedger(models.Model):
    class VerificationStatus(models.TextChoices):
        VERIFIED = "VERIFIED"
        MISMATCH = "MISMATCH"
        PENDING = "PENDING"

    ledger_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    company = models.ForeignKey(OrgUnit, on_delete=models.CASCADE, related_name="report_repro_ledger")
    execution = models.OneToOneField(ReportRun, on_delete=models.CASCADE, related_name="reproducibility_ledger")
    report_code = models.CharField(max_length=64)
    report_version = models.CharField(max_length=32)
    formula_version = models.CharField(max_length=64, default="", blank=True)
    dataset_version = models.CharField(max_length=64, default="", blank=True)
    effective_scope = models.JSONField(default=dict, blank=True)
    as_of = models.DateTimeField(null=True, blank=True)
    time_window = models.JSONField(default=dict, blank=True)
    input_manifest_hash = models.CharField(max_length=64)
    output_manifest_hash = models.CharField(max_length=64)
    signature = models.CharField(max_length=128, default="", blank=True)
    verification_status = models.CharField(max_length=16, choices=VerificationStatus.choices, default=VerificationStatus.PENDING)
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="report_repro_ledger_generated",
    )
    generated_at = models.DateTimeField(auto_now_add=True)
