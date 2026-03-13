#!/bin/bash
set -e

###############################################################################
# run_bug_bounty.sh
#
# Automated runner for the Necktral Bug Bounty security simulation suite.
#
# This script:
#   1. Validates the environment (Docker network, backend health)
#   2. Optionally starts Grafana + InfluxDB for real-time metrics
#   3. Runs the bug_bounty_security.js k6 script
#   4. Generates a JSON + Markdown report
#   5. Prints a summary with pass/fail verdicts
#
# Usage:
#   ./simulacion/run_bug_bounty.sh [VUS] [DURATION] [--monitor]
#
# Examples:
#   ./simulacion/run_bug_bounty.sh                   # default: 3 VUs, 45s
#   ./simulacion/run_bug_bounty.sh 5 60s             # custom load
#   ./simulacion/run_bug_bounty.sh 3 45s --monitor   # with Grafana dashboard
###############################################################################

# ─── Load .env ───────────────────────────────────────────────────────────────
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

# ─── Defaults ────────────────────────────────────────────────────────────────
VUS=${1:-3}
DURATION=${2:-45s}
ENABLE_MONITOR=false
if [ "${3}" = "--monitor" ] || [ "${MONITOR}" = "1" ]; then
  ENABLE_MONITOR=true
fi

SCRIPT="bug_bounty_security.js"
NETWORK_NAME="erp_crm_default"
REPORTS_DIR="$PWD/simulacion/reports"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
REPORT_FILE="bug_bounty_${TIMESTAMP}.json"

# ─── Validate network ───────────────────────────────────────────────────────
if ! docker network ls | grep -q "$NETWORK_NAME"; then
  echo "Error: Docker network '$NETWORK_NAME' not found."
  echo "Please start the backend services first:"
  echo "  docker compose up -d db backend"
  exit 1
fi

# ─── Optional: start monitoring stack ────────────────────────────────────────
if [ "$ENABLE_MONITOR" = true ]; then
  echo "--- Iniciando Entorno de Monitorización (Grafana + InfluxDB) ---"
  docker compose -f simulacion/docker-compose.monitoring.yaml up -d influxdb grafana
  echo "Esperando a InfluxDB..."
  sleep 5
  INFLUX_OUT="--out influxdb=http://k6_influxdb:8086/k6"
else
  INFLUX_OUT=""
fi

# ─── Create reports directory ────────────────────────────────────────────────
mkdir -p "$REPORTS_DIR"

echo ""
echo "╔══════════════════════════════════════════════════════════════╗"
echo "║          Necktral Bug Bounty – Security Simulation          ║"
echo "╠══════════════════════════════════════════════════════════════╣"
echo "║  Script:   $SCRIPT"
echo "║  VUs:      $VUS"
echo "║  Duration: $DURATION"
echo "║  Monitor:  $ENABLE_MONITOR"
echo "║  Report:   $REPORTS_DIR/$REPORT_FILE"
echo "╚══════════════════════════════════════════════════════════════╝"
echo ""

