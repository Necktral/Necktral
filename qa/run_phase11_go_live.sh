#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${ROOT_DIR}/backend/src"
MODE="${1:-full}"
TS="${TS:-$(date +%Y%m%d_%H%M%S)}"

OUT_DIR="${OUT_DIR:-${ROOT_DIR}/docs/operacion/evidencia/phase11_go_live_${TS}}"
mkdir -p "${OUT_DIR}"

COMPANY_ID="${COMPANY_ID:-5}"
BRANCH_ID="${BRANCH_ID:-6}"
CONSUMER="${CONSUMER:-accounting.projector}"

OPEN_SLA_HOURS="${OPEN_SLA_HOURS:-24}"
DISPUTE_SLA_HOURS="${DISPUTE_SLA_HOURS:-24}"

MAX_OPEN_INTERCOMPANY="${MAX_OPEN_INTERCOMPANY:-0}"
MAX_DISPUTED_INTERCOMPANY="${MAX_DISPUTED_INTERCOMPANY:-0}"
MAX_OPEN_OUTSIDE_SLA="${MAX_OPEN_OUTSIDE_SLA:-0}"
MAX_DISPUTED_OUTSIDE_SLA="${MAX_DISPUTED_OUTSIDE_SLA:-0}"
MAX_STALE_CONFIRMED_UNCLOSED="${MAX_STALE_CONFIRMED_UNCLOSED:-0}"
MAX_OPEN_BLOCKING_EXCEPTIONS="${MAX_OPEN_BLOCKING_EXCEPTIONS:-0}"
MAX_BLOCKED_CONSOLIDATION="${MAX_BLOCKED_CONSOLIDATION:-0}"
MAX_INBOX_FAILED="${MAX_INBOX_FAILED:-0}"
MAX_OUTBOX_FAILED="${MAX_OUTBOX_FAILED:-0}"

CYCLE_LIMIT="${CYCLE_LIMIT:-200}"
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
F10_SUMMARY="${F10_SUMMARY:-${ROOT_DIR}/docs/operacion/evidencia/phase10_go_live_20260309_200749/30_phase10_summary.json}"

LOCK_ROOT="${LOCK_ROOT:-${OUT_DIR}/.locks}"
LOCK_FILE="${LOCK_ROOT}/phase11_go_live.lock"

resolve_python() {
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    if command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
      printf '%s\n' "${PYTHON_BIN}"
      return 0
    fi
    echo "[phase11] PYTHON_BIN inválido: ${PYTHON_BIN}" >&2
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
  echo "[phase11] no se encontró intérprete Python (python3/python)" >&2
  return 1
}

PYTHON_BIN="$(resolve_python)" || exit 127

if command -v flock >/dev/null 2>&1; then
  mkdir -p "${LOCK_ROOT}"
  exec 9>"${LOCK_FILE}"
  if ! flock -n 9; then
    echo "[phase11] lock ocupado, evita solapamiento"
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
  COMPANY_ID="${COMPANY_ID}" \
  BRANCH_ID="${BRANCH_ID}" \
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
    }
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
        errors.append("F8 signoff contador no está en PASS.")


def _check_summary(path_env: str, key: str, field: str) -> None:
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
]:
    try:
        _check_summary(env_key, key, field)
    except Exception as exc:  # noqa: BLE001
        errors.append(f"No se pudo validar {key}: {exc}")

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
  local precheck_json="${OUT_DIR}/00_phase11_precheck.json"
  local manifest_json="${OUT_DIR}/01_phase11_manifest_precheck.json"

  local precheck_payload
  if ! precheck_payload="$(ensure_preconditions)"; then
    printf '%s\n' "${precheck_payload}" > "${precheck_json}"
    echo "[phase11] precheck falló: precondiciones F8/F9/F10 no cumplen" >&2
    return 2
  fi
  printf '%s\n' "${precheck_payload}" > "${precheck_json}"

  run_manage export_phase11_env_manifest \
    --company-id "${COMPANY_ID}" \
    --branch-id "${BRANCH_ID}" \
    --output "${manifest_json}"

  MANIFEST_FILE="${manifest_json}" "${PYTHON_BIN}" - <<'PY'
