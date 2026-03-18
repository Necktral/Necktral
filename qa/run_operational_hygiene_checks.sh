#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
MANAGE_PY="${ROOT_DIR}/backend/src/manage.py"

echo "[1/3] Verificando migraciones aplicadas..."
"${PYTHON_BIN}" "${MANAGE_PY}" migrate --check

echo "[2/3] Verificando que no existan migraciones pendientes..."
"${PYTHON_BIN}" "${MANAGE_PY}" makemigrations --check --dry-run

echo "[3/3] Verificando suites operacionales clave..."
(
  cd "${ROOT_DIR}/backend"
  pytest -q \
    src/tests/test_phase1_operational_contracts.py \
    src/tests/test_fuel_compensation_phase2.py \
    src/tests/test_phase5_posting_controlled.py \
    src/tests/test_phase5_accounting_api.py \
    ../modulos/facturacion/tests/test_billing_accounting_integration.py \
    ../modulos/inventarios/tests/test_inventory_accounting_integration.py
)

echo "Hygiene checks OK."
