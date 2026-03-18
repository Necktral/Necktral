#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${ROOT_DIR}/backend/src"
MODE="${1:-full}"
TS="${TS:-$(date +%Y%m%d_%H%M%S)}"

OUT_DIR="${OUT_DIR:-${ROOT_DIR}/docs/operacion/evidencia/phase10_go_live_${TS}}"
mkdir -p "${OUT_DIR}"

COMPANY_ID="${COMPANY_ID:-5}"
BRANCH_ID="${BRANCH_ID:-6}"
CONSUMER="${CONSUMER:-accounting.projector}"

MAX_INBOX_FAILED="${MAX_INBOX_FAILED:-0}"
MAX_OUTBOX_FAILED="${MAX_OUTBOX_FAILED:-0}"
MAX_OPEN_PROCUREMENT_DRAFTS="${MAX_OPEN_PROCUREMENT_DRAFTS:-0}"
MAX_OPEN_PROCUREMENT_BLOCKING_EXCEPTIONS="${MAX_OPEN_PROCUREMENT_BLOCKING_EXCEPTIONS:-0}"
MAX_POSTING_FAILED="${MAX_POSTING_FAILED:-0}"

PROJECTION_LIMIT="${PROJECTION_LIMIT:-200}"
POSTING_LIMIT="${POSTING_LIMIT:-500}"
DISPATCH_LIMIT="${DISPATCH_LIMIT:-200}"

MAX_CYCLE_ATTEMPTS="${MAX_CYCLE_ATTEMPTS:-6}"
CYCLE_SLEEP_SECONDS="${CYCLE_SLEEP_SECONDS:-120}"
REQUIRE_CONSECUTIVE_CLEAN_CYCLES="${REQUIRE_CONSECUTIVE_CLEAN_CYCLES:-2}"
CLEANUP_BLOCKED_ARTIFACTS="${CLEANUP_BLOCKED_ARTIFACTS:-1}"

F8_EVIDENCE_DIR="${F8_EVIDENCE_DIR:-${ROOT_DIR}/docs/operacion/evidencia/phase8_go_live_20260309_1040}"
F8_VERIFY_FILE="${F8_VERIFY_FILE:-${F8_EVIDENCE_DIR}/17_phase8_burnin_verify.json}"
F8_SUMMARY_FILE="${F8_SUMMARY_FILE:-${F8_EVIDENCE_DIR}/33_phase8_master_summary.json}"
F8_ACCOUNTANT_FILE="${F8_ACCOUNTANT_FILE:-${F8_EVIDENCE_DIR}/65_phase8_accountant_verify.json}"
F9_EMULATED_SUMMARY="${F9_EMULATED_SUMMARY:-${ROOT_DIR}/docs/operacion/evidencia/phase9_go_live_20260309_192841/30_phase9_summary.json}"
F9_HTTP_SUMMARY="${F9_HTTP_SUMMARY:-${ROOT_DIR}/docs/operacion/evidencia/phase9_go_live_http_20260309_193230/30_phase9_summary.json}"

LOCK_ROOT="${LOCK_ROOT:-${OUT_DIR}/.locks}"
LOCK_FILE="${LOCK_ROOT}/phase10_go_live.lock"

resolve_python() {
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    if command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
      printf '%s\n' "${PYTHON_BIN}"
      return 0
    fi
    echo "[phase10] PYTHON_BIN inválido: ${PYTHON_BIN}" >&2
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
  echo "[phase10] no se encontró intérprete Python (python3/python)" >&2
  return 1
}

PYTHON_BIN="$(resolve_python)" || exit 127

if command -v flock >/dev/null 2>&1; then
  mkdir -p "${LOCK_ROOT}"
  exec 9>"${LOCK_FILE}"
  if ! flock -n 9; then
    echo "[phase10] lock ocupado, evita solapamiento"
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
  COMPANY_ID="${COMPANY_ID}" \
  BRANCH_ID="${BRANCH_ID}" \
  "${PYTHON_BIN}" - <<'PY'
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

