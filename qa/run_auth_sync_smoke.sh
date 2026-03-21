#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
QA_REPORTS_DIR="${QA_REPORTS_DIR:-qa/reports}"
OUT_DIR="${ROOT_DIR}/${QA_REPORTS_DIR}"
OUT_JSON="${OUT_DIR}/auth_sync_smoke_report.json"
OUT_MD="${OUT_DIR}/auth_sync_smoke_report.md"

API_BASE_URL="${AUTH_SYNC_BASE_URL:-http://localhost:8000/api/backend}"
USERNAME="${AUTH_SYNC_USERNAME:-k6_admin}"
PASSWORD="${AUTH_SYNC_PASSWORD:-Aa!9_Sim_Seed}"

START_TS="$(date -u +"%Y-%m-%dT%H:%M:%SZ")"
TMP_DIR="$(mktemp -d)"
trap 'rm -rf "${TMP_DIR}" /tmp/auth_sync_keys.json' EXIT

mkdir -p "${OUT_DIR}"

resolve_scope() {
  if [[ -n "${COMPANY_ID:-}" && -n "${BRANCH_ID:-}" ]]; then
    echo "${COMPANY_ID},${BRANCH_ID}"
    return 0
  fi

  docker compose exec -T backend python src/manage.py shell -c '
from apps.modulos.iam.models import OrgUnit
c = OrgUnit.objects.filter(unit_type=OrgUnit.UnitType.COMPANY, is_active=True).order_by("id").first()
if not c:
    raise SystemExit(2)
b = OrgUnit.objects.filter(unit_type=OrgUnit.UnitType.BRANCH, parent=c, is_active=True).order_by("id").first()
if not b:
    raise SystemExit(3)
print(f"{c.id},{b.id}")
' | tail -n1
}

request_id_from_headers() {
  local headers_file="$1"
  awk -F': ' 'tolower($1)=="x-request-id"{gsub("\r","",$2); print $2}' "${headers_file}" | tail -n1
}

json_get_or_empty() {
  local json_file="$1"
  local key="$2"
  JSON_FILE="${json_file}" JSON_KEY="${key}" python - <<'PY'
import json
import os
from pathlib import Path

json_file = Path(os.environ["JSON_FILE"])
key = os.environ["JSON_KEY"]
if not json_file.exists():
    print("")
    raise SystemExit(0)
try:
    data = json.loads(json_file.read_text(encoding="utf-8") or "{}")
except Exception:
    print("")
    raise SystemExit(0)
value = data.get(key, "")
print(value if isinstance(value, str) else "")
PY
}

scope_csv="$(resolve_scope || true)"
if [[ -z "${scope_csv}" ]]; then
  echo "[auth-sync-smoke] FAIL: no se pudo resolver COMPANY_ID/BRANCH_ID activos." >&2
  exit 1
fi
COMPANY_ID="${scope_csv%%,*}"
BRANCH_ID="${scope_csv##*,}"

JWT_KEY_LEN="$(docker compose exec -T backend python - <<'PY'
import os
print(len((os.getenv("DJANGO_JWT_SIGNING_KEY") or "").encode("utf-8")))
PY
)"
if [[ "${JWT_KEY_LEN}" -lt 32 ]]; then
  echo "[auth-sync-smoke] FAIL: DJANGO_JWT_SIGNING_KEY < 32 bytes (${JWT_KEY_LEN})." >&2
  exit 1
fi

LOGIN_HEADERS="${TMP_DIR}/login.headers"
LOGIN_BODY="${TMP_DIR}/login.json"
LOGIN_CODE="$(curl -sS -D "${LOGIN_HEADERS}" -o "${LOGIN_BODY}" -w '%{http_code}' \
  -X POST "${API_BASE_URL}/auth/login/" \
  -H 'Origin: http://localhost:3100' \
  -H 'Content-Type: application/json' \
  --data "{\"username\":\"${USERNAME}\",\"password\":\"${PASSWORD}\"}")"

COOKIE_JAR="${TMP_DIR}/cookies.txt"
curl -sS -c "${COOKIE_JAR}" -X POST "${API_BASE_URL}/auth/login/" \
  -H 'Origin: http://localhost:3100' \
  -H 'Content-Type: application/json' \
  --data "{\"username\":\"${USERNAME}\",\"password\":\"${PASSWORD}\"}" >/dev/null

CSRF="$(awk '$6=="nt_csrf"{print $7}' "${COOKIE_JAR}" | tail -n1)"
if [[ -z "${CSRF}" ]]; then
  echo "[auth-sync-smoke] FAIL: no se obtuvo cookie CSRF (nt_csrf)." >&2
  exit 1