from __future__ import annotations
import json
import os
import sys
from pathlib import Path

p = Path(os.environ["MANIFEST_FILE"])
payload = json.loads(p.read_text(encoding="utf-8"))
errors = []
if int((payload.get("company_links") or {}).get("count") or 0) <= 0:
    errors.append("No hay CompanyLink activo para F11.")
if int((payload.get("write_grants") or {}).get("count") or 0) <= 0:
    errors.append("No hay LinkGrant WRITE activo para F11.")
if int((payload.get("dispute_reasons") or {}).get("count") or 0) <= 0:
    errors.append("No hay catálogo activo de dispute reasons.")
if errors:
    print("\n".join(errors))
    sys.exit(3)
PY

  echo "[phase11] precheck ok: ${precheck_json}"
}

run_certify() {
  run_manage export_phase11_env_manifest \
    --company-id "${COMPANY_ID}" \
    --branch-id "${BRANCH_ID}" \
    --output "${OUT_DIR}/20_phase11_staging_manifest.json"

  run_manage export_phase11_env_manifest \
    --company-id "${COMPANY_ID}" \
    --branch-id "${BRANCH_ID}" \
    --output "${OUT_DIR}/21_phase11_prod_manifest.json"

  run_manage certify_phase11_intercompany_sla \
    --company-id "${COMPANY_ID}" \
    --open-sla-hours "${OPEN_SLA_HOURS}" \
    --dispute-sla-hours "${DISPUTE_SLA_HOURS}" \
    --output "${OUT_DIR}/22_phase11_happy.json"

  run_manage certify_phase11_intercompany_sla \
    --company-id "${COMPANY_ID}" \
    --open-sla-hours "${OPEN_SLA_HOURS}" \
    --dispute-sla-hours "${DISPUTE_SLA_HOURS}" \
    --expect-blocked \
    --output "${OUT_DIR}/23_phase11_blocked.json"

  if [[ "${CLEANUP_BLOCKED_ARTIFACTS}" == "1" ]]; then
    cleanup_blocked_artifacts
  fi
}

