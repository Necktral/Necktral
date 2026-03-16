#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PRECHECK_ENV_BACKUP=""
PRECHECK_ENV_CREATED_FROM_LOADTEST="0"
PRECHECK_ENV_OVERLAY_ACTIVE="0"

wait_container_healthy() {
  local container_name="$1"
  local max_retries="${2:-60}"
  local sleep_seconds="${3:-2}"
  local status=""
  for _ in $(seq 1 "${max_retries}"); do
    status="$(docker inspect -f '{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "${container_name}" 2>/dev/null || echo error)"
    if [[ "${status}" == "healthy" ]]; then
      return 0
    fi
    sleep "${sleep_seconds}"
  done
  echo "ERROR: ${container_name} no quedo healthy (status final=${status})" >&2
  return 1
}

restore_env_overlay() {
  if [[ "${PRECHECK_ENV_OVERLAY_ACTIVE}" != "1" ]]; then
    return
  fi
  if [[ "${PRECHECK_ENV_CREATED_FROM_LOADTEST}" == "1" ]]; then
    rm -f "${ROOT_DIR}/.env"
  elif [[ -n "${PRECHECK_ENV_BACKUP}" && -f "${PRECHECK_ENV_BACKUP}" ]]; then
    mv -f "${PRECHECK_ENV_BACKUP}" "${ROOT_DIR}/.env"
  fi
}

trap restore_env_overlay EXIT

if [[ "${LOADTEST_ENV_FILE+x}" = x ]]; then
  LOADTEST_ENV_FILE="${LOADTEST_ENV_FILE}"
else
  LOADTEST_ENV_FILE=".env.loadtest"
