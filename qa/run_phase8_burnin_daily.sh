#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${ROOT_DIR}/backend/src"
TS="${TS:-$(date +%Y%m%d_%H%M%S)}"
TODAY_LOCAL="${TODAY_LOCAL:-$(date +%F)}"
DAY_TAG="${DAY_TAG:-${TODAY_LOCAL//-/}}"

OUT_DIR="${OUT_DIR:-${ROOT_DIR}/docs/operacion/evidencia/phase8_go_live_20260309_1040}"
COMPANY_ID="${COMPANY_ID:-5}"
BRANCH_ID="${BRANCH_ID:-6}"
PARENT_COMPANY_ID="${PARENT_COMPANY_ID:-5}"
COMPANY_IDS="${COMPANY_IDS:-5}"
PHASE8_START_DATE="${PHASE8_START_DATE:-2026-03-09}"
PHASE8_END_DATE="${PHASE8_END_DATE:-2026-03-22}"
PHASE8_CALENDAR_FILE="${PHASE8_CALENDAR_FILE:-}"
DAY_MODE_RESOLVED="${DAY_MODE_RESOLVED:-UNKNOWN}"
EVENTUAL_CLOSE_APPLIED="${EVENTUAL_CLOSE_APPLIED:-0}"
EVENTUAL_REASON_CODE="${EVENTUAL_REASON_CODE:-}"
EVENTUAL_APPROVED_BY="${EVENTUAL_APPROVED_BY:-}"
EVENTUAL_NOTE="${EVENTUAL_NOTE:-}"
LOCK_ROOT="${LOCK_ROOT:-${OUT_DIR}/.locks}"

resolve_python() {
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    if command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
      printf '%s\n' "${PYTHON_BIN}"
      return 0
    fi
    echo "[phase8-burnin-daily] PYTHON_BIN inválido: ${PYTHON_BIN}" >&2
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
  echo "[phase8-burnin-daily] no se encontró intérprete Python (python3/python)" >&2
  return 1
}

PYTHON_BIN="$(resolve_python)" || exit 127

if command -v flock >/dev/null 2>&1; then
  mkdir -p "${LOCK_ROOT}"
  LOCK_FILE="${LOCK_ROOT}/phase8_burnin_daily.lock"
  exec 9>"${LOCK_FILE}"
  if ! flock -n 9; then
    echo "[phase8-burnin-daily] lock ocupado, skip seguro"
    exit 0
  fi
fi

MIN_BURNIN_DAYS="${MIN_BURNIN_DAYS:-}"
if [[ -z "${MIN_BURNIN_DAYS}" ]]; then
  MIN_BURNIN_DAYS="$(PHASE8_CALENDAR_FILE="${PHASE8_CALENDAR_FILE}" "${PYTHON_BIN}" - <<'PY'
from __future__ import annotations

import json
import os

calendar_file = str(os.environ.get("PHASE8_CALENDAR_FILE", "") or "").strip()
default = 14
if not calendar_file:
    print(default)
    raise SystemExit(0)
try:
    with open(calendar_file, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    if isinstance(payload, dict):
        v = payload.get("required_pass_days")
        if isinstance(v, int) and v > 0:
            print(v)
            raise SystemExit(0)
except Exception:
    pass
print(default)
PY
)"
fi

if [[ ! -f "${OUT_DIR}/16_phase8_cutover_gate.json" ]]; then
  echo "[phase8-burnin-daily] falta 16_phase8_cutover_gate.json en ${OUT_DIR}" >&2
  exit 2
fi

OUT_DIR="${OUT_DIR}" \
COMPANY_ID="${COMPANY_ID}" \
BRANCH_ID="${BRANCH_ID}" \
PARENT_COMPANY_ID="${PARENT_COMPANY_ID}" \
COMPANY_IDS="${COMPANY_IDS}" \
TODAY_LOCAL="${TODAY_LOCAL}" \
DAY_TAG="${DAY_TAG}" \
"${ROOT_DIR}/qa/run_phase8_go_live.sh" burnin-day