fi

NO_CSRF_HEADERS="${TMP_DIR}/challenge_no_csrf.headers"
NO_CSRF_BODY="${TMP_DIR}/challenge_no_csrf.json"
NO_CSRF_CODE="$(curl -sS -D "${NO_CSRF_HEADERS}" -o "${NO_CSRF_BODY}" -w '%{http_code}' \
  -X POST "${API_BASE_URL}/sync/enrollment/challenges/" \
  -b "${COOKIE_JAR}" \
  -H 'Origin: http://localhost:3100' \
  -H 'Referer: http://localhost:3100/' \
  -H "X-Company-Id: ${COMPANY_ID}" \
  -H "X-Branch-Id: ${BRANCH_ID}" \
  -H 'Content-Type: application/json' \
  --data "{\"company_id\":${COMPANY_ID},\"branch_id\":${BRANCH_ID},\"expires_in_minutes\":15}")"

CHALLENGE_HEADERS="${TMP_DIR}/challenge.headers"
CHALLENGE_BODY="${TMP_DIR}/challenge.json"
CHALLENGE_CODE="$(curl -sS -D "${CHALLENGE_HEADERS}" -o "${CHALLENGE_BODY}" -w '%{http_code}' \
  -X POST "${API_BASE_URL}/sync/enrollment/challenges/" \
  -b "${COOKIE_JAR}" \
  -H 'Origin: http://localhost:3100' \
  -H 'Referer: http://localhost:3100/' \
  -H "X-CSRF-Token: ${CSRF}" \
  -H "X-Company-Id: ${COMPANY_ID}" \
  -H "X-Branch-Id: ${BRANCH_ID}" \
  -H 'Content-Type: application/json' \
  --data "{\"company_id\":${COMPANY_ID},\"branch_id\":${BRANCH_ID},\"label_hint\":\"QA Device\",\"expires_in_minutes\":15}")"

python - <<'PY'
import base64
import json
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

priv = Ed25519PrivateKey.generate()
pub = priv.public_key().public_bytes_raw()
with open('/tmp/auth_sync_keys.json', 'w', encoding='utf-8') as f:
    json.dump(
        {
            'private_key_b64': base64.b64encode(priv.private_bytes_raw()).decode('utf-8'),
            'public_key_b64': base64.b64encode(pub).decode('utf-8'),
        },
        f,
    )
PY

ENROLL_CODE="$(json_get_or_empty "${CHALLENGE_BODY}" "enrollment_code")"
PUB_B64="$(python - <<'PY'
import json
with open('/tmp/auth_sync_keys.json', 'r', encoding='utf-8') as f:
    print(json.load(f)['public_key_b64'])
PY
)"

ENROLL_HEADERS="${TMP_DIR}/enroll.headers"
ENROLL_BODY="${TMP_DIR}/enroll.json"
ENROLL_CODE_HTTP="$(curl -sS -D "${ENROLL_HEADERS}" -o "${ENROLL_BODY}" -w '%{http_code}' \
  -X POST "${API_BASE_URL}/sync/enroll/" \
  -H 'Origin: http://localhost:3100' \
  -H 'Content-Type: application/json' \
  --data "{\"enrollment_code\":\"${ENROLL_CODE}\",\"public_key_b64\":\"${PUB_B64}\",\"label\":\"QA Sync Device\",\"meta\":{\"os\":\"android\",\"app\":\"erp-mobile\"}}")"

DEVICE_ID="$(json_get_or_empty "${ENROLL_BODY}" "device_id")"

BATCH_PAYLOAD="${TMP_DIR}/batch_payload.json"
BATCH_PAYLOAD_PATH="${BATCH_PAYLOAD}" COMPANY_ID="${COMPANY_ID}" BRANCH_ID="${BRANCH_ID}" python - <<'PY'
import base64
import datetime as dt
import hashlib
import json
import os
import uuid
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

def canon_json(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)

def occurred_at_canonical(dt_value):
    if dt_value.tzinfo is None:
        dt_value = dt_value.replace(tzinfo=dt.timezone.utc)
    return dt_value.astimezone(dt.timezone.utc).isoformat(timespec="microseconds")

with open('/tmp/auth_sync_keys.json', 'r', encoding='utf-8') as f:
    keys = json.load(f)

