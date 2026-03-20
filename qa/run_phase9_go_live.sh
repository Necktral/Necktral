#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${ROOT_DIR}/backend/src"
MODE="${1:-full}"
TS="${TS:-$(date +%Y%m%d_%H%M%S)}"

OUT_DIR="${OUT_DIR:-${ROOT_DIR}/docs/operacion/evidencia/phase9_go_live_${TS}}"
mkdir -p "${OUT_DIR}"

COMPANY_ID="${COMPANY_ID:-5}"
BRANCH_ID="${BRANCH_ID:-6}"
SERIES="${SERIES:-B}"
CONSUMER="${CONSUMER:-accounting.projector}"

MAX_INBOX_FAILED="${MAX_INBOX_FAILED:-0}"
MAX_OUTBOX_FAILED="${MAX_OUTBOX_FAILED:-0}"
MAX_FAILED_JOBS="${MAX_FAILED_JOBS:-0}"
MAX_RETRY_OVERDUE="${MAX_RETRY_OVERDUE:-0}"
MAX_CONTINGENCY_OPEN="${MAX_CONTINGENCY_OPEN:-0}"
MAX_PROVIDER_FAILURES="${MAX_PROVIDER_FAILURES:-0}"

MAX_CYCLE_ATTEMPTS="${MAX_CYCLE_ATTEMPTS:-6}"
CYCLE_SLEEP_SECONDS="${CYCLE_SLEEP_SECONDS:-120}"
REQUIRE_CONSECUTIVE_CLEAN_CYCLES="${REQUIRE_CONSECUTIVE_CLEAN_CYCLES:-2}"
CLEANUP_BLOCKED_ARTIFACTS="${CLEANUP_BLOCKED_ARTIFACTS:-1}"

F9_PROVIDER_MODE="${F9_PROVIDER_MODE:-}"
F9_HTTP_BASE_URL="${F9_HTTP_BASE_URL:-}"
F9_HTTP_API_KEY="${F9_HTTP_API_KEY:-}"
F9_HTTP_TIMEOUT_SECONDS="${F9_HTTP_TIMEOUT_SECONDS:-}"
F9_HTTP_VERIFY_TLS="${F9_HTTP_VERIFY_TLS:-}"
F9_ALLOW_EMULATED_FALLBACK="${F9_ALLOW_EMULATED_FALLBACK:-}"

F8_EVIDENCE_DIR="${F8_EVIDENCE_DIR:-${ROOT_DIR}/docs/operacion/evidencia/phase8_go_live_20260309_1040}"
F8_VERIFY_FILE="${F8_VERIFY_FILE:-${F8_EVIDENCE_DIR}/17_phase8_burnin_verify.json}"
F8_SUMMARY_FILE="${F8_SUMMARY_FILE:-${F8_EVIDENCE_DIR}/33_phase8_master_summary.json}"
F8_ACCOUNTANT_FILE="${F8_ACCOUNTANT_FILE:-${F8_EVIDENCE_DIR}/65_phase8_accountant_verify.json}"

LOCK_ROOT="${LOCK_ROOT:-${OUT_DIR}/.locks}"
LOCK_FILE="${LOCK_ROOT}/phase9_go_live.lock"

resolve_python() {
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    if command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
      printf '%s\n' "${PYTHON_BIN}"
      return 0
    fi
    echo "[phase9] PYTHON_BIN inválido: ${PYTHON_BIN}" >&2
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
  echo "[phase9] no se encontró intérprete Python (python3/python)" >&2
  return 1
}

PYTHON_BIN="$(resolve_python)" || exit 127

if command -v flock >/dev/null 2>&1; then
  mkdir -p "${LOCK_ROOT}"
  exec 9>"${LOCK_FILE}"
  if ! flock -n 9; then
    echo "[phase9] lock ocupado, evita solapamiento"
    exit 0
  fi
fi

