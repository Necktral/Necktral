#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${ROOT_DIR}/backend/src"
MODE="${1:-full}"
TS="${TS:-$(date +%Y%m%d_%H%M%S)}"

OUT_DIR="${OUT_DIR:-${ROOT_DIR}/docs/operacion/evidencia/phase12_go_live_${TS}}"
mkdir -p "${OUT_DIR}"

COMPANY_ID="${COMPANY_ID:-5}"
BRANCH_ID="${BRANCH_ID:-6}"
PARENT_COMPANY_ID="${PARENT_COMPANY_ID:-5}"
COMPANY_IDS="${COMPANY_IDS:-5}"
COMPANY_IDS_CLI="${COMPANY_IDS//,/ }"
CONSUMER="${CONSUMER:-accounting.projector}"

YEAR="${YEAR:-$(date +%Y)}"
MONTH="${MONTH:-$(date +%m)}"
REQUIRED_PERIODS="${REQUIRED_PERIODS:-3}"
MAX_FAILED_PERIODS="${MAX_FAILED_PERIODS:-0}"
FX_BLOCKED_POLICY="${FX_BLOCKED_POLICY:-ALERT}"

POSTING_LIMIT="${POSTING_LIMIT:-500}"
INTERCOMPANY_LIMIT="${INTERCOMPANY_LIMIT:-200}"
DISPATCH_LIMIT="${DISPATCH_LIMIT:-200}"

MAX_INBOX_FAILED="${MAX_INBOX_FAILED:-0}"
MAX_OUTBOX_FAILED="${MAX_OUTBOX_FAILED:-0}"
MAX_MISSING_LINES="${MAX_MISSING_LINES:-0}"
MAX_STALE_REVALUATION="${MAX_STALE_REVALUATION:-0}"
MAX_OPEN_INTERCOMPANY="${MAX_OPEN_INTERCOMPANY:-0}"
MAX_DISPUTED_INTERCOMPANY="${MAX_DISPUTED_INTERCOMPANY:-0}"
MAX_BLOCKED_CONSOLIDATION="${MAX_BLOCKED_CONSOLIDATION:-0}"
MAX_OPEN_CONSOLIDATION_EXCEPTION="${MAX_OPEN_CONSOLIDATION_EXCEPTION:-0}"

MAX_CYCLE_ATTEMPTS="${MAX_CYCLE_ATTEMPTS:-6}"
CYCLE_SLEEP_SECONDS="${CYCLE_SLEEP_SECONDS:-120}"
REQUIRE_CONSECUTIVE_CLEAN_CYCLES="${REQUIRE_CONSECUTIVE_CLEAN_CYCLES:-2}"

F8_EVIDENCE_DIR="${F8_EVIDENCE_DIR:-${ROOT_DIR}/docs/operacion/evidencia/phase8_go_live_20260309_1040}"
F8_VERIFY_FILE="${F8_VERIFY_FILE:-${F8_EVIDENCE_DIR}/17_phase8_burnin_verify.json}"
F8_SUMMARY_FILE="${F8_SUMMARY_FILE:-${F8_EVIDENCE_DIR}/33_phase8_master_summary.json}"
F8_ACCOUNTANT_FILE="${F8_ACCOUNTANT_FILE:-${F8_EVIDENCE_DIR}/65_phase8_accountant_verify.json}"
F9_EMULATED_SUMMARY="${F9_EMULATED_SUMMARY:-${ROOT_DIR}/docs/operacion/evidencia/phase9_go_live_20260309_192841/30_phase9_summary.json}"
F9_HTTP_SUMMARY="${F9_HTTP_SUMMARY:-${ROOT_DIR}/docs/operacion/evidencia/phase9_go_live_http_20260309_193230/30_phase9_summary.json}"
F10_SUMMARY="${F10_SUMMARY:-${ROOT_DIR}/docs/operacion/evidencia/phase10_go_live_20260309_200749/30_phase10_summary.json}"
F11_SUMMARY="${F11_SUMMARY:-${ROOT_DIR}/docs/operacion/evidencia/phase11_go_live_20260309_210137/30_phase11_summary.json}"

LOCK_ROOT="${LOCK_ROOT:-${OUT_DIR}/.locks}"
LOCK_FILE="${LOCK_ROOT}/phase12_go_live.lock"

resolve_python() {
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    if command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
      printf '%s\n' "${PYTHON_BIN}"
      return 0
    fi
    echo "[phase12] PYTHON_BIN inválido: ${PYTHON_BIN}" >&2
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
  echo "[phase12] no se encontró intérprete Python (python3/python)" >&2
  return 1
}