priv = Ed25519PrivateKey.from_private_bytes(base64.b64decode(keys['private_key_b64']))
command_id = str(uuid.uuid4())
batch_id = str(uuid.uuid4())
occurred_at = occurred_at_canonical(dt.datetime.now(dt.timezone.utc))
payload = {'msg': 'qa-auth-sync-smoke'}
payload_hash = hashlib.sha256(canon_json(payload).encode('utf-8')).hexdigest()
company_id = int(os.environ['COMPANY_ID'])
branch_id = int(os.environ['BRANCH_ID'])
sequence = 1
prev_hash = ''
msg = f"{command_id}|DEMO_PING|{company_id}|{branch_id}|{occurred_at}|{sequence}|{payload_hash}|{prev_hash}".encode('utf-8')
signature = base64.b64encode(priv.sign(msg)).decode('utf-8')

out = {
    'batch_id': batch_id,
    'sent_at': occurred_at,
    'commands': [
        {
            'command_id': command_id,
            'command_type': 'DEMO_PING',
            'company_id': company_id,
            'branch_id': branch_id,
            'occurred_at': occurred_at,
            'sequence': sequence,
            'payload': payload,
            'payload_hash': payload_hash,
            'prev_hash': prev_hash,
            'signature': signature,
        }
    ],
}

with open(os.environ['BATCH_PAYLOAD_PATH'], 'w', encoding='utf-8') as f:
    json.dump(out, f)
PY

BATCH_HEADERS="${TMP_DIR}/batch.headers"
BATCH_BODY="${TMP_DIR}/batch.json"
BATCH_CODE="$(curl -sS -D "${BATCH_HEADERS}" -o "${BATCH_BODY}" -w '%{http_code}' \
  -X POST "${API_BASE_URL}/sync/batch/" \
  -H 'Origin: http://localhost:3100' \
  -H "X-Device-Id: ${DEVICE_ID}" \
  -H 'Content-Type: application/json' \
  --data @"${BATCH_PAYLOAD}")"

REVOKE_HEADERS="${TMP_DIR}/revoke.headers"
REVOKE_BODY="${TMP_DIR}/revoke.json"
REVOKE_CODE="$(curl -sS -D "${REVOKE_HEADERS}" -o "${REVOKE_BODY}" -w '%{http_code}' \
  -X POST "${API_BASE_URL}/sync/devices/${DEVICE_ID}/revoke/" \
  -b "${COOKIE_JAR}" \
  -H 'Origin: http://localhost:3100' \
  -H 'Referer: http://localhost:3100/' \
  -H "X-CSRF-Token: ${CSRF}" \
  -H "X-Company-Id: ${COMPANY_ID}" \
  -H "X-Branch-Id: ${BRANCH_ID}" \
  -H 'Content-Type: application/json' \
  --data '{}')"

WARNING_COUNT="$(docker compose logs --since "${START_TS}" backend 2>/dev/null | grep -c 'InsecureKeyLengthWarning' || true)"

OUT_JSON="${OUT_JSON}" OUT_MD="${OUT_MD}" \
LOGIN_CODE="${LOGIN_CODE}" NO_CSRF_CODE="${NO_CSRF_CODE}" CHALLENGE_CODE="${CHALLENGE_CODE}" \
ENROLL_CODE_HTTP="${ENROLL_CODE_HTTP}" BATCH_CODE="${BATCH_CODE}" REVOKE_CODE="${REVOKE_CODE}" \
WARNING_COUNT="${WARNING_COUNT}" COMPANY_ID="${COMPANY_ID}" BRANCH_ID="${BRANCH_ID}" API_BASE_URL="${API_BASE_URL}" \
LOGIN_HEADERS="${LOGIN_HEADERS}" NO_CSRF_HEADERS="${NO_CSRF_HEADERS}" CHALLENGE_HEADERS="${CHALLENGE_HEADERS}" \
ENROLL_HEADERS="${ENROLL_HEADERS}" BATCH_HEADERS="${BATCH_HEADERS}" REVOKE_HEADERS="${REVOKE_HEADERS}" \
LOGIN_BODY="${LOGIN_BODY}" NO_CSRF_BODY="${NO_CSRF_BODY}" CHALLENGE_BODY="${CHALLENGE_BODY}" \
ENROLL_BODY="${ENROLL_BODY}" BATCH_BODY="${BATCH_BODY}" REVOKE_BODY="${REVOKE_BODY}" \
python - <<'PY'
import json
import os
from datetime import datetime, timezone
from pathlib import Path


def load_json(path: str):
    p = Path(path)
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text(encoding="utf-8") or "{}")
    except Exception:
        return {}