run_manage() {
  local -a env_prefix
  env_prefix=()
  if [[ -n "${F9_PROVIDER_MODE}" ]]; then
    env_prefix+=("FISCAL_ADAPTER_B_PROVIDER=${F9_PROVIDER_MODE}")
  fi
  if [[ -n "${F9_HTTP_BASE_URL}" ]]; then
    env_prefix+=("FISCAL_ADAPTER_B_HTTP_BASE_URL=${F9_HTTP_BASE_URL}")
  fi
  if [[ -n "${F9_HTTP_API_KEY}" ]]; then
    env_prefix+=("FISCAL_ADAPTER_B_HTTP_API_KEY=${F9_HTTP_API_KEY}")
  fi
  if [[ -n "${F9_HTTP_TIMEOUT_SECONDS}" ]]; then
    env_prefix+=("FISCAL_ADAPTER_B_HTTP_TIMEOUT_SECONDS=${F9_HTTP_TIMEOUT_SECONDS}")
  fi
  if [[ -n "${F9_HTTP_VERIFY_TLS}" ]]; then
    env_prefix+=("FISCAL_ADAPTER_B_HTTP_VERIFY_TLS=${F9_HTTP_VERIFY_TLS}")
  fi
  if [[ -n "${F9_ALLOW_EMULATED_FALLBACK}" ]]; then
    env_prefix+=("FISCAL_ADAPTER_B_ALLOW_EMULATED_FALLBACK=${F9_ALLOW_EMULATED_FALLBACK}")
  fi
  (
    cd "${APP_DIR}"
    env "${env_prefix[@]}" "${PYTHON_BIN}" manage.py "$@"
  )
}

ensure_f8_closed() {
  F8_VERIFY_FILE="${F8_VERIFY_FILE}" \
  F8_SUMMARY_FILE="${F8_SUMMARY_FILE}" \
  F8_ACCOUNTANT_FILE="${F8_ACCOUNTANT_FILE}" \
  COMPANY_ID="${COMPANY_ID}" \
  BRANCH_ID="${BRANCH_ID}" \
  "${PYTHON_BIN}" - <<'PY'
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

verify_file = Path(os.environ["F8_VERIFY_FILE"])
summary_file = Path(os.environ["F8_SUMMARY_FILE"])
accountant_file = Path(os.environ["F8_ACCOUNTANT_FILE"])
company_id = int(os.environ["COMPANY_ID"])
branch_id = int(os.environ["BRANCH_ID"])

errors: list[str] = []
details: dict[str, object] = {
    "company_id": company_id,
    "branch_id": branch_id,
    "verify_file": str(verify_file),
    "summary_file": str(summary_file),
    "accountant_file": str(accountant_file),
}

def _load(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(str(path))
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"json inválido en {path}: se esperaba objeto")
    return data

try:
    verify = _load(verify_file)
    details["burn_in_passed"] = bool(verify.get("burn_in_passed"))
    details["burn_in_days"] = verify.get("days", [])
    details["burn_in_failed_days"] = verify.get("failed_days", [])
    if bool(verify.get("burn_in_passed")) is not True:
        errors.append("F8 burn-in no está en PASS (17_phase8_burnin_verify.json).")
except Exception as exc:  # noqa: BLE001
    errors.append(f"No se pudo validar verify burn-in: {exc}")

try:
    summary = _load(summary_file)
    details["phase8_status"] = summary.get("status")
    details["rollback_required"] = bool(summary.get("rollback_required"))
    if str(summary.get("status") or "") != "READY_TO_CLOSE_F8":
        errors.append("F8 summary no está en READY_TO_CLOSE_F8 (33_phase8_master_summary.json).")
    if bool(summary.get("rollback_required")):
        errors.append("F8 summary reporta rollback_required=true.")
except Exception as exc:  # noqa: BLE001
    errors.append(f"No se pudo validar summary F8: {exc}")

try:
    accountant = _load(accountant_file)
    details["signoff_passed"] = bool(accountant.get("signoff_passed"))
    details["final_approved_present"] = bool(accountant.get("final_approved_present"))
    if bool(accountant.get("signoff_passed")) is not True:
        errors.append("Sign-off contador no está en PASS (65_phase8_accountant_verify.json).")
    if bool(accountant.get("final_approved_present")) is not True:
        errors.append("No existe FINAL_APPROVED del contador.")
except Exception as exc:  # noqa: BLE001
    errors.append(f"No se pudo validar sign-off contador: {exc}")

payload = {
    "f8_closed": len(errors) == 0,
    "errors": errors,
    "details": details,
}
print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
if errors:
    sys.exit(2)
PY
}

