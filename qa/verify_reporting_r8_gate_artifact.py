#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


ALLOWED_FAILURE_CLASSES = {"none", "quality_breach", "latency_regression", "app_error", "infra_error"}
ALLOWED_GATE_STATUS = {"PASS", "WARN", "FAIL"}


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate reporting_r8_gate.json artifact schema.")
    parser.add_argument("--artifact", default="qa/reports/reporting_r8_gate.json")
    parser.add_argument("--output", default="qa/reports/reporting_r8_gate_guard.json")
    return parser.parse_args()


def _is_non_empty_str(value: Any) -> bool:
    return isinstance(value, str) and bool(value.strip())


def main() -> int:
    args = _parse_args()
    artifact_path = Path(args.artifact)
    output_path = Path(args.output)
    issues: list[str] = []

    if not artifact_path.exists():
        issues.append(f"missing artifact: {artifact_path}")
        payload: dict[str, Any] = {}
    else:
        try:
            payload = json.loads(artifact_path.read_text(encoding="utf-8"))
        except Exception as exc:  # noqa: BLE001
            issues.append(f"invalid json ({artifact_path}): {exc}")
            payload = {}

    gate_status = str(payload.get("gate_status") or "")
    if gate_status not in ALLOWED_GATE_STATUS:
        issues.append(f"gate_status inválido: {gate_status!r}")

    failure_class = str(payload.get("failure_class") or "")
    if failure_class not in ALLOWED_FAILURE_CLASSES:
        issues.append(f"failure_class inválido: {failure_class!r}")

    trigger_metric = payload.get("trigger_metric")
    breaches = payload.get("breaches")
    if not isinstance(breaches, list):
        issues.append("breaches debe ser list")
        breaches = []

    if failure_class == "none":
        if gate_status in {"WARN", "FAIL"}:
            issues.append("gate_status WARN/FAIL requiere failure_class distinto de none")
        if breaches:
            issues.append("failure_class=none debe tener breaches vacíos")
    else:
        if gate_status == "PASS":
            issues.append("gate_status PASS no puede coexistir con failure_class de brecha")
        if not _is_non_empty_str(trigger_metric):
            issues.append("trigger_metric requerido cuando failure_class != none")
        if not breaches:
            issues.append("breaches requerido cuando failure_class != none")

    for idx, breach in enumerate(breaches):
        if not isinstance(breach, dict):
            issues.append(f"breaches[{idx}] debe ser objeto")
            continue
        b_class = str(breach.get("failure_class") or "")
        if b_class not in ALLOWED_FAILURE_CLASSES - {"none"}:
            issues.append(f"breaches[{idx}].failure_class inválido: {b_class!r}")
        if not _is_non_empty_str(breach.get("metric")):
            issues.append(f"breaches[{idx}].metric requerido")
        if "actual" not in breach:
            issues.append(f"breaches[{idx}].actual requerido")
        if "threshold" not in breach:
            issues.append(f"breaches[{idx}].threshold requerido")

    summary = {
        "status": "passed" if not issues else "failed",
        "artifact": str(artifact_path),
        "gate_status": gate_status,
        "failure_class": failure_class,
        "issues": issues,
    }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if issues:
        print("[qa] reporting_r8_gate artifact guard failed")
        for issue in issues:
            print(f"[qa] - {issue}")
        return 1

    print("[qa] reporting_r8_gate artifact guard passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
