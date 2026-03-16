#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
NETWORK_NAME="erp_crm_default"

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

verify_grafana_provisioning() {
  local since_ts="$1"
  if docker logs --since "${since_ts}" k6_grafana 2>&1 | rg -q "failed to load dashboard|provisioning.dashboard.*level=error|invalid character .*object key string"; then
    echo "ERROR: Grafana reporto fallo de provisioning de dashboard" >&2
    docker logs --since "${since_ts}" k6_grafana 2>&1 | rg "failed to load dashboard|provisioning.dashboard|invalid character .*object key string" || true
    return 1
  fi
}

# Load .env safely if available
if [ -f "${ROOT_DIR}/.env" ]; then
  set -a
  # shellcheck disable=SC1091
  source "${ROOT_DIR}/.env"
  set +a
fi

# Default values
TEST_SCRIPT="${1:-auth_load_simulation_extended.js}"
VUS="${2:-8}"
DURATION="${3:-30s}"

# Check if network exists
if ! docker network ls | grep -q "${NETWORK_NAME}"; then
  echo "Error: Network '${NETWORK_NAME}' not found. Please start the backend services first." >&2
  exit 1
fi

echo "--- Preflight de observabilidad ---"
(cd "${ROOT_DIR}" && docker compose -f simulacion/docker-compose.monitoring.yaml config >/dev/null)
validate_dashboard_json "${ROOT_DIR}/simulacion/dashboards/k6-load-testing-results.json" >/dev/null

echo "--- Iniciando Entorno de Monitorización (Grafana + InfluxDB) ---"
monitoring_start_ts="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
(cd "${ROOT_DIR}" && docker compose -f simulacion/docker-compose.monitoring.yaml up -d influxdb grafana)

echo "esperando healthchecks de InfluxDB y Grafana..."
wait_container_healthy "k6_influxdb" 60 2
wait_container_healthy "k6_grafana" 60 2
verify_grafana_provisioning "${monitoring_start_ts}"

echo "--- Ejecutando Simulacion k6 ---"
echo "Script: ${TEST_SCRIPT}"
echo "VUs: ${VUS}"
echo "Duration: ${DURATION}"

# Run k6 with InfluxDB output AND local file report
mkdir -p "${ROOT_DIR}/simulacion/reports"
HOST_UID="$(id -u)"
HOST_GID="$(id -g)"
REPORT_TS="$(date +%s)"
REPORT_JSON="/simulacion/reports/report_${REPORT_TS}.json"
REPORT_SUMMARY="/simulacion/reports/report_${REPORT_TS}_summary.json"

docker run --rm -i \
  --user "${HOST_UID}:${HOST_GID}" \
  --network "${NETWORK_NAME}" \
  -v "${ROOT_DIR}/simulacion:/simulacion" \
  -e BASE_URL="${BASE_URL:-http://backend:8000/api}" \
  -e USER_USERNAME="${AUTH_SIM_USER_USERNAME:-k6_user}" \
  -e USER_PASSWORD="${AUTH_SIM_USER_PASSWORD:-}" \
  -e ADMIN_USERNAME="${AUTH_SIM_ADMIN_USERNAME:-k6_admin}" \
  -e ADMIN_PASSWORD="${AUTH_SIM_ADMIN_PASSWORD:-}" \
  -e ADMIN_TOTP_SECRET="${AUTH_SIM_ADMIN_TOTP_SECRET:-${ADMIN_TOTP_SECRET:-}}" \
  -e CSRF_COOKIE_NAME="${CSRF_COOKIE_NAME:-nt_csrf}" \
  -e VUS="${VUS}" \
  -e DURATION="${DURATION}" \
  grafana/k6 run \
  --out influxdb=http://k6_influxdb:8086/k6 \
  --out json="${REPORT_JSON}" \
  --summary-export "${REPORT_SUMMARY}" \
  "/simulacion/${TEST_SCRIPT}"

python3 "${ROOT_DIR}/simulacion/redact_k6_summary.py" "${ROOT_DIR}${REPORT_SUMMARY}" >/dev/null || true

echo "\n--- Simulacion Finalizada ---"
echo "Reporte guardado en: simulacion/reports/"
echo "JSON: simulacion/reports/report_${REPORT_TS}.json"
echo "Summary: simulacion/reports/report_${REPORT_TS}_summary.json"
echo "Puedes ver los resultados en Grafana: http://localhost:3000"
echo "Dashboard: K6 Load Testing Results (acceso anonimo en modo Viewer)"
