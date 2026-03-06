#!/bin/bash
set -e

# Load .env variables if available
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

# Default values - CHANGED to extended script to verify security requirements
TEST_SCRIPT=${1:-auth_load_simulation_extended.js}
# Increased VUs slightly for extended scenario mix
VUS=${2:-8} 
DURATION=${3:-30s}

# Check if network exists
NETWORK_NAME=${SIM_NETWORK_NAME:-erp_crm_default}
if ! docker network ls | grep -q "$NETWORK_NAME"; then
    echo "Error: Network '$NETWORK_NAME' not found. Please start the backend services first."
    exit 1
fi

echo "--- Iniciando Entorno de Monitorización (Grafana + InfluxDB) ---"
docker compose -f simulacion/docker-compose.monitoring.yaml up -d influxdb grafana

echo "esperando a influxdb..."
sleep 5

echo "--- Ejecutando Simulacion k6 ---"
echo "Script: $TEST_SCRIPT"
echo "VUs: $VUS"
echo "Duration: $DURATION"

# Run k6 with InfluxDB output AND local file report
mkdir -p "$PWD/simulacion/reports"

docker run --rm -i \
  --network $NETWORK_NAME \
  -v "$PWD/simulacion:/simulacion" \
  -e BASE_URL=${BASE_URL:-http://backend:8000/api} \
  -e USER_USERNAME=${AUTH_SIM_USER_USERNAME:-k6_user} \
  -e USER_PASSWORD=${AUTH_SIM_USER_PASSWORD:-Pass12345__Strong} \
  -e ADMIN_USERNAME=${AUTH_SIM_ADMIN_USERNAME:-k6_admin} \
  -e ADMIN_PASSWORD=${AUTH_SIM_ADMIN_PASSWORD:-Pass12345__Strong} \
  -e ADMIN_TOTP_SECRET=${AUTH_SIM_ADMIN_TOTP_SECRET:-$ADMIN_TOTP_SECRET} \
  -e CSRF_COOKIE_NAME=${CSRF_COOKIE_NAME:-nt_csrf} \
  -e ENABLE_429_TEST=${ENABLE_429_TEST:-0} \
  -e ONLY_429_TEST=${ONLY_429_TEST:-0} \
  -e THROTTLE_RATE=${THROTTLE_RATE:-20} \
  -e THROTTLE_DURATION=${THROTTLE_DURATION:-15s} \
  -e THROTTLE_PREALLOC=${THROTTLE_PREALLOC:-20} \
  -e THROTTLE_MAX=${THROTTLE_MAX:-50} \
  -e REQUIRE_ADMIN_TOTP=${REQUIRE_ADMIN_TOTP:-0} \
  -e REQUIRE_CSRF_COOKIE=${REQUIRE_CSRF_COOKIE:-0} \
  -e CSRF_CLEAR_REQUIRED=${CSRF_CLEAR_REQUIRED:-0} \
  -e VUS=$VUS \
  -e DURATION=$DURATION \
  grafana/k6 run \
  --out influxdb=http://k6_influxdb:8086/k6 \
  --out json=/simulacion/reports/report_$(date +%s).json \
  /simulacion/$TEST_SCRIPT

echo "\n--- Simulacion Finalizada ---"
echo "Reporte guardado en: simulacion/reports/"
echo "Puedes ver los resultados en Grafana: http://localhost:3000"
echo "Dashboard: K6 Load Testing Results (Login: admin/admin si pide, pero esta configurado anonimo)"