# ─── Run k6 ─────────────────────────────────────────────────────────────────
set +e
docker run --rm -i \
  --network "$NETWORK_NAME" \
  -v "$PWD/simulacion:/simulacion" \
  -v "$REPORTS_DIR:/reports" \
  -e BASE_URL=${BASE_URL:-http://backend:8000/api} \
  -e ADMIN_USERNAME=${AUTH_SIM_ADMIN_USERNAME:-${ADMIN_USERNAME:-k6_admin}} \
  -e ADMIN_PASSWORD=${AUTH_SIM_ADMIN_PASSWORD:-${ADMIN_PASSWORD:-}} \
  -e ADMIN_TOTP_SECRET=${AUTH_SIM_ADMIN_TOTP_SECRET:-${ADMIN_TOTP_SECRET:-}} \
  -e USER_USERNAME=${AUTH_SIM_USER_USERNAME:-${USER_USERNAME:-k6_user}} \
  -e USER_PASSWORD=${AUTH_SIM_USER_PASSWORD:-${USER_PASSWORD:-}} \
  -e VUS="$VUS" \
  -e DURATION="$DURATION" \
  grafana/k6 run \
  --out json=/reports/"$REPORT_FILE" \
  ${INFLUX_OUT} \
  /simulacion/$SCRIPT

K6_EXIT=$?
set -e

# ─── Generate summary report ────────────────────────────────────────────────
SUMMARY_FILE="$REPORTS_DIR/bug_bounty_summary_${TIMESTAMP}.json"
FINDINGS_FILE="$REPORTS_DIR/bug_bounty_findings_${TIMESTAMP}.md"

python3 - <<PYEOF
import json, hashlib, sys
from pathlib import Path

report_path = Path("${REPORTS_DIR}/${REPORT_FILE}")
summary_path = Path("${SUMMARY_FILE}")
findings_path = Path("${FINDINGS_FILE}")
k6_exit = int("${K6_EXIT}")

# Parse k6 JSON output for metrics
vuln_count = 0
tests_passed = 0
tests_failed = 0
metrics = {}

if report_path.exists():
    for line in report_path.read_text(errors="ignore").splitlines():
        try:
            obj = json.loads(line)
        except Exception:
            continue
        if obj.get("type") == "Point":
            metric = obj.get("metric", "")
            val = obj.get("data", {}).get("value", 0)
            if metric == "vuln_found":
                vuln_count += int(val)
            elif metric == "security_tests_passed":
                tests_passed += int(val)
            elif metric == "security_tests_failed":
                tests_failed += int(val)
            if metric not in metrics:
                metrics[metric] = []
            metrics[metric].append(val)

overall = "PASS" if vuln_count == 0 and k6_exit == 0 else "FAIL"

summary = {
    "status": overall,
    "timestamp": "${TIMESTAMP}",
    "k6_exit_code": k6_exit,
    "vulnerabilities_found": vuln_count,
    "security_tests_passed": tests_passed,
    "security_tests_failed": tests_failed,
    "categories_tested": [
        "A01_Broken_Access_Control",
        "A02_Cryptographic_Failures",
        "A03_Injection",
        "A04_Insecure_Design",
        "A05_Security_Misconfiguration",
        "A07_Authentication_Failures",
        "A08_Data_Integrity_Failures",
        "A09_Logging_Monitoring_Failures",
    ],
    "report_file": str(report_path),
}

summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False))

# Markdown findings
lines = [
    "# Necktral Bug Bounty – Security Findings",
    "",
    f"**Status:** {overall}",
    f"**Timestamp:** {summary['timestamp']}",
    f"**Vulnerabilities Found:** {vuln_count}",
    f"**Tests Passed:** {tests_passed}",
    f"**Tests Failed:** {tests_failed}",
    "",
    "## OWASP Categories Tested",
    "",
    "| Category | Description |",
    "|----------|-------------|",
    "| A01 | Broken Access Control (IDOR, unauth access, bootstrap replay, privilege escalation) |",
    "| A02 | Cryptographic Failures (JWT forgery, none-alg, token reuse, refresh rotation) |",
    "| A03 | Injection (SQL, NoSQL, XSS, path traversal) |",
    "| A04 | Insecure Design (mass assignment, parameter pollution) |",
    "| A05 | Security Misconfiguration (CORS, HTTP methods, debug endpoints) |",
    "| A07 | Auth Failures (brute force, 2FA replay, credential stuffing) |",
    "| A08 | Data Integrity (CSRF bypass, audit tampering) |",
    "| A09 | Logging Failures (info leakage, stack traces, user enumeration) |",
    "",
    "## Verdict",
    "",
]

if overall == "PASS":
    lines.append("> All security probes passed. No vulnerabilities detected.")
else:
    lines.append(f"> **{vuln_count}** vulnerability/ies detected. Review k6 output for details.")
    lines.append("")
    lines.append("Check the k6 console output above for `[VULN]` markers with specific details.")

lines.append("")
lines.append(f"---")
lines.append(f"Report: \`{report_path}\`")
lines.append(f"Summary: \`{summary_path}\`")

findings_path.write_text("\\n".join(lines) + "\\n")

print(f"\\n{'='*60}")
print(f"  Bug Bounty Result: {overall}")
print(f"  Vulnerabilities: {vuln_count}")
print(f"  Tests Passed: {tests_passed}")
print(f"  Tests Failed: {tests_failed}")
print(f"  Summary: {summary_path}")
print(f"  Findings: {findings_path}")
print(f"{'='*60}")

sys.exit(0 if overall == "PASS" else 1)
PYEOF

SUMMARY_EXIT=$?

echo ""
if [ "$ENABLE_MONITOR" = true ]; then
  echo "Dashboard disponible en: http://localhost:3000"
fi

if [ "$SUMMARY_EXIT" -eq 0 ]; then
  echo "Bug Bounty: PASS ✓"
else
  echo "Bug Bounty: FAIL ✗ – Review findings in $FINDINGS_FILE"
fi

exit $SUMMARY_EXIT
