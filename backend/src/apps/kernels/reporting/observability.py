from __future__ import annotations

from collections import defaultdict
from datetime import timedelta
from typing import Any

from django.conf import settings
from django.db.models import Count, Q
from django.utils import timezone

from .enums import MaterializationPolicy, RunStatus
from .models import ReportDatasetDefinition, ReportExportLog, ReportRun
from .registry import list_dataset_specs


def _percentile(values: list[int], p: float) -> float | None:
    if not values:
        return None
    ordered = sorted(values)
    if len(ordered) == 1:
        return float(ordered[0])
    k = (len(ordered) - 1) * p
    lower = int(k)
    upper = min(lower + 1, len(ordered) - 1)
    if lower == upper:
        return float(ordered[lower])
    weight = k - lower
    return float(ordered[lower] * (1.0 - weight) + ordered[upper] * weight)


def _policy_map() -> dict[str, str]:
    from_registry = {row.dataset_key: row.materialization_policy for row in list_dataset_specs()}
    from_db = {
        str(row["dataset_key"]): str(row["materialization_policy"])
        for row in ReportDatasetDefinition.objects.values("dataset_key", "materialization_policy")
    }
    out = dict(from_registry)
    out.update(from_db)
    return out


def _policy_latency_block(values: list[int]) -> dict[str, Any]:
    return {
        "count": int(len(values)),
        "p50_ms": _percentile(values, 0.50),
        "p95_ms": _percentile(values, 0.95),
        "max_ms": max(values) if values else None,
    }


def _thresholds() -> dict[str, float]:
    return {
        "snapshot_p95_max_ms": float(getattr(settings, "REPORTING_R8_GATE_SNAPSHOT_P95_MAX_MS", 800.0) or 800.0),
        "near_realtime_p95_max_ms": float(
            getattr(settings, "REPORTING_R8_GATE_NEAR_RT_P95_MAX_MS", 1500.0) or 1500.0
        ),
        "error_rate_max_pct": float(getattr(settings, "REPORTING_R8_GATE_ERROR_RATE_MAX_PCT", 0.5) or 0.5),
    }


def _latency_limit_for_policy(*, policy: str, thresholds: dict[str, float]) -> float:
    if policy == MaterializationPolicy.SNAPSHOT_REQUIRED:
        return float(thresholds["snapshot_p95_max_ms"])
    return float(thresholds["near_realtime_p95_max_ms"])