OUT_DIR="${OUT_DIR}" \
COMPANY_ID="${COMPANY_ID}" \
BRANCH_ID="${BRANCH_ID}" \
PARENT_COMPANY_ID="${PARENT_COMPANY_ID}" \
COMPANY_IDS="${COMPANY_IDS}" \
TODAY_LOCAL="${TODAY_LOCAL}" \
DAY_TAG="${DAY_TAG}" \
"${ROOT_DIR}/qa/run_phase8_go_live.sh" rollback-check

cd "${APP_DIR}"
"${PYTHON_BIN}" manage.py verify_phase8_burn_in \
  --evidence-dir "${OUT_DIR}" \
  --min-days "${MIN_BURNIN_DAYS}" \
  --max-failed-days 0 > "${OUT_DIR}/17_phase8_burnin_verify.json"

"${PYTHON_BIN}" manage.py verify_phase8_accountant_signoff \
  --evidence-dir "${OUT_DIR}" \
  --window-start "${PHASE8_START_DATE}" \
  --window-end "${PHASE8_END_DATE}" > "${OUT_DIR}/65_phase8_accountant_verify.json"

export OUT_DIR TS DAY_TAG COMPANY_ID BRANCH_ID PARENT_COMPANY_ID COMPANY_IDS PHASE8_START_DATE PHASE8_END_DATE PHASE8_CALENDAR_FILE MIN_BURNIN_DAYS DAY_MODE_RESOLVED TODAY_LOCAL EVENTUAL_CLOSE_APPLIED EVENTUAL_REASON_CODE EVENTUAL_APPROVED_BY EVENTUAL_NOTE

"${PYTHON_BIN}" - <<'PY'
from __future__ import annotations

import hashlib
import hmac
import json
import os
import sys
from datetime import date, datetime, timedelta, timezone

out_dir = os.environ["OUT_DIR"]
ts = os.environ["TS"]
day_tag = os.environ["DAY_TAG"]
today_iso = str(os.environ.get("TODAY_LOCAL", "") or "").strip() or date.today().isoformat()
day_mode_resolved = str(os.environ.get("DAY_MODE_RESOLVED", "UNKNOWN") or "UNKNOWN").strip().upper()
eventual_applied = str(os.environ.get("EVENTUAL_CLOSE_APPLIED", "0") or "0").strip().lower() in {"1", "true", "yes"}
eventual_reason = str(os.environ.get("EVENTUAL_REASON_CODE", "") or "").strip()
eventual_approved_by = str(os.environ.get("EVENTUAL_APPROVED_BY", "") or "").strip()
eventual_note = str(os.environ.get("EVENTUAL_NOTE", "") or "").strip()
company_id = int(os.environ.get("COMPANY_ID", "5"))
branch_id = int(os.environ.get("BRANCH_ID", "6"))
parent_company_id = int(os.environ.get("PARENT_COMPANY_ID", "5"))
company_ids = [int(x) for x in str(os.environ.get("COMPANY_IDS", "5")).split() if str(x).strip()]
window_start = date.fromisoformat(str(os.environ.get("PHASE8_START_DATE", "2026-03-09")))
window_end = date.fromisoformat(str(os.environ.get("PHASE8_END_DATE", "2026-03-22")))
calendar_file = str(os.environ.get("PHASE8_CALENDAR_FILE", "") or "").strip()
min_days_required = int(os.environ.get("MIN_BURNIN_DAYS", "14"))

burn_path = os.path.join(out_dir, f"phase8_burn_{day_tag}.json")
rollback_path = os.path.join(out_dir, "18_phase8_rollback_eval.json")
verify_path = os.path.join(out_dir, "17_phase8_burnin_verify.json")
summary_path = os.path.join(out_dir, "33_phase8_master_summary.json")
matrix_path = os.path.join(out_dir, "34_phase8_result_matrix.md")
hash_path = os.path.join(out_dir, "35_phase8_master_summary.sha256")
daily_gate_path = os.path.join(out_dir, f"57_phase8_daily_gate_{ts}.json")
tracker_json_path = os.path.join(out_dir, "61_phase8_burnin_calendar_tracker.json")
tracker_md_path = os.path.join(out_dir, "62_phase8_burnin_calendar_tracker.md")
accountant_verify_path = os.path.join(out_dir, "65_phase8_accountant_verify.json")
eventual_evidence_path = os.path.join(out_dir, f"58_phase8_eventual_close_{ts}.json")

