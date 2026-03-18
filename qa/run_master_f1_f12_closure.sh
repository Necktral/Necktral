#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${ROOT_DIR}/backend/src"
MODE="${1:-all}"
TS="${TS:-$(date +%Y%m%d_%H%M%S)}"
OUT_DIR="${OUT_DIR:-${ROOT_DIR}/docs/operacion/evidencia/master_closure_${TS}}"

COMPANY_ID="${COMPANY_ID:-5}"
BRANCH_ID="${BRANCH_ID:-6}"
PARENT_COMPANY_ID="${PARENT_COMPANY_ID:-5}"
COMPANY_IDS="${COMPANY_IDS:-5}"
YEAR="${YEAR:-$(date +%Y)}"
MONTH="${MONTH:-$(date +%m)}"

mkdir -p "${OUT_DIR}"

resolve_python() {
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    if command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
      printf '%s\n' "${PYTHON_BIN}"
      return 0
    fi
    echo "[master] PYTHON_BIN invalido: ${PYTHON_BIN}" >&2
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
  echo "[master] no se encontro interprete Python" >&2
  return 1
}

PYTHON_BIN="$(resolve_python)" || exit 127

run_precheck() {
  {
    echo "timestamp=${TS}"
    echo "branch=$(git -C "${ROOT_DIR}" rev-parse --abbrev-ref HEAD)"
    echo "head=$(git -C "${ROOT_DIR}" rev-parse HEAD)"
    echo "company_id=${COMPANY_ID}"
    echo "branch_id=${BRANCH_ID}"
    echo "parent_company_id=${PARENT_COMPANY_ID}"
    echo "company_ids=${COMPANY_IDS}"
    echo "year=${YEAR}"
    echo "month=${MONTH}"
  } > "${OUT_DIR}/00_precheck.txt"
}

run_security() {
  local sec_ts
  sec_ts="${SECURITY_TS:-${TS}}"
  "${ROOT_DIR}/qa/run_bug_bounty_local.sh" "${sec_ts}"
  local sec_dir="${ROOT_DIR}/docs/operacion/evidencia/bug_bounty_local_${sec_ts}"
  if [[ ! -f "${sec_dir}/30_bug_bounty_summary.json" ]]; then
    echo "[master] no se encontro resumen de bug bounty en ${sec_dir}" >&2
    return 2
  fi
  cat > "${OUT_DIR}/10_security_pointer.json" <<JSON
{
  "security_ts": "${sec_ts}",
  "security_dir": "${sec_dir}",
  "summary": "${sec_dir}/30_bug_bounty_summary.json"
}
JSON
}

run_staging_recert() {
  mkdir -p "${OUT_DIR}/staging_recert"
  (
    cd "${APP_DIR}"
    "${PYTHON_BIN}" manage.py export_staging_preflight_manifest \
      --company-id "${COMPANY_ID}" \
      --branch-id "${BRANCH_ID}" \
      --max-inbox-failed 0 \
      --max-outbox-failed 0 \
      --max-missing-lines 0 \
      --max-stale-revaluation 0 \
      --max-open-intercompany 0 \
      --max-disputed 0 \
      --output "${OUT_DIR}/staging_recert/11_preflight.json"

    "${PYTHON_BIN}" manage.py export_finance_operational_snapshot \
      --company-id "${COMPANY_ID}" \
      --branch-id "${BRANCH_ID}" \
      --max-inbox-failed 0 \
      --max-outbox-failed 0 \
      --max-missing-lines 0 \
      --max-stale-revaluation 0 \
      --max-open-intercompany 0 \
      --max-disputed 0 \
      --output "${OUT_DIR}/staging_recert/12_snapshot.json"
  )

  OUT_DIR="${OUT_DIR}/staging_recert" \
  COMPANY_ID="${COMPANY_ID}" \
  BRANCH_ID="${BRANCH_ID}" \
  PARENT_COMPANY_ID="${PARENT_COMPANY_ID}" \
  COMPANY_IDS="${COMPANY_IDS}" \
  YEAR="${YEAR}" \
  MONTH="${MONTH}" \
  REQUIRED_PERIODS="${REQUIRED_PERIODS:-3}" \
  FX_BLOCKED_POLICY="${FX_BLOCKED_POLICY:-ALERT}" \
  PYTHON_BIN="${PYTHON_BIN}" \
  "${ROOT_DIR}/qa/run_post_f8_phases.sh" all
}

