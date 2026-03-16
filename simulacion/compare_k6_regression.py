#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


DEFAULT_METRICS = [
    ("billing_write_ms", "p(95)"),
    ("inventory_write_ms", "p(95)"),
    ("posting_cycle_ms", "p(95)"),
    ("operational_error_rate", "value"),
]


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _get_metric_value(summary: dict[str, Any], metric_name: str, stat: str) -> float | None:
    metrics = summary.get("metrics")
    if not isinstance(metrics, dict):
        return None
    metric = metrics.get(metric_name)
    if not isinstance(metric, dict):
        return None
    raw = metric.get(stat)
    if raw is None:
        metric_values = metric.get("values")
        if isinstance(metric_values, dict):
            raw = metric_values.get(stat)
    if raw is None:
        return None
    try:
        return float(raw)
    except Exception:
        return None


def _parse_metric_spec(spec: str) -> tuple[str, str]:
    if ":" not in spec:
        raise ValueError(f"Metric spec invalida (esperado metric:stat): {spec}")
    name, stat = spec.split(":", 1)
    name = name.strip()
    stat = stat.strip()
    if not name or not stat:
        raise ValueError(f"Metric spec invalida: {spec}")
    return name, stat


def main() -> int:
    parser = argparse.ArgumentParser(description="Compara regresión entre summaries k6 con budget porcentual.")
    parser.add_argument("--baseline", required=True, help="Summary baseline.")
    parser.add_argument("--candidate", required=True, help="Summary candidato.")
    parser.add_argument(
        "--budget-pct",
        type=float,
        default=10.0,
        help="Regresión porcentual máxima permitida (default 10%%).",
    )
    parser.add_argument(
        "--metric",
        action="append",
        default=[],
        help="Métrica explícita en formato metric:stat. Repetible.",
    )
    parser.add_argument("--output", default="", help="Ruta opcional de salida JSON.")
    args = parser.parse_args()

    baseline = _load_json(Path(args.baseline))
    candidate = _load_json(Path(args.candidate))
    metric_specs = [_parse_metric_spec(item) for item in args.metric] if args.metric else list(DEFAULT_METRICS)

    checks: list[dict[str, Any]] = []
    overall_pass = True
    budget = float(args.budget_pct)

    for metric_name, stat in metric_specs:
        base_val = _get_metric_value(baseline, metric_name, stat)
        cand_val = _get_metric_value(candidate, metric_name, stat)
        if base_val is None or cand_val is None:
            checks.append(
                {
                    "metric": metric_name,
                    "stat": stat,
                    "status": "SKIP_MISSING",
                    "baseline": base_val,
                    "candidate": cand_val,
                    "regression_pct": None,
                }
            )
            continue

        if base_val == 0:
            regression_pct = 0.0 if cand_val == 0 else 100.0
        else:
            regression_pct = ((cand_val - base_val) / abs(base_val)) * 100.0

        passed = regression_pct <= budget
        overall_pass = overall_pass and passed
        checks.append(
            {
                "metric": metric_name,
                "stat": stat,
                "status": "PASS" if passed else "FAIL",
                "baseline": base_val,
                "candidate": cand_val,
                "regression_pct": regression_pct,
                "budget_pct": budget,
            }
        )

    report = {
        "status": "PASS" if overall_pass else "FAIL",
        "budget_pct": budget,
        "baseline": str(args.baseline),
        "candidate": str(args.candidate),
        "checks": checks,
    }

    if args.output:
        Path(args.output).write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2))

    return 0 if overall_pass else 1


if __name__ == "__main__":
    raise SystemExit(main())
