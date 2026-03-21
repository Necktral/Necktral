#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
REPORT_TS="$(date +%Y%m%d_%H%M%S)"
REPORT_DIR="${ROOT_DIR}/simulacion/reports/advanced_${REPORT_TS}"
RUN_SUMMARY="${REPORT_DIR}/run_summary.txt"
mkdir -p "${REPORT_DIR}"

log() {
  printf "\n[%s] %s\n" "$(date +%H:%M:%S)" "$1"
}

warn() {
  printf "\n[%s] WARNING: %s\n" "$(date +%H:%M:%S)" "$1" >&2
}

AUTH_PHASE_STATUS="not-run"
OPER_PHASE_STATUS="not-run"
QA_PHASE_STATUS="skipped"
SECURITY_PHASE_STATUS="skipped"
OVERALL_STATUS="ok"
TARGET_PASSED="unknown"
TARGET_HTTP_REQS="${TARGET_HTTP_REQS:-150000}"
AUTH_HTTP_REQS="0"
OPER_HTTP_REQS="0"
TOTAL_HTTP_REQS="0"
REQUIRED_LOADTEST_VARS=(
  AUTH_SIM_ADMIN_PASSWORD
  AUTH_SIM_USER_PASSWORD
  AUTH_SIM_ADMIN_TOTP_SECRET
  COMPANY_ID
  BRANCH_ID
  USERNAME
  PASSWORD
)

if [[ "${LOADTEST_ENV_FILE+x}" = x ]]; then
  LOADTEST_ENV_FILE="${LOADTEST_ENV_FILE}"
else
  LOADTEST_ENV_FILE=".env.loadtest"