company_id = int(os.environ["COMPANY_ID"])
branch_id = int(os.environ["BRANCH_ID"])

errors: list[str] = []
details: dict[str, object] = {
    "scope": {"company_id": company_id, "branch_id": branch_id},
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
        "verify_file": os.environ["F8_VERIFY_FILE"],
        "summary_file": os.environ["F8_SUMMARY_FILE"],
        "accountant_file": os.environ["F8_ACCOUNTANT_FILE"],
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
    if not bool(accountant.get("signoff_passed")):
        errors.append("F8 signoff contador no está en PASS.")
    if not bool(accountant.get("final_approved_present")):
        errors.append("F8 no tiene FINAL_APPROVED del contador.")

def _check_f9(path_env: str, key: str) -> None:
    path = Path(os.environ[path_env])
    payload = _load(path)
    details[key] = {
        "summary_file": str(path),
        "phase9_go_live_passed": bool(payload.get("phase9_go_live_passed")),
        "checks": payload.get("checks") or {},
    }
    if not bool(payload.get("phase9_go_live_passed")):
        errors.append(f"{key} no está en PASS.")

try:
    _check_f8()
except Exception as exc:  # noqa: BLE001
    errors.append(f"No se pudo validar precondición F8: {exc}")

for env_key, key in [
    ("F9_EMULATED_SUMMARY", "f9_emulated"),
    ("F9_HTTP_SUMMARY", "f9_http"),
]:
    try:
        _check_f9(env_key, key)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"No se pudo validar precondición {key}: {exc}")

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

run_precheck() {
  local precheck_json="${OUT_DIR}/00_phase10_precheck.json"
  local manifest_json="${OUT_DIR}/01_phase10_manifest_precheck.json"

  local precheck_payload
  if ! precheck_payload="$(ensure_preconditions)"; then
    printf '%s\n' "${precheck_payload}" > "${precheck_json}"
    echo "[phase10] precheck falló: precondiciones F8/F9 no cumplen" >&2
    return 2
  fi
  printf '%s\n' "${precheck_payload}" > "${precheck_json}"

  run_manage export_phase10_env_manifest \
    --company-id "${COMPANY_ID}" \
    --branch-id "${BRANCH_ID}" \
    --output "${manifest_json}"

  echo "[phase10] precheck ok: ${precheck_json}"
}