PYTHON_BIN="$(resolve_python)" || exit 127

if command -v flock >/dev/null 2>&1; then
  mkdir -p "${LOCK_ROOT}"
  exec 9>"${LOCK_FILE}"
  if ! flock -n 9; then
    echo "[phase12] lock ocupado, evita solapamiento"
    exit 0
  fi
fi

run_manage() {
  (
    cd "${APP_DIR}"
    "${PYTHON_BIN}" manage.py "$@"
  )
}

ensure_preconditions() {
  F8_VERIFY_FILE="${F8_VERIFY_FILE}" \
  F8_SUMMARY_FILE="${F8_SUMMARY_FILE}" \
  F8_ACCOUNTANT_FILE="${F8_ACCOUNTANT_FILE}" \
  F9_EMULATED_SUMMARY="${F9_EMULATED_SUMMARY}" \
  F9_HTTP_SUMMARY="${F9_HTTP_SUMMARY}" \
  F10_SUMMARY="${F10_SUMMARY}" \
  F11_SUMMARY="${F11_SUMMARY}" \
  COMPANY_ID="${COMPANY_ID}" \
  BRANCH_ID="${BRANCH_ID}" \
  REQUIRED_PERIODS="${REQUIRED_PERIODS}" \
  "${PYTHON_BIN}" - <<'PY'
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

errors: list[str] = []
details: dict[str, object] = {
    "scope": {
        "company_id": int(os.environ["COMPANY_ID"]),
        "branch_id": int(os.environ["BRANCH_ID"]),
    },
    "required_periods": int(os.environ["REQUIRED_PERIODS"]),
}

def _load(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(str(path))
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"JSON inválido en {path}")
    return data

def _check_f8() -> None:
    verify = _load(Path(os.environ["F8_VERIFY_FILE"]))
    summary = _load(Path(os.environ["F8_SUMMARY_FILE"]))
    accountant = _load(Path(os.environ["F8_ACCOUNTANT_FILE"]))
    details["f8"] = {
        "burn_in_passed": bool(verify.get("burn_in_passed")),
        "status": str(summary.get("status") or ""),
        "rollback_required": bool(summary.get("rollback_required")),
        "signoff_passed": bool(accountant.get("signoff_passed")),
        "final_approved_present": bool(accountant.get("final_approved_present")),
    }
    if not bool(verify.get("burn_in_passed")):
        errors.append("F8 burn-in no está en PASS.")
    if str(summary.get("status") or "") != "READY_TO_CLOSE_F8":
        errors.append("F8 summary no está en READY_TO_CLOSE_F8.")
    if bool(summary.get("rollback_required")):
        errors.append("F8 reporta rollback_required=true.")
    if not bool(accountant.get("signoff_passed")) or not bool(accountant.get("final_approved_present")):
        errors.append("F8 sign-off contador no está en PASS.")

def _check_phase(path_env: str, key: str, field: str) -> None:
    payload = _load(Path(os.environ[path_env]))
    details[key] = {"path": os.environ[path_env], field: bool(payload.get(field))}
    if not bool(payload.get(field)):
        errors.append(f"{key} no está en PASS.")

try:
    _check_f8()
except Exception as exc:  # noqa: BLE001
    errors.append(f"No se pudo validar F8: {exc}")

for env_key, key, field in [
    ("F9_EMULATED_SUMMARY", "f9_emulated", "phase9_go_live_passed"),
    ("F9_HTTP_SUMMARY", "f9_http", "phase9_go_live_passed"),
    ("F10_SUMMARY", "f10", "phase10_go_live_passed"),
    ("F11_SUMMARY", "f11", "phase11_go_live_passed"),
]:
    try:
        _check_phase(env_key, key, field)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"No se pudo validar {key}: {exc}")

if int(os.environ["REQUIRED_PERIODS"]) <= 0:
    errors.append("REQUIRED_PERIODS debe ser >= 1.")

payload = {
    "schema_version": 1,
    "precheck_passed": len(errors) == 0,
    "errors": errors,
    "details": details,
}
print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
if errors:
    sys.exit(2)
PY
}