with open(burn_path, "r", encoding="utf-8") as fh:
    burn = json.load(fh)
with open(rollback_path, "r", encoding="utf-8") as fh:
    rollback = json.load(fh)
with open(verify_path, "r", encoding="utf-8") as fh:
    verify = json.load(fh)
accountant_verify = {}
if os.path.exists(accountant_verify_path):
    with open(accountant_verify_path, "r", encoding="utf-8") as fh:
        accountant_verify = json.load(fh)

status_by_day = accountant_verify.get("status_by_day", {})
if not isinstance(status_by_day, dict):
    status_by_day = {}
accountant_review_status_today = str(status_by_day.get(today_iso) or "NONE")
accountant_final_signoff_present = bool(accountant_verify.get("final_approved_present"))

base_daily_passed = bool(burn.get("cycle_passed")) and not bool(rollback.get("rollback_required"))
eventual_valid = True
eventual_evidence_file = ""
if eventual_applied:
    validation_errors: list[str] = []
    if not eventual_reason:
        validation_errors.append("missing_reason_code")
    if not eventual_approved_by:
        validation_errors.append("missing_approved_by")
    if len(eventual_note) < 20:
        validation_errors.append("note_too_short")

    eventual_payload = {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "date_local": today_iso,
        "day_mode_resolved": day_mode_resolved,
        "eventual_close_applied": True,
        "reason_code": eventual_reason,
        "approved_by": eventual_approved_by,
        "note": eventual_note,
        "validation_errors": validation_errors,
        "burn_cycle_passed": bool(burn.get("cycle_passed")),
        "rollback_required": bool(rollback.get("rollback_required")),
        "burn_file": os.path.basename(burn_path),
        "rollback_file": os.path.basename(rollback_path),
    }
    raw = json.dumps(eventual_payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode("utf-8")
    digest = hashlib.sha256(raw).hexdigest()
    secret = str(os.environ.get("PHASE8_EVIDENCE_SECRET", "") or "").strip()
    if secret:
        signature = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
        signature_type = "hmac-sha256"
    else:
        signature = digest
        signature_type = "sha256"
    eventual_payload["evidence_hash"] = digest
    eventual_payload["signature"] = signature
    eventual_payload["signature_type"] = signature_type

    with open(eventual_evidence_path, "w", encoding="utf-8") as fh:
        json.dump(eventual_payload, fh, ensure_ascii=False, indent=2, sort_keys=True)
        fh.write("\n")
    eventual_evidence_file = os.path.basename(eventual_evidence_path)
    eventual_valid = len(validation_errors) == 0 and base_daily_passed

daily_passed = bool(base_daily_passed) and (bool(eventual_valid) if eventual_applied else True)

daily_gate = {
    "schema_version": 1,
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "date": day_tag,
    "date_iso": today_iso,
    "daily_passed": daily_passed,
    "burn_cycle_passed": bool(burn.get("cycle_passed")),
    "rollback_required": bool(rollback.get("rollback_required")),
    "rollback_triggers": rollback.get("triggers", []),
    "burn_file": os.path.basename(burn_path),
    "rollback_file": os.path.basename(rollback_path),
    "verify_file": os.path.basename(verify_path),
    "day_mode_resolved": day_mode_resolved,
    "eventual_close_applied": bool(eventual_applied),
    "eventual_close_evidence": eventual_evidence_file,
    "accountant_review_status_today": accountant_review_status_today,
    "accountant_final_signoff_present": accountant_final_signoff_present,
    "accountant_verify_file": os.path.basename(accountant_verify_path) if accountant_verify else "",
}
with open(daily_gate_path, "w", encoding="utf-8") as fh:
    json.dump(daily_gate, fh, ensure_ascii=False, indent=2, sort_keys=True)
    fh.write("\n")

summary = {}
if os.path.exists(summary_path):
    with open(summary_path, "r", encoding="utf-8") as fh:
        summary = json.load(fh)

burn_days = len(verify.get("days", []))
burn_in_passed = bool(verify.get("burn_in_passed"))

summary.update(
    {
        "schema_version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {
            "company_id": company_id,
            "branch_id": branch_id,
            "parent_company_id": parent_company_id,
            "company_ids": sorted(set(company_ids or [company_id])),
        },
        "precutover_passed": bool(summary.get("precutover_passed", True)),
        "phase6_gate_passed": bool(summary.get("phase6_gate_passed", True)),
        "phase7_gate_passed": bool(summary.get("phase7_gate_passed", True)),
        "phase7b_gate_passed": bool(summary.get("phase7b_gate_passed", True)),
        "cutover_passed": bool(summary.get("cutover_passed", True)),
        "burn_in": {
            "burn_in_passed": burn_in_passed,
            "days_covered": burn_days,
            "failed_days": len(verify.get("failed_days", [])),
            "min_days_required": int(min_days_required),
        },
        "rollback_required": bool(rollback.get("rollback_required")),
        "rollback_triggers": rollback.get("triggers", []),
        "latest_daily_gate": os.path.basename(daily_gate_path),
        "burnin_window": {"start": window_start.isoformat(), "end": window_end.isoformat()},
        "burnin_calendar_tracker": os.path.basename(tracker_json_path),
        "day_mode_resolved": day_mode_resolved,
        "eventual_close_applied": bool(eventual_applied),
        "eventual_close_evidence": eventual_evidence_file,
        "accountant_review_status_today": accountant_review_status_today,
        "accountant_final_signoff_present": accountant_final_signoff_present,
        "accountant_verify_file": os.path.basename(accountant_verify_path) if accountant_verify else "",
        "status": "READY_TO_CLOSE_F8"
        if burn_in_passed and not bool(rollback.get("rollback_required")) and accountant_final_signoff_present
        else "IN_PROGRESS_BURN_IN",
    }
)