fi
if [[ -n "${LOADTEST_ENV_FILE}" && "${LOADTEST_ENV_FILE}" != /* ]]; then
  LOADTEST_ENV_FILE="${ROOT_DIR}/${LOADTEST_ENV_FILE}"
fi

# Preserva overrides de entorno/comando para que no los sobreescriba el perfil .env.loadtest.
OVERRIDE_TOTAL_DURATION="${TOTAL_DURATION-}"
OVERRIDE_AUTH_VUS="${AUTH_VUS-}"
OVERRIDE_AUTH_ADMIN_2FA_VUS="${AUTH_ADMIN_2FA_VUS-}"
OVERRIDE_AUTH_ADMIN_2FA_SLEEP="${AUTH_ADMIN_2FA_SLEEP-}"
OVERRIDE_OPER_BILLING_VUS="${OPER_BILLING_VUS-}"
OVERRIDE_OPER_INVENTORY_VUS="${OPER_INVENTORY_VUS-}"
OVERRIDE_OPER_POSTING_VUS="${OPER_POSTING_VUS-}"
OVERRIDE_OPER_POSTING_LIMIT="${OPER_POSTING_LIMIT-}"
OVERRIDE_RUN_QA_GATES="${RUN_QA_GATES-}"
OVERRIDE_RUN_SECURITY_SCAN="${RUN_SECURITY_SCAN-}"
OVERRIDE_TARGET_HTTP_REQS="${TARGET_HTTP_REQS-}"
OVERRIDE_AUTH_TRANSPORT="${AUTH_TRANSPORT-}"

LOADTEST_ENV_LOADED="no"
ENV_OVERLAY_ACTIVE="no"
ENV_BACKUP_FILE=""
ENV_CREATED_FROM_LOADTEST="no"

write_run_summary() {
  cat >"${RUN_SUMMARY}" <<SUMMARY
report_dir=${REPORT_DIR}
auth_phase_status=${AUTH_PHASE_STATUS}
operational_phase_status=${OPER_PHASE_STATUS}
qa_phase_status=${QA_PHASE_STATUS}
security_phase_status=${SECURITY_PHASE_STATUS}
auth_http_reqs=${AUTH_HTTP_REQS}
operational_http_reqs=${OPER_HTTP_REQS}
total_http_reqs=${TOTAL_HTTP_REQS}
target_http_reqs=${TARGET_HTTP_REQS}
target_passed=${TARGET_PASSED}
overall_status=${OVERALL_STATUS}
loadtest_env_file=${LOADTEST_ENV_FILE}
loadtest_env_loaded=${LOADTEST_ENV_LOADED}
env_overlay_active=${ENV_OVERLAY_ACTIVE}
adaptive_retry_on_failure=${ADAPTIVE_RETRY_ON_FAILURE}
regression_budget_pct=${REGRESSION_BUDGET_PCT}
baseline_run_dir=${BASELINE_RUN_DIR}
operational_summary_path=${OPER_SUMMARY_HOST}
SUMMARY
}

on_exit() {
  local exit_code=$?
  if [ "${ENV_OVERLAY_ACTIVE}" = "yes" ]; then
    if [ "${ENV_CREATED_FROM_LOADTEST}" = "yes" ]; then
      rm -f "${ROOT_DIR}/.env"
    elif [ -n "${ENV_BACKUP_FILE}" ] && [ -f "${ENV_BACKUP_FILE}" ]; then
      mv -f "${ENV_BACKUP_FILE}" "${ROOT_DIR}/.env"
    fi
    ENV_OVERLAY_ACTIVE="restored"
  fi
  if [ "${exit_code}" -ne 0 ] && [ "${OVERALL_STATUS}" = "ok" ]; then
    OVERALL_STATUS="hard-fail"
  fi
  write_run_summary
}

trap on_exit EXIT

if [ -f "${ROOT_DIR}/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.env"
  set +a
fi

if [ -n "${LOADTEST_ENV_FILE}" ]; then
  if [ ! -f "${LOADTEST_ENV_FILE}" ]; then
    echo "ERROR: perfil de carga no encontrado: ${LOADTEST_ENV_FILE}" >&2
    echo "Crea el perfil base con:" >&2
    echo "  cp .env.loadtest.example .env.loadtest" >&2
    echo "O ajusta LOADTEST_ENV_FILE para apuntar al archivo correcto." >&2
    echo "Variables requeridas:" >&2
    printf '  - %s\n' "${REQUIRED_LOADTEST_VARS[@]}" >&2
    OVERALL_STATUS="hard-fail"
    exit 2
  fi
  if ! python3 - <<'PY' "${LOADTEST_ENV_FILE}" "${REQUIRED_LOADTEST_VARS[@]}"
import sys
from pathlib import Path

path = Path(sys.argv[1])
required = sys.argv[2:]
values = {}

for raw_line in path.read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#"):
        continue
    if line.startswith("export "):
        line = line[len("export "):].lstrip()
    if "=" not in line:
        continue
    key, value = line.split("=", 1)
    key = key.strip()
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
        value = value[1:-1]
    values[key] = value

invalid = []
for name in required:
    value = values.get(name)
    if value is None or value == "" or value == "CHANGE_ME":
        invalid.append(name)

if invalid:
    print(f"ERROR: perfil de carga invalido: {path}", file=sys.stderr)
    print("Completa estas variables requeridas antes de ejecutar loadtest:", file=sys.stderr)
    for name in invalid:
        print(f"  - {name}", file=sys.stderr)
    print("Plantilla base: cp .env.loadtest.example .env.loadtest", file=sys.stderr)
    raise SystemExit(2)
PY
  then
    OVERALL_STATUS="hard-fail"
    exit 2
  fi
fi

if [ -n "${LOADTEST_ENV_FILE}" ] && [ -f "${LOADTEST_ENV_FILE}" ]; then
  set -a
  # shellcheck disable=SC1090
  source "${LOADTEST_ENV_FILE}"
  set +a
  LOADTEST_ENV_LOADED="yes"
fi

if [ -n "${OVERRIDE_TOTAL_DURATION}" ]; then TOTAL_DURATION="${OVERRIDE_TOTAL_DURATION}"; fi
if [ -n "${OVERRIDE_AUTH_VUS}" ]; then AUTH_VUS="${OVERRIDE_AUTH_VUS}"; fi
if [ -n "${OVERRIDE_AUTH_ADMIN_2FA_VUS}" ]; then AUTH_ADMIN_2FA_VUS="${OVERRIDE_AUTH_ADMIN_2FA_VUS}"; fi
if [ -n "${OVERRIDE_AUTH_ADMIN_2FA_SLEEP}" ]; then AUTH_ADMIN_2FA_SLEEP="${OVERRIDE_AUTH_ADMIN_2FA_SLEEP}"; fi
if [ -n "${OVERRIDE_OPER_BILLING_VUS}" ]; then OPER_BILLING_VUS="${OVERRIDE_OPER_BILLING_VUS}"; fi
if [ -n "${OVERRIDE_OPER_INVENTORY_VUS}" ]; then OPER_INVENTORY_VUS="${OVERRIDE_OPER_INVENTORY_VUS}"; fi
if [ -n "${OVERRIDE_OPER_POSTING_VUS}" ]; then OPER_POSTING_VUS="${OVERRIDE_OPER_POSTING_VUS}"; fi
if [ -n "${OVERRIDE_OPER_POSTING_LIMIT}" ]; then OPER_POSTING_LIMIT="${OVERRIDE_OPER_POSTING_LIMIT}"; fi
if [ -n "${OVERRIDE_RUN_QA_GATES}" ]; then RUN_QA_GATES="${OVERRIDE_RUN_QA_GATES}"; fi
if [ -n "${OVERRIDE_RUN_SECURITY_SCAN}" ]; then RUN_SECURITY_SCAN="${OVERRIDE_RUN_SECURITY_SCAN}"; fi
if [ -n "${OVERRIDE_TARGET_HTTP_REQS}" ]; then TARGET_HTTP_REQS="${OVERRIDE_TARGET_HTTP_REQS}"; fi
if [ -n "${OVERRIDE_AUTH_TRANSPORT}" ]; then AUTH_TRANSPORT="${OVERRIDE_AUTH_TRANSPORT}"; fi

if [ "${LOADTEST_ENV_LOADED}" = "yes" ]; then
  if [ -f "${ROOT_DIR}/.env" ]; then
    ENV_BACKUP_FILE="${ROOT_DIR}/.env.backup.${REPORT_TS}"
    cp "${ROOT_DIR}/.env" "${ENV_BACKUP_FILE}"
    {
      echo "# Runtime overlay generado por run_advanced_integral.sh (${REPORT_TS})"
      cat "${ENV_BACKUP_FILE}"
      echo
      cat "${LOADTEST_ENV_FILE}"
    } > "${ROOT_DIR}/.env"
    ENV_OVERLAY_ACTIVE="yes"
  else
    cp "${LOADTEST_ENV_FILE}" "${ROOT_DIR}/.env"
    ENV_CREATED_FROM_LOADTEST="yes"
    ENV_OVERLAY_ACTIVE="yes"
  fi
fi

TOTAL_DURATION="${TOTAL_DURATION:-15m}"
AUTH_VUS="${AUTH_VUS:-120}"
AUTH_ADMIN_2FA_VUS="${AUTH_ADMIN_2FA_VUS:-6}"
AUTH_ADMIN_2FA_SLEEP="${AUTH_ADMIN_2FA_SLEEP:-1}"
OPER_BILLING_VUS="${OPER_BILLING_VUS:-80}"
OPER_INVENTORY_VUS="${OPER_INVENTORY_VUS:-80}"
OPER_POSTING_VUS="${OPER_POSTING_VUS:-24}"
OPER_POSTING_LIMIT="${OPER_POSTING_LIMIT:-15}"
RUN_QA_GATES="${RUN_QA_GATES:-1}"
RUN_SECURITY_SCAN="${RUN_SECURITY_SCAN:-1}"
TARGET_HTTP_REQS="${TARGET_HTTP_REQS:-150000}"
AUTH_TRANSPORT="${AUTH_TRANSPORT:-header}"
SIM_PROFILE="${SIM_PROFILE:-integral}"
ADAPTIVE_RETRY_ON_FAILURE="${ADAPTIVE_RETRY_ON_FAILURE:-0}"
ADAPTIVE_BILLING_SCALE="${ADAPTIVE_BILLING_SCALE:-0.5}"
ADAPTIVE_DURATION="${ADAPTIVE_DURATION:-5m}"
REGRESSION_BUDGET_PCT="${REGRESSION_BUDGET_PCT:-10}"
BASELINE_RUN_DIR="${BASELINE_RUN_DIR:-}"

sim_profile_raw="$(printf '%s' "${SIM_PROFILE}" | tr '[:upper:]' '[:lower:]')"
case "${sim_profile_raw}" in
  integral|auth-only)
    SIM_PROFILE="${sim_profile_raw}"
    ;;
  *)
    echo "ERROR: SIM_PROFILE invalido: ${SIM_PROFILE}" >&2
    OVERALL_STATUS="hard-fail"
    exit 2
    ;;
esac

if [ "${SIM_PROFILE}" != "integral" ]; then
  warn "SIM_PROFILE=${SIM_PROFILE} ignorado para corrida integral; se fuerza SIM_PROFILE=integral."
fi
SIM_PROFILE="integral"

if [ "${AUTH_TRANSPORT}" != "header" ]; then
  warn "AUTH_TRANSPORT=${AUTH_TRANSPORT} ignorado para corrida integral; se fuerza AUTH_TRANSPORT=header."
fi
AUTH_TRANSPORT="header"

NETWORK_NAME="erp_crm_default"
BASE_URL="${BASE_URL:-http://backend:8000/api}"
HOST_UID="$(id -u)"
HOST_GID="$(id -g)"
AUTH_SUMMARY_HOST="${REPORT_DIR}/auth_summary.json"
OPER_SUMMARY_HOST="${REPORT_DIR}/operational_summary.json"

require_var() {
  local name="$1"
  if [ -z "${!name:-}" ]; then
    echo "ERROR: variable requerida faltante: ${name}" >&2
    OVERALL_STATUS="hard-fail"
    exit 2
  fi
}

run_manage() {
  local cmd="$1"
  if docker compose exec -T backend python src/manage.py ${cmd}; then
    return 0
  fi
  docker compose exec -T backend python manage.py ${cmd}
}

wait_container_healthy() {
  local container_name="$1"
  local max_retries="${2:-60}"
  local sleep_seconds="${3:-2}"
  local status=""
  for _ in $(seq 1 "${max_retries}"); do
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${container_name}" 2>/dev/null || echo error)"
    if [ "${status}" = "healthy" ]; then
      return 0
    fi
    sleep "${sleep_seconds}"
  done
  echo "ERROR: ${container_name} no quedo healthy (status final=${status})" >&2
  return 1
}

ensure_backend_running() {
  local running=""
  running="$(docker inspect -f '{{.State.Running}}' erpcrm_backend 2>/dev/null || echo false)"

  if [ "${running}" = "true" ] && wait_container_healthy "erpcrm_backend" 30 2; then
    return 0
  fi

  warn "backend no esta disponible para la fase operacional; intentando levantar db/backend."
  if ! (
    cd "${ROOT_DIR}"
    USE_GUNICORN="${USE_GUNICORN:-1}" GUNICORN_WORKERS="${GUNICORN_WORKERS:-16}" docker compose up -d db backend
  ); then
    echo "ERROR: no fue posible levantar db/backend antes de fase operacional" >&2
    return 1
  fi

  if ! wait_container_healthy "erpcrm_backend" 60 2; then
    echo "ERROR: backend no quedo healthy antes de fase operacional" >&2
    (cd "${ROOT_DIR}" && docker compose logs backend | tail -n 120) || true
    return 1
  fi

  return 0
}

verify_grafana_provisioning() {
  local since_ts="$1"
  local strict_pattern="failed to load dashboard|provisioning.dashboard.*level=error|invalid character .*object key string"
  local print_pattern="failed to load dashboard|provisioning.dashboard|invalid character .*object key string"

  if command -v rg >/dev/null 2>&1; then
    if docker logs --since "${since_ts}" k6_grafana 2>&1 | rg -q "${strict_pattern}"; then
      echo "ERROR: Grafana reporto fallo de provisioning de dashboard" >&2
      docker logs --since "${since_ts}" k6_grafana 2>&1 | rg "${print_pattern}" || true
      return 1
    fi
  else
    if docker logs --since "${since_ts}" k6_grafana 2>&1 | grep -Eq "${strict_pattern}"; then
      echo "ERROR: Grafana reporto fallo de provisioning de dashboard" >&2
      docker logs --since "${since_ts}" k6_grafana 2>&1 | grep -E "${print_pattern}" || true
      return 1
    fi
  fi
}

validate_dashboard_json() {
  local dashboard_file="$1"
  python3 - <<'PY' "${dashboard_file}"
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
data = json.loads(path.read_text(encoding="utf-8"))
if not isinstance(data, dict):
    raise SystemExit("dashboard JSON must be an object")
print("ok")
PY
}

extract_http_reqs() {
  local summary_path="$1"
  python3 - <<'PY' "${summary_path}"
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
if not path.exists() or path.stat().st_size == 0:
    print("0")
    raise SystemExit(0)

try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    print("0")
    raise SystemExit(0)

metrics = data.get("metrics", {}) if isinstance(data, dict) else {}
http_reqs = metrics.get("http_reqs", {}) if isinstance(metrics, dict) else {}
count = 0
if isinstance(http_reqs, dict):
    values = http_reqs.get("values")
    if isinstance(values, dict) and "count" in values:
        count = values.get("count", 0)
    else:
        count = http_reqs.get("count", 0)

try:
    print(float(count))
except Exception:
    print("0")
PY
}

extract_check_fails() {
  local summary_path="$1"
  local check_name="$2"
  python3 - <<'PY' "${summary_path}" "${check_name}"
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
check_name = str(sys.argv[2])
if not path.exists() or path.stat().st_size == 0:
    print("0")
    raise SystemExit(0)

try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    print("0")
    raise SystemExit(0)

root = data.get("root_group", {}) if isinstance(data, dict) else {}
checks = root.get("checks", {}) if isinstance(root, dict) else {}
target = checks.get(check_name, {}) if isinstance(checks, dict) else {}
fails = target.get("fails", 0) if isinstance(target, dict) else 0
try:
    print(int(fails))
except Exception:
    print("0")
PY
}

extract_metric_value() {
  local summary_path="$1"
  local metric_name="$2"
  local stat_name="$3"
  python3 - <<'PY' "${summary_path}" "${metric_name}" "${stat_name}"
import json
import sys
from pathlib import Path

path = Path(sys.argv[1])
metric_name = str(sys.argv[2])
stat_name = str(sys.argv[3])

if not path.exists() or path.stat().st_size == 0:
    print("0")
    raise SystemExit(0)

try:
    data = json.loads(path.read_text(encoding="utf-8"))
except Exception:
    print("0")
    raise SystemExit(0)

metrics = data.get("metrics", {}) if isinstance(data, dict) else {}
metric = metrics.get(metric_name, {}) if isinstance(metrics, dict) else {}
if not isinstance(metric, dict):
    print("0")
    raise SystemExit(0)

value = metric.get(stat_name)
if value is None:
    metric_values = metric.get("values")
    if isinstance(metric_values, dict):
        value = metric_values.get(stat_name)

try:
    print(float(value))
except Exception:
    print("0")
PY
}

redact_summary_file() {
  local summary_path="$1"
  if [ -f "${summary_path}" ] && [ -s "${summary_path}" ]; then
    python3 "${ROOT_DIR}/simulacion/redact_k6_summary.py" "${summary_path}" >/dev/null
  fi
}

run_regression_compare_if_configured() {
  local candidate_summary="$1"
  local output_report="$2"

  if [ -z "${BASELINE_RUN_DIR}" ]; then
    return 0
  fi

  local baseline_summary="${BASELINE_RUN_DIR}/operational_summary.json"
  if [ ! -f "${baseline_summary}" ]; then
    warn "baseline summary no encontrado en BASELINE_RUN_DIR=${BASELINE_RUN_DIR}; se omite comparador."
    return 0
  fi

  set +e
  python3 "${ROOT_DIR}/simulacion/compare_k6_regression.py" \
    --baseline "${baseline_summary}" \
    --candidate "${candidate_summary}" \
    --budget-pct "${REGRESSION_BUDGET_PCT}" \
    --output "${output_report}"
  local cmp_exit=$?
  set -e

  if [ "${cmp_exit}" -ne 0 ]; then
    warn "comparador de regresion detecto degradacion por encima de budget=${REGRESSION_BUDGET_PCT}%."
    if [ "${OVERALL_STATUS}" = "ok" ]; then
      OVERALL_STATUS="soft-fail"
    fi
  fi
  return 0
}

verify_backend_runtime_settings() {
  local expected_auth_transport="${AUTH_TOKEN_TRANSPORT:-header}"
  local expected_allow_override="${AUTH_ALLOW_TRANSPORT_OVERRIDE:-1}"
  local expected_throttle_anon="${DRF_THROTTLE_ANON:-}"
  local expected_throttle_user="${DRF_THROTTLE_USER:-}"
  local expected_throttle_auth_login="${DRF_THROTTLE_AUTH_LOGIN:-}"
  local expected_throttle_auth_refresh="${DRF_THROTTLE_AUTH_REFRESH:-}"
  local expected_throttle_auth_logout="${DRF_THROTTLE_AUTH_LOGOUT:-}"
  local expected_throttle_auth_sensitive="${DRF_THROTTLE_AUTH_SENSITIVE:-}"

  set +e
  docker compose exec -T backend env \
    LT_EXPECT_AUTH_TOKEN_TRANSPORT="${expected_auth_transport}" \
    LT_EXPECT_AUTH_ALLOW_TRANSPORT_OVERRIDE="${expected_allow_override}" \
    LT_EXPECT_DRF_THROTTLE_ANON="${expected_throttle_anon}" \
    LT_EXPECT_DRF_THROTTLE_USER="${expected_throttle_user}" \
    LT_EXPECT_DRF_THROTTLE_AUTH_LOGIN="${expected_throttle_auth_login}" \
    LT_EXPECT_DRF_THROTTLE_AUTH_REFRESH="${expected_throttle_auth_refresh}" \
    LT_EXPECT_DRF_THROTTLE_AUTH_LOGOUT="${expected_throttle_auth_logout}" \
    LT_EXPECT_DRF_THROTTLE_AUTH_SENSITIVE="${expected_throttle_auth_sensitive}" \
    python src/manage.py shell <<'PY'
import os

from django.conf import settings


def parse_truthy(raw: str | None) -> bool:
    return str(raw or "").strip().lower() in {"1", "true", "yes", "y", "on"}


def as_text(value) -> str:
    return "" if value is None else str(value)


rates = (getattr(settings, "REST_FRAMEWORK", {}) or {}).get("DEFAULT_THROTTLE_RATES", {}) or {}

actual = {
    "AUTH_TOKEN_TRANSPORT": as_text(getattr(settings, "AUTH_TOKEN_TRANSPORT", "")),
    "AUTH_ALLOW_TRANSPORT_OVERRIDE": "1" if bool(getattr(settings, "AUTH_ALLOW_TRANSPORT_OVERRIDE", False)) else "0",
    "DRF_THROTTLE_ANON": as_text(rates.get("anon")),
    "DRF_THROTTLE_USER": as_text(rates.get("user")),
    "DRF_THROTTLE_AUTH_LOGIN": as_text(rates.get("auth_login")),
    "DRF_THROTTLE_AUTH_REFRESH": as_text(rates.get("auth_refresh")),
    "DRF_THROTTLE_AUTH_LOGOUT": as_text(rates.get("auth_logout")),
    "DRF_THROTTLE_AUTH_SENSITIVE": as_text(rates.get("auth_sensitive")),
}

expected = {
    "AUTH_TOKEN_TRANSPORT": (os.environ.get("LT_EXPECT_AUTH_TOKEN_TRANSPORT") or "header").strip(),
    "AUTH_ALLOW_TRANSPORT_OVERRIDE": (os.environ.get("LT_EXPECT_AUTH_ALLOW_TRANSPORT_OVERRIDE") or "1").strip(),
    "DRF_THROTTLE_ANON": (os.environ.get("LT_EXPECT_DRF_THROTTLE_ANON") or "").strip(),
    "DRF_THROTTLE_USER": (os.environ.get("LT_EXPECT_DRF_THROTTLE_USER") or "").strip(),
    "DRF_THROTTLE_AUTH_LOGIN": (os.environ.get("LT_EXPECT_DRF_THROTTLE_AUTH_LOGIN") or "").strip(),
    "DRF_THROTTLE_AUTH_REFRESH": (os.environ.get("LT_EXPECT_DRF_THROTTLE_AUTH_REFRESH") or "").strip(),
    "DRF_THROTTLE_AUTH_LOGOUT": (os.environ.get("LT_EXPECT_DRF_THROTTLE_AUTH_LOGOUT") or "").strip(),
    "DRF_THROTTLE_AUTH_SENSITIVE": (os.environ.get("LT_EXPECT_DRF_THROTTLE_AUTH_SENSITIVE") or "").strip(),
}

errors = []

if actual["AUTH_TOKEN_TRANSPORT"] != expected["AUTH_TOKEN_TRANSPORT"]:
    errors.append(
        "AUTH_TOKEN_TRANSPORT mismatch: "
        f"expected={expected['AUTH_TOKEN_TRANSPORT']} actual={actual['AUTH_TOKEN_TRANSPORT']}"
    )

expected_override = parse_truthy(expected["AUTH_ALLOW_TRANSPORT_OVERRIDE"])
actual_override = actual["AUTH_ALLOW_TRANSPORT_OVERRIDE"] == "1"
if actual_override != expected_override:
    errors.append(
        "AUTH_ALLOW_TRANSPORT_OVERRIDE mismatch: "
        f"expected={expected_override} actual={actual_override}"
    )
if not actual_override:
    errors.append("AUTH_ALLOW_TRANSPORT_OVERRIDE must be True for loadtest integral.")

for key in (
    "DRF_THROTTLE_ANON",
    "DRF_THROTTLE_USER",
    "DRF_THROTTLE_AUTH_LOGIN",
    "DRF_THROTTLE_AUTH_REFRESH",
    "DRF_THROTTLE_AUTH_LOGOUT",
    "DRF_THROTTLE_AUTH_SENSITIVE",
):
    expected_value = expected[key]
    if expected_value and actual[key] != expected_value:
        errors.append(f"{key} mismatch: expected={expected_value} actual={actual[key]}")

print(f"runtime.auth_token_transport={actual['AUTH_TOKEN_TRANSPORT']}")
print(f"runtime.auth_allow_transport_override={actual['AUTH_ALLOW_TRANSPORT_OVERRIDE']}")
print(f"runtime.drf_throttle_anon={actual['DRF_THROTTLE_ANON']}")
print(f"runtime.drf_throttle_user={actual['DRF_THROTTLE_USER']}")
print(f"runtime.drf_throttle_auth_login={actual['DRF_THROTTLE_AUTH_LOGIN']}")
print(f"runtime.drf_throttle_auth_refresh={actual['DRF_THROTTLE_AUTH_REFRESH']}")
print(f"runtime.drf_throttle_auth_logout={actual['DRF_THROTTLE_AUTH_LOGOUT']}")
print(f"runtime.drf_throttle_auth_sensitive={actual['DRF_THROTTLE_AUTH_SENSITIVE']}")

if errors:
    print("BACKEND_RUNTIME_CHECK=FAIL")
    for item in errors:
        print(f" - {item}")
    raise SystemExit(2)

print("BACKEND_RUNTIME_CHECK=OK")
PY
  local runtime_check_exit=$?
  set -e
  return "${runtime_check_exit}"
}

ensure_operational_prereqs() {
  set +e
  docker compose exec -T backend env \
    LT_OPER_USERNAME="${USERNAME}" \
    LT_OPER_COMPANY_ID="${COMPANY_ID}" \
    LT_OPER_BRANCH_ID="${BRANCH_ID}" \
    python src/manage.py shell <<'PY'
import os

from django.contrib.auth import get_user_model

from apps.modulos.iam.models import OrgUnit, UserMembership
from apps.modulos.rbac.models import Role, RoleAssignment
from apps.modulos.rbac.seed_v01 import seed_rbac_v01


def fail(msg: str) -> None:
    print(f"OPERATIONAL_PREREQ_STATUS=FAIL")
    print(f" - {msg}")
    raise SystemExit(2)


username = (os.environ.get("LT_OPER_USERNAME") or "").strip()
try:
    company_id = int((os.environ.get("LT_OPER_COMPANY_ID") or "0").strip())
    branch_id = int((os.environ.get("LT_OPER_BRANCH_ID") or "0").strip())
except ValueError:
    fail("COMPANY_ID/BRANCH_ID deben ser enteros.")

if not username:
    fail("USERNAME vacio para fase operacional.")
if company_id <= 0 or branch_id <= 0:
    fail("COMPANY_ID y BRANCH_ID deben ser > 0 para fase operacional.")

seed_rbac_v01()

User = get_user_model()
user = User.objects.filter(username=username, is_active=True).first()
if user is None:
    fail(f"usuario operacional no existe o esta inactivo: {username}")

company = OrgUnit.objects.filter(
    id=company_id,
    unit_type=OrgUnit.UnitType.COMPANY,
    is_active=True,
).first()
if company is None:
    fail(f"company invalida o inactiva: {company_id}")

branch = OrgUnit.objects.filter(
    id=branch_id,
    unit_type=OrgUnit.UnitType.BRANCH,
    parent=company,
    is_active=True,
).first()
if branch is None:
    fail(f"branch invalida o fuera de company={company_id}: {branch_id}")

for org in (company, branch):
    membership, created = UserMembership.objects.get_or_create(
        user=user,
        org_unit=org,
        defaults={"is_active": True},
    )
    if not created and not membership.is_active:
        membership.is_active = True
        membership.left_at = None
        membership.save(update_fields=["is_active", "left_at"])

role = Role.objects.filter(name="company_admin", is_active=True).first()
if role is None:
    fail("role company_admin no existe o esta inactivo.")

assignment, created = RoleAssignment.objects.get_or_create(
    user=user,
    role=role,
    org_unit=company,
    origin=RoleAssignment.Origin.SYSTEM,
    defaults={"is_active": True, "origin_ref": "loadtest"},
)
if not created:
    updates = []
    if not assignment.is_active:
        assignment.is_active = True
        updates.append("is_active")
    if assignment.origin_ref != "loadtest":
        assignment.origin_ref = "loadtest"
        updates.append("origin_ref")
    if updates:
        assignment.save(update_fields=updates)

print("OPERATIONAL_PREREQ_STATUS=OK")
print(f"user={user.username}")
print(f"company_id={company.id}")
print(f"branch_id={branch.id}")
print(f"company_admin_assignment_origin={assignment.origin}")
PY
  local prereq_exit=$?
  set -e
  return "${prereq_exit}"
}

require_var AUTH_SIM_ADMIN_PASSWORD
require_var AUTH_SIM_USER_PASSWORD
require_var AUTH_SIM_ADMIN_TOTP_SECRET
require_var COMPANY_ID
require_var BRANCH_ID
require_var USERNAME
require_var PASSWORD

log "Fase 0/5: preflight de comandos, perfiles y observabilidad"
command -v docker >/dev/null 2>&1 || { echo "ERROR: docker no disponible" >&2; OVERALL_STATUS="hard-fail"; exit 2; }
if ! docker compose version >/dev/null 2>&1; then
  echo "ERROR: docker compose no disponible" >&2
  OVERALL_STATUS="hard-fail"
  exit 2
fi

if ! (cd "${ROOT_DIR}" && docker compose -f simulacion/docker-compose.monitoring.yaml config >/dev/null); then
  echo "ERROR: docker-compose.monitoring.yaml invalido" >&2
  OVERALL_STATUS="hard-fail"
  exit 1
fi

if ! validate_dashboard_json "${ROOT_DIR}/simulacion/dashboards/k6-load-testing-results.json" >/dev/null; then
  echo "ERROR: dashboard JSON invalido" >&2
  OVERALL_STATUS="hard-fail"
  exit 1
fi

log "Perfil base .env: $( [ -f "${ROOT_DIR}/.env" ] && echo "cargado" || echo "no encontrado" )"
log "Perfil loadtest (${LOADTEST_ENV_FILE}): ${LOADTEST_ENV_LOADED}"
log "Perfil simulacion forzado: ${SIM_PROFILE}"
log "DJANGO_ALLOWED_HOSTS=${DJANGO_ALLOWED_HOSTS:-unset}"
log "Throttles: login=${DRF_THROTTLE_AUTH_LOGIN:-unset}, refresh=${DRF_THROTTLE_AUTH_REFRESH:-unset}, logout=${DRF_THROTTLE_AUTH_LOGOUT:-unset}, auth_sensitive=${DRF_THROTTLE_AUTH_SENSITIVE:-10/min}"

log "Fase 1/5: levantar backend + db y esperar healthcheck"
if ! (
  cd "${ROOT_DIR}"
  USE_GUNICORN="${USE_GUNICORN:-1}" GUNICORN_WORKERS="${GUNICORN_WORKERS:-16}" docker compose up -d --force-recreate db backend
); then
  OVERALL_STATUS="hard-fail"
  exit 1
fi

backend_status=""
for _ in $(seq 1 60); do
  backend_status="$(docker inspect -f '{{.State.Health.Status}}' erpcrm_backend 2>/dev/null || echo error)"
  if [ "${backend_status}" = "healthy" ]; then
    break
  fi
  sleep 2
done
if [ "${backend_status}" != "healthy" ]; then
  echo "ERROR: backend no quedo healthy a tiempo" >&2
  (cd "${ROOT_DIR}" && docker compose logs backend | tail -n 200)
  OVERALL_STATUS="hard-fail"
  exit 1
fi

log "Fase 1.0: validar configuracion runtime efectiva del backend"
if ! verify_backend_runtime_settings; then
  OVERALL_STATUS="hard-fail"
  exit 1
fi

if ! docker network ls | grep -q "${NETWORK_NAME}"; then
  echo "ERROR: red ${NETWORK_NAME} no encontrada" >&2
  OVERALL_STATUS="hard-fail"
  exit 1
fi

log "Fase 1.1: migraciones + seed + axes reset"
if ! (
  cd "${ROOT_DIR}"
  run_manage "migrate --noinput"
  run_manage "seed_auth_users --admin-username ${AUTH_SIM_ADMIN_USERNAME:-k6_admin} --admin-password ${AUTH_SIM_ADMIN_PASSWORD} --admin-totp-secret ${AUTH_SIM_ADMIN_TOTP_SECRET} --admin-enable-2fa --user-username ${AUTH_SIM_USER_USERNAME:-k6_user} --user-password ${AUTH_SIM_USER_PASSWORD}"
  run_manage "axes_reset"
); then
  OVERALL_STATUS="hard-fail"
  exit 1
fi

log "Fase 1.2: validar prerequisitos RBAC/contexto para carga operacional"
if ! ensure_operational_prereqs; then
  OPER_PHASE_STATUS="hard-fail"
  OVERALL_STATUS="hard-fail"
  exit 1
fi

log "Fase 2/5: levantar observabilidad (InfluxDB + Grafana)"
monitoring_start_ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
if ! (
  cd "${ROOT_DIR}"
  docker compose -f simulacion/docker-compose.monitoring.yaml up -d influxdb grafana
); then
  OVERALL_STATUS="hard-fail"
  exit 1
fi

if ! wait_container_healthy "k6_influxdb" 60 2; then
  OVERALL_STATUS="hard-fail"
  exit 1
fi
if ! wait_container_healthy "k6_grafana" 60 2; then
  OVERALL_STATUS="hard-fail"
  exit 1
fi
if ! verify_grafana_provisioning "${monitoring_start_ts}"; then
  OVERALL_STATUS="hard-fail"
  exit 1
fi

log "Fase 2.1: corrida extendida de autenticacion/seguridad"
AUTH_SUMMARY_CONTAINER="/simulacion/reports/advanced_${REPORT_TS}/auth_summary.json"
set +e
(
  cd "${ROOT_DIR}"
  docker run --rm -i \
    --user "${HOST_UID}:${HOST_GID}" \
    --network "${NETWORK_NAME}" \
    -v "${ROOT_DIR}/simulacion:/simulacion" \
    -e BASE_URL="${BASE_URL}" \
    -e USER_USERNAME="${AUTH_SIM_USER_USERNAME:-k6_user}" \
    -e USER_PASSWORD="${AUTH_SIM_USER_PASSWORD}" \
    -e ADMIN_USERNAME="${AUTH_SIM_ADMIN_USERNAME:-k6_admin}" \
    -e ADMIN_PASSWORD="${AUTH_SIM_ADMIN_PASSWORD}" \
    -e ADMIN_TOTP_SECRET="${AUTH_SIM_ADMIN_TOTP_SECRET}" \
    -e CSRF_COOKIE_NAME="${CSRF_COOKIE_NAME:-nt_csrf}" \
    -e VUS="${AUTH_VUS}" \
    -e DURATION="${TOTAL_DURATION}" \
    -e ADMIN_2FA_VUS="${AUTH_ADMIN_2FA_VUS}" \
    -e ADMIN_2FA_SLEEP="${AUTH_ADMIN_2FA_SLEEP}" \
    grafana/k6 run \
    --out influxdb=http://k6_influxdb:8086/k6 \
    --summary-export "${AUTH_SUMMARY_CONTAINER}" \
    /simulacion/auth_load_simulation_extended.js
)
AUTH_K6_EXIT=$?
set -e

if [ "${AUTH_K6_EXIT}" -eq 0 ]; then
  AUTH_PHASE_STATUS="ok"
elif [ -s "${AUTH_SUMMARY_HOST}" ]; then
  AUTH_PHASE_STATUS="soft-fail"
  if [ "${OVERALL_STATUS}" = "ok" ]; then
    OVERALL_STATUS="soft-fail"
  fi
  warn "Fase auth termino con thresholds fallidos (soft-fail). Se continua para recolectar evidencia."
else
  AUTH_PHASE_STATUS="hard-fail"
  OVERALL_STATUS="hard-fail"
  echo "ERROR: Fase auth fallo sin summary exportado" >&2
  exit 1
fi
redact_summary_file "${AUTH_SUMMARY_HOST}"

log "Fase 3/5: corrida operacional + snapshot de DB"
OP_BEFORE="${REPORT_DIR}/snapshot_before.json"
OP_AFTER="${REPORT_DIR}/snapshot_after.json"

if ! ensure_backend_running; then
  OPER_PHASE_STATUS="hard-fail"
  OVERALL_STATUS="hard-fail"
  exit 1
fi

if ! (
  cd "${ROOT_DIR}"
  run_manage "export_operational_load_snapshot --company-id ${COMPANY_ID} --branch-id ${BRANCH_ID} --output ${OP_BEFORE}"
); then
  OPER_PHASE_STATUS="hard-fail"
  OVERALL_STATUS="hard-fail"
  exit 1
fi

set +e
(
  cd "${ROOT_DIR}"
  docker run --rm -i \
    --user "${HOST_UID}:${HOST_GID}" \
    --network "${NETWORK_NAME}" \
    -v "${ROOT_DIR}:/workspace" \
    -e BASE_URL="${BASE_URL}" \
    -e USERNAME="${USERNAME}" \
    -e PASSWORD="${PASSWORD}" \
    -e COMPANY_ID="${COMPANY_ID}" \
    -e BRANCH_ID="${BRANCH_ID}" \
    -e AUTH_TRANSPORT="${AUTH_TRANSPORT}" \
    -e WAREHOUSE_ID="${WAREHOUSE_ID:-}" \
    -e ITEM_ID="${ITEM_ID:-}" \
    -e DURATION="${TOTAL_DURATION}" \
    -e BILLING_VUS="${OPER_BILLING_VUS}" \
    -e INVENTORY_VUS="${OPER_INVENTORY_VUS}" \
    -e POSTING_VUS="${OPER_POSTING_VUS}" \
    -e POSTING_LIMIT="${OPER_POSTING_LIMIT}" \
    grafana/k6 run /workspace/qa/k6/operational_posting_load.js \
    --summary-export "/workspace/simulacion/reports/advanced_${REPORT_TS}/operational_summary.json"
)
OPER_K6_EXIT=$?
set -e

if [ "${OPER_K6_EXIT}" -eq 0 ]; then
  OPER_PHASE_STATUS="ok"
elif [ -s "${OPER_SUMMARY_HOST}" ]; then
  OPER_PHASE_STATUS="soft-fail"
  if [ "${OVERALL_STATUS}" = "ok" ]; then
    OVERALL_STATUS="soft-fail"
  fi
  warn "Fase operacional termino con thresholds fallidos (soft-fail)."
else
  OPER_PHASE_STATUS="hard-fail"
  OVERALL_STATUS="hard-fail"
  echo "ERROR: Fase operacional fallo sin summary exportado" >&2
  exit 1
fi
redact_summary_file "${OPER_SUMMARY_HOST}"

if [ "${ADAPTIVE_RETRY_ON_FAILURE}" = "1" ] && [ -s "${OPER_SUMMARY_HOST}" ]; then
  billing_fails="$(extract_check_fails "${OPER_SUMMARY_HOST}" "billing_doc_create status valid")"
  operational_error_rate="$(extract_metric_value "${OPER_SUMMARY_HOST}" "operational_error_rate" "value")"
  billing_p95_ms="$(extract_metric_value "${OPER_SUMMARY_HOST}" "billing_write_ms" "p(95)")"

  adaptive_trigger="$(python3 - <<'PY' "${billing_fails}" "${operational_error_rate}" "${billing_p95_ms}"
import sys

billing_fails = int(float(sys.argv[1]))
error_rate = float(sys.argv[2])
billing_p95 = float(sys.argv[3])

trigger = billing_fails > 0 or error_rate > 0.01 or billing_p95 > 400.0
print("1" if trigger else "0")
PY
)"

  if [ "${adaptive_trigger}" = "1" ]; then
    warn "control adaptativo: activado (billing_fails=${billing_fails}, error_rate=${operational_error_rate}, billing_p95_ms=${billing_p95_ms})."

    adaptive_billing_vus="$(python3 - <<'PY' "${OPER_BILLING_VUS}" "${ADAPTIVE_BILLING_SCALE}"
import sys

base = max(1, int(float(sys.argv[1])))
scale = float(sys.argv[2])
val = int(base * scale)
print(max(1, val))
PY
)"
    OPER_ADAPTIVE_SUMMARY_HOST="${REPORT_DIR}/operational_summary_adaptive.json"

    set +e
    (
      cd "${ROOT_DIR}"
      docker run --rm -i \
        --user "${HOST_UID}:${HOST_GID}" \
        --network "${NETWORK_NAME}" \
        -v "${ROOT_DIR}:/workspace" \
        -e BASE_URL="${BASE_URL}" \
        -e USERNAME="${USERNAME}" \
        -e PASSWORD="${PASSWORD}" \
        -e COMPANY_ID="${COMPANY_ID}" \
        -e BRANCH_ID="${BRANCH_ID}" \
        -e AUTH_TRANSPORT="${AUTH_TRANSPORT}" \
        -e WAREHOUSE_ID="${WAREHOUSE_ID:-}" \
        -e ITEM_ID="${ITEM_ID:-}" \
        -e DURATION="${ADAPTIVE_DURATION}" \
        -e BILLING_VUS="${adaptive_billing_vus}" \
        -e INVENTORY_VUS="${OPER_INVENTORY_VUS}" \
        -e POSTING_VUS="${OPER_POSTING_VUS}" \
        -e POSTING_LIMIT="${OPER_POSTING_LIMIT}" \
        grafana/k6 run /workspace/qa/k6/operational_posting_load.js \
        --summary-export "/workspace/simulacion/reports/advanced_${REPORT_TS}/operational_summary_adaptive.json"
    )
    adaptive_exit=$?
    set -e
    redact_summary_file "${OPER_ADAPTIVE_SUMMARY_HOST}"

    if [ "${adaptive_exit}" -eq 0 ] || [ -s "${OPER_ADAPTIVE_SUMMARY_HOST}" ]; then
      base_fails="${billing_fails}"
      adaptive_fails="$(extract_check_fails "${OPER_ADAPTIVE_SUMMARY_HOST}" "billing_doc_create status valid")"
      if [ "${adaptive_fails}" -lt "${base_fails}" ]; then
        OPER_SUMMARY_HOST="${OPER_ADAPTIVE_SUMMARY_HOST}"
        warn "control adaptativo: se adopta corrida ajustada (billing fails ${base_fails} -> ${adaptive_fails})."
        if [ "${OPER_PHASE_STATUS}" = "soft-fail" ] && [ "${adaptive_exit}" -eq 0 ]; then
          OPER_PHASE_STATUS="ok"
        fi
      else
        warn "control adaptativo: no mejora (billing fails ${base_fails} -> ${adaptive_fails}); se conserva corrida original."
      fi
    else
      warn "control adaptativo: corrida ajustada fallida sin summary; se conserva corrida original."
    fi
  fi
fi

if ! (
  cd "${ROOT_DIR}"
  run_manage "export_operational_load_snapshot --company-id ${COMPANY_ID} --branch-id ${BRANCH_ID} --output ${OP_AFTER}"
); then
  OPER_PHASE_STATUS="hard-fail"
  OVERALL_STATUS="hard-fail"
  exit 1
fi

run_regression_compare_if_configured "${OPER_SUMMARY_HOST}" "${REPORT_DIR}/operational_regression_report.json"

log "Fase 4/5: consolidar transacciones y validar objetivo >=${TARGET_HTTP_REQS}"
AUTH_HTTP_REQS="$(extract_http_reqs "${AUTH_SUMMARY_HOST}")"
OPER_HTTP_REQS="$(extract_http_reqs "${OPER_SUMMARY_HOST}")"
TOTAL_HTTP_REQS="$(python3 - <<'PY' "${AUTH_HTTP_REQS}" "${OPER_HTTP_REQS}"
import sys
print(float(sys.argv[1]) + float(sys.argv[2]))
PY
)"

TARGET_PASSED="$(python3 - <<'PY' "${TOTAL_HTTP_REQS}" "${TARGET_HTTP_REQS}"
import sys
print("yes" if float(sys.argv[1]) >= float(sys.argv[2]) else "no")
PY
)"

if [ "${TARGET_PASSED}" = "no" ] && [ "${OVERALL_STATUS}" = "ok" ]; then
  OVERALL_STATUS="soft-fail"
fi

if [ "${RUN_QA_GATES}" = "1" ]; then
  log "Fase 4.1: ejecutar Gates de calidad backend/frontend"
  QA_PHASE_STATUS="running"
  set +e
  (
    cd "${ROOT_DIR}"
    make qa-ci-gate1
    make qa-ci-gate2
    make qa-ci-gate3
    make qa-frontend-ci
  )
  qa_exit=$?
  set -e
  if [ "${qa_exit}" -eq 0 ]; then
    QA_PHASE_STATUS="ok"
  else
    QA_PHASE_STATUS="hard-fail"
    OVERALL_STATUS="hard-fail"
    echo "ERROR: QA gates fallaron" >&2
    exit 1
  fi
fi

if [ "${RUN_SECURITY_SCAN}" = "1" ]; then
  log "Fase 4.2: ejecutar escaneo de seguridad local"
  SECURITY_PHASE_STATUS="running"
  set +e
  (
    cd "${ROOT_DIR}"
    bash qa/run_bug_bounty_local.sh
  )
  security_exit=$?
  set -e
  if [ "${security_exit}" -eq 0 ]; then
    SECURITY_PHASE_STATUS="ok"
  else
    SECURITY_PHASE_STATUS="hard-fail"
    OVERALL_STATUS="hard-fail"
    echo "ERROR: escaneo de seguridad fallo" >&2
    exit 1
  fi
fi

log "Fase 5/5: corrida integral finalizada"
cat <<EOF_REPORT
Reportes:
- ${REPORT_DIR}
- ${AUTH_SUMMARY_HOST}
- ${OPER_SUMMARY_HOST}
- ${RUN_SUMMARY}
Grafana: http://localhost:3000
Estados:
- auth_phase_status=${AUTH_PHASE_STATUS}
- operational_phase_status=${OPER_PHASE_STATUS}
- qa_phase_status=${QA_PHASE_STATUS}
- security_phase_status=${SECURITY_PHASE_STATUS}
- target_http_reqs=${TARGET_HTTP_REQS}
- target_passed=${TARGET_PASSED}
- overall_status=${OVERALL_STATUS}
EOF_REPORT

if [ "${OVERALL_STATUS}" != "ok" ]; then
  exit 1
fi