run_summary() {
  MASTER_OUT_DIR="${OUT_DIR}" \
  "${PYTHON_BIN}" - <<'PY'
from __future__ import annotations

import glob
import hashlib
import json
import os
from pathlib import Path

out = Path(os.environ["MASTER_OUT_DIR"])


def load_json(path: Path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

precheck = (out / "00_precheck.txt").read_text(encoding="utf-8", errors="ignore") if (out / "00_precheck.txt").exists() else ""
security_pointer = load_json(out / "10_security_pointer.json") or {}
security_summary = load_json(Path(security_pointer.get("summary", ""))) if security_pointer.get("summary") else None

staging = out / "staging_recert"
phase9_summary = load_json(staging / "30_phase9_summary.json")
phase10_summary = load_json(staging / "30_phase10_summary.json")
phase11_summary = load_json(staging / "30_phase11_summary.json")
phase12_summary = load_json(staging / "30_phase12_summary.json")

result = {
    "schema_version": 1,
    "precheck_present": bool(precheck.strip()),
    "security": {
        "status": (security_summary or {}).get("status"),
        "summary_path": security_pointer.get("summary"),
    },
    "staging": {
        "phase9_passed": bool((phase9_summary or {}).get("phase9_go_live_passed")),
        "phase10_passed": bool((phase10_summary or {}).get("phase10_go_live_passed")),
        "phase11_passed": bool((phase11_summary or {}).get("phase11_go_live_passed")),
        "phase12_passed": bool((phase12_summary or {}).get("phase12_go_live_passed")),
    },
    "artifacts": {
        "phase9": "staging_recert/30_phase9_summary.json",
        "phase10": "staging_recert/30_phase10_summary.json",
        "phase11": "staging_recert/30_phase11_summary.json",
        "phase12": "staging_recert/30_phase12_summary.json",
    },
}

result["master_closure_passed"] = (
    result["precheck_present"]
    and result["security"]["status"] == "PASS"
    and all(result["staging"].values())
)

summary_path = out / "30_master_summary.json"
matrix_path = out / "31_master_result_matrix.md"
hash_path = out / "32_master_summary.sha256"

summary_path.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

matrix = [
    "# Master Closure F1-F12",
    "",
    "| Check | Status | Artifact |",
    "|---|---|---|",
    f"| Security Bug Bounty | {'PASS' if result['security']['status'] == 'PASS' else 'FAIL'} | {result['security']['summary_path'] or '-'} |",
    f"| Phase 9 staging | {'PASS' if result['staging']['phase9_passed'] else 'FAIL'} | staging_recert/30_phase9_summary.json |",
    f"| Phase 10 staging | {'PASS' if result['staging']['phase10_passed'] else 'FAIL'} | staging_recert/30_phase10_summary.json |",
    f"| Phase 11 staging | {'PASS' if result['staging']['phase11_passed'] else 'FAIL'} | staging_recert/30_phase11_summary.json |",
    f"| Phase 12 staging | {'PASS' if result['staging']['phase12_passed'] else 'FAIL'} | staging_recert/30_phase12_summary.json |",
    "",
    f"Estado global: **{'PASS' if result['master_closure_passed'] else 'FAIL'}**",
]
matrix_path.write_text("\n".join(matrix) + "\n", encoding="utf-8")

sha = hashlib.sha256(summary_path.read_bytes()).hexdigest()
hash_path.write_text(f"{sha}  30_master_summary.json\n", encoding="utf-8")

print(json.dumps({"master_closure_passed": result["master_closure_passed"], "summary": str(summary_path)}, ensure_ascii=False))
PY
}

case "${MODE}" in
  precheck)
    run_precheck
    ;;
  security)
    run_security
    ;;
  staging)
    run_staging_recert
    ;;
  summary)
    run_summary
    ;;
  all)
    run_precheck
    run_security
    run_staging_recert
    run_summary
    ;;
  *)
    echo "Usage: $0 {precheck|security|staging|summary|all}" >&2
    exit 1
    ;;
esac

echo "[master] done mode=${MODE} out=${OUT_DIR}"