period_rows() {
  YEAR="${YEAR}" MONTH="${MONTH}" REQUIRED_PERIODS="${REQUIRED_PERIODS}" "${PYTHON_BIN}" - <<'PY'
from __future__ import annotations

import os

year = int(os.environ["YEAR"])
month = int(os.environ["MONTH"])
required = int(os.environ["REQUIRED_PERIODS"])

def shift_month(y: int, m: int, delta: int) -> tuple[int, int]:
    total = (y * 12 + (m - 1)) + delta
    ny = total // 12
    nm = total % 12 + 1
    return ny, nm

for offset in range(required - 1, -1, -1):
    y, m = shift_month(year, month, -offset)
    print(f"{y} {m:02d} {y:04d}{m:02d}")
PY
}

run_precheck() {
  local precheck_json="${OUT_DIR}/00_phase12_precheck.json"
  local manifest_json="${OUT_DIR}/01_phase12_manifest_precheck.json"

  local precheck_payload
  if ! precheck_payload="$(ensure_preconditions)"; then
    printf '%s\n' "${precheck_payload}" > "${precheck_json}"
    echo "[phase12] precheck falló: precondiciones no cumplen" >&2
    return 2
  fi
  printf '%s\n' "${precheck_payload}" > "${precheck_json}"

  run_manage export_phase12_env_manifest \
    --company-id "${COMPANY_ID}" \
    --branch-id "${BRANCH_ID}" \
    --output "${manifest_json}"

  echo "[phase12] precheck ok: ${precheck_json}"
}

run_certify() {
  run_manage export_phase12_env_manifest \
    --company-id "${COMPANY_ID}" \
    --branch-id "${BRANCH_ID}" \
    --output "${OUT_DIR}/20_phase12_staging_manifest.json"

  run_manage export_phase12_env_manifest \
    --company-id "${COMPANY_ID}" \
    --branch-id "${BRANCH_ID}" \
    --output "${OUT_DIR}/21_phase12_prod_manifest.json"

  run_manage compare_phase12_env_manifests \
    --left "${OUT_DIR}/20_phase12_staging_manifest.json" \
    --right "${OUT_DIR}/21_phase12_prod_manifest.json" \
    --strict

  local row
  mapfile -t PERIOD_ROWS < <(period_rows)
  for row in "${PERIOD_ROWS[@]}"; do
    local y
    local m
    local ym
    y="$(awk '{print $1}' <<< "${row}")"
    m="$(awk '{print $2}' <<< "${row}")"
    ym="$(awk '{print $3}' <<< "${row}")"
    run_manage run_phase12_monthly_close \
      --company-id "${COMPANY_ID}" \
      --parent-company-id "${PARENT_COMPANY_ID}" \
      --company-ids ${COMPANY_IDS_CLI} \
      --year "${y}" \
      --month "${m}" \
      --consumer "${CONSUMER}" \
      --posting-limit "${POSTING_LIMIT}" \
      --intercompany-limit "${INTERCOMPANY_LIMIT}" \
      --dispatch-limit "${DISPATCH_LIMIT}" \
      --max-inbox-failed "${MAX_INBOX_FAILED}" \
      --max-outbox-failed "${MAX_OUTBOX_FAILED}" \
      --max-missing-lines "${MAX_MISSING_LINES}" \
      --max-stale-revaluation "${MAX_STALE_REVALUATION}" \
      --max-open-intercompany "${MAX_OPEN_INTERCOMPANY}" \
      --max-disputed-intercompany "${MAX_DISPUTED_INTERCOMPANY}" \
      --max-blocked-consolidation "${MAX_BLOCKED_CONSOLIDATION}" \
      --max-open-consolidation-exception "${MAX_OPEN_CONSOLIDATION_EXCEPTION}" \
      --fx-blocked-policy "${FX_BLOCKED_POLICY}" \
      --output "${OUT_DIR}/22_phase12_monthly_close_${ym}.json"
  done

  local current_ym
  current_ym="$(printf '%04d%02d' "${YEAR}" "${MONTH}")"
  run_manage certify_phase12_monthly_determinism \
    --company-id "${COMPANY_ID}" \
    --parent-company-id "${PARENT_COMPANY_ID}" \
    --company-ids ${COMPANY_IDS_CLI} \
    --year "${YEAR}" \
    --month "${MONTH}" \
    --consumer "${CONSUMER}" \
    --fx-blocked-policy "${FX_BLOCKED_POLICY}" \
    --output "${OUT_DIR}/23_phase12_determinism_${current_ym}.json"
  cp "${OUT_DIR}/23_phase12_determinism_${current_ym}.json" "${OUT_DIR}/23_phase12_determinism_latest.json"
}

