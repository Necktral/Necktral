#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${ROOT_DIR}/backend/src"
TS="${TS:-$(date +%Y%m%d_%H%M)}"
OUT_DIR="${OUT_DIR:-${ROOT_DIR}/docs/operacion/evidencia/post_f8_${TS}}"

COMPANY_ID="${COMPANY_ID:-5}"
BRANCH_ID="${BRANCH_ID:-6}"
PARENT_COMPANY_ID="${PARENT_COMPANY_ID:-5}"
COMPANY_IDS="${COMPANY_IDS:-5}"
YEAR="${YEAR:-$(date +%Y)}"
MONTH="${MONTH:-$(date +%m)}"

MODE="${1:-all}"

mkdir -p "${OUT_DIR}"
cd "${APP_DIR}"

resolve_python() {
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    if command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
      printf '%s\n' "${PYTHON_BIN}"
      return 0
    fi
    echo "[post-f8] PYTHON_BIN inválido: ${PYTHON_BIN}" >&2
    return 1
  fi
  if command -v python3 >/dev/null 2>&1; then
    printf '%s\n' "python3"
    return 0
  fi
  if command -v python >/dev/null 2>&1; then
    printf '%s\n' "python"
    return 0
  fi
  echo "[post-f8] no se encontró intérprete Python (python3/python)" >&2
  return 1
}

PYTHON_BIN="$(resolve_python)" || exit 127

IFS=' ' read -r -a COMPANY_IDS_ARR <<< "${COMPANY_IDS}"

run_phase9() {
  OUT_DIR="${OUT_DIR}" \
  COMPANY_ID="${COMPANY_ID}" \
  BRANCH_ID="${BRANCH_ID}" \
  PYTHON_BIN="${PYTHON_BIN}" \
  "${ROOT_DIR}/qa/run_phase9_go_live.sh" full
}

run_phase10() {
  OUT_DIR="${OUT_DIR}" \
  COMPANY_ID="${COMPANY_ID}" \
  BRANCH_ID="${BRANCH_ID}" \
  PYTHON_BIN="${PYTHON_BIN}" \
  "${ROOT_DIR}/qa/run_phase10_go_live.sh" full
}

run_phase11() {
  OUT_DIR="${OUT_DIR}" \
  COMPANY_ID="${COMPANY_ID}" \
  BRANCH_ID="${BRANCH_ID}" \
  PYTHON_BIN="${PYTHON_BIN}" \
  "${ROOT_DIR}/qa/run_phase11_go_live.sh" full
}

run_phase12() {
  OUT_DIR="${OUT_DIR}" \
  COMPANY_ID="${COMPANY_ID}" \
  BRANCH_ID="${BRANCH_ID}" \
  PARENT_COMPANY_ID="${PARENT_COMPANY_ID}" \
  COMPANY_IDS="${COMPANY_IDS}" \
  YEAR="${YEAR}" \
  MONTH="${MONTH}" \
  REQUIRED_PERIODS="${REQUIRED_PERIODS:-3}" \
  FX_BLOCKED_POLICY="${FX_BLOCKED_POLICY:-ALERT}" \
  PYTHON_BIN="${PYTHON_BIN}" \
  "${ROOT_DIR}/qa/run_phase12_go_live.sh" full
}

case "${MODE}" in
  phase9)
    run_phase9
    ;;
  phase10)
    run_phase10
    ;;
  phase11)
    run_phase11
    ;;
  phase12)
    run_phase12
    ;;
  all)
    run_phase9
    run_phase10
    run_phase11
    run_phase12
    ;;
  *)
    echo "Usage: $0 {phase9|phase10|phase11|phase12|all}" >&2
    exit 1
    ;;
esac

echo "[post-f8] done mode=${MODE} out=${OUT_DIR}"
