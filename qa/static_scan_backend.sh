#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-/app}"
REPORT_DIR="${ROOT_DIR}/qa/reports"

mkdir -p "${REPORT_DIR}"

TARGET_DIR="${ROOT_DIR}/login_module/src/apps"

# Scan enfocado en indicadores típicos de deuda crítica en rutas sensibles.
# Evita falsos positivos excluyendo migraciones.
PATTERN='(TODO|FIXME|XXX|HACK|NotImplementedError)'

matches="$(
  grep -RInE "${PATTERN}" "${TARGET_DIR}" \
    --exclude-dir=migrations \
    --exclude-dir=__pycache__ \
    || true
)"

{
  echo "static_scan_target=${TARGET_DIR}"
  echo "static_scan_pattern=${PATTERN}"
  echo
  if [[ -n "${matches}" ]]; then
    echo "HALLAZGOS:"
    echo "${matches}"
  else
    echo "OK: sin hallazgos"
  fi
} > "${REPORT_DIR}/static_scan.txt"

if [[ -n "${matches}" ]]; then
  echo "Static scan falló: ver ${REPORT_DIR}/static_scan.txt" >&2
  exit 2
fi

echo "Static scan OK: ${REPORT_DIR}/static_scan.txt"