cycle_check_clean() {
  local cycle_file="$1"
  CYCLE_FILE="${cycle_file}" FX_BLOCKED_POLICY="${FX_BLOCKED_POLICY}" "${PYTHON_BIN}" - <<'PY'
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

path = Path(os.environ["CYCLE_FILE"])
if not path.exists():
    sys.exit(2)

payload = json.loads(path.read_text(encoding="utf-8"))
health = payload.get("health") or {}
phase7 = (health.get("phase7a") or {}) if isinstance(health, dict) else {}
phase7b = (health.get("phase7b") or {}) if isinstance(health, dict) else {}
revaluation = payload.get("revaluation") or {}
reval_status = str(revaluation.get("status") or "")
policy = str(os.environ.get("FX_BLOCKED_POLICY", "ALERT")).strip().upper()
fx_ok = reval_status == "COMPLETED" or (policy == "ALERT" and reval_status == "BLOCKED")

ok = (
    bool(payload.get("cycle_passed"))
    and fx_ok
    and int(health.get("inbox_failed_count") or 0) == 0
    and int(health.get("outbox_failed_count") or 0) == 0
    and int(phase7.get("missing_lines_count") or 0) == 0
    and int(phase7.get("stale_revaluation_count") or 0) == 0
    and int(phase7b.get("open_intercompany_count") or 0) == 0
    and int(phase7b.get("disputed_intercompany_count") or 0) == 0
    and int(phase7b.get("blocked_consolidation_count") or 0) == 0
    and int(phase7b.get("open_consolidation_exception_count") or 0) == 0
)
sys.exit(0 if ok else 1)
PY
}

run_cycle() {
  local attempt=0
  local consecutive_clean=0
  local cycle_ok=0
  local cycle_file

  while [[ "${attempt}" -lt "${MAX_CYCLE_ATTEMPTS}" ]]; do
    attempt=$((attempt + 1))
    cycle_file="${OUT_DIR}/27_phase12_cycle_${attempt}.json"

    local rc=0
    set +e
    run_manage run_phase12_monthly_close \
      --company-id "${COMPANY_ID}" \
      --parent-company-id "${PARENT_COMPANY_ID}" \
      --company-ids ${COMPANY_IDS_CLI} \
      --year "${YEAR}" \
      --month "${MONTH}" \
      --consumer "${CONSUMER}" \
      --posting-limit "${POSTING_LIMIT}" \
      --intercompany-limit "${INTERCOMPANY_LIMIT}" \
      --dispatch-limit "${DISPATCH_LIMIT}" \
      --max-inbox-failed "${MAX_INBOX_FAILED}" \
      --max-outbox-failed "${MAX_OUTBOX_FAILED}" \
      --max-missing-lines "${MAX_MISSING_LINES}" \
      --max-stale-revaluation "${MAX_STALE_REVALUATION}" \
      --max-open-intercompany "${MAX_OPEN_INTERCOMPANY}" \
      --max-disputed-intercompany "${MAX_DISPUTED_INTERCOMPANY}" \
      --max-blocked-consolidation "${MAX_BLOCKED_CONSOLIDATION}" \
      --max-open-consolidation-exception "${MAX_OPEN_CONSOLIDATION_EXCEPTION}" \
      --fx-blocked-policy "${FX_BLOCKED_POLICY}" \
      --output "${cycle_file}"
    rc=$?
    set -e

    if cycle_check_clean "${cycle_file}" && [[ "${rc}" -eq 0 ]]; then
      consecutive_clean=$((consecutive_clean + 1))
    else
      consecutive_clean=0
    fi

    if [[ "${consecutive_clean}" -ge "${REQUIRE_CONSECUTIVE_CLEAN_CYCLES}" ]]; then
      cycle_ok=1
      break
    fi

    if [[ "${attempt}" -lt "${MAX_CYCLE_ATTEMPTS}" ]]; then
      sleep "${CYCLE_SLEEP_SECONDS}"
    fi
  done

  if [[ "${cycle_ok}" -ne 1 ]]; then
    echo "[phase12] cycle no alcanzó estabilidad estricta en ${MAX_CYCLE_ATTEMPTS} intentos" >&2
    return 4
  fi
  echo "[phase12] cycle estable con ${REQUIRE_CONSECUTIVE_CLEAN_CYCLES} corridas limpias consecutivas"
}

