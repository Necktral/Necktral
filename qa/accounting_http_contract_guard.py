#!/usr/bin/env python3
"""Guardas de arquitectura HTTP para accounting reports/dashboard."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def _read(rel_path: str) -> str:
    target = ROOT / rel_path
    if not target.exists():
        raise FileNotFoundError(rel_path)
    return target.read_text(encoding="utf-8")


def main() -> int:
    errors: list[str] = []

    config_urls = _read("backend/src/config/urls.py")
    if 'path("api/backend/accounting/", include("apps.modulos.accounting.urls"))' not in config_urls:
        errors.append("Falta ruta canónica /api/backend/accounting/* en config/urls.py")
    if 'path("api/accounting/", include("apps.modulos.accounting.urls"))' not in config_urls:
        errors.append("Falta alias legacy /api/accounting/* en config/urls.py")

    accounting_urls = _read("backend/src/apps/modulos/accounting/urls.py")
    required_routes = (
        'path("reports/trial-balance/"',
        'path("reports/general-ledger/"',
        'path("reports/pnl/"',
        'path("reports/balance-sheet/"',
        'path("reports/operational-reconciliation/"',
        'path("dashboard/executive-summary/"',
        'path("dashboard/revenue-vs-expense/"',
        'path("dashboard/cash-position/"',
        'path("dashboard/reconciliation-health/"',
        'path("dashboard/branch-performance/"',
        'path("dashboard/monthly-trends/"',
    )
    for token in required_routes:
        if token not in accounting_urls:
            errors.append(f"Falta endpoint contable requerido: {token}")

    reports_view = _read("backend/src/apps/modulos/accounting/api/views_reports.py")
    dashboard_view = _read("backend/src/apps/modulos/accounting/api/views_dashboard.py")
    forbidden_http_imports = (
        "from ..models import",
        "from apps.modulos.accounting.models import",
        "from ..phase7 import",
        "from apps.modulos.accounting.phase7 import",
        "from ..services import reconcile_operational_vs_accounting",
    )
    for token in forbidden_http_imports:
        if token in reports_view or token in dashboard_view:
            errors.append(f"Capa HTTP no debe importar dominio directo: {token}")

    if errors:
        print("accounting_http_contract_guard: FAIL")
        for item in errors:
            print(f" - {item}")
        return 1

    print("accounting_http_contract_guard: PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())