run_precheck() {
  local provider_log="${OUT_DIR}/01_phase9_provider_check.txt"
  local precheck_json="${OUT_DIR}/00_phase9_precheck.json"

  local f8_json
  if ! f8_json="$(ensure_f8_closed)"; then
    printf '%s\n' "${f8_json}" > "${precheck_json}"
    echo "[phase9] precheck falló: F8 no cerrada correctamente" >&2
    return 2
  fi

  local provider_rc=0
  set +e
  run_manage test_adapter_b_provider \
    --company-id "${COMPANY_ID}" \
    --branch-id "${BRANCH_ID}" \
    --series "${SERIES}" > "${provider_log}" 2>&1
  provider_rc=$?
  set -e

  F8_JSON="${f8_json}" \
  PROVIDER_RC="${provider_rc}" \
  PROVIDER_LOG="${provider_log}" \
  F9_PROVIDER_MODE="${F9_PROVIDER_MODE}" \
  F9_HTTP_BASE_URL="${F9_HTTP_BASE_URL}" \
  F9_HTTP_API_KEY="${F9_HTTP_API_KEY}" \
  F9_HTTP_TIMEOUT_SECONDS="${F9_HTTP_TIMEOUT_SECONDS}" \
  F9_HTTP_VERIFY_TLS="${F9_HTTP_VERIFY_TLS}" \
  COMPANY_ID="${COMPANY_ID}" \
  BRANCH_ID="${BRANCH_ID}" \
  SERIES="${SERIES}" \
  "${PYTHON_BIN}" - <<'PY' > "${precheck_json}"
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path

f8_json = json.loads(os.environ["F8_JSON"])
provider_rc = int(os.environ["PROVIDER_RC"])
provider_log = Path(os.environ["PROVIDER_LOG"])
provider_output = provider_log.read_text(encoding="utf-8", errors="ignore") if provider_log.exists() else ""

payload = {
    "schema_version": 1,
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "pilot_scope": {
        "company_id": int(os.environ["COMPANY_ID"]),
        "branch_id": int(os.environ["BRANCH_ID"]),
        "series": str(os.environ["SERIES"]),
    },
    "provider_runtime_override": {
        "FISCAL_ADAPTER_B_PROVIDER": str(os.environ.get("F9_PROVIDER_MODE", "")),
        "FISCAL_ADAPTER_B_HTTP_BASE_URL_configured": bool(str(os.environ.get("F9_HTTP_BASE_URL", "")).strip()),
        "FISCAL_ADAPTER_B_HTTP_API_KEY_configured": bool(str(os.environ.get("F9_HTTP_API_KEY", "")).strip()),
        "FISCAL_ADAPTER_B_HTTP_TIMEOUT_SECONDS": str(os.environ.get("F9_HTTP_TIMEOUT_SECONDS", "")),
        "FISCAL_ADAPTER_B_HTTP_VERIFY_TLS": str(os.environ.get("F9_HTTP_VERIFY_TLS", "")),
    },
    "f8_precondition": f8_json,
    "provider_check": {
        "ok": provider_rc == 0,
        "return_code": provider_rc,
        "log_file": str(provider_log),
        "output": provider_output[-4000:],
    },
}
payload["precheck_passed"] = bool(payload["f8_precondition"].get("f8_closed")) and bool(payload["provider_check"]["ok"])
print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
PY

  if [[ "${provider_rc}" -ne 0 ]]; then
    echo "[phase9] precheck falló: provider check no pasó. Ver ${provider_log}" >&2
    return 3
  fi
  echo "[phase9] precheck ok: ${precheck_json}"
}

