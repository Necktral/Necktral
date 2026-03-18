#!/usr/bin/env python3
"""Guardas contractuales para simulaciones (qa/k6 y simulacion)."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCAN_ROOTS = (
    "qa/k6",
    "simulacion",
)
FORBIDDEN_PATTERNS = (
    "/api/auth/",
    "/api/iam/",
    "/api/org/",
    "login_module/",
)
EXCLUDED_DIR_NAMES = {
    "__pycache__",
    "reports",
}
SMOKE_STRESS_FILES = (
    "qa/k6/auth_smoke.js",
    "qa/k6/auth_stress.js",
)


def _iter_files(rel_root: str) -> list[Path]:
    root = ROOT / rel_root
    if not root.exists():
        return []

    out: list[Path] = []
    for path in root.rglob("*"):
        if path.is_dir():
            continue
        if any(part in EXCLUDED_DIR_NAMES for part in path.parts):
            continue
        out.append(path)
    return out


def _read_text(path: Path) -> str | None:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None


def main() -> int:
    errors: list[str] = []

    for rel_root in SCAN_ROOTS:
        for path in _iter_files(rel_root):
            text = _read_text(path)
            if text is None:
                continue
            rel = path.relative_to(ROOT).as_posix()
            for pattern in FORBIDDEN_PATTERNS:
                if pattern in text:
                    errors.append(f"[forbidden] {rel}: '{pattern}'")

    for rel_path in SMOKE_STRESS_FILES:
        target = ROOT / rel_path
        if not target.exists():
            errors.append(f"[missing] {rel_path}")
            continue
        text = target.read_text(encoding="utf-8")
        if "login usable session" not in text:
            errors.append(f"[missing] {rel_path}: 'login usable session'")
        if "login has access" in text:
            errors.append(f"[forbidden] {rel_path}: 'login has access'")

    if errors:
        print("simulation_contract_guard: FAIL")
        for item in errors:
            print(f" - {item}")
        return 1

    print("simulation_contract_guard: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