def build_reporting_observability(*, window_hours: int = 24) -> dict[str, Any]:
    hours = max(int(window_hours or 24), 1)
    since = timezone.now() - timedelta(hours=hours)
    runs = ReportRun.objects.filter(created_at__gte=since)

    total_runs = int(runs.count())
    succeeded_runs = int(runs.filter(status=RunStatus.SUCCEEDED).count())
    failed_runs = int(runs.filter(status=RunStatus.FAILED).count())
    error_rate_pct = round((failed_runs / total_runs * 100.0), 4) if total_runs else 0.0

    quality_counts = {
        "PASS": int(runs.filter(quality_status="PASS").count()),
        "WARN": int(runs.filter(quality_status="WARN").count()),
        "FAIL": int(runs.filter(quality_status="FAIL").count()),
    }

    by_policy: dict[str, list[int]] = defaultdict(list)
    near_realtime_cache: list[int] = []
    policy_map = _policy_map()
    thresholds = _thresholds()

    dataset_stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "runs": 0,
            "failed_runs": 0,
            "quality_fail_runs": 0,
            "duration_values": [],
        }
    )
    failure_class_counts: dict[str, int] = {
        "none": 0,
        "quality_breach": 0,
        "latency_regression": 0,
        "app_error": 0,
        "infra_error": 0,
    }

    for run_row in runs.values("dataset_key", "status", "quality_status", "duration_ms"):
        dataset_key = str(run_row["dataset_key"] or "")
        status = str(run_row["status"] or "")
        quality_status = str(run_row["quality_status"] or "")
        duration_ms = int(run_row["duration_ms"] or 0)
        policy = str(policy_map.get(dataset_key) or MaterializationPolicy.LIVE_ONLY)

        ds = dataset_stats[dataset_key]
        ds["runs"] += 1
        run_failure_class = "none"
        if status == RunStatus.FAILED:
            ds["failed_runs"] += 1
            run_failure_class = "app_error"
        if quality_status == "FAIL":
            ds["quality_fail_runs"] += 1

        if status != RunStatus.SUCCEEDED:
            if run_failure_class == "none" and quality_status == "FAIL":
                run_failure_class = "quality_breach"
            failure_class_counts[run_failure_class] += 1
            continue
        if duration_ms <= 0:
            if run_failure_class == "none" and quality_status == "FAIL":
                run_failure_class = "quality_breach"
            failure_class_counts[run_failure_class] += 1
            continue

        ds["duration_values"].append(duration_ms)
        by_policy[policy].append(duration_ms)
        if policy in {MaterializationPolicy.CACHE_ALLOWED, MaterializationPolicy.LIVE_ONLY}:
            near_realtime_cache.append(duration_ms)
        latency_limit = _latency_limit_for_policy(policy=policy, thresholds=thresholds)
        if duration_ms > latency_limit and run_failure_class == "none":
            run_failure_class = "latency_regression"
        if quality_status == "FAIL" and run_failure_class == "none":
            run_failure_class = "quality_breach"
        failure_class_counts[run_failure_class] += 1

    dataset_slo: list[dict[str, Any]] = []
    for dataset_key, ds_stats in dataset_stats.items():
        runs_count = int(ds_stats["runs"] or 0)
        failed_count = int(ds_stats["failed_runs"] or 0)
        quality_fail_count = int(ds_stats["quality_fail_runs"] or 0)
        duration_values = [int(v) for v in list(ds_stats["duration_values"] or []) if int(v) > 0]
        policy = str(policy_map.get(dataset_key) or MaterializationPolicy.LIVE_ONLY)
        dataset_slo.append(
            {
                "dataset_key": dataset_key,
                "policy": policy,
                "runs": runs_count,
                "failed_runs": failed_count,
                "quality_fail_runs": quality_fail_count,
                "error_rate_pct": round((failed_count / runs_count * 100.0), 4) if runs_count else 0.0,
                "p95_ms": _percentile(duration_values, 0.95),
            }
        )
    dataset_slo.sort(key=lambda row: (-int(row["runs"]), str(row["dataset_key"])))

    top_datasets = list(
        runs.values("dataset_key")
        .annotate(
            total=Count("id"),
            failed=Count("id", filter=Q(status=RunStatus.FAILED)),
            quality_fail=Count("id", filter=Q(quality_status="FAIL")),
        )
        .order_by("-total", "dataset_key")[:10]
    )

    exports = list(
        ReportExportLog.objects.filter(created_at__gte=since)
        .values("format")
        .annotate(total=Count("id"))
        .order_by("-total", "format")
    )

    top_consumers = list(
        runs.exclude(consumer_ref="").values("consumer_ref")
        .annotate(total=Count("id"))
        .order_by("-total", "consumer_ref")[:10]
    )
    runs_by_consumer_type = list(
        runs.values("consumer_type")
        .annotate(total=Count("id"))
        .order_by("-total", "consumer_type")
    )

    legacy_accounting_runs = int(runs.filter(consumer_ref__startswith="legacy:/api/accounting/reports/").count())

    return {
        "window_hours": hours,
        "runs_total": total_runs,
        "runs_succeeded": succeeded_runs,
        "runs_failed": failed_runs,
        "error_rate_pct": error_rate_pct,
        "quality_status_counts": quality_counts,
        "failure_classes_last_window": failure_class_counts,
        "latency_ms_by_policy": {
            MaterializationPolicy.SNAPSHOT_REQUIRED: _policy_latency_block(by_policy[MaterializationPolicy.SNAPSHOT_REQUIRED]),
            MaterializationPolicy.CACHE_ALLOWED: _policy_latency_block(by_policy[MaterializationPolicy.CACHE_ALLOWED]),
            MaterializationPolicy.LIVE_ONLY: _policy_latency_block(by_policy[MaterializationPolicy.LIVE_ONLY]),
            "near_realtime_cache": _policy_latency_block(near_realtime_cache),
        },
        "runs_by_consumer_type": [
            {"consumer_type": str(row["consumer_type"]), "runs": int(row["total"] or 0)}
            for row in runs_by_consumer_type
        ],
        "top_consumers": [
            {"consumer_ref": str(row["consumer_ref"] or ""), "runs": int(row["total"] or 0)}
            for row in top_consumers
        ],
        "dataset_slo": dataset_slo[:15],
        "top_datasets": [
            {
                "dataset_key": str(row["dataset_key"]),
                "runs": int(row["total"] or 0),
                "failed_runs": int(row["failed"] or 0),
                "quality_fail_runs": int(row["quality_fail"] or 0),
            }
            for row in top_datasets
        ],
        "exports_by_format": [
            {"format": str(row["format"]), "count": int(row["total"] or 0)}
            for row in exports
        ],
        "legacy_accounting_report_runs": legacy_accounting_runs,
    }
