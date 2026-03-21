#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
LOADTEST_ENV_FILE="${LOADTEST_ENV_FILE:-.env.loadtest}"
USE_LOADTEST_OVERLAY="${USE_LOADTEST_OVERLAY:-1}"

COMPANY_ID="${COMPANY_ID:-}"
BRANCH_ID="${BRANCH_ID:-}"
USERNAME="${USERNAME:-k6_admin}"
PASSWORD="${PASSWORD:-}"

RUNS="${OPER_AGGR_RUNS:-3}"
DURATION="${OPER_AGGR_DURATION:-2m}"
BILLING_VUS="${OPER_AGGR_BILLING_VUS:-2}"
INVENTORY_VUS="${OPER_AGGR_INVENTORY_VUS:-2}"
POSTING_VUS="${OPER_AGGR_POSTING_VUS:-1}"
SLEEP_SECONDS="${OPER_AGGR_SLEEP:-0.1}"
POSTING_LIMIT="${OPER_AGGR_POSTING_LIMIT:-15}"
AUTH_TRANSPORT="${OPER_GATE_AUTH_TRANSPORT:-header}"
DRAIN_PROJECTOR_BETWEEN_RUNS="${DRAIN_PROJECTOR_BETWEEN_RUNS:-0}"

if [[ -z "${COMPANY_ID}" || -z "${BRANCH_ID}" || -z "${PASSWORD}" ]]; then
  echo "ERROR: COMPANY_ID, BRANCH_ID y PASSWORD son requeridos." >&2
  exit 2
fi

ENV_BACKUP_FILE=""
OVERLAY_ACTIVE=0

wait_backend_health() {
  local max_tries=60
  local i=1
  while [[ "${i}" -le "${max_tries}" ]]; do
    if curl -fsS "http://localhost:8000/api/backend/iam/bootstrap/status/" >/dev/null 2>&1; then
      return 0
    fi
    sleep 2
    i=$((i + 1))
  done
  echo "ERROR: backend no quedó healthy tras recreate." >&2
  return 1
}

restore_env_overlay() {
  if [[ "${OVERLAY_ACTIVE}" != "1" ]]; then
    return 0
  fi
  if [[ -n "${ENV_BACKUP_FILE}" && -f "${ENV_BACKUP_FILE}" ]]; then
    mv -f "${ENV_BACKUP_FILE}" "${ROOT_DIR}/.env"
  fi
  (
    cd "${ROOT_DIR}"
    docker compose up -d --build --force-recreate backend >/dev/null
  )
  wait_backend_health || true
}

trap restore_env_overlay EXIT

(
  cd "${ROOT_DIR}"
  make qa-auth-sync-smoke
)

if [[ "${USE_LOADTEST_OVERLAY}" = "1" ]]; then
  if [[ ! -f "${ROOT_DIR}/${LOADTEST_ENV_FILE}" ]]; then
    echo "ERROR: no existe ${LOADTEST_ENV_FILE} para overlay de carga." >&2
    exit 2
  fi
  if [[ -f "${ROOT_DIR}/.env" ]]; then
    ENV_BACKUP_FILE="${ROOT_DIR}/.env.backup.aggr.$(date +%Y%m%d_%H%M%S)"
    cp "${ROOT_DIR}/.env" "${ENV_BACKUP_FILE}"
    {
      cat "${ENV_BACKUP_FILE}"
      echo
      cat "${ROOT_DIR}/${LOADTEST_ENV_FILE}"
    } > "${ROOT_DIR}/.env"
  else
    cp "${ROOT_DIR}/${LOADTEST_ENV_FILE}" "${ROOT_DIR}/.env"
    ENV_BACKUP_FILE=""
  fi
  OVERLAY_ACTIVE=1
fi

(
  cd "${ROOT_DIR}"
  USE_GUNICORN=1 \
  GUNICORN_WORKERS="${GUNICORN_WORKERS:-4}" \
  GUNICORN_THREADS="${GUNICORN_THREADS:-4}" \
  docker compose up -d --build --force-recreate backend
)
wait_backend_health

i=1
while [[ "${i}" -le "${RUNS}" ]]; do
  echo "Running aggressive gate ${i}/${RUNS} (duration=${DURATION}, vus=${BILLING_VUS}/${INVENTORY_VUS}/${POSTING_VUS})"
  (
    cd "${ROOT_DIR}"
    make qa-load-reset-axes
    COMPANY_ID="${COMPANY_ID}" \
    BRANCH_ID="${BRANCH_ID}" \
    USERNAME="${USERNAME}" \
    PASSWORD="${PASSWORD}" \
    OPER_GATE_DURATION="${DURATION}" \
    OPER_GATE_BILLING_VUS="${BILLING_VUS}" \
    OPER_GATE_INVENTORY_VUS="${INVENTORY_VUS}" \
    OPER_GATE_POSTING_VUS="${POSTING_VUS}" \
    OPER_GATE_SLEEP="${SLEEP_SECONDS}" \
    OPER_GATE_POSTING_LIMIT="${POSTING_LIMIT}" \
    OPER_GATE_AUTH_TRANSPORT="${AUTH_TRANSPORT}" \
    make qa-operational-gate
  )
  if [[ "${DRAIN_PROJECTOR_BETWEEN_RUNS}" = "1" ]]; then
    (
      cd "${ROOT_DIR}"
      make qa-operational-projector-drain COMPANY_ID="${COMPANY_ID}"
    )
  fi
  i=$((i + 1))
done

echo "Aggressive operational gate PASS (${RUNS}/${RUNS})"
