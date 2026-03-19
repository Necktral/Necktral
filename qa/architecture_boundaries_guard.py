#!/usr/bin/env python3
"""Guarda de fronteras modulares (apps.modulos + kernels verticales)."""

from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read_text(rel_path: str) -> str:
    target = ROOT / rel_path
    if not target.exists():
        raise FileNotFoundError(f"No existe {rel_path}")
    return target.read_text(encoding="utf-8")


def _require_contains(content: str, needle: str, *, source: str, errors: list[str]) -> None:
    if needle not in content:
        errors.append(f"[missing] {source}: '{needle}'")


def _require_absent(content: str, needle: str, *, source: str, errors: list[str]) -> None:
    if needle in content:
        errors.append(f"[forbidden] {source}: '{needle}'")


def _check_legacy_imports(errors: list[str]) -> None:
    pattern = re.compile(r"\b(?:from|import)\s+apps\.(?!modulos\.)")
    roots = (ROOT / "backend/src", ROOT / "qa")
    for base in roots:
        for path in base.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            if pattern.search(text):
                rel = path.relative_to(ROOT).as_posix()
                errors.append(f"[forbidden] legacy import namespace: {rel}")


def main() -> int:
    errors: list[str] = []

    config_urls = _read_text("backend/src/config/urls.py")
    _require_contains(config_urls, 'include("modulos.auth_kernel.urls")', source="config/urls.py", errors=errors)
    _require_contains(config_urls, 'include("apps.modulos.iam.urls")', source="config/urls.py", errors=errors)
    _require_contains(config_urls, 'include("apps.modulos.org.urls")', source="config/urls.py", errors=errors)
    _require_contains(config_urls, 'include("apps.modulos.reports.urls")', source="config/urls.py", errors=errors)
    _require_absent(config_urls, 'include("apps.iam.urls")', source="config/urls.py", errors=errors)
    _require_absent(config_urls, 'include("apps.org.urls")', source="config/urls.py", errors=errors)
    _require_absent(config_urls, 'include("apps.reports.urls")', source="config/urls.py", errors=errors)
    _require_absent(config_urls, 'include("modulos.reports.urls")', source="config/urls.py", errors=errors)
    _require_absent(config_urls, 'path("api/reports/"', source="config/urls.py", errors=errors)

    settings_base = _read_text("backend/src/config/settings/base.py")
    _require_contains(
        settings_base,
        "apps.modulos.reports.apps.ReportsConfig",
        source="config/settings/base.py",
        errors=errors,
    )
    _require_contains(
        settings_base,
        "apps.modulos.iam.apps.IamConfig",
        source="config/settings/base.py",
        errors=errors,
    )
    _require_contains(
        settings_base,
        "apps.modulos.org.apps.OrgConfig",
        source="config/settings/base.py",
        errors=errors,
    )
    _require_contains(
        settings_base,
        "apps.modulos.audit.middleware.AuditAccessDeniedMiddleware",
        source="config/settings/base.py",
        errors=errors,
    )
    _require_contains(
        settings_base,
        "apps.modulos.iam.authentication.JWTAuthWithOrgContext",
        source="config/settings/base.py",
        errors=errors,
    )

    deprecation_middleware = _read_text("backend/src/config/middleware/legacy_api_deprecation.py")
    _require_contains(deprecation_middleware, '"/api/auth/"', source="legacy_api_deprecation.py", errors=errors)
    _require_contains(deprecation_middleware, '"/api/iam/"', source="legacy_api_deprecation.py", errors=errors)
    _require_contains(deprecation_middleware, '"/api/org/"', source="legacy_api_deprecation.py", errors=errors)
    _require_absent(deprecation_middleware, '"/api/reports/"', source="legacy_api_deprecation.py", errors=errors)

    accounts_views = _read_text("backend/src/apps/modulos/accounts/views.py")
    _require_contains(
        accounts_views,
        "modulos.auth_kernel.views",
        source="apps/modulos/accounts/views.py",
        errors=errors,
    )

    iam_urls = _read_text("backend/src/apps/modulos/iam/urls.py")
    _require_contains(iam_urls, 'path("bootstrap/status/"', source="apps/modulos/iam/urls.py", errors=errors)
    _require_contains(iam_urls, 'path("bootstrap/init-admin/"', source="apps/modulos/iam/urls.py", errors=errors)

    org_urls = _read_text("backend/src/apps/modulos/org/urls.py")
    _require_contains(
        org_urls,
        'path("bootstrap/organization/"',
        source="apps/modulos/org/urls.py",
        errors=errors,
    )

    _check_legacy_imports(errors)

    if errors:
        print("architecture_boundaries_guard: FAIL")
        for item in errors:
            print(f" - {item}")
        return 1

    print("architecture_boundaries_guard: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
