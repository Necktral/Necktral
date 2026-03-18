#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${ROOT_DIR}/backend/src"
PYTHON_BIN="${PYTHON_BIN:-python3}"
MODE="${1:-full}"

TS="${TS:-$(date +%Y%m%d_%H%M%S)}"
OUT_DIR="${OUT_DIR:-${ROOT_DIR}/docs/operacion/evidencia/operational_go_live_${TS}}"
mkdir -p "${OUT_DIR}"

COMPANY_ID="${COMPANY_ID:-}"
BRANCH_ID="${BRANCH_ID:-}"
USERNAME="${USERNAME:-k6_operational}"
PASSWORD="${PASSWORD:-}"
BASE_URL="${BASE_URL:-http://localhost:8000/api}"
REQUIRED_DAYS="${REQUIRED_DAYS:-7}"
MAX_FAILED_OUTBOX="${MAX_FAILED_OUTBOX:-0}"
MAX_RECONCILIATION_MISMATCH="${MAX_RECONCILIATION_MISMATCH:-0}"
MAX_DRAFT_EXCEPTION="${MAX_DRAFT_EXCEPTION:-0}"
MAX_PENDING_OPERATIONAL="${MAX_PENDING_OPERATIONAL:-0}"
MAX_FUEL_PENDING="${MAX_FUEL_PENDING:-0}"
MAX_FUEL_FAILED="${MAX_FUEL_FAILED:-0}"
REQUIRE_PERFORMANCE_PASS="${REQUIRE_PERFORMANCE_PASS:-1}"
REQUIRE_OWNER_APPROVALS="${REQUIRE_OWNER_APPROVALS:-1}"
REQUIRE_FINAL_SIGNOFF="${REQUIRE_FINAL_SIGNOFF:-1}"
REQUIRE_CLOSE_OK="${REQUIRE_CLOSE_OK:-0}"
ALLOW_EXCUSED_DAYS="${ALLOW_EXCUSED_DAYS:-0}"
MAX_EXCUSED_DAYS="${MAX_EXCUSED_DAYS:-0}"
MAX_CALENDAR_DAYS="${MAX_CALENDAR_DAYS:-0}"
EXCUSED_DAY_PATTERN="${EXCUSED_DAY_PATTERN:-**/operational_go_live_excused_day_*.json}"
AUTO_SIGNOFF="${AUTO_SIGNOFF:-0}"
AUTO_SIGNOFF_DATE="${AUTO_SIGNOFF_DATE:-}"
FUNCTIONAL_REVIEWER="${FUNCTIONAL_REVIEWER:-functional_owner}"
TECHNICAL_REVIEWER="${TECHNICAL_REVIEWER:-technical_owner}"
FINAL_SIGNOFF_REVIEWER="${FINAL_SIGNOFF_REVIEWER:-${TECHNICAL_REVIEWER}}"
FUNCTIONAL_SUMMARY="${FUNCTIONAL_SUMMARY:-Functional checklist approved for pilot go-live.}"
TECHNICAL_SUMMARY="${TECHNICAL_SUMMARY:-Technical checklist approved for pilot go-live.}"
FINAL_SIGNOFF_SUMMARY="${FINAL_SIGNOFF_SUMMARY:-Final go-live signoff approved for pilot scope.}"

if [[ -z "${COMPANY_ID}" || -z "${BRANCH_ID}" ]]; then
  echo "ERROR: COMPANY_ID y BRANCH_ID son requeridos." >&2
  exit 2
fi
if [[ "${MODE}" == "full" && -z "${PASSWORD}" ]]; then
  echo "ERROR: PASSWORD es requerido en modo full." >&2
  exit 2
fi

run_manage() {
  (
    cd "${APP_DIR}"
    "${PYTHON_BIN}" manage.py "$@"
  )
}