cleanup_blocked_artifacts() {
  local cleanup_json="${OUT_DIR}/26_phase10_cleanup.json"
  (
    cd "${APP_DIR}"
    HAPPY_EVIDENCE_FILE="${OUT_DIR}/22_phase10_happy.json" \
    BLOCKED_EVIDENCE_FILE="${OUT_DIR}/23_phase10_blocked.json" \
    COMPANY_ID="${COMPANY_ID}" \
    BRANCH_ID="${BRANCH_ID}" \
    "${PYTHON_BIN}" manage.py shell <<'PY'
from __future__ import annotations

import json
import os

from apps.cec.models import CECException, CloseRun
from django.utils import timezone

blocked_path = str(os.environ["BLOCKED_EVIDENCE_FILE"])
happy_path = str(os.environ["HAPPY_EVIDENCE_FILE"])
company_id = int(os.environ["COMPANY_ID"])
branch_id = int(os.environ["BRANCH_ID"])

with open(blocked_path, "r", encoding="utf-8") as fh:
    blocked = json.load(fh)
with open(happy_path, "r", encoding="utf-8") as fh:
    happy = json.load(fh)

run_id = str(blocked.get("run_id") or "")
happy_run_id = str(happy.get("run_id") or "")
resolved = []
target_codes = {"SHADOW_RULE_NOT_FOUND", "SHADOW_DRAFT_INVALID", "SHADOW_RULESET_NOT_FOUND"}
run = None
if run_id:
    run = CloseRun.objects.filter(run_id=run_id, company_id=company_id, branch_id=branch_id).first()

qs = CECException.objects.filter(
    company_id=company_id,
    branch_id=branch_id,
    source_module="ACCOUNTING",
    is_blocking=True,
    status__in=[CECException.Status.OPEN, CECException.Status.IN_PROGRESS],
    code__in=target_codes,
).order_by("id")

resolved_current_run = 0
resolved_legacy = 0
for ex in qs:
    if run is not None and ex.close_run_id == run.id:
        resolved_current_run += 1
    else:
        resolved_legacy += 1
    ex.status = CECException.Status.RESOLVED
    ex.resolved_at = timezone.now()
    ex.resolution_note = "phase10 cleanup after blocked certification"
    ex.save(update_fields=["status", "resolved_at", "resolution_note"])
    resolved.append(
        {
            "exception_id": str(ex.exception_id),
            "code": ex.code,
            "close_run_id": str(ex.close_run.run_id) if ex.close_run_id else "",
            "status": ex.status,
        }
    )

payload = {
    "schema_version": 1,
    "pilot_scope": {"company_id": company_id, "branch_id": branch_id},
    "blocked_run_id": run_id,
    "resolved_count": len(resolved),
    "resolved_current_run_count": int(resolved_current_run),
    "resolved_legacy_count": int(resolved_legacy),
    "resolved_exceptions": resolved,
}

# Evita reproyección infinita de corridas viejas de certificación fase10 que
# quedaron en PACKAGED.
stale_qs = CloseRun.objects.filter(
    company_id=company_id,
    branch_id=branch_id,
    status=CloseRun.Status.PACKAGED,
    summary_json__source="phase10_certification",
).exclude(run_id=happy_run_id)
stale_ids = [str(x.run_id) for x in stale_qs]
stale_updated = stale_qs.update(status=CloseRun.Status.REOPENED_EXCEPTION, updated_at=timezone.now())
payload["stale_packaged_runs_reopened"] = int(stale_updated)
payload["stale_packaged_run_ids"] = stale_ids

print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
PY
  ) > "${cleanup_json}"
  echo "[phase10] cleanup blocked artifacts: ${cleanup_json}"
}

run_certify() {
  run_manage export_phase10_env_manifest \
    --company-id "${COMPANY_ID}" \
    --branch-id "${BRANCH_ID}" \
    --output "${OUT_DIR}/20_phase10_staging_manifest.json"

  run_manage export_phase10_env_manifest \
    --company-id "${COMPANY_ID}" \
    --branch-id "${BRANCH_ID}" \
    --output "${OUT_DIR}/21_phase10_prod_manifest.json"

  run_manage certify_phase10_procurement_run \
    --company-id "${COMPANY_ID}" \
    --branch-id "${BRANCH_ID}" \
    --output "${OUT_DIR}/22_phase10_happy.json"

  run_manage certify_phase10_procurement_run \
    --company-id "${COMPANY_ID}" \
    --branch-id "${BRANCH_ID}" \
    --expect-blocked \
    --output "${OUT_DIR}/23_phase10_blocked.json"

  if [[ "${CLEANUP_BLOCKED_ARTIFACTS}" == "1" ]]; then
    cleanup_blocked_artifacts
  fi
}

