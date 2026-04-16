#!/usr/bin/env bash
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORTS_REL="${QA_REPORTS_DIR:-qa/reports}"
REPORTS_DIR="${ROOT_DIR}/${REPORTS_REL}"
QA_FRESH_DB="${QA_FRESH_DB:-0}"
QA_KEEP_FRONTEND="${QA_KEEP_FRONTEND:-1}"
QA_PIPELINE_PROFILE="${QA_PIPELINE_PROFILE:-default}"
QA_PIPELINE_MANIFEST="${QA_PIPELINE_MANIFEST:-}"
QA_PIPELINE_OVERRIDES_JSON="${QA_PIPELINE_OVERRIDES_JSON:-[]}"
MAKE_BIN="${MAKE_BIN:-make}"

mkdir -p "${REPORTS_DIR}"

LOG_FILE="${REPORTS_DIR}/qa-ci-run.log"
: > "${LOG_FILE}"
exec > >(tee -a "${LOG_FILE}") 2>&1

RUN_STARTED_AT="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
RUN_START_EPOCH="$(date +%s)"

setup_status="skipped"
gate1_status="skipped"
gate2_status="skipped"
gate3_status="skipped"
run_status="passed"
failed_gate=""

cleanup_reports() {
  rm -f \
    "${REPORTS_DIR}/static_scan.txt" \
    "${REPORTS_DIR}/bandit.txt" \
    "${REPORTS_DIR}/ruff.txt" \
    "${REPORTS_DIR}/mypy_strict_critical.txt" \
    "${REPORTS_DIR}/mypy.txt" \
    "${REPORTS_DIR}/static_gate_summary.json" \
    "${REPORTS_DIR}/kernel_compat_usage.json" \
    "${REPORTS_DIR}/makemigrations_check.txt" \
    "${REPORTS_DIR}/migration_safety_guard.json" \
    "${REPORTS_DIR}/mypy_delta.json" \
    "${REPORTS_DIR}/mypy_delta.txt" \
    "${REPORTS_DIR}/reporting_contract_guard.json" \
    "${REPORTS_DIR}/route_contract_report.json" \
    "${REPORTS_DIR}/readme_section_guard.json" \
    "${REPORTS_DIR}/pr_blast_radius.json" \
    "${REPORTS_DIR}/package_install.txt" \
    "${REPORTS_DIR}/package_imports.txt" \
    "${REPORTS_DIR}/package_check.txt" \
    "${REPORTS_DIR}/architecture_dependency_guard.json" \
    "${REPORTS_DIR}/action_pin_guard.json" \
    "${REPORTS_DIR}/github_required_checks_guard.json" \
    "${REPORTS_DIR}/runner_hygiene_guard.json" \
    "${REPORTS_DIR}/security_exceptions_guard.json" \
    "${REPORTS_DIR}/security_findings_guard.json" \
    "${REPORTS_DIR}/release_evidence_u6.json" \
    "${REPORTS_DIR}/pytest.xml" \
    "${REPORTS_DIR}/coverage.xml" \
    "${REPORTS_DIR}/coverage.txt" \
    "${REPORTS_DIR}/sync_contract_guard.txt" \
    "${REPORTS_DIR}/inventory_offline_private_e2e_guard.txt" \
    "${REPORTS_DIR}/retail_pos_backend_contract_guard.txt" \
    "${REPORTS_DIR}/sync_pos_contract_guard.txt" \
    "${REPORTS_DIR}/frontend_pos_queue_contract_guard.txt" \
    "${REPORTS_DIR}/retail_pos_edge_simulator_guard.txt" \
    "${REPORTS_DIR}/retail_pos_edge_simulator_guard.json" \
    "${REPORTS_DIR}/retail_pos_edge_e2e_guard.txt" \
    "${REPORTS_DIR}/retail_pos_edge_e2e_guard.json" \
    "${REPORTS_DIR}/retail_pos_edge_e2e_request_response.json" \
    "${REPORTS_DIR}/coverage_by_domain.json" \
    "${REPORTS_DIR}/audit_integrity.json" \
    "${REPORTS_DIR}/reporting_r8_gate.json" \
    "${REPORTS_DIR}/reporting_r8_gate_guard.json" \
    "${REPORTS_DIR}/reporting_observability_snapshot.json" \
    "${REPORTS_DIR}/run_manifest.json"
}

