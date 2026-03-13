/**
 * full_platform_stress.js
 *
 * Advanced K6 stress / spike / soak test that hammers every major subsystem
 * of the Necktral platform simultaneously:
 *
 *   • Auth layer       – login, refresh, logout, me, acl
 *   • RBAC / IAM       – roles, permissions, context
 *   • Organization     – companies, branches, company profile
 *   • HR               – positions, employees listing
 *   • Accounting       – health, periods, chart, trial-balance
 *   • Payments         – health, cash sessions
 *   • Audit            – bitacora listing
 *
 * Three load profiles are supported via PROFILE env var:
 *
 *   spike      – sudden 10× surge for 20 s then drop (default)
 *   soak       – moderate load sustained for 5 min
 *   breakpoint – gradual ramp to find the ceiling
 *
 * Run:
 *   BASE_URL=http://localhost:8000/api \
 *   USERNAME=k6_user PASSWORD=<pw> \
 *   PROFILE=spike \
 *   k6 run simulacion/full_platform_stress.js
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend, Counter } from "k6/metrics";

// ─── Configuration ──────────────────────────────────────────────────────────

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000/api";
const USERNAME = __ENV.USERNAME || __ENV.ADMIN_USERNAME || "k6_user";
const PASSWORD = __ENV.PASSWORD || __ENV.ADMIN_PASSWORD || "";

const COMPANY_ID = __ENV.COMPANY_ID || "";
const BRANCH_ID = __ENV.BRANCH_ID || "";

const PROFILE = (__ENV.PROFILE || "spike").toLowerCase();

// ─── Custom metrics ─────────────────────────────────────────────────────────

const stressErrors = new Rate("stress_error_rate");
const authMs = new Trend("stress_auth_ms", true);
const rbacMs = new Trend("stress_rbac_ms", true);
const orgMs = new Trend("stress_org_ms", true);
const hrMs = new Trend("stress_hr_ms", true);
const accountingMs = new Trend("stress_accounting_ms", true);
const paymentsMs = new Trend("stress_payments_ms", true);
const auditMs = new Trend("stress_audit_ms", true);
const requestsTotal = new Counter("stress_requests_total");

// ─── Load profiles ──────────────────────────────────────────────────────────

function spikeStages() {
  const base = Number(__ENV.SPIKE_BASE || 5);
  const peak = Number(__ENV.SPIKE_PEAK || 50);
  return [
    { duration: "10s", target: base },
    { duration: "5s", target: peak },
    { duration: "20s", target: peak },
    { duration: "5s", target: base },
    { duration: "20s", target: base },
    { duration: "5s", target: 0 },
  ];
}

function soakStages() {
  const level = Number(__ENV.SOAK_VUS || 15);
  const dur = __ENV.SOAK_DURATION || "5m";
  return [
    { duration: "15s", target: level },
    { duration: dur, target: level },
    { duration: "10s", target: 0 },
  ];
}

function breakpointStages() {
  const max = Number(__ENV.BP_MAX || 100);
  const step = Number(__ENV.BP_STEP_DURATION || 15);
  const steps = Number(__ENV.BP_STEPS || 10);
  const stages = [];
  for (let i = 1; i <= steps; i++) {
    stages.push({
      duration: `${step}s`,
      target: Math.ceil((max / steps) * i),
    });
  }
  stages.push({ duration: "10s", target: 0 });
  return stages;
}

function getStages() {
  if (PROFILE === "soak") return soakStages();
  if (PROFILE === "breakpoint") return breakpointStages();
  return spikeStages();
}

export const options = {
  scenarios: {
    full_platform: {
      executor: "ramping-vus",
      exec: "fullPlatformCycle",
      startVUs: 0,
      stages: getStages(),
    },
  },
  thresholds: {
    stress_error_rate: ["rate<0.10"],
    stress_auth_ms: ["p(95)<1200"],
    stress_rbac_ms: ["p(95)<800"],
    stress_org_ms: ["p(95)<800"],
    stress_hr_ms: ["p(95)<1000"],
    stress_accounting_ms: ["p(95)<1000"],
    stress_payments_ms: ["p(95)<800"],
    stress_audit_ms: ["p(95)<800"],
    http_req_failed: ["rate<0.15"],
  },
};

// ─── Helpers ────────────────────────────────────────────────────────────────

function jsonOrNull(res) {
  try {
    return res && res.json ? res.json() : null;
  } catch (_) {
    return null;
  }
}

function authHeaders(token) {
  const h = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
  if (COMPANY_ID) h["X-Company-Id"] = COMPANY_ID;
  if (BRANCH_ID) h["X-Branch-Id"] = BRANCH_ID;
  return h;
}

function record(res, name, okStatuses) {
  const isOk = okStatuses.includes(res.status);
  stressErrors.add(!isOk, { name });
  requestsTotal.add(1, { name });
  check(res, { [`${name} ok`]: () => isOk });
  return isOk;
}

// ─── Main flow ──────────────────────────────────────────────────────────────

export function fullPlatformCycle() {
  // ── Auth ──────────────────────────────────────────────────────────────
  const authStart = Date.now();

  const loginRes = http.post(
    `${BASE_URL}/auth/login/`,
    JSON.stringify({ username: USERNAME, password: PASSWORD }),
    {
      headers: {
        "Content-Type": "application/json",
        "X-Auth-Transport": "header",
      },
      tags: { name: "stress_login" },
    },
  );
  const loginBody = jsonOrNull(loginRes);
  const access = loginBody && loginBody.access ? loginBody.access : null;
  const refresh = loginBody && loginBody.refresh ? loginBody.refresh : null;

  if (!record(loginRes, "stress_login", [200])) {
    authMs.add(Date.now() - authStart);
    sleep(0.5);
    return;
  }

  const hdrs = authHeaders(access);

  // /me
  const meRes = http.get(`${BASE_URL}/auth/me/`, {
    headers: hdrs,
    tags: { name: "stress_me" },
  });
  record(meRes, "stress_me", [200]);

  // /me/acl
  const aclRes = http.get(`${BASE_URL}/auth/me/acl/`, {
    headers: hdrs,
    tags: { name: "stress_acl" },
  });
  record(aclRes, "stress_acl", [200]);

  // Refresh
  const refRes = http.post(
    `${BASE_URL}/auth/refresh/`,
    JSON.stringify({ refresh }),
    {
      headers: {
        "Content-Type": "application/json",
        "X-Auth-Transport": "header",
      },
      tags: { name: "stress_refresh" },
    },
  );
  record(refRes, "stress_refresh", [200]);
  const refBody = jsonOrNull(refRes);
  const newAccess = (refBody && refBody.access) || access;
  const newRefresh = (refBody && refBody.refresh) || refresh;
  const freshHdrs = authHeaders(newAccess);

  authMs.add(Date.now() - authStart);

  // ── RBAC ──────────────────────────────────────────────────────────────
  const rbacStart = Date.now();

  const rolesRes = http.get(`${BASE_URL}/rbac/roles/`, {
    headers: freshHdrs,
    tags: { name: "stress_roles" },
  });
  record(rolesRes, "stress_roles", [200, 403]);

  const permsRes = http.get(`${BASE_URL}/rbac/permissions/`, {
    headers: freshHdrs,
    tags: { name: "stress_perms" },
  });
  record(permsRes, "stress_perms", [200, 403]);

  rbacMs.add(Date.now() - rbacStart);

  // ── Organization ──────────────────────────────────────────────────────
  const orgStart = Date.now();

  const compRes = http.get(`${BASE_URL}/org/companies/`, {
    headers: freshHdrs,
    tags: { name: "stress_companies" },
  });
  record(compRes, "stress_companies", [200, 403]);

  const branchRes = http.get(`${BASE_URL}/org/branches/`, {
    headers: freshHdrs,
    tags: { name: "stress_branches" },
  });
  record(branchRes, "stress_branches", [200, 403]);

  const profileRes = http.get(`${BASE_URL}/org/company/profile/`, {
    headers: freshHdrs,
    tags: { name: "stress_company_profile" },
  });
  record(profileRes, "stress_company_profile", [200, 403, 404]);

  orgMs.add(Date.now() - orgStart);

  // ── HR ────────────────────────────────────────────────────────────────
  const hrStart = Date.now();

  const posRes = http.get(`${BASE_URL}/hr/positions/`, {
    headers: freshHdrs,
    tags: { name: "stress_positions" },
  });
  record(posRes, "stress_positions", [200, 403]);

  const empRes = http.get(`${BASE_URL}/hr/employees/`, {
    headers: freshHdrs,
    tags: { name: "stress_employees" },
  });
  record(empRes, "stress_employees", [200, 403]);

  hrMs.add(Date.now() - hrStart);

  // ── Accounting ────────────────────────────────────────────────────────
  const accStart = Date.now();

  const accHealthRes = http.get(`${BASE_URL}/accounting/health/`, {
    headers: freshHdrs,
    tags: { name: "stress_acc_health" },
  });
  record(accHealthRes, "stress_acc_health", [200, 403, 404]);

  const periodsRes = http.get(`${BASE_URL}/accounting/periods/`, {
    headers: freshHdrs,
    tags: { name: "stress_periods" },
  });
  record(periodsRes, "stress_periods", [200, 403, 404]);

  const coaRes = http.get(`${BASE_URL}/accounting/chart-of-accounts/`, {
    headers: freshHdrs,
    tags: { name: "stress_coa" },
  });
  record(coaRes, "stress_coa", [200, 403, 404]);

  const tbRes = http.get(`${BASE_URL}/accounting/reports/trial-balance/`, {
    headers: freshHdrs,
    tags: { name: "stress_trial_balance" },
  });
  record(tbRes, "stress_trial_balance", [200, 403, 404]);

  accountingMs.add(Date.now() - accStart);

  // ── Payments ──────────────────────────────────────────────────────────
  const payStart = Date.now();

  const payHealthRes = http.get(`${BASE_URL}/payments/health/`, {
    headers: freshHdrs,
    tags: { name: "stress_pay_health" },
  });
  record(payHealthRes, "stress_pay_health", [200, 403, 404]);

  const sessionsRes = http.get(`${BASE_URL}/payments/cash-sessions/`, {
    headers: freshHdrs,
    tags: { name: "stress_cash_sessions" },
  });
  record(sessionsRes, "stress_cash_sessions", [200, 403, 404]);

  paymentsMs.add(Date.now() - payStart);

  // ── Audit ─────────────────────────────────────────────────────────────
  const auditStart = Date.now();

  const bitRes = http.get(`${BASE_URL}/audit/bitacora/?page_size=10`, {
    headers: freshHdrs,
    tags: { name: "stress_audit" },
  });
  record(bitRes, "stress_audit", [200, 403]);

  auditMs.add(Date.now() - auditStart);

  // ── Logout ────────────────────────────────────────────────────────────
  http.post(
    `${BASE_URL}/auth/logout/`,
    JSON.stringify({ refresh: newRefresh }),
    {
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${newAccess}`,
      },
      tags: { name: "stress_logout" },
    },
  );

  sleep(Number(__ENV.SLEEP || 0.1));
}