def req_id(headers_path: str) -> str:
    p = Path(headers_path)
    if not p.exists():
        return ""
    for line in p.read_text(encoding="utf-8", errors="ignore").splitlines():
        if line.lower().startswith("x-request-id:"):
            return line.split(":", 1)[1].strip()
    return ""

login_body = load_json(os.environ["LOGIN_BODY"])
no_csrf_body = load_json(os.environ["NO_CSRF_BODY"])
challenge_body = load_json(os.environ["CHALLENGE_BODY"])
enroll_body = load_json(os.environ["ENROLL_BODY"])
batch_body = load_json(os.environ["BATCH_BODY"])
revoke_body = load_json(os.environ["REVOKE_BODY"])

no_csrf_error_code = str(no_csrf_body.get("error", {}).get("code", ""))
batch_applied = int((batch_body.get("summary") or {}).get("applied") or 0)
revoke_status = str(revoke_body.get("status") or "")

checks = [
    {
        "name": "login",
        "ok": int(os.environ["LOGIN_CODE"]) == 200,
        "http_status": int(os.environ["LOGIN_CODE"]),
        "request_id": req_id(os.environ["LOGIN_HEADERS"]),
        "reason": "",
    },
    {
        "name": "challenge_without_csrf",
        "ok": int(os.environ["NO_CSRF_CODE"]) == 403 and no_csrf_error_code == "AUTH_CSRF_FAILED",
        "http_status": int(os.environ["NO_CSRF_CODE"]),
        "request_id": req_id(os.environ["NO_CSRF_HEADERS"]),
        "reason": no_csrf_error_code,
    },
    {
        "name": "challenge_with_csrf",
        "ok": int(os.environ["CHALLENGE_CODE"]) == 201,
        "http_status": int(os.environ["CHALLENGE_CODE"]),
        "request_id": req_id(os.environ["CHALLENGE_HEADERS"]),
        "reason": "",
    },
    {
        "name": "enroll",
        "ok": int(os.environ["ENROLL_CODE_HTTP"]) == 201,
        "http_status": int(os.environ["ENROLL_CODE_HTTP"]),
        "request_id": req_id(os.environ["ENROLL_HEADERS"]),
        "reason": "",
    },
    {
        "name": "batch_signed_demo_ping",
        "ok": int(os.environ["BATCH_CODE"]) == 200 and batch_applied >= 1,
        "http_status": int(os.environ["BATCH_CODE"]),
        "request_id": req_id(os.environ["BATCH_HEADERS"]),
        "reason": f"applied={batch_applied}",
    },
    {
        "name": "revoke",
        "ok": int(os.environ["REVOKE_CODE"]) == 200 and revoke_status == "REVOKED",
        "http_status": int(os.environ["REVOKE_CODE"]),
        "request_id": req_id(os.environ["REVOKE_HEADERS"]),
        "reason": revoke_status,
    },
    {
        "name": "jwt_insecure_warning_absent",
        "ok": int(os.environ["WARNING_COUNT"]) == 0,
        "http_status": 0,
        "request_id": "",
        "reason": f"warning_count={int(os.environ['WARNING_COUNT'])}",
    },
]

status = "PASS" if all(c["ok"] for c in checks) else "FAIL"

report = {
    "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
    "overall_status": status,
    "context": {
        "company_id": int(os.environ["COMPANY_ID"]),
        "branch_id": int(os.environ["BRANCH_ID"]),
        "api_base_url": os.environ["API_BASE_URL"],
    },
    "checks": checks,
    "evidence": {
        "login": login_body,
        "challenge_without_csrf": no_csrf_body,
        "challenge_with_csrf": challenge_body,
        "enroll": enroll_body,
        "batch": batch_body,
        "revoke": revoke_body,
    },
}

out_json = Path(os.environ["OUT_JSON"])
out_md = Path(os.environ["OUT_MD"])
out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

lines = [
    "# Auth/Sync Smoke Report",
    "",
    f"- Timestamp: `{report['timestamp']}`",
    f"- Overall: **{status}**",
    f"- Context: company={report['context']['company_id']} branch={report['context']['branch_id']}",
    "",
    "| Check | Result | HTTP | Reason | Request ID |",
    "|---|---|---:|---|---|",
]
for c in checks:
    lines.append(
        f"| {c['name']} | {'PASS' if c['ok'] else 'FAIL'} | {c['http_status']} | {c['reason']} | {c['request_id']} |"
    )

out_md.write_text("\n".join(lines) + "\n", encoding="utf-8")

if status != "PASS":
    raise SystemExit(1)
PY

echo "[auth-sync-smoke] PASS -> ${OUT_JSON}"