run_gate() {
  run_manage verify_phase12_operational_slo \
    --evidence-dir "${OUT_DIR}" \
    --pattern "22_phase12_monthly_close_*.json" \
    --min-periods "${REQUIRED_PERIODS}" \
    --max-failed-periods "${MAX_FAILED_PERIODS}" \
    --max-inbox-failed "${MAX_INBOX_FAILED}" \
    --max-outbox-failed "${MAX_OUTBOX_FAILED}" \
    --max-missing-lines "${MAX_MISSING_LINES}" \
    --max-stale-revaluation "${MAX_STALE_REVALUATION}" \
    --max-open-intercompany "${MAX_OPEN_INTERCOMPANY}" \
    --max-disputed-intercompany "${MAX_DISPUTED_INTERCOMPANY}" \
    --fx-blocked-policy "${FX_BLOCKED_POLICY}" \
    --output "${OUT_DIR}/24_phase12_slo_gate.json"

  run_manage verify_phase12_go_live \
    --company-id "${COMPANY_ID}" \
    --consumer "${CONSUMER}" \
    --staging-manifest "${OUT_DIR}/20_phase12_staging_manifest.json" \
    --prod-manifest "${OUT_DIR}/21_phase12_prod_manifest.json" \
    --determinism-evidence "${OUT_DIR}/23_phase12_determinism_latest.json" \
    --slo-evidence "${OUT_DIR}/24_phase12_slo_gate.json" \
    --fx-blocked-policy "${FX_BLOCKED_POLICY}" \
    --max-inbox-failed "${MAX_INBOX_FAILED}" \
    --max-outbox-failed "${MAX_OUTBOX_FAILED}" \
    --max-missing-lines "${MAX_MISSING_LINES}" \
    --max-stale-revaluation "${MAX_STALE_REVALUATION}" \
    --max-open-intercompany "${MAX_OPEN_INTERCOMPANY}" \
    --max-disputed-intercompany "${MAX_DISPUTED_INTERCOMPANY}" \
    --max-blocked-consolidation "${MAX_BLOCKED_CONSOLIDATION}" \
    --max-open-consolidation-exception "${MAX_OPEN_CONSOLIDATION_EXCEPTION}" \
    --output "${OUT_DIR}/25_phase12_gate.json"
}

