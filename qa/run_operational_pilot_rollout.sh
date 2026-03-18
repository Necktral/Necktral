#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON_BIN="${PYTHON_BIN:-python3}"
MANAGE_PY="${ROOT_DIR}/backend/src/manage.py"

MODE="${1:-status}"
case "${MODE}" in
  status|stage1|stage2|stage3|rollback) ;;
  *)
    echo "Uso: $0 [status|stage1|stage2|stage3|rollback]" >&2
    exit 2
    ;;
esac

COMPANY_ID="${COMPANY_ID:-}"
BRANCH_ID="${BRANCH_ID:-}"
if [[ -z "${COMPANY_ID}" || -z "${BRANCH_ID}" ]]; then
  echo "ERROR: COMPANY_ID y BRANCH_ID son requeridos." >&2
  exit 2
fi

TS="$(date +%Y%m%d_%H%M%S)"
DEFAULT_OUT_DIR="${ROOT_DIR}/docs/operacion/evidencia/operational_pilot_${TS}"
OUT_DIR="${OUT_DIR:-${DEFAULT_OUT_DIR}}"
mkdir -p "${OUT_DIR}"

OUTPUT_JSON="${OUT_DIR}/pilot_${MODE}.json"
OUTPUT_SHA="${OUT_DIR}/pilot_${MODE}.sha256"

CMD=(
  "${PYTHON_BIN}" "${MANAGE_PY}" manage_operational_posting_pilot
  --company-id "${COMPANY_ID}"
  --branch-id "${BRANCH_ID}"
  --action "${MODE}"
  --output "${OUTPUT_JSON}"
)

if [[ -n "${DATE_FROM:-}" && -n "${DATE_TO:-}" ]]; then
  CMD+=(--date-from "${DATE_FROM}" --date-to "${DATE_TO}")
fi
if [[ "${MODE}" == "stage3" && "${ATTEMPT_CLOSE:-0}" == "1" ]]; then
  CMD+=(--attempt-close)
  if [[ -n "${YEAR:-}" ]]; then
    CMD+=(--year "${YEAR}")
  fi
  if [[ -n "${MONTH:-}" ]]; then
    CMD+=(--month "${MONTH}")
  fi
  if [[ "${FORCE_CLOSE:-0}" == "1" ]]; then
    CMD+=(--force)
  fi
fi
if [[ "${MODE}" == "rollback" ]]; then
  CMD+=(--cycles "${ROLLBACK_CYCLES:-2}")
  CMD+=(--dispatch-limit "${ROLLBACK_DISPATCH_LIMIT:-200}")
  CMD+=(--fuel-limit "${ROLLBACK_FUEL_LIMIT:-200}")
fi

"${CMD[@]}"

"${PYTHON_BIN}" - <<'PY' "${OUTPUT_JSON}" "${OUTPUT_SHA}"
import hashlib
import json
import sys
from pathlib import Path

json_path = Path(sys.argv[1])
sha_path = Path(sys.argv[2])
raw = json_path.read_text(encoding="utf-8")
payload = json.loads(raw)
digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
sha_path.write_text(f"{digest}  {json_path.name}\n", encoding="utf-8")

print(json.dumps(
    {
        "action": payload.get("action"),
        "company_id": payload.get("company_id"),
        "branch_id": payload.get("branch_id"),
        "config_after": payload.get("config_after"),
        "failed_outbox": ((payload.get("snapshot") or {}).get("failed_outbox") or {}),
    },
    ensure_ascii=False,
    indent=2,
))
PY

echo "Piloto ${MODE} ejecutado. Evidencia: ${OUTPUT_JSON}"