record_go_live_review() {
  local reviewer="${1}"
  local role="${2}"
  local status="${3}"
  local summary="${4}"
  shift 4
  local linked=("$@")

  local cmd=(
    record_operational_go_live_review
    --evidence-dir "${OUT_DIR}"
    --reviewer "${reviewer}"
    --role "${role}"
    --status "${status}"
    --summary "${summary}"
  )
  if [[ -n "${AUTO_SIGNOFF_DATE}" ]]; then
    cmd+=(--date "${AUTO_SIGNOFF_DATE}")
  fi
  if [[ ${#linked[@]} -gt 0 ]]; then
    cmd+=(--linked-evidence "${linked[@]}")
  fi
  run_manage "${cmd[@]}"
}

run_full() {
  local perf_dir="${OUT_DIR}/performance"
  local pilot_dir="${OUT_DIR}/pilot"
  mkdir -p "${perf_dir}" "${pilot_dir}"

  OUT_DIR="${perf_dir}" \
  BASE_URL="${BASE_URL}" \
  COMPANY_ID="${COMPANY_ID}" \
  BRANCH_ID="${BRANCH_ID}" \
  USERNAME="${USERNAME}" \
  PASSWORD="${PASSWORD}" \
  DURATION="${DURATION:-2m}" \
  BILLING_VUS="${BILLING_VUS:-6}" \
  INVENTORY_VUS="${INVENTORY_VUS:-6}" \
  POSTING_VUS="${POSTING_VUS:-1}" \
  "${ROOT_DIR}/qa/run_operational_performance_gate.sh"

  OUT_DIR="${pilot_dir}" COMPANY_ID="${COMPANY_ID}" BRANCH_ID="${BRANCH_ID}" \
    "${ROOT_DIR}/qa/run_operational_pilot_rollout.sh" stage1
  OUT_DIR="${pilot_dir}" COMPANY_ID="${COMPANY_ID}" BRANCH_ID="${BRANCH_ID}" \
    "${ROOT_DIR}/qa/run_operational_pilot_rollout.sh" stage2
  OUT_DIR="${pilot_dir}" COMPANY_ID="${COMPANY_ID}" BRANCH_ID="${BRANCH_ID}" ATTEMPT_CLOSE=1 \
    "${ROOT_DIR}/qa/run_operational_pilot_rollout.sh" stage3
}

run_auto_signoff_if_enabled() {
  if [[ "${AUTO_SIGNOFF}" != "1" ]]; then
    return 0
  fi

  local linked=()
  if [[ -f "${OUT_DIR}/performance/gate_report.json" ]]; then
    linked+=("${OUT_DIR}/performance/gate_report.json")
  fi
  if [[ -f "${OUT_DIR}/pilot/pilot_stage3.json" ]]; then
    linked+=("${OUT_DIR}/pilot/pilot_stage3.json")
  fi
  if [[ -f "${OUT_DIR}/pilot/pilot_stage3_close.json" ]]; then
    linked+=("${OUT_DIR}/pilot/pilot_stage3_close.json")
  fi

  record_go_live_review "${FUNCTIONAL_REVIEWER}" "FUNCTIONAL" "APPROVED" "${FUNCTIONAL_SUMMARY}" "${linked[@]}"
  record_go_live_review "${TECHNICAL_REVIEWER}" "TECHNICAL" "APPROVED" "${TECHNICAL_SUMMARY}" "${linked[@]}"
  record_go_live_review "${FINAL_SIGNOFF_REVIEWER}" "TECHNICAL" "FINAL_APPROVED" "${FINAL_SIGNOFF_SUMMARY}" "${linked[@]}"
}

run_verify() {
  if [[ "${AUTO_SIGNOFF}" == "1" ]]; then
    run_auto_signoff_if_enabled
  elif [[ ! -f "${OUT_DIR}/operational_go_live_final_signoff.json" ]]; then
    cat <<EOF
WARNING: no se detecto operational_go_live_final_signoff.json en ${OUT_DIR}
Registre aprobacion funcional, tecnica y signoff final con:
  cd ${APP_DIR}
  ${PYTHON_BIN} manage.py record_operational_go_live_review --evidence-dir "${OUT_DIR}" --reviewer "<owner>" --role FUNCTIONAL --status APPROVED --summary "<resumen>"
  ${PYTHON_BIN} manage.py record_operational_go_live_review --evidence-dir "${OUT_DIR}" --reviewer "<owner>" --role TECHNICAL --status APPROVED --summary "<resumen>"
  ${PYTHON_BIN} manage.py record_operational_go_live_review --evidence-dir "${OUT_DIR}" --reviewer "<owner>" --role TECHNICAL --status FINAL_APPROVED --summary "<resumen>"
EOF
  fi

  local out_json="${OUT_DIR}/operational_go_live_gate.json"
  local out_hash="${OUT_DIR}/operational_go_live_gate.sha256"
  local cmd=(
    verify_operational_pilot_go_live
    --evidence-dir "${OUT_DIR}"
    --required-days "${REQUIRED_DAYS}"
    --max-failed-outbox "${MAX_FAILED_OUTBOX}"
    --max-reconciliation-mismatch "${MAX_RECONCILIATION_MISMATCH}"
    --max-draft-exception "${MAX_DRAFT_EXCEPTION}"
    --max-pending-operational "${MAX_PENDING_OPERATIONAL}"
    --max-fuel-pending "${MAX_FUEL_PENDING}"
    --max-fuel-failed "${MAX_FUEL_FAILED}"
    --max-excused-days "${MAX_EXCUSED_DAYS}"
    --max-calendar-days "${MAX_CALENDAR_DAYS}"
    --excused-day-pattern "${EXCUSED_DAY_PATTERN}"
    --output "${out_json}"
  )
  if [[ "${REQUIRE_PERFORMANCE_PASS}" != "1" ]]; then
    cmd+=(--no-require-performance-pass)
  fi
  if [[ "${REQUIRE_OWNER_APPROVALS}" != "1" ]]; then
    cmd+=(--no-require-owner-approvals)
  fi
  if [[ "${REQUIRE_FINAL_SIGNOFF}" != "1" ]]; then
    cmd+=(--no-require-final-signoff)
  fi
  if [[ "${REQUIRE_CLOSE_OK}" == "1" ]]; then
    cmd+=(--require-close-ok)
  fi
  if [[ "${ALLOW_EXCUSED_DAYS}" == "1" ]]; then
    cmd+=(--allow-excused-days)
  fi

  run_manage "${cmd[@]}"

  "${PYTHON_BIN}" - <<'PY' "${out_json}" "${out_hash}"
import hashlib
import json
import sys
from pathlib import Path

json_path = Path(sys.argv[1])
hash_path = Path(sys.argv[2])
raw = json_path.read_text(encoding="utf-8")
payload = json.loads(raw)
digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
hash_path.write_text(f"{digest}  {json_path.name}\n", encoding="utf-8")
print(json.dumps(
    {
        "go_live_passed": bool(payload.get("go_live_passed")),
        "risk_level": payload.get("risk_level"),
        "required_days": payload.get("required_days"),
        "checks": payload.get("checks"),
    },
    ensure_ascii=False,
    indent=2,
))
PY
}

case "${MODE}" in
  full)
    run_full
    run_verify
    ;;
  verify)
    run_verify
    ;;
  *)
    echo "Uso: $0 [full|verify]" >&2
    exit 2
    ;;
esac

echo "Operational go-live (${MODE}) finalizado. Evidencia: ${OUT_DIR}"
