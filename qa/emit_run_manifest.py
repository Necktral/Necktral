#!/usr/bin/env python3
from __future__ import annotations

import argparse
import datetime as dt
import json
from pathlib import Path


ARTIFACTS = [
    ("static_scan.txt", "gate1"),
    ("bandit.txt", "gate1"),
    ("ruff.txt", "gate1"),
    ("mypy_strict_critical.txt", "gate1"),
    ("mypy.txt", "gate1"),
    ("static_gate_summary.json", "gate1"),
    ("makemigrations_check.txt", "gate1"),
    ("mypy_delta.json", "gate1"),
    ("mypy_delta.txt", "gate1"),
    ("reporting_contract_guard.json", "gate1"),
    ("pytest.xml", "gate2"),
    ("coverage.xml", "gate2"),
    ("coverage.txt", "gate2"),
    ("audit_integrity.json", "gate3"),
    ("reporting_r8_gate.json", "gate3"),
    ("reporting_r8_gate_guard.json", "gate3"),
    ("reporting_observability_snapshot.json", "gate3"),
    ("qa-ci-run.log", "setup"),
]


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Generate QA run manifest")
    p.add_argument("--reports-dir", required=True)
    p.add_argument("--run-start-epoch", type=int, required=True)
    p.add_argument("--run-started-at", required=True)
    p.add_argument("--run-finished-at", required=True)
    p.add_argument("--setup-status", required=True)
    p.add_argument("--gate1-status", required=True)
    p.add_argument("--gate2-status", required=True)
    p.add_argument("--gate3-status", required=True)
    p.add_argument("--run-status", required=True)
    p.add_argument("--failed-gate", default="")
    return p.parse_args()


def _iso_from_mtime(epoch_seconds: float) -> str:
    return dt.datetime.fromtimestamp(epoch_seconds, tz=dt.timezone.utc).isoformat()


def _artifact_status(
    *,
    path: Path,
    gate_status: str,
    run_start_epoch: int,
) -> tuple[str, bool, str | None]:
    if path.exists():
        mtime = path.stat().st_mtime
        is_fresh = mtime >= run_start_epoch
        if is_fresh:
            return "generated", True, _iso_from_mtime(mtime)
        return "stale", False, _iso_from_mtime(mtime)

    if gate_status in {"skipped", "not_run"}:
        return "skipped", False, None
    if gate_status in {"failed", "blocked"}:
        return "failed", False, None
    return "missing", False, None


def main() -> int:
    args = _parse_args()
    reports_dir = Path(args.reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)

    gate_statuses = {
        "setup": args.setup_status,
        "gate1": args.gate1_status,
        "gate2": args.gate2_status,
        "gate3": args.gate3_status,
    }

    artifacts: dict[str, dict[str, object]] = {}
    for filename, gate in ARTIFACTS:
        path = reports_dir / filename
        status, fresh, generated_at = _artifact_status(
            path=path,
            gate_status=gate_statuses.get(gate, "not_run"),
            run_start_epoch=args.run_start_epoch,
        )
        artifacts[filename] = {
            "gate": gate,
            "status": status,
            "fresh": fresh,
            "generated_at": generated_at,
        }

    manifest = {
        "run_started_at": args.run_started_at,
        "run_finished_at": args.run_finished_at,
        "run_status": args.run_status,
        "failed_gate": args.failed_gate or None,
        "gates": gate_statuses,
        "artifacts": artifacts,
    }

    output_path = reports_dir / "run_manifest.json"
    output_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[qa] run manifest generated: {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