cleanup_blocked_artifacts() {
  local cleanup_json="${OUT_DIR}/26_phase11_cleanup.json"
  (
    cd "${APP_DIR}"
    HAPPY_EVIDENCE_FILE="${OUT_DIR}/22_phase11_happy.json" \
    BLOCKED_EVIDENCE_FILE="${OUT_DIR}/23_phase11_blocked.json" \
    COMPANY_ID="${COMPANY_ID}" \
    "${PYTHON_BIN}" manage.py shell <<'PY'
from __future__ import annotations

import json
import os

from django.utils import timezone

from apps.accounting.models import IntercompanyDisputeCase, IntercompanyTransaction
from apps.accounting.phase7b import settle_intercompany_transaction
from apps.cec.models import CECException

blocked_path = str(os.environ["BLOCKED_EVIDENCE_FILE"])
happy_path = str(os.environ["HAPPY_EVIDENCE_FILE"])
company_id = int(os.environ["COMPANY_ID"])

with open(blocked_path, "r", encoding="utf-8") as fh:
    blocked = json.load(fh)
with open(happy_path, "r", encoding="utf-8") as fh:
    happy = json.load(fh)

target_ids = set()
for payload in [blocked, happy]:
    tx_id = str(payload.get("tx_id") or "").strip()
    if tx_id:
        target_ids.add(tx_id)

legacy_ids = list(
    IntercompanyTransaction.objects.filter(
        source_company_id=company_id,
        description__startswith="phase11-cert-",
    )
    .exclude(status=IntercompanyTransaction.Status.CLOSED)
    .values_list("tx_id", flat=True)
)
for tx_id in legacy_ids:
    target_ids.add(str(tx_id))

closed_ids: list[str] = []
close_errors: list[dict[str, str]] = []
for tx_id in sorted(target_ids):
    tx = IntercompanyTransaction.objects.filter(tx_id=tx_id, source_company_id=company_id).first()
    if tx is None:
        continue
    if str(tx.status) != IntercompanyTransaction.Status.CLOSED:
        try:
            settle_intercompany_transaction(
                tx_id=str(tx.tx_id),
                source_amount=tx.amount,
                target_amount=tx.amount,
                actor_user=None,
                note="phase11 cleanup after blocked certification",
                close_when_confirmed=True,
                allow_difference=False,
                effective_company_id=int(company_id),
            )
            closed_ids.append(str(tx.tx_id))
        except Exception as exc:  # noqa: BLE001
            close_errors.append({"tx_id": str(tx.tx_id), "error": str(exc)})

open_statuses = [CECException.Status.OPEN, CECException.Status.IN_PROGRESS]
resolved_ex_count = 0
for tx_id in sorted(target_ids):
    qs = CECException.objects.filter(
        source_module="ACCOUNTING",
        related_object_type="INTERCOMPANY_TX",
        related_object_id=str(tx_id),
        status__in=open_statuses,
    )
    rows = list(qs)
    for row in rows:
        row.status = CECException.Status.RESOLVED
        row.resolved_at = timezone.now()
        row.resolution_note = "phase11 cleanup after blocked certification"
        row.save(update_fields=["status", "resolved_at", "resolution_note"])
        resolved_ex_count += 1

settled_disputes = 0
for tx_id in sorted(target_ids):
    rows = list(
        IntercompanyDisputeCase.objects.filter(
            transaction__tx_id=str(tx_id),
            status__in=[
                IntercompanyDisputeCase.Status.OPEN,
                IntercompanyDisputeCase.Status.UNDER_REVIEW,
                IntercompanyDisputeCase.Status.APPROVED,
            ],
        )
    )
    for row in rows:
        row.status = IntercompanyDisputeCase.Status.SETTLED
        row.resolution_note = "phase11 cleanup after blocked certification"
        row.settled_at = timezone.now()
        row.closed_at = timezone.now()
        row.save(update_fields=["status", "resolution_note", "settled_at", "closed_at", "updated_at"])
        settled_disputes += 1

payload = {
    "schema_version": 1,
    "pilot_scope": {"company_id": int(company_id)},
    "target_tx_ids": sorted(target_ids),
    "closed_count": int(len(closed_ids)),
    "closed_tx_ids": closed_ids,
    "close_errors": close_errors,
    "resolved_exceptions_count": int(resolved_ex_count),
    "settled_dispute_cases_count": int(settled_disputes),
}
print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))
PY
  ) > "${cleanup_json}"
  echo "[phase11] cleanup blocked artifacts: ${cleanup_json}"
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
ok = (
    bool(payload.get("cycle_passed"))
    and int(health.get("open_intercompany_count") or 0) == 0
    and int(health.get("disputed_intercompany_count") or 0) == 0
    and int(health.get("open_outside_sla_count") or 0) == 0
    and int(health.get("disputed_outside_sla_count") or 0) == 0
    and int(health.get("stale_confirmed_unclosed_count") or 0) == 0
    and int(health.get("open_intercompany_blocking_exception_count") or 0) == 0
    and int(health.get("inbox_failed_count") or 0) == 0
    and int(health.get("outbox_failed_count") or 0) == 0
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
    cycle_file="${OUT_DIR}/24_phase11_cycle_${attempt}.json"

    local rc=0
    set +e
    run_manage run_phase11_intercompany_cycle \
      --company-id "${COMPANY_ID}" \
      --consumer "${CONSUMER}" \
      --limit "${CYCLE_LIMIT}" \
      --dispatch-limit "${DISPATCH_LIMIT}" \
      --open-sla-hours "${OPEN_SLA_HOURS}" \
      --dispute-sla-hours "${DISPUTE_SLA_HOURS}" \
      --max-open-intercompany "${MAX_OPEN_INTERCOMPANY}" \
      --max-disputed-intercompany "${MAX_DISPUTED_INTERCOMPANY}" \
      --max-open-outside-sla "${MAX_OPEN_OUTSIDE_SLA}" \
      --max-disputed-outside-sla "${MAX_DISPUTED_OUTSIDE_SLA}" \
      --max-stale-confirmed-unclosed "${MAX_STALE_CONFIRMED_UNCLOSED}" \
      --max-open-blocking-exceptions "${MAX_OPEN_BLOCKING_EXCEPTIONS}" \
      --max-inbox-failed "${MAX_INBOX_FAILED}" \
      --max-outbox-failed "${MAX_OUTBOX_FAILED}" \
      --output "${cycle_file}"
    rc=$?
    set -e

    if cycle_check_clean "${cycle_file}" && [[ "${rc}" -eq 0 ]]; then
      consecutive_clean=$((consecutive_clean + 1))
    else
      consecutive_clean=0
      if [[ "${CLEANUP_BLOCKED_ARTIFACTS}" == "1" ]] && [[ -f "${OUT_DIR}/23_phase11_blocked.json" ]]; then
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
    echo "[phase11] cycle no alcanzó estabilidad estricta en ${MAX_CYCLE_ATTEMPTS} intentos" >&2
    return 4
  fi
  echo "[phase11] cycle estable con ${REQUIRE_CONSECUTIVE_CLEAN_CYCLES} corridas limpias consecutivas"
}