summary_raw = json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True)
with open(summary_path, "w", encoding="utf-8") as fh:
    fh.write(summary_raw + "\n")

summary_hash = hashlib.sha256(summary_raw.encode("utf-8")).hexdigest()
with open(hash_path, "w", encoding="utf-8") as fh:
    fh.write(f"{summary_hash}  33_phase8_master_summary.json\n")

burn_cell = "PASS" if burn_in_passed else f"PENDING ({burn_days}/{int(min_days_required)})"
matrix = (
    "# F8 Go-Live Execution Matrix\n\n"
    "| Check | Result | Evidence |\n"
    "|---|---|---|\n"
    f"| Pre-cut gate | {'PASS' if summary.get('precutover_passed') else 'FAIL'} | 05_precutover_gate.json |\n"
    f"| F6 gate | {'PASS' if summary.get('phase6_gate_passed') else 'FAIL'} | 13_phase6_gate.json |\n"
    f"| F7A gate | {'PASS' if summary.get('phase7_gate_passed') else 'FAIL'} | 14_phase7_gate.json |\n"
    f"| F7B gate | {'PASS' if summary.get('phase7b_gate_passed') else 'FAIL'} | 15_phase7b_gate.json |\n"
    f"| Cutover gate | {'PASS' if summary.get('cutover_passed') else 'FAIL'} | 16_phase8_cutover_gate.json |\n"
    f"| Burn-in verify ({int(min_days_required)}d) | {burn_cell} | 17_phase8_burnin_verify.json |\n"
    f"| Accountant sign-off final | {'PRESENT' if accountant_final_signoff_present else 'MISSING'} | 64_phase8_accountant_final_signoff.json |\n"
    f"| Rollback triggers | {'NONE' if not bool(rollback.get('rollback_required')) else 'ACTIVE'} | 18_phase8_rollback_eval.json |\n"
    f"| Daily gate ({day_tag}) | {'PASS' if daily_passed else 'FAIL'} | {os.path.basename(daily_gate_path)} |\n"
    "\n"
    f"Estado global: **{summary.get('status')}**\n"
)
with open(matrix_path, "w", encoding="utf-8") as fh:
    fh.write(matrix)

