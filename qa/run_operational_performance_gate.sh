#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
K6_BIN="${K6_BIN:-k6}"
MANAGE_PY="${ROOT_DIR}/backend/src/manage.py"
K6_SCRIPT="${ROOT_DIR}/qa/k6/operational_posting_load.js"

BASE_URL="${BASE_URL:-http://localhost:8000/api}"
COMPANY_ID="${COMPANY_ID:-}"
BRANCH_ID="${BRANCH_ID:-}"
USERNAME="${USERNAME:-}"
PASSWORD="${PASSWORD:-}"

if [[ -z "${COMPANY_ID}" || -z "${BRANCH_ID}" ]]; then
  echo "ERROR: COMPANY_ID y BRANCH_ID son requeridos." >&2
  exit 2
fi
if [[ -z "${USERNAME}" || -z "${PASSWORD}" ]]; then
  echo "ERROR: USERNAME y PASSWORD son requeridos." >&2
  exit 2
fi

if ! command -v "${K6_BIN}" >/dev/null 2>&1; then
  echo "ERROR: no se encontró '${K6_BIN}' en PATH." >&2
  exit 2
fi

TS="$(date +%Y%m%d_%H%M%S)"
DEFAULT_OUT_DIR="${ROOT_DIR}/docs/operacion/evidencia/operational_performance_${TS}"
OUT_DIR="${OUT_DIR:-${DEFAULT_OUT_DIR}}"
mkdir -p "${OUT_DIR}"

SNAPSHOT_BEFORE="${OUT_DIR}/snapshot_before.json"
SNAPSHOT_AFTER="${OUT_DIR}/snapshot_after.json"
K6_SUMMARY="${OUT_DIR}/k6_summary.json"
GATE_REPORT="${OUT_DIR}/gate_report.json"
GATE_HASH="${OUT_DIR}/gate_report.sha256"

echo "[1/4] Exportando snapshot inicial..."
"${PYTHON_BIN}" "${MANAGE_PY}" export_operational_load_snapshot \
  --company-id "${COMPANY_ID}" \
  --branch-id "${BRANCH_ID}" \
  --output "${SNAPSHOT_BEFORE}"

echo "[2/4] Ejecutando carga operacional (k6)..."
K6_ARGS=(
  run
  "${K6_SCRIPT}"
  --summary-export "${K6_SUMMARY}"
  -e "BASE_URL=${BASE_URL}"
  -e "USERNAME=${USERNAME}"
  -e "PASSWORD=${PASSWORD}"
  -e "COMPANY_ID=${COMPANY_ID}"
  -e "BRANCH_ID=${BRANCH_ID}"
)
if [[ -n "${WAREHOUSE_ID:-}" ]]; then
  K6_ARGS+=(-e "WAREHOUSE_ID=${WAREHOUSE_ID}")
fi
if [[ -n "${ITEM_ID:-}" ]]; then
  K6_ARGS+=(-e "ITEM_ID=${ITEM_ID}")
fi
if [[ -n "${DURATION:-}" ]]; then
  K6_ARGS+=(-e "DURATION=${DURATION}")
fi
if [[ -n "${BILLING_VUS:-}" ]]; then
  K6_ARGS+=(-e "BILLING_VUS=${BILLING_VUS}")
fi
if [[ -n "${INVENTORY_VUS:-}" ]]; then
  K6_ARGS+=(-e "INVENTORY_VUS=${INVENTORY_VUS}")
fi
if [[ -n "${POSTING_VUS:-}" ]]; then
  K6_ARGS+=(-e "POSTING_VUS=${POSTING_VUS}")
fi
"${K6_BIN}" "${K6_ARGS[@]}"

echo "[3/4] Exportando snapshot final..."
"${PYTHON_BIN}" "${MANAGE_PY}" export_operational_load_snapshot \
  --company-id "${COMPANY_ID}" \
  --branch-id "${BRANCH_ID}" \
  --output "${SNAPSHOT_AFTER}"

echo "[4/4] Evaluando gate SLO..."
"${PYTHON_BIN}" - <<'PY' "${K6_SUMMARY}" "${SNAPSHOT_BEFORE}" "${SNAPSHOT_AFTER}" "${GATE_REPORT}" "${GATE_HASH}"
import hashlib
import json
import sys
from pathlib import Path

summary_path = Path(sys.argv[1])
before_path = Path(sys.argv[2])
after_path = Path(sys.argv[3])
report_path = Path(sys.argv[4])
hash_path = Path(sys.argv[5])

summary = json.loads(summary_path.read_text(encoding="utf-8"))
before = json.loads(before_path.read_text(encoding="utf-8"))
after = json.loads(after_path.read_text(encoding="utf-8"))

metrics = summary.get("metrics", {})
def metric_value(name: str, key: str, default: float = 0.0) -> float:
    row = metrics.get(name, {})
    values = row.get("values", {})
    try:
        return float(values.get(key, default))
    except Exception:
        return float(default)

billing_p95 = metric_value("billing_write_ms", "p(95)")
inventory_p95 = metric_value("inventory_write_ms", "p(95)")
posting_p95 = metric_value("posting_cycle_ms", "p(95)")
error_rate = metric_value("operational_error_rate", "rate")

before_failed = (before.get("failed_outbox") or {}).get("by_module") or {}
after_failed = (after.get("failed_outbox") or {}).get("by_module") or {}
modules = sorted(set(before_failed.keys()) | set(after_failed.keys()))
failed_delta = {
    m: int(after_failed.get(m, 0)) - int(before_failed.get(m, 0))
    for m in modules
}
no_failed_growth = all(delta <= 0 for delta in failed_delta.values())

reasons = []
if billing_p95 > 400.0:
    reasons.append(f"billing_write_ms p95={billing_p95:.2f} > 400")
if inventory_p95 > 400.0:
    reasons.append(f"inventory_write_ms p95={inventory_p95:.2f} > 400")
if posting_p95 > 400.0:
    reasons.append(f"posting_cycle_ms p95={posting_p95:.2f} > 400")
if error_rate > 0.01:
    reasons.append(f"operational_error_rate={error_rate:.4f} > 0.01")
if not no_failed_growth:
    reasons.append(f"failed_outbox_growth_detected={failed_delta}")

report = {
    "gate_name": "operational_performance_balance_profile",
    "passed": len(reasons) == 0,
    "k6": {
        "billing_write_ms_p95": billing_p95,
        "inventory_write_ms_p95": inventory_p95,
        "posting_cycle_ms_p95": posting_p95,
        "operational_error_rate": error_rate,
    },
    "outbox_failed": {
        "before_by_module": before_failed,
        "after_by_module": after_failed,
        "delta_by_module": failed_delta,
        "no_growth": no_failed_growth,
    },
    "reasons": reasons,
}

raw = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
report_path.write_text(raw, encoding="utf-8")
digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
hash_path.write_text(f"{digest}  {report_path.name}\n", encoding="utf-8")

print(raw)
if not report["passed"]:
    raise SystemExit(1)
PY

echo "Gate OK. Evidencia: ${OUT_DIR}"
