#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate canonical and legacy API route contracts.")
    parser.add_argument("--root", default=".", help="Repository root")
    parser.add_argument("--output", default="qa/reports/route_contract_report.json", help="Output report path")
    return parser.parse_args()


def main() -> int:
    args = _parse_args()
    root = Path(args.root).resolve()
    backend_src = root / "backend" / "src"
    sys.path.insert(0, str(backend_src))
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.test")

    import django  # noqa: PLC0415

    django.setup()

    from django.urls import get_resolver  # noqa: PLC0415
    from config.routing_policy import CANONICAL_ROUTE_PREFIXES, LEGACY_ROUTE_POLICIES  # noqa: PLC0415

    routes = [str(getattr(pattern.pattern, "_route", "")) for pattern in get_resolver().url_patterns]
    issues: list[str] = []

    for name, canonical_prefix in CANONICAL_ROUTE_PREFIXES.items():
        route_fragment = canonical_prefix.lstrip("/")
        count = routes.count(route_fragment)
        if count != 1:
            issues.append(f"canonical prefix '{canonical_prefix}' for domain '{name}' expected once, found {count}")

    for legacy_prefix in LEGACY_ROUTE_POLICIES:
        route_fragment = legacy_prefix.lstrip("/")
        count = routes.count(route_fragment)
        if count != 1:
            issues.append(f"legacy prefix '{legacy_prefix}' expected once, found {count}")

    report = {
        "status": "failed" if issues else "passed",
        "canonical_prefixes": CANONICAL_ROUTE_PREFIXES,
        "legacy_prefixes": sorted(LEGACY_ROUTE_POLICIES),
        "top_level_routes": routes,
        "issues": issues,
    }
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if issues:
        print("[qa] route contract guard failed")
        for issue in issues:
            print(f"[qa] - {issue}")
        return 1

    print("[qa] route contract guard passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
