#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${ROOT_DIR}/backend/src"
TS="${TS:-$(date +%Y%m%d_%H%M)}"
MODE="${1:-full}"

COMPANY_ID="${COMPANY_ID:-5}"
BRANCH_ID="${BRANCH_ID:-6}"
PARENT_COMPANY_ID="${PARENT_COMPANY_ID:-5}"
COMPANY_IDS="${COMPANY_IDS:-5}"
CONSUMER="${CONSUMER:-accounting.projector}"
YEAR="${YEAR:-$(date +%Y)}"
MONTH="${MONTH:-$(date +%m)}"
MIN_BURNIN_DAYS="${MIN_BURNIN_DAYS:-14}"
PHASE8_START_DATE="${PHASE8_START_DATE:-2026-03-09}"
PHASE8_END_DATE="${PHASE8_END_DATE:-2026-03-22}"

MAX_INBOX_FAILED="${MAX_INBOX_FAILED:-0}"
MAX_OUTBOX_FAILED="${MAX_OUTBOX_FAILED:-0}"
MAX_MISSING_LINES="${MAX_MISSING_LINES:-0}"
MAX_STALE_REVALUATION="${MAX_STALE_REVALUATION:-0}"
MAX_OPEN_INTERCOMPANY="${MAX_OPEN_INTERCOMPANY:-0}"
MAX_DISPUTED_INTERCOMPANY="${MAX_DISPUTED_INTERCOMPANY:-0}"

OUT_DIR="${OUT_DIR:-${ROOT_DIR}/docs/operacion/evidencia/phase8_go_live_${TS}}"
mkdir -p "${OUT_DIR}"

STAGING_MANIFEST="${STAGING_MANIFEST:-}"
SECURITY_SUMMARY="${SECURITY_SUMMARY:-${ROOT_DIR}/docs/operacion/evidencia/bug_bounty_local_20260309_0141/30_bug_bounty_summary.json}"
PHASE6_BLOCKED_EVIDENCE="${PHASE6_BLOCKED_EVIDENCE:-}"
PHASE7_BLOCKED_EVIDENCE="${PHASE7_BLOCKED_EVIDENCE:-}"
RUN_ID="${RUN_ID:-}"

resolve_python() {
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    if command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
      printf '%s\n' "${PYTHON_BIN}"
      return 0
    fi
    echo "[phase8] PYTHON_BIN inválido: ${PYTHON_BIN}" >&2
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
  echo "[phase8] no se encontró intérprete Python (python3/python)" >&2
  return 1
}

PYTHON_BIN="$(resolve_python)" || exit 127

function require_file() {
  local path="$1"
  local label="$2"
  if [[ -z "${path}" || ! -f "${path}" ]]; then
    echo "[phase8] missing ${label}: ${path}" >&2
    exit 2
  fi
}

