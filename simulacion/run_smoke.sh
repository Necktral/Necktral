#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ -f "${ROOT_DIR}/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.env"
  set +a
fi

AUTH_SIM_ADMIN_USERNAME="${AUTH_SIM_ADMIN_USERNAME:-k6_admin}"
AUTH_SIM_ADMIN_PASSWORD="${AUTH_SIM_ADMIN_PASSWORD:-Aa!9_Sim_Seed}"
AUTH_SIM_ADMIN_TOTP_SECRET="${AUTH_SIM_ADMIN_TOTP_SECRET:-JBSWY3DPEHPK3PXP}"
AUTH_SIM_USER_USERNAME="${AUTH_SIM_USER_USERNAME:-k6_user}"
AUTH_SIM_USER_PASSWORD="${AUTH_SIM_USER_PASSWORD:-Aa!9_Sim_Seed}"

run_manage() {
  local cmd="$1"
  if docker compose exec -T backend python src/manage.py ${cmd}; then
    return 0
  fi
  docker compose exec -T backend python manage.py ${cmd}
}

echo "[smoke] Levantando db/backend..."
(
  cd "${ROOT_DIR}"
  docker compose up -d db backend
)

echo "[smoke] Esperando backend healthy..."
status=""
for i in $(seq 1 60); do
  status="$(docker inspect -f '{{.State.Health.Status}}' erpcrm_backend 2>/dev/null || echo error)"
  if [ "${status}" = "healthy" ]; then
    break
  fi
  sleep 2
done
if [ "${status}" != "healthy" ]; then
  echo "ERROR: backend no quedo healthy a tiempo" >&2
  exit 1
fi

echo "[smoke] Seed de usuarios de auth para k6..."
(
  cd "${ROOT_DIR}"
  run_manage "migrate --noinput"
  run_manage "seed_auth_users --admin-username ${AUTH_SIM_ADMIN_USERNAME} --admin-password ${AUTH_SIM_ADMIN_PASSWORD} --admin-totp-secret ${AUTH_SIM_ADMIN_TOTP_SECRET} --admin-enable-2fa --user-username ${AUTH_SIM_USER_USERNAME} --user-password ${AUTH_SIM_USER_PASSWORD}"
  run_manage "axes_reset"
)

echo "[smoke] Ejecutando corrida corta..."
(
  cd "${ROOT_DIR}"
  AUTH_SIM_ADMIN_USERNAME="${AUTH_SIM_ADMIN_USERNAME}" \
  AUTH_SIM_ADMIN_PASSWORD="${AUTH_SIM_ADMIN_PASSWORD}" \
  AUTH_SIM_ADMIN_TOTP_SECRET="${AUTH_SIM_ADMIN_TOTP_SECRET}" \
  AUTH_SIM_USER_USERNAME="${AUTH_SIM_USER_USERNAME}" \
  AUTH_SIM_USER_PASSWORD="${AUTH_SIM_USER_PASSWORD}" \
  ./simulacion/run_simulation.sh auth_load_simulation_extended.js 1 10s
)

echo "[smoke] Listo. Revisa simulacion/reports y Grafana en http://localhost:3000"
