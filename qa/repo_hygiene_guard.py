#!/usr/bin/env python3
"""Guardas de higiene para evitar reintroducción de legado/residuos en git."""

from __future__ import annotations

import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

ALLOWED_EVIDENCE_TRACKED = {
    "docs/operacion/evidencia/.gitkeep",
    "docs/operacion/evidencia/etup-git-less-help.txt",
}

BLOCKED_PREFIXES = (
    "backend/",
    "frontend/node_modules/",
    "frontend/dist/",
    "frontend/.quasar/",
    "system_wis/",
)

BLOCKED_SEGMENTS = (
    "/__pycache__/",
    "/.pytest_cache/",
    "/.mypy_cache/",
    "/.ruff_cache/",
)


def tracked_files() -> list[str]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def main() -> int:
    files = tracked_files()
    errors: list[str] = []

    if not (ROOT / "docs/CONTRACT_PACK_v1.1.md").exists():
        errors.append("Falta docs/CONTRACT_PACK_v1.1.md")

    for path in files:
        if path.startswith("docs/operacion/evidencia/") and path not in ALLOWED_EVIDENCE_TRACKED:
            errors.append(f"Evidencia masiva trackeada fuera de allowlist: {path}")

        if any(path.startswith(prefix) for prefix in BLOCKED_PREFIXES):
            errors.append(f"Ruta bloqueada en git: {path}")

        if any(segment in f"/{path}" for segment in BLOCKED_SEGMENTS):
            errors.append(f"Artefacto cacheado trackeado: {path}")

        if path.endswith((".pyc", ".pyo", ".pyd")):
            errors.append(f"Binario Python trackeado: {path}")

    if errors:
        print("[repo-hygiene] FAIL")
        for item in errors:
            print(f"- {item}")
        return 1

    print("[repo-hygiene] PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
