#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
APP_DIR="${ROOT_DIR}/backend/src"
TS="${TS:-$(date +%Y%m%d_%H%M%S)}"

OUT_DIR="${OUT_DIR:-${ROOT_DIR}/docs/operacion/evidencia/phase8_go_live_20260309_1040}"
COMPANY_ID="${COMPANY_ID:-5}"
BRANCH_ID="${BRANCH_ID:-6}"

MAX_INBOX_FAILED="${MAX_INBOX_FAILED:-0}"
MAX_OUTBOX_FAILED="${MAX_OUTBOX_FAILED:-0}"
MAX_FAILED_JOBS="${MAX_FAILED_JOBS:-0}"
MAX_RETRY_OVERDUE="${MAX_RETRY_OVERDUE:-0}"
MAX_STALE_PENDING="${MAX_STALE_PENDING:-0}"
MAX_OPEN_CONTINGENCY="${MAX_OPEN_CONTINGENCY:-0}"
MAX_UNBALANCED_ENTRIES="${MAX_UNBALANCED_ENTRIES:-0}"
MAX_MISSING_LINES="${MAX_MISSING_LINES:-0}"
MAX_STALE_REVALUATION="${MAX_STALE_REVALUATION:-0}"
LOCK_ROOT="${LOCK_ROOT:-${OUT_DIR}/.locks}"

if [[ ! -d "${OUT_DIR}" ]]; then
  echo "[phase8-live-tick] OUT_DIR no existe: ${OUT_DIR}" >&2
  exit 2
fi

resolve_python() {
  if [[ -n "${PYTHON_BIN:-}" ]]; then
    if command -v "${PYTHON_BIN}" >/dev/null 2>&1; then
      printf '%s\n' "${PYTHON_BIN}"
      return 0
    fi
    echo "[phase8-live-tick] PYTHON_BIN inválido: ${PYTHON_BIN}" >&2
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
  echo "[phase8-live-tick] no se encontró intérprete Python (python3/python)" >&2
  return 1
}

PYTHON_BIN="$(resolve_python)" || exit 127

if command -v flock >/dev/null 2>&1; then
  mkdir -p "${LOCK_ROOT}"
  LOCK_FILE="${LOCK_ROOT}/phase8_live_tick.lock"
  exec 9>"${LOCK_FILE}"
  if ! flock -n 9; then
    echo "[phase8-live-tick] lock ocupado, skip seguro"
    exit 0
  fi
fi

cd "${APP_DIR}"

"${PYTHON_BIN}" manage.py run_adapter_b_cycle \
  --company-id "${COMPANY_ID}" \
  --branch-id "${BRANCH_ID}" \
  --max-inbox-failed "${MAX_INBOX_FAILED}" \
  --max-outbox-failed "${MAX_OUTBOX_FAILED}" \
  --max-failed-jobs "${MAX_FAILED_JOBS}" \
  --max-retry-overdue "${MAX_RETRY_OVERDUE}" \
  --max-stale-pending "${MAX_STALE_PENDING}" \
  --max-open-contingency "${MAX_OPEN_CONTINGENCY}" \
  --output "${OUT_DIR}/70_live_adapter_cycle_${TS}.json"

"${PYTHON_BIN}" manage.py run_phase7_gl_cycle \
  --company-id "${COMPANY_ID}" \
  --max-inbox-failed "${MAX_INBOX_FAILED}" \
  --max-outbox-failed "${MAX_OUTBOX_FAILED}" \
  --max-unbalanced-entries "${MAX_UNBALANCED_ENTRIES}" \
  --max-missing-lines "${MAX_MISSING_LINES}" \
  --max-stale-revaluation "${MAX_STALE_REVALUATION}" \
  --output "${OUT_DIR}/71_live_gl_cycle_${TS}.json"

"${PYTHON_BIN}" manage.py run_intercompany_cycle \
  --company-id "${COMPANY_ID}" \
  --output "${OUT_DIR}/72_live_intercompany_cycle_${TS}.json"

export OUT_DIR TS

"${PYTHON_BIN}" - <<'PY'
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone

out_dir = os.environ["OUT_DIR"]
ts = os.environ["TS"]

files = [
    f"70_live_adapter_cycle_{ts}.json",
    f"71_live_gl_cycle_{ts}.json",
    f"72_live_intercompany_cycle_{ts}.json",
]

summary = {
    "schema_version": 1,
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "timestamp": ts,
    "checks": [],
}

all_green = True
for name in files:
    path = os.path.join(out_dir, name)
    with open(path, "r", encoding="utf-8") as fh:
        payload = json.load(fh)
    row = {"file": name}
    if "cycle_passed" in payload:
        row["cycle_passed"] = bool(payload["cycle_passed"])
        all_green = all_green and bool(payload["cycle_passed"])
    if "checks" in payload:
        row["failed_checks"] = [c.get("name") for c in payload["checks"] if not bool(c.get("passed"))]
    summary["checks"].append(row)

summary["tick_passed"] = bool(all_green)

output = os.path.join(out_dir, f"73_live_tick_{ts}.json")
with open(output, "w", encoding="utf-8") as fh:
    json.dump(summary, fh, ensure_ascii=False, indent=2, sort_keys=True)
    fh.write("\n")

if not all_green:
    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    sys.exit(1)
PY

echo "[phase8-live-tick] done ts=${TS} out=${OUT_DIR}"