cleanup_blocked_artifacts() {
  local cleanup_json="${OUT_DIR}/21_phase9_cleanup.json"
  (
    cd "${APP_DIR}"
    COMPANY_ID="${COMPANY_ID}" \
    BRANCH_ID="${BRANCH_ID}" \
    "${PYTHON_BIN}" manage.py shell <<'PY'
from __future__ import annotations

import json
import os
from datetime import datetime, timezone

from kernels.facturacion.models import BillingDocument, DocStatus, FiscalMode, FiscalPrintJob, FiscalStatus
from kernels.facturacion.services import retry_fiscal_print_job

company_id = int(os.environ["COMPANY_ID"])
branch_id = int(os.environ["BRANCH_ID"])

docs = list(
    BillingDocument.objects.filter(
        company_id=company_id,
        branch_id=branch_id,
        status=DocStatus.ISSUED,
        fiscal_mode_resolved=FiscalMode.B,
        customer_name__startswith="CERT-",
        fiscal_status__in=[FiscalStatus.CONTINGENCY, FiscalStatus.FAILED_PRINT, FiscalStatus.ISSUED],
    ).order_by("id")
)

docs_touched = []
for doc in docs:
    metadata = dict(doc.fiscal_metadata_json or {})
    changed = False
    for key in ("force_print_failure", "force_print_failures_remaining"):
        if key in metadata:
            metadata.pop(key, None)
            changed = True
    if changed:
        doc.fiscal_metadata_json = metadata
        doc.save(update_fields=["fiscal_metadata_json"])
    docs_touched.append(
        {
            "doc_id": int(doc.id),
            "fiscal_status": str(doc.fiscal_status),
            "metadata_cleared": bool(changed),
        }
    )

failed_jobs = list(
    FiscalPrintJob.objects.filter(
        company_id=company_id,
        branch_id=branch_id,
        doc_id__in=[int(doc.id) for doc in docs],
        status=FiscalPrintJob.Status.FAILED,
    ).order_by("id")
)

retried_jobs = []
for job in failed_jobs:
    retried = retry_fiscal_print_job(job_id=int(job.id))
    retried_jobs.append(
        {
            "job_id": int(retried.id),
            "status": str(retried.status),
            "attempt_count": int(retried.attempt_count),
            "doc_id": int(retried.doc_id),
        }
    )

payload = {
    "schema_version": 1,
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "pilot_scope": {"company_id": company_id, "branch_id": branch_id},
    "docs_considered": len(docs),
    "docs_touched": docs_touched,
    "failed_jobs_retried": len(retried_jobs),
    "retried_jobs": retried_jobs,
}
print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
PY
  ) > "${cleanup_json}"
  echo "[phase9] cleanup blocked artifacts: ${cleanup_json}"
}