make_cmd() {
  "${MAKE_BIN}" QA_REPORTS_DIR="${REPORTS_REL}" QA_FRESH_DB="${QA_FRESH_DB}" "$@"
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
    --profile "${QA_PIPELINE_PROFILE}" \
    --manifest "${QA_PIPELINE_MANIFEST}" \
    --overrides-json "${QA_PIPELINE_OVERRIDES_JSON}"
}

ensure_frontend_up() {
  if [[ "${QA_KEEP_FRONTEND}" != "1" ]]; then
    echo "[qa] QA_KEEP_FRONTEND=${QA_KEEP_FRONTEND}: frontend auto-start deshabilitado."
    return
  fi

  echo "[qa] ensuring frontend is up on http://localhost:3000 ..."
  if docker compose up -d frontend; then
    echo "[qa] frontend service ensured."
  else
    echo "[qa] WARNING: failed to auto-start frontend service."
  fi
}

cd "${ROOT_DIR}"
cleanup_reports

echo "[qa] run_started_at=${RUN_STARTED_AT}"
echo "[qa] reports_dir=${REPORTS_REL}"

if make_cmd qa-ci-up; then
  setup_status="passed"
else
  setup_status="failed"
  run_status="failed"
  failed_gate="setup"
fi

if [[ "${run_status}" == "passed" ]]; then
  if make_cmd qa-namespace-guard \
    && make_cmd qa-analytics-contract-guard \
    && make_cmd qa-route-contract-guard \
    && make_cmd qa-readme-section-guard \
    && make_cmd qa-pr-blast-radius-guard \
    && make_cmd qa-reporting-registry-guard \
    && make_cmd qa-reporting-contract-version-guard \
    && make_cmd qa-pythonpath-bootstrap-guard \
    && make_cmd qa-backend-package-check \
    && make_cmd qa-architecture-dependency-guard \
    && make_cmd qa-action-pin-guard \
    && make_cmd qa-github-required-checks-guard \
    && make_cmd qa-runner-hygiene-guard \
    && make_cmd qa-validate-security-exceptions \
    && make_cmd qa-security-findings-enforce \
    && make_cmd qa-static-scan \
    && make_cmd qa-backend-bandit \
    && make_cmd qa-backend-ruff \
    && make_cmd qa-backend-mypy \
    && make_cmd qa-verify-static-gate \
    && make_cmd qa-makemigrations-check \
    && make_cmd qa-migration-safety-guard \
    && make_cmd qa-frontend-ci; then
    gate1_status="passed"
  else
    gate1_status="failed"
    run_status="failed"
    failed_gate="gate1"
  fi
fi

if [[ "${run_status}" == "passed" ]]; then
  if make_cmd qa-backend-tests \
    && make_cmd qa-sync-contract-guard \
    && make_cmd qa-inventory-offline-private-e2e-guard \
    && make_cmd qa-retail-pos-backend-contract-guard \
    && make_cmd qa-retail-pos-sync-contract-guard \
    && make_cmd qa-retail-pos-frontend-queue-contract-guard \
    && make_cmd qa-retail-pos-edge-simulator-guard \
    && make_cmd qa-retail-pos-edge-e2e-guard \
    && make_cmd qa-coverage-by-domain-guard; then
    gate2_status="passed"
  else
    gate2_status="failed"
    run_status="failed"
    failed_gate="gate2"
  fi
fi

if [[ "${run_status}" == "passed" ]]; then
  if make_cmd qa-audit-integrity \
    && make_cmd qa-reporting-r8-gate \
    && make_cmd qa-verify-reporting-r8-gate-artifact \
    && make_cmd qa-export-u6-release-evidence; then
    gate3_status="passed"
  else
    gate3_status="failed"
    run_status="failed"
    failed_gate="gate3"
  fi
fi

emit_manifest
ensure_frontend_up

if [[ "${run_status}" != "passed" ]]; then
  echo "[qa] FAILED at ${failed_gate}"
  exit 1
fi

echo "[qa] PASSED"
exit 0