fi
if [[ -n "${LOADTEST_ENV_FILE}" && "${LOADTEST_ENV_FILE}" != /* ]]; then
  LOADTEST_ENV_FILE="${ROOT_DIR}/${LOADTEST_ENV_FILE}"
fi

if [[ ! -f "${LOADTEST_ENV_FILE}" ]]; then
  echo "ERROR: perfil de carga no encontrado: ${LOADTEST_ENV_FILE}" >&2
  echo "Sugerencia: cp .env.loadtest.example .env.loadtest" >&2
  exit 2
fi

if [[ -f "${ROOT_DIR}/.env" ]]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.env"
  set +a
fi

set -a
# shellcheck disable=SC1090
source "${LOADTEST_ENV_FILE}"
set +a

if ! (
  cd "${ROOT_DIR}"
  docker compose exec -T backend true >/dev/null 2>&1
); then
  echo "ERROR: backend no esta disponible para precheck." >&2
  echo "Levanta backend primero (ej: docker compose up -d db backend)." >&2
  exit 2
fi

cd "${ROOT_DIR}"

if [[ -f "${ROOT_DIR}/.env" ]]; then
  PRECHECK_ENV_BACKUP="${ROOT_DIR}/.env.precheck.backup.$$"
  cp "${ROOT_DIR}/.env" "${PRECHECK_ENV_BACKUP}"
  {
    echo "# Runtime overlay temporal generado por precheck_loadtest_auth.sh"
    cat "${PRECHECK_ENV_BACKUP}"
    echo
    cat "${LOADTEST_ENV_FILE}"
  } > "${ROOT_DIR}/.env"
  PRECHECK_ENV_OVERLAY_ACTIVE="1"
else
  cp "${LOADTEST_ENV_FILE}" "${ROOT_DIR}/.env"
  PRECHECK_ENV_CREATED_FROM_LOADTEST="1"
  PRECHECK_ENV_OVERLAY_ACTIVE="1"
fi

if ! (
  cd "${ROOT_DIR}"
  USE_GUNICORN="${USE_GUNICORN:-1}" GUNICORN_WORKERS="${GUNICORN_WORKERS:-16}" docker compose up -d --force-recreate db backend
); then
  echo "ERROR: no fue posible recrear backend con overlay loadtest para precheck." >&2
  exit 2
fi

if ! wait_container_healthy "erpcrm_backend" 60 2; then
  echo "ERROR: backend no quedo healthy tras recreacion para precheck." >&2
  exit 2
fi

transport_value="${AUTH_TOKEN_TRANSPORT:-}"
override_raw="$(printf '%s' "${AUTH_ALLOW_TRANSPORT_OVERRIDE:-0}" | tr '[:upper:]' '[:lower:]')"
override_enabled="0"
case "${override_raw}" in
  1|true|yes|y)
    override_enabled="1"
    ;;
esac

expected_throttle_anon="${DRF_THROTTLE_ANON:-}"
expected_throttle_user="${DRF_THROTTLE_USER:-}"
expected_throttle_auth_login="${DRF_THROTTLE_AUTH_LOGIN:-}"
expected_throttle_auth_refresh="${DRF_THROTTLE_AUTH_REFRESH:-}"
expected_throttle_auth_logout="${DRF_THROTTLE_AUTH_LOGOUT:-}"
expected_throttle_auth_sensitive="${DRF_THROTTLE_AUTH_SENSITIVE:-}"

echo "AUTH_TOKEN_TRANSPORT=${transport_value:-}"
echo "AUTH_ALLOW_TRANSPORT_OVERRIDE=${override_enabled}"
echo "DRF_THROTTLE_ANON=${expected_throttle_anon:-}"
echo "DRF_THROTTLE_USER=${expected_throttle_user:-}"
echo "DRF_THROTTLE_AUTH_LOGIN=${expected_throttle_auth_login:-}"
echo "DRF_THROTTLE_AUTH_REFRESH=${expected_throttle_auth_refresh:-}"
echo "DRF_THROTTLE_AUTH_LOGOUT=${expected_throttle_auth_logout:-}"
echo "DRF_THROTTLE_AUTH_SENSITIVE=${expected_throttle_auth_sensitive:-}"

config_errors=()
if [[ "${transport_value}" != "header" ]]; then
  config_errors+=("AUTH_TOKEN_TRANSPORT must be 'header'")
fi
if [[ "${override_enabled}" != "1" ]]; then
  config_errors+=("AUTH_ALLOW_TRANSPORT_OVERRIDE must be 1")
fi
for item in "${config_errors[@]}"; do
  echo " - ${item}"
done

set +e
docker compose exec -T backend env \
  LT_EXPECT_AUTH_TOKEN_TRANSPORT="${transport_value:-header}" \
  LT_EXPECT_AUTH_ALLOW_TRANSPORT_OVERRIDE="${override_enabled}" \
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
        "AUTH_TOKEN_TRANSPORT runtime mismatch: "
        f"expected={expected['AUTH_TOKEN_TRANSPORT']} actual={actual['AUTH_TOKEN_TRANSPORT']}"
    )

expected_override = parse_truthy(expected["AUTH_ALLOW_TRANSPORT_OVERRIDE"])
actual_override = actual["AUTH_ALLOW_TRANSPORT_OVERRIDE"] == "1"
if actual_override != expected_override:
    errors.append(
        "AUTH_ALLOW_TRANSPORT_OVERRIDE runtime mismatch: "
        f"expected={expected_override} actual={actual_override}"
    )

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
        errors.append(f"{key} runtime mismatch: expected={expected_value} actual={actual[key]}")

print(f"runtime.AUTH_TOKEN_TRANSPORT={actual['AUTH_TOKEN_TRANSPORT']}")
print(f"runtime.AUTH_ALLOW_TRANSPORT_OVERRIDE={actual['AUTH_ALLOW_TRANSPORT_OVERRIDE']}")
print(f"runtime.DRF_THROTTLE_ANON={actual['DRF_THROTTLE_ANON']}")
print(f"runtime.DRF_THROTTLE_USER={actual['DRF_THROTTLE_USER']}")
print(f"runtime.DRF_THROTTLE_AUTH_LOGIN={actual['DRF_THROTTLE_AUTH_LOGIN']}")
print(f"runtime.DRF_THROTTLE_AUTH_REFRESH={actual['DRF_THROTTLE_AUTH_REFRESH']}")
print(f"runtime.DRF_THROTTLE_AUTH_LOGOUT={actual['DRF_THROTTLE_AUTH_LOGOUT']}")
print(f"runtime.DRF_THROTTLE_AUTH_SENSITIVE={actual['DRF_THROTTLE_AUTH_SENSITIVE']}")

if errors:
    print("BACKEND_RUNTIME_CHECK_STATUS=FAIL")
    for item in errors:
        print(f" - {item}")
    raise SystemExit(2)

print("BACKEND_RUNTIME_CHECK_STATUS=OK")
PY
runtime_check_exit=$?
set -e

set +e
docker compose exec -T backend env LT_USERNAME="${USERNAME:-}" LT_PASSWORD="${PASSWORD:-}" python src/manage.py shell <<'PY'
import os
from django.contrib.auth import get_user_model

username = os.environ.get("LT_USERNAME", "")
password = os.environ.get("LT_PASSWORD", "")
user = get_user_model().objects.filter(username=username).first()

user_exists = bool(user)
password_ok = bool(user and password and user.check_password(password))
totp_enabled = bool(getattr(user, "totp_enabled", False)) if user else False

errors = []
if not username:
    errors.append("USERNAME is empty")
if not password:
    errors.append("PASSWORD is empty")
if not user_exists:
    errors.append("USERNAME does not exist")
if user_exists and not password_ok:
    errors.append("PASSWORD mismatch for USERNAME")
if user_exists and totp_enabled:
    errors.append("USERNAME has 2FA enabled")

print(f"user_exists={user_exists}")
print(f"password_ok={password_ok}")
print(f"totp_enabled={totp_enabled}")
print("USER_CHECK_STATUS=OK" if not errors else "USER_CHECK_STATUS=FAIL")
for item in errors:
    print(f" - {item}")
raise SystemExit(0 if not errors else 2)
PY
user_check_exit=$?
set -e

if [[ "${runtime_check_exit}" -ne 0 || "${user_check_exit}" -ne 0 || "${#config_errors[@]}" -gt 0 ]]; then
  echo "PRECHECK_STATUS=FAIL"
  exit 2
fi

echo "PRECHECK_STATUS=OK"
