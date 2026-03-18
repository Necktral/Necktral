#!/usr/bin/env python3
"""Guarda de fronteras modulares (Auth/IAM/ORG)."""

from __future__ import annotations

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


def main() -> int:
    errors: list[str] = []

    config_urls = _read_text("backend/src/config/urls.py")
    _require_contains(config_urls, 'include("modulos.auth_kernel.urls")', source="config/urls.py", errors=errors)
    _require_contains(config_urls, 'path("api/backend/auth/"', source="config/urls.py", errors=errors)
    _require_contains(config_urls, 'path("api/backend/iam/"', source="config/urls.py", errors=errors)
    _require_contains(config_urls, 'path("api/backend/org/"', source="config/urls.py", errors=errors)
    _require_contains(config_urls, 'path("api/auth/"', source="config/urls.py", errors=errors)
    _require_contains(config_urls, 'path("api/iam/"', source="config/urls.py", errors=errors)
    _require_contains(config_urls, 'path("api/org/"', source="config/urls.py", errors=errors)

    settings_base = _read_text("backend/src/config/settings/base.py")
    _require_contains(
        settings_base,
        "config.middleware.legacy_api_deprecation.LegacyApiDeprecationMiddleware",
        source="config/settings/base.py",
        errors=errors,
    )

    deprecation_middleware = _read_text("backend/src/config/middleware/legacy_api_deprecation.py")
    _require_contains(deprecation_middleware, '"/api/auth/"', source="legacy_api_deprecation.py", errors=errors)
    _require_contains(deprecation_middleware, '"/api/iam/"', source="legacy_api_deprecation.py", errors=errors)
    _require_contains(deprecation_middleware, '"/api/org/"', source="legacy_api_deprecation.py", errors=errors)
    _require_contains(deprecation_middleware, 'response["Deprecation"]', source="legacy_api_deprecation.py", errors=errors)
    _require_contains(deprecation_middleware, 'response["Sunset"]', source="legacy_api_deprecation.py", errors=errors)
    _require_contains(deprecation_middleware, 'response["Link"]', source="legacy_api_deprecation.py", errors=errors)

    accounts_views = _read_text("backend/src/apps/accounts/views.py")
    _require_contains(
        accounts_views,
        "modulos.auth_kernel.views",
        source="apps/accounts/views.py",
        errors=errors,
    )
    _require_absent(accounts_views, "seed_rbac_v01", source="apps/accounts/views.py", errors=errors)
    _require_absent(accounts_views, "OrgUnit", source="apps/accounts/views.py", errors=errors)

    iam_urls = _read_text("backend/src/apps/iam/urls.py")
    _require_contains(iam_urls, 'path("bootstrap/status/"', source="apps/iam/urls.py", errors=errors)
    _require_contains(iam_urls, 'path("bootstrap/init-admin/"', source="apps/iam/urls.py", errors=errors)

    org_urls = _read_text("backend/src/apps/org/urls.py")
    _require_contains(
        org_urls,
        'path("bootstrap/organization/"',
        source="apps/org/urls.py",
        errors=errors,
    )

    auth_kernel_urls = _read_text("modulos/auth_kernel/urls.py")
    _require_contains(auth_kernel_urls, 'path("login/"', source="modulos/auth_kernel/urls.py", errors=errors)
    _require_contains(
        auth_kernel_urls,
        'path("bootstrap/status/"',
        source="modulos/auth_kernel/urls.py",
        errors=errors,
    )

    if errors:
        print("architecture_boundaries_guard: FAIL")
        for item in errors:
            print(f" - {item}")
        return 1

    print("architecture_boundaries_guard: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