function run_precutover() {
  require_file "${STAGING_MANIFEST}" "STAGING_MANIFEST"
  require_file "${SECURITY_SUMMARY}" "SECURITY_SUMMARY"
  cd "${APP_DIR}"
  "${PYTHON_BIN}" manage.py export_phase8_release_baseline \
    --company-id "${COMPANY_ID}" \
    --branch-id "${BRANCH_ID}" \
    --parent-company-id "${PARENT_COMPANY_ID}" \
    --company-ids ${COMPANY_IDS} \
    --output "${OUT_DIR}/01_phase8_release_baseline.json"

  "${PYTHON_BIN}" manage.py export_phase8_env_manifest \
    --company-id "${COMPANY_ID}" \
    --branch-id "${BRANCH_ID}" \
    --parent-company-id "${PARENT_COMPANY_ID}" \
    --company-ids ${COMPANY_IDS} \
    --output "${OUT_DIR}/02_phase8_prod_manifest.json"

  "${PYTHON_BIN}" manage.py compare_phase8_env_manifests \
    --left "${STAGING_MANIFEST}" \
    --right "${OUT_DIR}/02_phase8_prod_manifest.json" \
    --strict

  "${PYTHON_BIN}" manage.py export_staging_preflight_manifest \
    --company-id "${COMPANY_ID}" \
    --branch-id "${BRANCH_ID}" \
    --max-inbox-failed "${MAX_INBOX_FAILED}" \
    --max-outbox-failed "${MAX_OUTBOX_FAILED}" \
    --max-missing-lines "${MAX_MISSING_LINES}" \
    --max-stale-revaluation "${MAX_STALE_REVALUATION}" \
    --max-open-intercompany "${MAX_OPEN_INTERCOMPANY}" \
    --max-disputed "${MAX_DISPUTED_INTERCOMPANY}" \
    --output "${OUT_DIR}/03_preflight.json"

  "${PYTHON_BIN}" manage.py export_finance_operational_snapshot \
    --company-id "${COMPANY_ID}" \
    --branch-id "${BRANCH_ID}" \
    --max-inbox-failed "${MAX_INBOX_FAILED}" \
    --max-outbox-failed "${MAX_OUTBOX_FAILED}" \
    --max-missing-lines "${MAX_MISSING_LINES}" \
    --max-stale-revaluation "${MAX_STALE_REVALUATION}" \
    --max-open-intercompany "${MAX_OPEN_INTERCOMPANY}" \
    --max-disputed "${MAX_DISPUTED_INTERCOMPANY}" \
    --output "${OUT_DIR}/04_snapshot.json"

  "${PYTHON_BIN}" manage.py verify_phase8_precutover \
    --company-id "${COMPANY_ID}" \
    --branch-id "${BRANCH_ID}" \
    --parent-company-id "${PARENT_COMPANY_ID}" \
    --company-ids ${COMPANY_IDS} \
    --staging-manifest "${STAGING_MANIFEST}" \
    --prod-manifest "${OUT_DIR}/02_phase8_prod_manifest.json" \
    --release-baseline "${OUT_DIR}/01_phase8_release_baseline.json" \
    --preflight-report "${OUT_DIR}/03_preflight.json" \
    --snapshot-report "${OUT_DIR}/04_snapshot.json" \
    --security-summary "${SECURITY_SUMMARY}" \
    --max-inbox-failed "${MAX_INBOX_FAILED}" \
    --max-outbox-failed "${MAX_OUTBOX_FAILED}" \
    --max-missing-lines "${MAX_MISSING_LINES}" \
    --max-stale-revaluation "${MAX_STALE_REVALUATION}" \
    --max-open-intercompany "${MAX_OPEN_INTERCOMPANY}" \
    --max-disputed-intercompany "${MAX_DISPUTED_INTERCOMPANY}" \
    --output "${OUT_DIR}/05_precutover_gate.json"
}

