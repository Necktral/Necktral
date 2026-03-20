#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path


ERROR_RE = re.compile(r"^(?P<path>.+?):(?P<line>\d+): error: (?P<message>.+?)\s+\[(?P<code>[^\]]+)\]\s*$")


def _domain_for(path: str) -> str:
    normalized = path.replace("\\", "/")
    if "/apps/accounting/" in normalized:
        return "accounting"
    if "/apps/accounts/" in normalized:
        return "accounts"
    if "/kernels/facturacion/" in normalized:
        return "facturacion"
    if "/kernels/estacion_servicios/" in normalized or "/fuel_" in normalized:
        return "fuel"
    return "other"


def _parse_mypy_report(report_path: Path) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    if not report_path.exists():
        return rows

    for raw in report_path.read_text(encoding="utf-8", errors="ignore").splitlines():
        match = ERROR_RE.match(raw.strip())
        if not match:
            continue
        item = {
            "path": match.group("path"),
            "line": match.group("line"),
            "code": match.group("code"),
            "message": match.group("message"),
        }
        item["domain"] = _domain_for(item["path"])
        rows.append(item)
    return rows


def _fingerprint(item: dict[str, str]) -> str:
    # El baseline ignora número de línea para evitar ruido por desplazamientos triviales.
    return f"{item['path']}|{item['code']}|{item['message']}"


def _load_baseline(path: Path) -> set[str]:
    if not path.exists():
        return set()
    return {
        line.strip()
        for line in path.read_text(encoding="utf-8", errors="ignore").splitlines()
        if line.strip() and not line.strip().startswith("#")
    }


def _write_baseline(path: Path, fingerprints: set[str]) -> None:
    lines = sorted(fingerprints)
    content = "\n".join(lines) + ("\n" if lines else "")
    path.write_text(content, encoding="utf-8")


def _by_domain(fingerprints: set[str]) -> dict[str, int]:
    out: dict[str, int] = {"accounting": 0, "accounts": 0, "facturacion": 0, "fuel": 0, "other": 0}
    for fp in fingerprints:
        path = fp.split("|", 1)[0]
        out[_domain_for(path)] += 1
    return out


def _emit_delta_report(
    *,
    delta_json_path: Path,
    delta_text_path: Path | None,
    baseline: set[str],
    current: set[str],
    new_errors: set[str],
    resolved: set[str],
) -> None:
    baseline_domains = _by_domain(baseline)
    current_domains = _by_domain(current)
    new_domains = _by_domain(new_errors)
    resolved_domains = _by_domain(resolved)

    payload = {
        "summary": {
            "baseline_errors": len(baseline),
            "current_errors": len(current),
            "new_errors": len(new_errors),
            "resolved_errors": len(resolved),
            "status": "fail" if new_errors else "pass",
        },
        "domains": {
            domain: {
                "baseline": baseline_domains[domain],
                "current": current_domains[domain],
                "new": new_domains[domain],
                "resolved": resolved_domains[domain],
            }
            for domain in ("accounting", "accounts", "facturacion", "fuel", "other")
        },
        "new_errors": sorted(new_errors),
        "resolved_errors": sorted(resolved),
    }
    delta_json_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    if delta_text_path is None:
        return

    lines = [
        f"baseline_errors={len(baseline)}",
        f"current_errors={len(current)}",
        f"new_errors={len(new_errors)}",
        f"resolved_errors={len(resolved)}",
        "",
        "domains:",
    ]
    for domain in ("accounting", "accounts", "facturacion", "fuel", "other"):
        lines.append(
            (
                f"  {domain}: baseline={baseline_domains[domain]} "
                f"current={current_domains[domain]} new={new_domains[domain]} resolved={resolved_domains[domain]}"
            )
        )
    if new_errors:
        lines.append("")
        lines.append("new_errors_list:")
        lines.extend([f"  {row}" for row in sorted(new_errors)])

    delta_text_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _cmd_refresh(args: argparse.Namespace) -> int:
    report_rows = _parse_mypy_report(Path(args.report))
    fingerprints = {_fingerprint(item) for item in report_rows}
    baseline_path = Path(args.baseline)
    baseline_path.parent.mkdir(parents=True, exist_ok=True)
    _write_baseline(baseline_path, fingerprints)
    print(f"[qa] mypy baseline refreshed: {baseline_path} ({len(fingerprints)} entries)")
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    report_path = Path(args.report)
    baseline_path = Path(args.baseline)
    delta_json_path = Path(args.delta_report)
    delta_text_path = Path(args.delta_text) if args.delta_text else None

    report_rows = _parse_mypy_report(report_path)
    current = {_fingerprint(item) for item in report_rows}
    baseline = _load_baseline(baseline_path)
    if not baseline_path.exists():
        print(f"[qa] missing baseline file: {baseline_path}")
        return 2

    new_errors = current - baseline
    resolved = baseline - current
    delta_json_path.parent.mkdir(parents=True, exist_ok=True)
    _emit_delta_report(
        delta_json_path=delta_json_path,
        delta_text_path=delta_text_path,
        baseline=baseline,
        current=current,
        new_errors=new_errors,
        resolved=resolved,
    )

    print(
        (
            "[qa] mypy baseline check: "
            f"baseline={len(baseline)} current={len(current)} "
            f"new={len(new_errors)} resolved={len(resolved)}"
        )
    )
    if new_errors:
        print("[qa] mypy baseline check failed: new typing errors detected.")
        return 1
    print("[qa] mypy baseline check passed: no new typing errors.")
    return 0


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Manage and check mypy baseline")
    sub = parser.add_subparsers(dest="command", required=True)

    refresh = sub.add_parser("refresh", help="Refresh baseline from a mypy report")
    refresh.add_argument("--report", required=True, help="Path to mypy report")
    refresh.add_argument("--baseline", required=True, help="Path to baseline output file")
    refresh.set_defaults(func=_cmd_refresh)

    check = sub.add_parser("check", help="Check mypy report against baseline")
    check.add_argument("--report", required=True, help="Path to mypy report")
    check.add_argument("--baseline", required=True, help="Path to baseline file")
    check.add_argument("--delta-report", required=True, help="Path to delta JSON report")
    check.add_argument("--delta-text", help="Optional path to delta text report")
    check.set_defaults(func=_cmd_check)
    return parser


def main() -> int:
    parser = _build_parser()
    args = parser.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