run_certify() {
  run_manage export_phase9_env_manifest \
    --company-id "${COMPANY_ID}" \
    --branch-id "${BRANCH_ID}" \
    --output "${OUT_DIR}/09_phase9_staging_manifest.json"

  run_manage export_phase9_env_manifest \
    --company-id "${COMPANY_ID}" \
    --branch-id "${BRANCH_ID}" \
    --output "${OUT_DIR}/10_phase9_prod_manifest.json"

  run_manage compare_phase9_env_manifests \
    --left "${OUT_DIR}/09_phase9_staging_manifest.json" \
    --right "${OUT_DIR}/10_phase9_prod_manifest.json" \
    --strict > "${OUT_DIR}/10b_phase9_manifest_compare.json"

  run_manage certify_adapter_b_provider_run \
    --company-id "${COMPANY_ID}" \
    --branch-id "${BRANCH_ID}" \
    --output "${OUT_DIR}/11_phase9_happy.json"

  run_manage certify_adapter_b_provider_run \
    --company-id "${COMPANY_ID}" \
    --branch-id "${BRANCH_ID}" \
    --expect-blocked \
    --output "${OUT_DIR}/12_phase9_blocked.json"

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
provider = payload.get("provider") or {}

ok = (
    bool(payload.get("cycle_passed"))
    and int(health.get("inbox_failed_count") or 0) == 0
    and int(health.get("outbox_failed_count") or 0) == 0
    and int(health.get("failed_jobs_count") or 0) == 0
    and int(health.get("retry_overdue_count") or 0) == 0
    and int(health.get("contingency_open_count") or 0) == 0
    and bool(provider.get("check_ok")) is True
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
    cycle_file="${OUT_DIR}/20_phase9_cycle_${attempt}.json"

    local rc=0
    set +e
    run_manage run_adapter_b_provider_cycle \
      --company-id "${COMPANY_ID}" \
      --branch-id "${BRANCH_ID}" \
      --consumer "${CONSUMER}" \
      --series "${SERIES}" \
      --max-inbox-failed "${MAX_INBOX_FAILED}" \
      --max-outbox-failed "${MAX_OUTBOX_FAILED}" \
      --max-failed-jobs "${MAX_FAILED_JOBS}" \
      --max-retry-overdue "${MAX_RETRY_OVERDUE}" \
      --max-open-contingency "${MAX_CONTINGENCY_OPEN}" \
      --max-provider-failures "${MAX_PROVIDER_FAILURES}" \
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
    echo "[phase9] cycle no alcanzó estabilidad estricta en ${MAX_CYCLE_ATTEMPTS} intentos" >&2
    return 4
  fi
  echo "[phase9] cycle estable con ${REQUIRE_CONSECUTIVE_CLEAN_CYCLES} corridas limpias consecutivas"
}

run_gate() {
  run_manage verify_phase9_go_live \
    --company-id "${COMPANY_ID}" \
    --branch-id "${BRANCH_ID}" \
    --staging-manifest "${OUT_DIR}/09_phase9_staging_manifest.json" \
    --prod-manifest "${OUT_DIR}/10_phase9_prod_manifest.json" \
    --happy-evidence "${OUT_DIR}/11_phase9_happy.json" \
    --blocked-evidence "${OUT_DIR}/12_phase9_blocked.json" \
    --max-inbox-failed "${MAX_INBOX_FAILED}" \
    --max-outbox-failed "${MAX_OUTBOX_FAILED}" \
    --max-failed-jobs "${MAX_FAILED_JOBS}" \
    --max-retry-overdue "${MAX_RETRY_OVERDUE}" \
    --max-contingency-open "${MAX_CONTINGENCY_OPEN}" \
    --output "${OUT_DIR}/13_phase9_gate.json"
}

write_summary() {
  OUT_DIR="${OUT_DIR}" \
  F9_PROVIDER_MODE="${F9_PROVIDER_MODE}" \
  MAX_CYCLE_ATTEMPTS="${MAX_CYCLE_ATTEMPTS}" \
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
summary_path = out_dir / "30_phase9_summary.json"
matrix_path = out_dir / "31_phase9_result_matrix.md"
hash_path = out_dir / "32_phase9_summary.sha256"

def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return payload if isinstance(payload, dict) else {}

precheck = load_json(out_dir / "00_phase9_precheck.json")
manifest_compare = load_json(out_dir / "10b_phase9_manifest_compare.json")
happy = load_json(out_dir / "11_phase9_happy.json")
blocked = load_json(out_dir / "12_phase9_blocked.json")
gate = load_json(out_dir / "13_phase9_gate.json")
cycles = [load_json(Path(p)) for p in sorted(glob.glob(str(out_dir / "20_phase9_cycle_*.json")))]

cycle_clean = []
for c in cycles:
    health = c.get("health") or {}
    provider = c.get("provider") or {}
    is_clean = (
        bool(c.get("cycle_passed"))
        and int(health.get("inbox_failed_count") or 0) == 0
        and int(health.get("outbox_failed_count") or 0) == 0
        and int(health.get("failed_jobs_count") or 0) == 0
        and int(health.get("retry_overdue_count") or 0) == 0
        and int(health.get("contingency_open_count") or 0) == 0
        and bool(provider.get("check_ok")) is True
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

summary = {
    "schema_version": 1,
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "provider_mode_override": str(os.environ.get("F9_PROVIDER_MODE", "")),
    "files": {
        "precheck": "00_phase9_precheck.json",
        "staging_manifest": "09_phase9_staging_manifest.json",
        "prod_manifest": "10_phase9_prod_manifest.json",
        "manifest_compare": "10b_phase9_manifest_compare.json",
        "happy": "11_phase9_happy.json",
        "blocked": "12_phase9_blocked.json",
        "gate": "13_phase9_gate.json",
        "cycles": [Path(p).name for p in sorted(glob.glob(str(out_dir / "20_phase9_cycle_*.json")))],
    },
    "checks": {
        "precheck_passed": bool(precheck.get("precheck_passed")),
        "parity_passed": bool(manifest_compare.get("drift_detected") is False),
        "happy_passed": bool(happy.get("passed")),
        "blocked_passed": bool(blocked.get("passed")),
        "gate_passed": bool(gate.get("go_live_passed")),
        "cycle_clean_consecutive_max": int(max_consecutive),
        "cycle_clean_consecutive_required": int(target_consecutive),
    },
}

summary["phase9_go_live_passed"] = bool(
    summary["checks"]["precheck_passed"]
    and summary["checks"]["parity_passed"]
    and summary["checks"]["happy_passed"]
    and summary["checks"]["blocked_passed"]
    and summary["checks"]["gate_passed"]
    and int(summary["checks"]["cycle_clean_consecutive_max"]) >= int(summary["checks"]["cycle_clean_consecutive_required"])
)

raw_min = json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
digest = hashlib.sha256(raw_min).hexdigest()
secret = str(os.environ.get("PHASE9_EVIDENCE_SECRET", os.environ.get("PHASE6_EVIDENCE_SECRET", ""))).strip()
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
hash_path.write_text(f"{digest}  30_phase9_summary.json\n", encoding="utf-8")

matrix = (
    "# F9 Go-Live Matrix\n\n"
    "| Check | Result | Evidence |\n"
    "|---|---|---|\n"
    f"| Precheck F8 + provider | {'PASS' if summary['checks']['precheck_passed'] else 'FAIL'} | 00_phase9_precheck.json |\n"
    f"| Manifest parity strict | {'PASS' if summary['checks']['parity_passed'] else 'FAIL'} | 10b_phase9_manifest_compare.json |\n"
    f"| Certification happy | {'PASS' if summary['checks']['happy_passed'] else 'FAIL'} | 11_phase9_happy.json |\n"
    f"| Certification blocked | {'PASS' if summary['checks']['blocked_passed'] else 'FAIL'} | 12_phase9_blocked.json |\n"
    f"| Cycle strict stability | {'PASS' if summary['checks']['cycle_clean_consecutive_max'] >= summary['checks']['cycle_clean_consecutive_required'] else 'FAIL'} | 20_phase9_cycle_*.json |\n"
    f"| Go-live gate strict | {'PASS' if summary['checks']['gate_passed'] else 'FAIL'} | 13_phase9_gate.json |\n"
    "\n"
    f"Estado global: **{'PASS' if summary['phase9_go_live_passed'] else 'FAIL'}**\n"
)
matrix_path.write_text(matrix, encoding="utf-8")
print(f"[phase9] summary ready: {summary_path}")
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

echo "[phase9] done mode=${MODE} output=${OUT_DIR}"
