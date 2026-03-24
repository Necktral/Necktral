#!/usr/bin/env bash
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORTS_REL="${QA_REPORTS_DIR:-qa/reports}"
REPORTS_DIR="${ROOT_DIR}/${REPORTS_REL}"
QA_FRESH_DB="${QA_FRESH_DB:-0}"
QA_KEEP_FRONTEND="${QA_KEEP_FRONTEND:-1}"
MAKE_BIN="${MAKE_BIN:-make}"

mkdir -p "${REPORTS_DIR}"

LOG_FILE="${REPORTS_DIR}/qa-ci-run.log"
: > "${LOG_FILE}"
exec > >(tee -a "${LOG_FILE}") 2>&1

RUN_STARTED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
RUN_START_EPOCH="$(date +%s)"
STEPS_FILE="${REPORTS_DIR}/run_steps.tsv"

setup_status="skipped"
gate1_status="skipped"
gate2_status="skipped"
gate3_status="skipped"
preflight_status="skipped"
frontend_quality_status="skipped"
frontend_bundle_budget_status="skipped"
gate2_tests_status="skipped"
gate2_coverage_status="skipped"
gate2_reports_contracts_status="skipped"
gate3_audit_status="skipped"
run_status="passed"
failed_gate=""
failed_step=""

cleanup_reports() {
  rm -f \
    "${REPORTS_DIR}/static_scan.txt" \
    "${REPORTS_DIR}/bandit.txt" \
    "${REPORTS_DIR}/ruff.txt" \
    "${REPORTS_DIR}/mypy_strict_critical.txt" \
    "${REPORTS_DIR}/mypy.txt" \
    "${REPORTS_DIR}/mypy_delta.json" \
    "${REPORTS_DIR}/mypy_delta.txt" \
    "${REPORTS_DIR}/pytest.xml" \
    "${REPORTS_DIR}/coverage.xml" \
    "${REPORTS_DIR}/coverage.txt" \
    "${REPORTS_DIR}/coverage_by_domain.json" \
    "${REPORTS_DIR}/coverage_by_domain.md" \
    "${REPORTS_DIR}/reports_contract_check.txt" \
    "${REPORTS_DIR}/reports_repro_check.txt" \
    "${REPORTS_DIR}/frontend_bundle_budget.json" \
    "${REPORTS_DIR}/frontend_bundle_budget.md" \
    "${REPORTS_DIR}/audit_integrity.json" \
    "${REPORTS_DIR}/run_manifest.json" \
    "${STEPS_FILE}"
}

make_cmd() {
  "${MAKE_BIN}" QA_REPORTS_DIR="${REPORTS_REL}" QA_FRESH_DB="${QA_FRESH_DB}" "$@"
}

run_step() {
  local step_name="$1"
  local status_var="$2"
  shift 2

  local started_epoch started_at finished_epoch finished_at duration_sec step_status rc
  started_epoch="$(date +%s)"
  started_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  echo "[qa][step] ${step_name} START ${started_at}"

  if "$@"; then
    rc=0
    step_status="passed"
  else
    rc=$?
    step_status="failed"
  fi

  finished_epoch="$(date +%s)"
  finished_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
  duration_sec="$((finished_epoch - started_epoch))"
  printf -v "${status_var}" '%s' "${step_status}"
  echo "${step_name}|${step_status}|${started_at}|${finished_at}|${duration_sec}" >> "${STEPS_FILE}"
  echo "[qa][step] ${step_name} ${step_status} duration=${duration_sec}s"
  return "${rc}"
}

emit_manifest() {
  local run_finished_at
  run_finished_at="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"

  python "${ROOT_DIR}/qa/emit_run_manifest.py" \
    --reports-dir "${REPORTS_DIR}" \
    --run-start-epoch "${RUN_START_EPOCH}" \
    --run-started-at "${RUN_STARTED_AT}" \
    --run-finished-at "${run_finished_at}" \
    --setup-status "${setup_status}" \
    --gate1-status "${gate1_status}" \
    --gate2-status "${gate2_status}" \
    --gate3-status "${gate3_status}" \
    --run-status "${run_status}" \
    --failed-gate "${failed_gate}" \
    --failed-step "${failed_step}" \
    --steps-file "${STEPS_FILE}"
}

ensure_frontend_up() {
  if [[ "${QA_KEEP_FRONTEND}" != "1" ]]; then
    echo "[qa] QA_KEEP_FRONTEND=${QA_KEEP_FRONTEND}: frontend auto-start deshabilitado."
    return
  fi

  echo "[qa] ensuring frontend is up on http://localhost:3100 ..."
  if docker compose up -d frontend; then
    echo "[qa] frontend service ensured."
  else
    echo "[qa] WARNING: failed to auto-start frontend service."
  fi
}

cd "${ROOT_DIR}"
cleanup_reports
: > "${STEPS_FILE}"

echo "[qa] run_started_at=${RUN_STARTED_AT}"
echo "[qa] reports_dir=${REPORTS_REL}"

if ! run_step "setup" setup_status make_cmd qa-ci-up; then
  setup_status="failed"
  run_status="failed"
  failed_gate="setup"
  failed_step="setup"
fi

if [[ "${run_status}" == "passed" ]]; then
  if run_step "preflight" preflight_status make_cmd qa-ci-preflight; then
    if run_step "frontend_quality" frontend_quality_status make_cmd qa-frontend-quality; then
      if run_step "frontend_bundle_budget" frontend_bundle_budget_status make_cmd qa-frontend-bundle-budget; then
        gate1_status="passed"
      else
        gate1_status="failed"
        run_status="failed"
        failed_gate="gate1"
        failed_step="frontend_bundle_budget"
      fi
    else
      gate1_status="failed"
      run_status="failed"
      failed_gate="gate1"
      failed_step="frontend_quality"
    fi
  else
    gate1_status="failed"
    run_status="failed"
    failed_gate="gate1"
    failed_step="preflight"
  fi
fi

if [[ "${run_status}" == "passed" ]]; then
  if run_step "gate2_tests" gate2_tests_status make_cmd qa-backend-tests; then
    if run_step "gate2_coverage" gate2_coverage_status make_cmd qa-coverage-domains; then
      if run_step "gate2_reports_contracts" gate2_reports_contracts_status make_cmd qa-reports-contract-check; then
        gate2_status="passed"
      else
        gate2_status="failed"
        run_status="failed"
        failed_gate="gate2"
        failed_step="gate2_reports_contracts"
      fi
    else
      gate2_status="failed"
      run_status="failed"
      failed_gate="gate2"
      failed_step="gate2_coverage"
    fi
  else
    gate2_status="failed"
    run_status="failed"
    failed_gate="gate2"
    failed_step="gate2_tests"
  fi
fi

if [[ "${run_status}" == "passed" ]]; then
  if run_step "gate3_audit" gate3_audit_status make_cmd qa-audit-integrity; then
    gate3_status="passed"
  else
    gate3_status="failed"
    run_status="failed"
    failed_gate="gate3"
    failed_step="gate3_audit"
  fi
fi

emit_manifest
ensure_frontend_up

if [[ "${run_status}" != "passed" ]]; then
  echo "[qa] FAILED at ${failed_gate} (step=${failed_step})"
  exit 1
fi

echo "[qa] PASSED"
exit 0