run_gate() {
  run_manage verify_phase11_go_live \
    --company-id "${COMPANY_ID}" \
    --consumer "${CONSUMER}" \
    --open-sla-hours "${OPEN_SLA_HOURS}" \
    --dispute-sla-hours "${DISPUTE_SLA_HOURS}" \
    --staging-manifest "${OUT_DIR}/20_phase11_staging_manifest.json" \
    --prod-manifest "${OUT_DIR}/21_phase11_prod_manifest.json" \
    --happy-evidence "${OUT_DIR}/22_phase11_happy.json" \
    --blocked-evidence "${OUT_DIR}/23_phase11_blocked.json" \
    --max-open-intercompany "${MAX_OPEN_INTERCOMPANY}" \
    --max-disputed-intercompany "${MAX_DISPUTED_INTERCOMPANY}" \
    --max-open-outside-sla "${MAX_OPEN_OUTSIDE_SLA}" \
    --max-disputed-outside-sla "${MAX_DISPUTED_OUTSIDE_SLA}" \
    --max-stale-confirmed-unclosed "${MAX_STALE_CONFIRMED_UNCLOSED}" \
    --max-open-blocking-exceptions "${MAX_OPEN_BLOCKING_EXCEPTIONS}" \
    --max-blocked-consolidation "${MAX_BLOCKED_CONSOLIDATION}" \
    --max-inbox-failed "${MAX_INBOX_FAILED}" \
    --max-outbox-failed "${MAX_OUTBOX_FAILED}" \
    --output "${OUT_DIR}/25_phase11_gate.json"
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
summary_path = out_dir / "30_phase11_summary.json"
matrix_path = out_dir / "31_phase11_result_matrix.md"
hash_path = out_dir / "32_phase11_summary.sha256"

def load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    return payload if isinstance(payload, dict) else {}

precheck = load_json(out_dir / "00_phase11_precheck.json")
happy = load_json(out_dir / "22_phase11_happy.json")
blocked = load_json(out_dir / "23_phase11_blocked.json")
gate = load_json(out_dir / "25_phase11_gate.json")
cycles = [load_json(Path(p)) for p in sorted(glob.glob(str(out_dir / "24_phase11_cycle_*.json")))]

cycle_clean = []
for c in cycles:
    health = c.get("health") or {}
    is_clean = (
        bool(c.get("cycle_passed"))
        and int(health.get("open_intercompany_count") or 0) == 0
        and int(health.get("disputed_intercompany_count") or 0) == 0
        and int(health.get("open_outside_sla_count") or 0) == 0
        and int(health.get("disputed_outside_sla_count") or 0) == 0
        and int(health.get("stale_confirmed_unclosed_count") or 0) == 0
        and int(health.get("open_intercompany_blocking_exception_count") or 0) == 0
        and int(health.get("inbox_failed_count") or 0) == 0
        and int(health.get("outbox_failed_count") or 0) == 0
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

blocked_ok = bool(
    bool(blocked.get("passed"))
    and bool(blocked.get("blocked"))
    and bool(blocked.get("deterministic_replay"))
)
happy_ok = bool(
    bool(happy.get("passed"))
    and not bool(happy.get("blocked"))
    and bool(happy.get("deterministic_replay"))
)

summary = {
    "schema_version": 1,
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "files": {
        "precheck": "00_phase11_precheck.json",
        "staging_manifest": "20_phase11_staging_manifest.json",
        "prod_manifest": "21_phase11_prod_manifest.json",
        "happy": "22_phase11_happy.json",
        "blocked": "23_phase11_blocked.json",
        "gate": "25_phase11_gate.json",
        "cycles": [Path(p).name for p in sorted(glob.glob(str(out_dir / "24_phase11_cycle_*.json")))],
    },
    "checks": {
        "precheck_passed": bool(precheck.get("precheck_passed")),
        "happy_passed": bool(happy_ok),
        "blocked_passed": bool(blocked_ok),
        "gate_passed": bool(gate.get("go_live_passed")),
        "cycle_clean_consecutive_max": int(max_consecutive),
        "cycle_clean_consecutive_required": int(target_consecutive),
    },
}
summary["phase11_go_live_passed"] = bool(
    summary["checks"]["precheck_passed"]
    and summary["checks"]["happy_passed"]
    and summary["checks"]["blocked_passed"]
    and summary["checks"]["gate_passed"]
    and int(summary["checks"]["cycle_clean_consecutive_max"]) >= int(summary["checks"]["cycle_clean_consecutive_required"])
)

raw_min = json.dumps(summary, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
digest = hashlib.sha256(raw_min).hexdigest()
secret = str(os.environ.get("PHASE11_EVIDENCE_SECRET", "")).strip()
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
hash_path.write_text(f"{digest}  30_phase11_summary.json\n", encoding="utf-8")

matrix = (
    "# F11 Go-Live Matrix\n\n"
    "| Check | Result |\n"
    "| --- | --- |\n"
    f"| precheck_passed | {'PASS' if summary['checks']['precheck_passed'] else 'FAIL'} |\n"
    f"| happy_passed | {'PASS' if summary['checks']['happy_passed'] else 'FAIL'} |\n"
    f"| blocked_passed | {'PASS' if summary['checks']['blocked_passed'] else 'FAIL'} |\n"
    f"| gate_passed | {'PASS' if summary['checks']['gate_passed'] else 'FAIL'} |\n"
    f"| cycle_stability | {summary['checks']['cycle_clean_consecutive_max']}/{summary['checks']['cycle_clean_consecutive_required']} |\n"
    f"| phase11_go_live_passed | {'PASS' if summary['phase11_go_live_passed'] else 'FAIL'} |\n"
)
matrix_path.write_text(matrix, encoding="utf-8")
PY
  echo "[phase11] summary ready: ${OUT_DIR}/30_phase11_summary.json"
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

echo "[phase11] done mode=${MODE} output=${OUT_DIR}"