write_summary() {
  OUT_DIR="${OUT_DIR}" \
  REQUIRED_PERIODS="${REQUIRED_PERIODS}" \
  REQUIRE_CONSECUTIVE_CLEAN_CYCLES="${REQUIRE_CONSECUTIVE_CLEAN_CYCLES}" \
  FX_BLOCKED_POLICY="${FX_BLOCKED_POLICY}" \
  "${PYTHON_BIN}" - <<'PY'
from __future__ import annotations

import glob
import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from pathlib import Path

out_dir = Path(os.environ["OUT_DIR"])
summary_path = out_dir / "30_phase12_summary.json"
matrix_path = out_dir / "31_phase12_result_matrix.md"
hash_path = out_dir / "32_phase12_summary.sha256"
target_consecutive = max(1, int(os.environ.get("REQUIRE_CONSECUTIVE_CLEAN_CYCLES", "2")))
required_periods = max(1, int(os.environ.get("REQUIRED_PERIODS", "3")))
fx_policy = str(os.environ.get("FX_BLOCKED_POLICY", "ALERT")).strip().upper()

def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return payload if isinstance(payload, dict) else {}

precheck = load_json(out_dir / "00_phase12_precheck.json")
gate = load_json(out_dir / "25_phase12_gate.json")
slo = load_json(out_dir / "24_phase12_slo_gate.json")
determinism = load_json(out_dir / "23_phase12_determinism_latest.json")
monthly_files = [Path(p) for p in sorted(glob.glob(str(out_dir / "22_phase12_monthly_close_*.json")))]
cycle_files = [Path(p) for p in sorted(glob.glob(str(out_dir / "27_phase12_cycle_*.json")))]
cycles = [load_json(p) for p in cycle_files]

cycle_clean = []
for c in cycles:
    health = c.get("health") or {}
    phase7 = (health.get("phase7a") or {}) if isinstance(health, dict) else {}
    phase7b = (health.get("phase7b") or {}) if isinstance(health, dict) else {}
    revaluation = c.get("revaluation") or {}
    status = str(revaluation.get("status") or "")
    fx_ok = status == "COMPLETED" or (fx_policy == "ALERT" and status == "BLOCKED")
    is_clean = (
        bool(c.get("cycle_passed"))
        and fx_ok
        and int(health.get("inbox_failed_count") or 0) == 0
        and int(health.get("outbox_failed_count") or 0) == 0
        and int(phase7.get("missing_lines_count") or 0) == 0
        and int(phase7.get("stale_revaluation_count") or 0) == 0
        and int(phase7b.get("open_intercompany_count") or 0) == 0
        and int(phase7b.get("disputed_intercompany_count") or 0) == 0
        and int(phase7b.get("blocked_consolidation_count") or 0) == 0
        and int(phase7b.get("open_consolidation_exception_count") or 0) == 0
    )
    cycle_clean.append(is_clean)

max_consecutive = 0
current = 0
for val in cycle_clean:
    if val:
        current += 1
    else:
        current = 0
    max_consecutive = max(max_consecutive, current)

checks = {
    "precheck_passed": bool(precheck.get("precheck_passed")),
    "periods_covered": len(monthly_files),
    "required_periods": required_periods,
    "determinism_passed": bool(determinism.get("passed")) and bool(determinism.get("deterministic_replay")),
    "slo_passed": bool(slo.get("slo_passed")),
    "gate_passed": bool(gate.get("phase12_go_live_passed") or gate.get("go_live_passed")),
    "cycle_clean_consecutive_max": int(max_consecutive),
    "cycle_clean_consecutive_required": int(target_consecutive),
}

phase12_go_live_passed = bool(
    checks["precheck_passed"]
    and int(checks["periods_covered"]) >= int(checks["required_periods"])
    and checks["determinism_passed"]
    and checks["slo_passed"]
    and checks["gate_passed"]
    and int(checks["cycle_clean_consecutive_max"]) >= int(checks["cycle_clean_consecutive_required"])
)

summary = {
    "schema_version": 2,
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "fx_policy_applied": fx_policy,
    "files": {
        "precheck": "00_phase12_precheck.json",
        "staging_manifest": "20_phase12_staging_manifest.json",
        "prod_manifest": "21_phase12_prod_manifest.json",
        "monthly_close": [p.name for p in monthly_files],
        "determinism": "23_phase12_determinism_latest.json",
        "slo_gate": "24_phase12_slo_gate.json",
        "go_live_gate": "25_phase12_gate.json",
        "cycles": [p.name for p in cycle_files],
    },
    "checks": checks,
    "phase12_go_live_passed": phase12_go_live_passed,
}

raw_min = json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
digest = hashlib.sha256(raw_min).hexdigest()
secret = str(os.environ.get("PHASE12_EVIDENCE_SECRET", "")).strip()
if secret:
    signature = hmac.new(secret.encode("utf-8"), raw_min, hashlib.sha256).hexdigest()
    signature_type = "hmac-sha256"
else:
    signature = digest
    signature_type = "sha256"
summary["evidence_hash"] = digest
summary["signature"] = signature
summary["signature_type"] = signature_type

summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
hash_path.write_text(f"{digest}  30_phase12_summary.json\n", encoding="utf-8")

matrix = (
    "# F12 Go-Live Matrix\n\n"
    "| Check | Result |\n"
    "| --- | --- |\n"
    f"| precheck_passed | {'PASS' if checks['precheck_passed'] else 'FAIL'} |\n"
    f"| periods_covered | {checks['periods_covered']}/{checks['required_periods']} |\n"
    f"| determinism_passed | {'PASS' if checks['determinism_passed'] else 'FAIL'} |\n"
    f"| slo_passed | {'PASS' if checks['slo_passed'] else 'FAIL'} |\n"
    f"| gate_passed | {'PASS' if checks['gate_passed'] else 'FAIL'} |\n"
    f"| cycle_stability | {checks['cycle_clean_consecutive_max']}/{checks['cycle_clean_consecutive_required']} |\n"
    f"| phase12_go_live_passed | {'PASS' if phase12_go_live_passed else 'FAIL'} |\n"
)
matrix_path.write_text(matrix, encoding="utf-8")
PY
  echo "[phase12] summary ready: ${OUT_DIR}/30_phase12_summary.json"
}

case "${MODE}" in
  precheck)
    run_precheck
    ;;
  certify)
    run_certify
    ;;
  cycle)
    run_cycle
    ;;
  gate)
    run_gate
    ;;
  summary)
    write_summary
    ;;
  full)
    run_precheck
    run_certify
    run_cycle
    run_gate
    write_summary
    ;;
  *)
    echo "Usage: $0 {precheck|certify|cycle|gate|summary|full}" >&2
    exit 1
    ;;
esac

echo "[phase12] done mode=${MODE} output=${OUT_DIR}"
