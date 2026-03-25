from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from apps.kernels.reporting.observability import build_reporting_observability


def _parse_date(raw: str, *, field_name: str) -> date:
    try:
        return date.fromisoformat(str(raw).strip())
    except Exception as exc:
        raise ValueError(f"{field_name} inválido (esperado YYYY-MM-DD): {raw}") from exc


@dataclass
class GateSummary:
    generated_at: str
    mode: str
    gate_status: str
    window_hours: int
    warn_until: str
    hard_fail_from: str
    thresholds: dict[str, Any]
    metrics: dict[str, Any]
    failure_class: str
    trigger_metric: str
    breaches: list[dict[str, Any]]
    reasons: list[str]


_CLASS_PRIORITY = ("infra_error", "app_error", "latency_regression", "quality_breach")
_ALLOWED_FAILURE_CLASSES = {"none", "quality_breach", "latency_regression", "app_error", "infra_error"}


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float))


def _policy_threshold(*, policy: str, snapshot_limit: float, near_rt_limit: float) -> float:
    if str(policy) == "SNAPSHOT_REQUIRED":
        return float(snapshot_limit)
    return float(near_rt_limit)


def _trigger_metric_for(breach: dict[str, Any]) -> str:
    dataset_key = str(breach.get("dataset_key") or "").strip()
    policy = str(breach.get("policy") or "").strip()
    metric = str(breach.get("metric") or "").strip() or "unknown_metric"
    if dataset_key:
        return f"{dataset_key}.{metric}"
    if policy:
        return f"{policy}.{metric}"
    return metric


def _select_failure_class(breaches: list[dict[str, Any]]) -> str:
    seen = {str(row.get("failure_class") or "").strip() for row in breaches}
    for cls in _CLASS_PRIORITY:
        if cls in seen:
            return cls
    return "none"