function run_cutover() {
  require_file "${STAGING_MANIFEST}" "STAGING_MANIFEST"
  require_file "${PHASE6_BLOCKED_EVIDENCE}" "PHASE6_BLOCKED_EVIDENCE"
  require_file "${PHASE7_BLOCKED_EVIDENCE}" "PHASE7_BLOCKED_EVIDENCE"
  if [[ -z "${RUN_ID}" ]]; then
    echo "[phase8] RUN_ID is required for cutover" >&2
    exit 2
  fi
  cd "${APP_DIR}"

  "${PYTHON_BIN}" manage.py certify_adapter_b_run \
    --company-id "${COMPANY_ID}" \
    --branch-id "${BRANCH_ID}" \
    --output "${OUT_DIR}/10_phase6_happy.json"

  "${PYTHON_BIN}" manage.py certify_phase7_gl_run \
    --company-id "${COMPANY_ID}" \
    --run-id "${RUN_ID}" \
    --year "${YEAR}" \
    --month "${MONTH}" \
    --output "${OUT_DIR}/11_phase7_happy.json"

  "${PYTHON_BIN}" manage.py certify_phase7b_consolidation \
    --parent-company-id "${PARENT_COMPANY_ID}" \
    --year "${YEAR}" \
    --month "${MONTH}" \
    --company-ids ${COMPANY_IDS} \
    --output "${OUT_DIR}/12_phase7b_cert.json"

  "${PYTHON_BIN}" manage.py verify_phase6_go_live \
    --company-id "${COMPANY_ID}" \
    --branch-id "${BRANCH_ID}" \
    --staging-manifest "${STAGING_MANIFEST}" \
    --prod-manifest "${OUT_DIR}/02_phase8_prod_manifest.json" \
    --happy-evidence "${OUT_DIR}/10_phase6_happy.json" \
    --blocked-evidence "${PHASE6_BLOCKED_EVIDENCE}" \
    --max-inbox-failed "${MAX_INBOX_FAILED}" \
    --max-outbox-failed "${MAX_OUTBOX_FAILED}" \
    --output "${OUT_DIR}/13_phase6_gate.json"

  "${PYTHON_BIN}" manage.py verify_phase7_go_live \
    --company-id "${COMPANY_ID}" \
    --staging-manifest "${STAGING_MANIFEST}" \
    --prod-manifest "${OUT_DIR}/02_phase8_prod_manifest.json" \
    --happy-evidence "${OUT_DIR}/11_phase7_happy.json" \
    --blocked-evidence "${PHASE7_BLOCKED_EVIDENCE}" \
    --max-inbox-failed "${MAX_INBOX_FAILED}" \
    --max-outbox-failed "${MAX_OUTBOX_FAILED}" \
    --max-unbalanced-entries 0 \
    --max-missing-lines "${MAX_MISSING_LINES}" \
    --max-stale-revaluation "${MAX_STALE_REVALUATION}" \
    --output "${OUT_DIR}/14_phase7_gate.json"

  "${PYTHON_BIN}" manage.py verify_phase7b_go_live \
    --company-id "${COMPANY_ID}" \
    --certification "${OUT_DIR}/12_phase7b_cert.json" \
    --max-open-intercompany "${MAX_OPEN_INTERCOMPANY}" \
    --max-disputed-intercompany "${MAX_DISPUTED_INTERCOMPANY}" \
    --max-blocked-consolidation 0 \
    --max-open-consolidation-exception 0 \
    --max-inbox-failed "${MAX_INBOX_FAILED}" \
    --max-outbox-failed "${MAX_OUTBOX_FAILED}" \
    --output "${OUT_DIR}/15_phase7b_gate.json"

  "${PYTHON_BIN}" manage.py certify_phase8_cutover \
    --company-id "${COMPANY_ID}" \
    --branch-id "${BRANCH_ID}" \
    --parent-company-id "${PARENT_COMPANY_ID}" \
    --company-ids ${COMPANY_IDS} \
    --staging-manifest "${STAGING_MANIFEST}" \
    --prod-manifest "${OUT_DIR}/02_phase8_prod_manifest.json" \
    --phase6-gate "${OUT_DIR}/13_phase6_gate.json" \
    --phase7-gate "${OUT_DIR}/14_phase7_gate.json" \
    --phase7b-gate "${OUT_DIR}/15_phase7b_gate.json" \
    --max-inbox-failed "${MAX_INBOX_FAILED}" \
    --max-outbox-failed "${MAX_OUTBOX_FAILED}" \
    --max-missing-lines "${MAX_MISSING_LINES}" \
    --max-stale-revaluation "${MAX_STALE_REVALUATION}" \
    --max-open-intercompany "${MAX_OPEN_INTERCOMPANY}" \
    --max-disputed-intercompany "${MAX_DISPUTED_INTERCOMPANY}" \
    --output "${OUT_DIR}/16_phase8_cutover_gate.json"
}

