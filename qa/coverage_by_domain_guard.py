#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


@dataclass(frozen=True)
class DomainScope:
    key: str
    path_prefix: str


CRITICAL_DOMAIN_SCOPES: tuple[DomainScope, ...] = (
    DomainScope("apps.kernels.portfolio", "backend/src/apps/kernels/portfolio/"),
    DomainScope("apps.modulos.sync_engine", "backend/src/apps/modulos/sync_engine/"),
    DomainScope("apps.kernels.reporting", "backend/src/apps/kernels/reporting/"),
    DomainScope("apps.kernels.accounting", "backend/src/apps/kernels/accounting/"),
    DomainScope("apps.modulos.accounts", "backend/src/apps/modulos/accounts/"),
    DomainScope("apps.modulos.dashboard", "backend/src/apps/modulos/dashboard/"),
    DomainScope("apps.modulos.integration", "backend/src/apps/modulos/integration/"),
    DomainScope("apps.modulos.estacion_servicios", "backend/src/apps/modulos/estacion_servicios/"),
)


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Compute and enforce coverage by critical domain.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument(
        "--coverage-report",
        default="qa/reports/coverage.txt",
        help="coverage text report file (coverage report output)",
    )
    parser.add_argument(
        "--baseline",
        default="qa/contracts/coverage_by_domain_baseline.json",
        help="baseline contract for ratchet thresholds",
    )
    parser.add_argument(
        "--output",
        default="qa/reports/coverage_by_domain.json",
        help="output report path",
    )
    parser.add_argument(
        "--write-baseline",
        action="store_true",
        help="write baseline file with current measured percentages",
    )
    return parser.parse_args()


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _run_git(args: list[str], *, root: Path) -> str:
    try:
        proc = subprocess.run(
            ["git", *args],
            cwd=str(root),
            check=False,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError:
        return ""
    if proc.returncode != 0:
        return ""
    return (proc.stdout or "").strip()


def _resolve_base_ref(root: Path) -> str:
    base_ref = ""

    candidate = ""
    try:
        import os

        candidate = str(os.getenv("QA_COVERAGE_BASE_REF", "")).strip()
        if not candidate:
            github_base = str(os.getenv("GITHUB_BASE_REF", "")).strip()
            if github_base:
                candidate = f"origin/{github_base}"
    except Exception:
        candidate = ""

    if candidate:
        merge_base = _run_git(["merge-base", "HEAD", candidate], root=root)
        if merge_base:
            return merge_base

    for fallback in ("origin/master", "origin/main"):
        merge_base = _run_git(["merge-base", "HEAD", fallback], root=root)
        if merge_base:
            return merge_base

    head_prev = _run_git(["rev-parse", "HEAD~1"], root=root)
    return head_prev


def _changed_python_files(root: Path) -> list[str]:
    base = _resolve_base_ref(root)
    if not base:
        return []
    changed = _run_git(["diff", "--name-only", f"{base}...HEAD"], root=root)
    out: list[str] = []
    for line in changed.splitlines():
        rel = line.strip().replace("\\", "/")
        if not rel.endswith(".py"):
            continue
        if "/migrations/" in rel or "/tests/" in rel:
            continue
        out.append(rel)
    return sorted(set(out))


_COVERAGE_ROW_RE = re.compile(r"^(src/\S+\.py)\s+(\d+)\s+(\d+)\s+(\d+)%(?:\s+.*)?$")


def _parse_coverage_report(coverage_report: Path) -> dict[str, dict[str, int]]:
    rows: dict[str, dict[str, int]] = {}
    for line in coverage_report.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = _COVERAGE_ROW_RE.match(line.strip())
        if not match:
            continue
        rel_src = match.group(1)
        stmts = int(match.group(2))
        miss = int(match.group(3))
        covered = max(stmts - miss, 0)
        rel = f"backend/{rel_src}".replace("\\", "/")
        rows[rel] = {"covered": covered, "total": stmts}
    return rows


def _pct(covered: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round((covered / total) * 100.0, 2)


def _domain_aggregation(file_cov: dict[str, dict[str, int]]) -> dict[str, dict[str, object]]:
    domains: dict[str, dict[str, object]] = {}
    for scope in CRITICAL_DOMAIN_SCOPES:
        covered = 0
        total = 0
        files: list[str] = []
        for rel, row in file_cov.items():
            if rel.startswith(scope.path_prefix):
                covered += int(row["covered"])
                total += int(row["total"])
                files.append(rel)
        domains[scope.key] = {
            "path_prefix": scope.path_prefix,
            "covered_lines": covered,
            "total_lines": total,
            "coverage_pct": _pct(covered, total),
            "files_measured": sorted(files),
        }
    return domains


def _load_baseline(path: Path) -> dict[str, object]:
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _write_baseline(*, baseline_path: Path, domains: dict[str, dict[str, object]], changed_files_floor_pct: float) -> None:
    payload = {
        "version": 1,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "changed_files_floor_pct": changed_files_floor_pct,
        "domains": {
            key: {
                "baseline_pct": float(row["coverage_pct"]),
                "floor_pct": 1.0,
            }
            for key, row in sorted(domains.items())
        },
    }
    _write_json(baseline_path, payload)


def main() -> int:
    args = _parse_args()
    root = Path(args.root).resolve()
    coverage_report = (root / args.coverage_report).resolve()
    baseline_path = (root / args.baseline).resolve()
    output_path = (root / args.output).resolve()

    issues: list[str] = []
    warnings: list[str] = []

    if not coverage_report.exists():
        issues.append(f"coverage report not found: {coverage_report}")
        _write_json(
            output_path,
            {
                "status": "failed",
                "generated_at": datetime.now(tz=timezone.utc).isoformat(),
                "issues": issues,
            },
        )
        print("[qa] coverage by domain guard failed")
        for issue in issues:
            print(f"[qa] - {issue}")
        return 1

    file_cov = _parse_coverage_report(coverage_report=coverage_report)
    domains = _domain_aggregation(file_cov)
    changed_files = _changed_python_files(root)

    baseline_payload = _load_baseline(baseline_path)
    baseline_domains = baseline_payload.get("domains", {}) if isinstance(baseline_payload, dict) else {}
    changed_files_floor_pct = float(baseline_payload.get("changed_files_floor_pct", 50.0) or 50.0)

    if args.write_baseline:
        _write_baseline(
            baseline_path=baseline_path,
            domains=domains,
            changed_files_floor_pct=changed_files_floor_pct,
        )
        print(f"[qa] coverage baseline written: {baseline_path}")
        return 0

    for scope in CRITICAL_DOMAIN_SCOPES:
        if scope.key not in domains:
            issues.append(f"critical domain missing in coverage aggregation: {scope.key}")
            continue
        row = domains[scope.key]
        if int(row["total_lines"]) <= 0:
            issues.append(f"critical domain has no measured lines: {scope.key}")
            continue

        baseline_row = baseline_domains.get(scope.key, {})
        baseline_pct = float(baseline_row.get("baseline_pct", 0.0) or 0.0)
        floor_pct = float(baseline_row.get("floor_pct", 1.0) or 1.0)
        measured = float(row["coverage_pct"])
        if measured < baseline_pct:
            issues.append(
                f"{scope.key}: coverage regression {measured:.2f}% < baseline {baseline_pct:.2f}%"
            )
        if measured < floor_pct:
            issues.append(
                f"{scope.key}: coverage {measured:.2f}% below floor {floor_pct:.2f}%"
            )

    touched_results: list[dict[str, object]] = []
    for rel in changed_files:
        matching_scope = next((s for s in CRITICAL_DOMAIN_SCOPES if rel.startswith(s.path_prefix)), None)
        if matching_scope is None:
            continue
        row = file_cov.get(rel, {"covered": 0, "total": 0})
        covered = int(row["covered"])
        total = int(row["total"])
        pct = _pct(covered, total)
        touched_results.append(
            {
                "file": rel,
                "domain": matching_scope.key,
                "covered_lines": covered,
                "total_lines": total,
                "coverage_pct": pct,
            }
        )
        if total <= 0:
            issues.append(f"touched critical file has no coverage data: {rel}")
        elif pct < changed_files_floor_pct:
            issues.append(
                f"touched critical file below floor: {rel} ({pct:.2f}% < {changed_files_floor_pct:.2f}%)"
            )

    if not baseline_domains:
        warnings.append("baseline domains not configured; ratchet uses default 0.00% baseline")

    status = "failed" if issues else "passed"
    payload = {
        "status": status,
        "generated_at": datetime.now(tz=timezone.utc).isoformat(),
        "coverage_report": coverage_report.relative_to(root).as_posix(),
        "baseline_file": args.baseline,
        "changed_files_floor_pct": changed_files_floor_pct,
        "domains": domains,
        "changed_python_files": changed_files,
        "changed_critical_files_coverage": touched_results,
        "issues": issues,
        "warnings": warnings,
    }
    _write_json(output_path, payload)

    if issues:
        print("[qa] coverage by domain guard failed")
        for issue in issues:
            print(f"[qa] - {issue}")
        return 1

    print("[qa] coverage by domain guard passed")
    for warning in warnings:
        print(f"[qa] warning: {warning}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
