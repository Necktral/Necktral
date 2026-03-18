#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="${1:-/app}"
REPORT_FILE="${2:-}"
REPORT_DIR="${ROOT_DIR}/qa/reports"

if [[ -z "${REPORT_FILE}" ]]; then
  REPORT_FILE="${REPORT_DIR}/static_scan.txt"
fi

REPORT_PARENT="$(dirname "${REPORT_FILE}")"
mkdir -p "${REPORT_PARENT}"

TARGET_DIR="${ROOT_DIR}/backend/src/apps"

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
} > "${REPORT_FILE}"

if [[ -n "${matches}" ]]; then
  echo "Static scan falló: ver ${REPORT_FILE}" >&2
  exit 2
fi

echo "Static scan OK: ${REPORT_FILE}"
