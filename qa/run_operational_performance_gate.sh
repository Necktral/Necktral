#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
K6_BIN="${K6_BIN:-k6}"
K6_IMAGE="${K6_IMAGE:-grafana/k6}"
NETWORK_NAME="${NETWORK_NAME:-erp_crm_default}"
USE_DOCKER_K6=0
HOST_UID="$(id -u)"
HOST_GID="$(id -g)"
MANAGE_PY="${ROOT_DIR}/backend/src/manage.py"
K6_SCRIPT="${ROOT_DIR}/qa/k6/operational_posting_load.js"

BASE_URL="${BASE_URL:-http://localhost:8000/api}"
COMPANY_ID="${COMPANY_ID:-}"
BRANCH_ID="${BRANCH_ID:-}"
USERNAME="${USERNAME:-}"
PASSWORD="${PASSWORD:-}"
AUTH_TRANSPORT="${AUTH_TRANSPORT:-}"

if [[ -z "${COMPANY_ID}" || -z "${BRANCH_ID}" ]]; then
  echo "ERROR: COMPANY_ID y BRANCH_ID son requeridos." >&2
  exit 2
fi
if [[ -z "${USERNAME}" || -z "${PASSWORD}" ]]; then
  echo "ERROR: USERNAME y PASSWORD son requeridos." >&2
  exit 2
fi

if command -v "${K6_BIN}" >/dev/null 2>&1; then
  USE_DOCKER_K6=0
else
  if ! command -v docker >/dev/null 2>&1; then
    echo "ERROR: no se encontró '${K6_BIN}' en PATH y docker no está disponible para fallback." >&2
    exit 2
  fi
  USE_DOCKER_K6=1
  echo "WARN: no se encontró '${K6_BIN}' en PATH; se usará fallback con contenedor ${K6_IMAGE}." >&2
fi

if [[ "${USE_DOCKER_K6}" -eq 1 ]] && [[ "${BASE_URL}" =~ localhost|127\.0\.0\.1 ]]; then
  BASE_URL="http://backend:8000/api"
  echo "WARN: BASE_URL ajustado a ${BASE_URL} para ejecución de k6 en contenedor." >&2
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
if [[ -n "${SLEEP:-}" ]]; then
  K6_ARGS+=(-e "SLEEP=${SLEEP}")
fi
if [[ -n "${POSTING_LIMIT:-}" ]]; then
  K6_ARGS+=(-e "POSTING_LIMIT=${POSTING_LIMIT}")
fi
if [[ -n "${AUTH_TRANSPORT}" ]]; then
  K6_ARGS+=(-e "AUTH_TRANSPORT=${AUTH_TRANSPORT}")
fi
K6_EXIT_CODE=0
if [[ "${USE_DOCKER_K6}" -eq 0 ]]; then
  set +e
  "${K6_BIN}" "${K6_ARGS[@]}"
  K6_EXIT_CODE=$?
  set -e
else
  K6_SUMMARY_CONTAINER="/workspace/${K6_SUMMARY#${ROOT_DIR}/}"
  if ! docker network ls --format '{{.Name}}' | grep -qx "${NETWORK_NAME}"; then
    echo "ERROR: red Docker '${NETWORK_NAME}' no encontrada para fallback k6." >&2
    echo "Sugerencia: docker compose up -d db backend" >&2
    exit 2
  fi
  set +e
  docker run --rm -i \
    --user "${HOST_UID}:${HOST_GID}" \
    --network "${NETWORK_NAME}" \
    -v "${ROOT_DIR}:/workspace" \
    -w /workspace \
    "${K6_IMAGE}" \
    run \
    "/workspace/${K6_SCRIPT#${ROOT_DIR}/}" \
    --summary-export "${K6_SUMMARY_CONTAINER}" \
    "${K6_ARGS[@]:4}"
  K6_EXIT_CODE=$?
  set -e
fi

echo "[3/4] Exportando snapshot final..."
"${PYTHON_BIN}" "${MANAGE_PY}" export_operational_load_snapshot \
  --company-id "${COMPANY_ID}" \
  --branch-id "${BRANCH_ID}" \
  --output "${SNAPSHOT_AFTER}"

echo "[4/4] Evaluando gate SLO..."
"${PYTHON_BIN}" - <<'PY' "${K6_SUMMARY}" "${SNAPSHOT_BEFORE}" "${SNAPSHOT_AFTER}" "${GATE_REPORT}" "${GATE_HASH}" "${K6_EXIT_CODE}"
import hashlib
import json
import sys
from pathlib import Path

summary_path = Path(sys.argv[1])
before_path = Path(sys.argv[2])
after_path = Path(sys.argv[3])
report_path = Path(sys.argv[4])
hash_path = Path(sys.argv[5])
k6_exit_code = int(sys.argv[6])
if summary_path.exists():
    summary = json.loads(summary_path.read_text(encoding="utf-8"))
else:
    summary = {}
before = json.loads(before_path.read_text(encoding="utf-8"))
after = json.loads(after_path.read_text(encoding="utf-8"))

metrics = summary.get("metrics", {})
def metric_row(name: str) -> dict:
    row = metrics.get(name, {})
    values = row.get("values", {}) if isinstance(row, dict) else {}
    if isinstance(row, dict):
        return {**row, **values}
    return {}

def metric_value(name: str, key: str, default: float = 0.0) -> float:
    merged = metric_row(name)
    try:
        return float(merged.get(key, default))
    except Exception:
        return float(default)

def metric_has_key(name: str, key: str) -> bool:
    merged = metric_row(name)
    return key in merged

billing_p95 = metric_value("billing_write_ms", "p(95)")
inventory_p95 = metric_value("inventory_write_ms", "p(95)")
posting_p95 = metric_value("posting_cycle_ms", "p(95)")
error_rate = metric_value("operational_error_rate", "rate", default=metric_value("operational_error_rate", "value"))
billing_count = metric_value("billing_write_ms", "count") if metric_has_key("billing_write_ms", "count") else None
inventory_count = metric_value("inventory_write_ms", "count") if metric_has_key("inventory_write_ms", "count") else None
posting_count = metric_value("posting_cycle_ms", "count") if metric_has_key("posting_cycle_ms", "count") else None
http_reqs_count = metric_value("http_reqs", "count")
iterations_count = metric_value("iterations", "count")

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
if iterations_count < 1:
    reasons.append("iterations_missing_or_zero")
if http_reqs_count < 1:
    reasons.append("http_reqs_missing_or_zero")
if not metric_has_key("billing_write_ms", "p(95)"):
    reasons.append("billing_write_ms_samples_missing")
if not metric_has_key("inventory_write_ms", "p(95)"):
    reasons.append("inventory_write_ms_samples_missing")
if not metric_has_key("posting_cycle_ms", "p(95)"):
    reasons.append("posting_cycle_ms_samples_missing")
if k6_exit_code != 0:
    reasons.append(f"k6_exit_code={k6_exit_code}")

report = {
    "gate_name": "operational_performance_balance_profile",
    "passed": len(reasons) == 0,
    "k6_exit_code": int(k6_exit_code),
    "k6": {
        "iterations_count": iterations_count,
        "http_reqs_count": http_reqs_count,
        "billing_write_ms_count": billing_count,
        "inventory_write_ms_count": inventory_count,
        "posting_cycle_ms_count": posting_count,
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