passed_days = set(verify.get("passed_days", []))
failed_days = set(verify.get("failed_days", []))
rows = []

def parse_date_list(raw):
    out = set()
    for item in raw or []:
        if isinstance(item, str):
            try:
                out.add(date.fromisoformat(item))
            except Exception:
                continue
    return out

selected_dates = []
hybrid_calendar = False
if calendar_file and os.path.exists(calendar_file):
    try:
        with open(calendar_file, "r", encoding="utf-8") as fh:
            payload = json.load(fh)
        if isinstance(payload, dict):
            mode = str(payload.get("mode") or "").strip().upper()
            if mode == "HYBRID":
                hybrid_calendar = True
                w_start = str(payload.get("window_start") or "").strip()
                w_end = str(payload.get("window_end") or "").strip()
                try:
                    window_start = date.fromisoformat(w_start) if w_start else window_start
                except Exception:
                    pass
                try:
                    window_end = date.fromisoformat(w_end) if w_end else window_end
                except Exception:
                    pass
                manual_days = payload.get("manual_days")
                if isinstance(manual_days, dict) and manual_days:
                    ds = set()
                    for k in manual_days.keys():
                        try:
                            ds.add(date.fromisoformat(str(k).strip()))
                        except Exception:
                            continue
                    selected_dates = sorted(ds)
            else:
                ds = set()
                ds |= parse_date_list(payload.get("work_days"))
                ds |= parse_date_list(payload.get("minimal_days"))
                for row in payload.get("days", []) or []:
                    if not isinstance(row, dict):
                        continue
                    try:
                        ds.add(date.fromisoformat(str(row.get("date") or "").strip()))
                    except Exception:
                        continue
                selected_dates = sorted(ds)
                if selected_dates:
                    window_start = selected_dates[0]
                    window_end = selected_dates[-1]
    except Exception:
        selected_dates = []

if selected_dates and not hybrid_calendar:
    iter_dates = selected_dates
else:
    iter_dates = []
    d = window_start
    while d <= window_end:
        iter_dates.append(d)
        d += timedelta(days=1)

for d in iter_dates:
    ds = d.isoformat()
    if ds in failed_days:
        st = "FAILED"
    elif ds in passed_days:
        st = "PASS"
    else:
        st = "PENDING"
    rows.append({"date": ds, "weekday": d.strftime("%A"), "status": st})

tracker = {
    "schema_version": 1,
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "window_start": window_start.isoformat(),
    "window_end": window_end.isoformat(),
    "days_total": len(rows),
    "days_passed": sum(1 for r in rows if r["status"] == "PASS"),
    "days_failed": sum(1 for r in rows if r["status"] == "FAILED"),
    "days_pending": sum(1 for r in rows if r["status"] == "PENDING"),
    "rows": rows,
}
with open(tracker_json_path, "w", encoding="utf-8") as fh:
    json.dump(tracker, fh, ensure_ascii=False, indent=2, sort_keys=True)
    fh.write("\n")

lines = [
    "# Phase8 Burn-in Calendar Tracker",
    "",
    "| Date | Day | Status |",
    "|---|---|---|",
]
for row in rows:
    lines.append(f"| {row['date']} | {row['weekday']} | {row['status']} |")
lines.extend(
    [
        "",
        f"Passed: {tracker['days_passed']}/{tracker['days_total']}",
        f"Failed: {tracker['days_failed']}",
        f"Pending: {tracker['days_pending']}",
    ]
)
with open(tracker_md_path, "w", encoding="utf-8") as fh:
    fh.write("\n".join(lines) + "\n")

if not daily_passed:
    print(json.dumps(daily_gate, ensure_ascii=False, sort_keys=True))
    sys.exit(1)
PY

echo "[phase8-burnin-daily] done day=${DAY_TAG} out=${OUT_DIR}"