function run_burnin_day() {
  cd "${APP_DIR}"
  local day_tag
  local today_local
  today_local="${TODAY_LOCAL:-$(date +%F)}"
  day_tag="${DAY_TAG:-${today_local//-/}}"
  "${PYTHON_BIN}" manage.py run_phase8_burnin_cycle \
    --company-id "${COMPANY_ID}" \
    --branch-id "${BRANCH_ID}" \
    --parent-company-id "${PARENT_COMPANY_ID}" \
    --company-ids ${COMPANY_IDS} \
    --year "${YEAR}" \
    --month "${MONTH}" \
    --max-inbox-failed "${MAX_INBOX_FAILED}" \
    --max-outbox-failed "${MAX_OUTBOX_FAILED}" \
    --max-missing-lines "${MAX_MISSING_LINES}" \
    --max-stale-revaluation "${MAX_STALE_REVALUATION}" \
    --max-open-intercompany "${MAX_OPEN_INTERCOMPANY}" \
    --max-disputed-intercompany "${MAX_DISPUTED_INTERCOMPANY}" \
    --output "${OUT_DIR}/phase8_burn_${day_tag}.json"

  "${PYTHON_BIN}" manage.py export_finance_operational_snapshot \
    --company-id "${COMPANY_ID}" \
    --branch-id "${BRANCH_ID}" \
    --max-inbox-failed "${MAX_INBOX_FAILED}" \
    --max-outbox-failed "${MAX_OUTBOX_FAILED}" \
    --max-missing-lines "${MAX_MISSING_LINES}" \
    --max-stale-revaluation "${MAX_STALE_REVALUATION}" \
    --max-open-intercompany "${MAX_OPEN_INTERCOMPANY}" \
    --max-disputed "${MAX_DISPUTED_INTERCOMPANY}" \
    --output "${OUT_DIR}/phase8_snapshot_${day_tag}.json"
}

function run_verify_burnin() {
  cd "${APP_DIR}"
  "${PYTHON_BIN}" manage.py verify_phase8_burn_in \
    --evidence-dir "${OUT_DIR}" \
    --min-days "${MIN_BURNIN_DAYS}" \
    --max-failed-days 0 \
    --strict > "${OUT_DIR}/17_phase8_burnin_verify.json"

  "${PYTHON_BIN}" manage.py verify_phase8_accountant_signoff \
    --evidence-dir "${OUT_DIR}" \
    --window-start "${PHASE8_START_DATE}" \
    --window-end "${PHASE8_END_DATE}" \
    --strict > "${OUT_DIR}/65_phase8_accountant_verify.json"
}

function run_rollback_check() {
  cd "${APP_DIR}"
  local burnin_files=()
  while IFS= read -r file; do
    burnin_files+=("${file}")
  done < <(find "${OUT_DIR}" -maxdepth 1 -type f -name "phase8_burn_*.json" | sort)
  "${PYTHON_BIN}" manage.py evaluate_phase8_rollback \
    --cutover-report "${OUT_DIR}/16_phase8_cutover_gate.json" \
    --burnin-reports "${burnin_files[@]}" \
    --sustained-minutes 15 \
    --output "${OUT_DIR}/18_phase8_rollback_eval.json"
}

case "${MODE}" in
  pre-cut)
    run_precutover
    ;;
  cutover)
    run_cutover
    ;;
  burnin-day)
    run_burnin_day
    ;;
  verify-burnin)
    run_verify_burnin
    ;;
  rollback-check)
    run_rollback_check
    ;;
  full)
    run_precutover
    run_cutover
    run_burnin_day
    run_verify_burnin
    run_rollback_check
    ;;
  *)
    echo "Usage: $0 {pre-cut|cutover|burnin-day|verify-burnin|rollback-check|full}" >&2
    exit 2
    ;;
esac

echo "[phase8] done mode=${MODE} output=${OUT_DIR}"