cycle_check_clean() {
  local cycle_file="$1"
  CYCLE_FILE="${cycle_file}" \
  "${PYTHON_BIN}" - <<'PY'
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
posting = payload.get("posting") or {}
ok = (
    bool(payload.get("cycle_passed"))
    and int(health.get("inbox_failed_count") or 0) == 0
    and int(health.get("outbox_failed_count") or 0) == 0
    and int(health.get("open_procurement_drafts_count") or 0) == 0
    and int(health.get("open_procurement_blocking_exceptions_count") or 0) == 0
    and int(posting.get("failed") or 0) == 0
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
    cycle_file="${OUT_DIR}/24_phase10_cycle_${attempt}.json"

    local rc=0
    set +e
    run_manage run_phase10_procurement_cycle \
      --company-id "${COMPANY_ID}" \
      --branch-id "${BRANCH_ID}" \
      --consumer "${CONSUMER}" \
      --projection-limit "${PROJECTION_LIMIT}" \
      --posting-limit "${POSTING_LIMIT}" \
      --dispatch-limit "${DISPATCH_LIMIT}" \
      --max-inbox-failed "${MAX_INBOX_FAILED}" \
      --max-outbox-failed "${MAX_OUTBOX_FAILED}" \
      --max-open-procurement-drafts "${MAX_OPEN_PROCUREMENT_DRAFTS}" \
      --max-open-procurement-blocking-exceptions "${MAX_OPEN_PROCUREMENT_BLOCKING_EXCEPTIONS}" \
      --max-posting-failed "${MAX_POSTING_FAILED}" \
      --output "${cycle_file}"
    rc=$?
    set -e

    if cycle_check_clean "${cycle_file}" && [[ "${rc}" -eq 0 ]]; then
      consecutive_clean=$((consecutive_clean + 1))
    else
      consecutive_clean=0
      # Cuando el escenario blocked deja excepciones abiertas de accounting,
      # limpiamos antes del siguiente intento para recuperar estabilidad estricta.
      if [[ "${CLEANUP_BLOCKED_ARTIFACTS}" == "1" ]] && [[ -f "${OUT_DIR}/23_phase10_blocked.json" ]]; then
        cleanup_blocked_artifacts
      fi
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
    echo "[phase10] cycle no alcanzó estabilidad estricta en ${MAX_CYCLE_ATTEMPTS} intentos" >&2
    return 4
  fi
  echo "[phase10] cycle estable con ${REQUIRE_CONSECUTIVE_CLEAN_CYCLES} corridas limpias consecutivas"
}

run_gate() {
  run_manage verify_phase10_go_live \
    --company-id "${COMPANY_ID}" \
    --branch-id "${BRANCH_ID}" \
    --staging-manifest "${OUT_DIR}/20_phase10_staging_manifest.json" \
    --prod-manifest "${OUT_DIR}/21_phase10_prod_manifest.json" \
    --certification "${OUT_DIR}/22_phase10_happy.json" \
    --max-inbox-failed "${MAX_INBOX_FAILED}" \
    --max-outbox-failed "${MAX_OUTBOX_FAILED}" \
    --max-open-procurement-drafts "${MAX_OPEN_PROCUREMENT_DRAFTS}" \
    --max-open-procurement-blocking-exceptions "${MAX_OPEN_PROCUREMENT_BLOCKING_EXCEPTIONS}" \
    --output "${OUT_DIR}/25_phase10_gate.json"
}

write_summary() {
  OUT_DIR="${OUT_DIR}" \
  REQUIRE_CONSECUTIVE_CLEAN_CYCLES="${REQUIRE_CONSECUTIVE_CLEAN_CYCLES}" \
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
summary_path = out_dir / "30_phase10_summary.json"
matrix_path = out_dir / "31_phase10_result_matrix.md"
hash_path = out_dir / "32_phase10_summary.sha256"

def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return payload if isinstance(payload, dict) else {}

precheck = load_json(out_dir / "00_phase10_precheck.json")
happy = load_json(out_dir / "22_phase10_happy.json")
blocked = load_json(out_dir / "23_phase10_blocked.json")
gate = load_json(out_dir / "25_phase10_gate.json")
cycles = [load_json(Path(p)) for p in sorted(glob.glob(str(out_dir / "24_phase10_cycle_*.json")))]

cycle_clean = []
for c in cycles:
    health = c.get("health") or {}
    posting = c.get("posting") or {}
    is_clean = (
        bool(c.get("cycle_passed"))
        and int(health.get("inbox_failed_count") or 0) == 0
        and int(health.get("outbox_failed_count") or 0) == 0
        and int(health.get("open_procurement_drafts_count") or 0) == 0
        and int(health.get("open_procurement_blocking_exceptions_count") or 0) == 0
        and int(posting.get("failed") or 0) == 0
    )
    cycle_clean.append(is_clean)

target_consecutive = max(1, int(os.environ.get("REQUIRE_CONSECUTIVE_CLEAN_CYCLES", "2")))
max_consecutive = 0
current = 0
for val in cycle_clean:
    if val:
        current += 1
    else:
        current = 0
    max_consecutive = max(max_consecutive, current)

blocked_ok = (
    bool(blocked.get("passed"))
    and bool(blocked.get("blocked"))
    and bool(blocked.get("deterministic_replay"))
    and str(blocked.get("close_run_status") or "") == "REOPENED_EXCEPTION"
)

summary = {
    "schema_version": 1,
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "files": {
        "precheck": "00_phase10_precheck.json",
        "staging_manifest": "20_phase10_staging_manifest.json",
        "prod_manifest": "21_phase10_prod_manifest.json",
        "happy": "22_phase10_happy.json",
        "blocked": "23_phase10_blocked.json",
        "gate": "25_phase10_gate.json",
        "cleanup": "26_phase10_cleanup.json",
        "cycles": [Path(p).name for p in sorted(glob.glob(str(out_dir / "24_phase10_cycle_*.json")))],
    },
    "checks": {
        "precheck_passed": bool(precheck.get("precheck_passed")),
        "happy_passed": bool(happy.get("passed")),
        "blocked_passed": bool(blocked_ok),
        "gate_passed": bool(gate.get("go_live_passed")),
        "cycle_clean_consecutive_max": int(max_consecutive),
        "cycle_clean_consecutive_required": int(target_consecutive),
    },
}

summary["phase10_go_live_passed"] = bool(
    summary["checks"]["precheck_passed"]
    and summary["checks"]["happy_passed"]
    and summary["checks"]["blocked_passed"]
    and summary["checks"]["gate_passed"]
    and int(summary["checks"]["cycle_clean_consecutive_max"]) >= int(summary["checks"]["cycle_clean_consecutive_required"])
)

raw_min = json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
digest = hashlib.sha256(raw_min).hexdigest()
secret = str(os.environ.get("PHASE10_EVIDENCE_SECRET", "")).strip()
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
hash_path.write_text(f"{digest}  30_phase10_summary.json\n", encoding="utf-8")

matrix = (
    "# F10 Go-Live Matrix\n\n"
    "| Check | Result | Evidence |\n"
    "|---|---|---|\n"
    f"| Precheck F8+F9 | {'PASS' if summary['checks']['precheck_passed'] else 'FAIL'} | 00_phase10_precheck.json |\n"
    f"| Certification happy | {'PASS' if summary['checks']['happy_passed'] else 'FAIL'} | 22_phase10_happy.json |\n"
    f"| Certification blocked | {'PASS' if summary['checks']['blocked_passed'] else 'FAIL'} | 23_phase10_blocked.json |\n"
    f"| Cycle strict stability | {'PASS' if summary['checks']['cycle_clean_consecutive_max'] >= summary['checks']['cycle_clean_consecutive_required'] else 'FAIL'} | 24_phase10_cycle_*.json |\n"
    f"| Go-live gate strict | {'PASS' if summary['checks']['gate_passed'] else 'FAIL'} | 25_phase10_gate.json |\n"
    "\n"
    f"Estado global: **{'PASS' if summary['phase10_go_live_passed'] else 'FAIL'}**\n"
)
matrix_path.write_text(matrix, encoding="utf-8")
print(f"[phase10] summary ready: {summary_path}")
PY
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
    exit 2
    ;;
esac

echo "[phase10] done mode=${MODE} output=${OUT_DIR}"