def _to_reasons(breaches: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for breach in breaches:
        failure_class = str(breach.get("failure_class") or "unknown")
        metric = str(breach.get("metric") or "unknown_metric")
        actual = breach.get("actual")
        threshold = breach.get("threshold")
        dataset_key = str(breach.get("dataset_key") or "").strip()
        prefix = f"{dataset_key}." if dataset_key else ""
        out.append(f"{failure_class}:{prefix}{metric} actual={actual} threshold={threshold}")
    return out


class Command(BaseCommand):
    help = "Evalúa gate R8 de calidad+SLO sobre runs de reporting (WARN→FAIL)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--window-hours",
            type=int,
            default=int(getattr(settings, "REPORTING_R8_GATE_WINDOW_HOURS", 24) or 24),
        )
        parser.add_argument(
            "--warn-until",
            type=str,
            default=str(getattr(settings, "REPORTING_R8_GATE_WARN_UNTIL", "2026-04-07")),
        )
        parser.add_argument(
            "--hard-fail-from",
            type=str,
            default=str(getattr(settings, "REPORTING_R8_GATE_HARD_FAIL_FROM", "2026-04-08")),
        )
        parser.add_argument("--snapshot-p95-max-ms", type=float, default=800.0)
        parser.add_argument("--near-realtime-p95-max-ms", type=float, default=1500.0)
        parser.add_argument("--error-rate-max-pct", type=float, default=0.5)
        parser.add_argument("--today", type=str, default="", help="Override de fecha para pruebas (YYYY-MM-DD).")
        parser.add_argument("--output", type=str, default="", help="Ruta JSON de salida (opcional).")

    def handle(self, *args, **options):
        window_hours = max(int(options["window_hours"]), 1)
        warn_until = _parse_date(options["warn_until"], field_name="warn_until")
        hard_fail_from = _parse_date(options["hard_fail_from"], field_name="hard_fail_from")
        today_raw = str(options.get("today") or "").strip()
        today = _parse_date(today_raw, field_name="today") if today_raw else timezone.localdate()
        mode = "HARD_FAIL" if today >= hard_fail_from else "WARN"

        report_error: str = ""
        try:
            report = build_reporting_observability(window_hours=window_hours)
        except Exception as exc:  # pragma: no cover - exercised via command-level tests
            report_error = f"{exc.__class__.__name__}: {exc}"
            report = {
                "runs_total": 0,
                "runs_failed": 0,
                "error_rate_pct": 0.0,
                "quality_status_counts": {"PASS": 0, "WARN": 0, "FAIL": 0},
                "latency_ms_by_policy": {
                    "SNAPSHOT_REQUIRED": {"p95_ms": None},
                    "near_realtime_cache": {"p95_ms": None},
                },
                "dataset_slo": [],
            }

        quality_fail = int((report.get("quality_status_counts") or {}).get("FAIL") or 0)
        snapshot_p95 = (report.get("latency_ms_by_policy") or {}).get("SNAPSHOT_REQUIRED", {}).get("p95_ms")
        snapshot_limit = float(options["snapshot_p95_max_ms"])
        near_rt_p95 = (report.get("latency_ms_by_policy") or {}).get("near_realtime_cache", {}).get("p95_ms")
        near_rt_limit = float(options["near_realtime_p95_max_ms"])
        error_rate_pct = float(report.get("error_rate_pct") or 0.0)
        runs_failed = int(report.get("runs_failed") or 0)
        error_limit = float(options["error_rate_max_pct"])

        breaches: list[dict[str, Any]] = []
        dataset_slo_rows = list(report.get("dataset_slo") or [])
        if report_error:
            breaches.append(
                {
                    "failure_class": "infra_error",
                    "metric": "observability.build_error",
                    "actual": report_error,
                    "threshold": "none",
                    "dataset_key": "",
                    "policy": "",
                }
            )

        if quality_fail > 0:
            found_dataset_quality = False
            for row in dataset_slo_rows:
                quality_fail_runs = int(row.get("quality_fail_runs") or 0)
                if quality_fail_runs <= 0:
                    continue
                found_dataset_quality = True
                breaches.append(
                    {
                        "failure_class": "quality_breach",
                        "metric": "quality_fail_runs",
                        "actual": quality_fail_runs,
                        "threshold": 0,
                        "dataset_key": str(row.get("dataset_key") or ""),
                        "policy": str(row.get("policy") or ""),
                    }
                )
            if not found_dataset_quality:
                breaches.append(
                    {
                        "failure_class": "quality_breach",
                        "metric": "quality_fail_runs",
                        "actual": quality_fail,
                        "threshold": 0,
                        "dataset_key": "",
                        "policy": "",
                    }
                )

        if _is_number(snapshot_p95) and float(snapshot_p95) > snapshot_limit:
            breaches.append(
                {
                    "failure_class": "latency_regression",
                    "metric": "snapshot_p95_ms",
                    "actual": float(snapshot_p95),
                    "threshold": snapshot_limit,
                    "dataset_key": "",
                    "policy": "SNAPSHOT_REQUIRED",
                }
            )
        if _is_number(near_rt_p95) and float(near_rt_p95) > near_rt_limit:
            breaches.append(
                {
                    "failure_class": "latency_regression",
                    "metric": "near_realtime_cache_p95_ms",
                    "actual": float(near_rt_p95),
                    "threshold": near_rt_limit,
                    "dataset_key": "",
                    "policy": "near_realtime_cache",
                }
            )

        for row in dataset_slo_rows:
            p95 = row.get("p95_ms")
            if not _is_number(p95):
                continue
            policy = str(row.get("policy") or "")
            threshold = _policy_threshold(policy=policy, snapshot_limit=snapshot_limit, near_rt_limit=near_rt_limit)
            if float(p95) > threshold:
                breaches.append(
                    {
                        "failure_class": "latency_regression",
                        "metric": "p95_ms",
                        "actual": float(p95),
                        "threshold": float(threshold),
                        "dataset_key": str(row.get("dataset_key") or ""),
                        "policy": policy,
                    }
                )

        if runs_failed > 0:
            breaches.append(
                {
                    "failure_class": "app_error",
                    "metric": "runs_failed",
                    "actual": runs_failed,
                    "threshold": 0,
                    "dataset_key": "",
                    "policy": "",
                }
            )
        if error_rate_pct > error_limit:
            breaches.append(
                {
                    "failure_class": "app_error",
                    "metric": "error_rate_pct",
                    "actual": error_rate_pct,
                    "threshold": error_limit,
                    "dataset_key": "",
                    "policy": "",
                }
            )
        for row in dataset_slo_rows:
            failed_runs = int(row.get("failed_runs") or 0)
            if failed_runs <= 0:
                continue
            breaches.append(
                {
                    "failure_class": "app_error",
                    "metric": "failed_runs",
                    "actual": failed_runs,
                    "threshold": 0,
                    "dataset_key": str(row.get("dataset_key") or ""),
                    "policy": str(row.get("policy") or ""),
                }
            )

        failure_class = _select_failure_class(breaches)
        trigger_metric = ""
        if failure_class != "none":
            class_breaches = [row for row in breaches if str(row.get("failure_class")) == failure_class]
            if class_breaches:
                trigger_metric = _trigger_metric_for(class_breaches[0])

        if failure_class == "none":
            gate_status = "PASS"
            exit_code = 0
        else:
            gate_status = "WARN" if mode == "WARN" else "FAIL"
            exit_code = 0 if mode == "WARN" else 2

        reasons = _to_reasons(breaches)
        if failure_class not in _ALLOWED_FAILURE_CLASSES:
            invalid_failure_class = failure_class
            failure_class = "infra_error"
            trigger_metric = "observability.failure_class_invalid"
            gate_status = "WARN" if mode == "WARN" else "FAIL"
            exit_code = 0 if mode == "WARN" else 2
            breaches.append(
                {
                    "failure_class": "infra_error",
                    "metric": "observability.failure_class_invalid",
                    "actual": str(invalid_failure_class),
                    "threshold": "allowed_failure_class",
                    "dataset_key": "",
                    "policy": "",
                }
            )
            reasons = _to_reasons(breaches)

        summary = GateSummary(
            generated_at=timezone.now().isoformat(),
            mode=mode,
            gate_status=gate_status,
            window_hours=window_hours,
            warn_until=warn_until.isoformat(),
            hard_fail_from=hard_fail_from.isoformat(),
            thresholds={
                "snapshot_p95_max_ms": snapshot_limit,
                "near_realtime_p95_max_ms": near_rt_limit,
                "error_rate_max_pct": error_limit,
            },
            metrics={
                "runs_total": report.get("runs_total"),
                "runs_failed": report.get("runs_failed"),
                "error_rate_pct": report.get("error_rate_pct"),
                "quality_status_counts": report.get("quality_status_counts"),
                "snapshot_p95_ms": snapshot_p95,
                "near_realtime_cache_p95_ms": near_rt_p95,
            },
            failure_class=failure_class,
            trigger_metric=trigger_metric,
            breaches=breaches,
            reasons=reasons,
        )
        payload = asdict(summary)
        output = str(options.get("output") or "").strip()
        if output:
            path = Path(output)
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            self.stdout.write(self.style.SUCCESS(f"reporting_r8_gate summary -> {path}"))
        else:
            self.stdout.write(json.dumps(payload, ensure_ascii=False, indent=2))

        if exit_code != 0:
            raise SystemExit(exit_code)
