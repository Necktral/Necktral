/**
 * user_lifecycle_simulation.js
 *
 * Advanced K6 load-test that exercises the complete user-lifecycle of the
 * Necktral platform:
 *
 *   1. Bootstrap   – create root admin + org hierarchy (setup phase, once)
 *   2. HR flow     – create positions, employees, provision users
 *   3. Auth churn  – concurrent login / me / acl / refresh / logout
 *   4. RBAC gate   – verify permission enforcement under load
 *   5. Password    – force-change passwords on provisioned users
 *   6. 2FA toggle  – enable → confirm → verify → disable 2FA cycle
 *
 * Run:
 *   BASE_URL=http://localhost:8000/api \
 *   ADMIN_PASSWORD=<pw> \
 *   k6 run simulacion/user_lifecycle_simulation.js
 */

import http from "k6/http";
import { check, fail, sleep, group } from "k6";
import { Rate, Trend, Counter } from "k6/metrics";
import crypto from "k6/crypto";

// ─── Configuration ──────────────────────────────────────────────────────────

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000/api";
const DURATION = __ENV.DURATION || "60s";
const TOTAL_VUS = Number(__ENV.VUS || 10);

// Bootstrap credentials (first-run admin)
const BOOT_USERNAME = __ENV.BOOT_USERNAME || "lifecycle_root";
const BOOT_EMAIL = __ENV.BOOT_EMAIL || "lifecycle_root@test.com";
const BOOT_PASSWORD = __ENV.BOOT_PASSWORD || __ENV.ADMIN_PASSWORD || "";

// Pre-seeded admin (for HR provisioning, falls back to bootstrap user)
const ADMIN_USERNAME = __ENV.ADMIN_USERNAME || BOOT_USERNAME;
const ADMIN_PASSWORD = __ENV.ADMIN_PASSWORD || BOOT_PASSWORD;

// Employee user template
const EMPLOYEE_PREFIX = __ENV.EMPLOYEE_PREFIX || "k6emp";
const EMPLOYEE_COUNT = Number(__ENV.EMPLOYEE_COUNT || 5);
const EMPLOYEE_TEMP_PW = __ENV.EMPLOYEE_TEMP_PW || "Tmp!9_K6_Empl";
const EMPLOYEE_NEW_PW = __ENV.EMPLOYEE_NEW_PW || "New!9_K6_Empl";

// ─── Custom metrics ─────────────────────────────────────────────────────────

const lifecycleErrors = new Rate("lifecycle_error_rate");
const bootstrapMs = new Trend("bootstrap_ms", true);
const hrProvisionMs = new Trend("hr_provision_ms", true);
const authCycleMs = new Trend("auth_cycle_ms", true);
const rbacCheckMs = new Trend("rbac_check_ms", true);
const passwordChangeMs = new Trend("password_change_ms", true);
const twoFaCycleMs = new Trend("twofa_cycle_ms", true);
const usersCreated = new Counter("users_created");

// ─── Scenario definition ────────────────────────────────────────────────────

function share(vus, ratio, minVal) {
  return Math.max(minVal, Math.floor(vus * ratio));
}

export const options = {
  scenarios: {
    auth_churn: {
      executor: "ramping-vus",
      exec: "authChurnFlow",
      startVUs: 0,
      stages: [
        { duration: "10s", target: share(TOTAL_VUS, 0.3, 2) },
        { duration: DURATION, target: share(TOTAL_VUS, 0.5, 3) },
        { duration: "10s", target: 0 },
      ],
    },
    rbac_gate: {
      executor: "constant-vus",
      exec: "rbacGateFlow",
      vus: share(TOTAL_VUS, 0.2, 1),
      duration: DURATION,
    },
    password_change: {
      executor: "constant-vus",
      exec: "passwordChangeFlow",
      vus: share(TOTAL_VUS, 0.15, 1),
      duration: DURATION,
    },
    twofa_toggle: {
      executor: "constant-vus",
      exec: "twofaToggleFlow",
      vus: 1,
      duration: DURATION,
    },
  },
  thresholds: {
    lifecycle_error_rate: ["rate<0.05"],
    auth_cycle_ms: ["p(95)<900"],
    rbac_check_ms: ["p(95)<600"],
    password_change_ms: ["p(95)<800"],
    twofa_cycle_ms: ["p(95)<1200"],
    hr_provision_ms: ["p(95)<1500"],
    bootstrap_ms: ["p(95)<3000"],
    http_req_failed: ["rate<0.05"],
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

function uid() {
  return `${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
}

function authHeaders(token, extras) {
  const h = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
  if (extras) Object.assign(h, extras);
  return h;
}

function postJson(url, body, hdrs, tags) {
  return http.post(url, JSON.stringify(body), {
    headers: hdrs || { "Content-Type": "application/json" },
    tags: tags || {},
  });
}

function ok(res, name, expected) {
  const isOk = expected.includes(res.status);
  lifecycleErrors.add(!isOk, { name });
  check(res, { [`${name} status valid`]: () => isOk });
  if (!isOk) {
    console.error(
      `${name} status=${res.status} body=${res.body ? String(res.body).slice(0, 300) : ""}`,
    );
  }
  return isOk;
}

// ─── TOTP helpers (RFC 6238) ────────────────────────────────────────────────

function base32ToBytes(input) {
  const clean = String(input || "")
    .replace(/=+$/g, "")
    .toUpperCase()
    .replace(/[^A-Z2-7]/g, "");
  const alpha = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = 0,
    value = 0;
  const out = [];
  for (let i = 0; i < clean.length; i++) {
    const idx = alpha.indexOf(clean[i]);
    if (idx === -1) continue;
    value = (value << 5) | idx;
    bits += 5;
    if (bits >= 8) {
      out.push((value >>> (bits - 8)) & 0xff);
      bits -= 8;
    }
  }
  return new Uint8Array(out);
}

function toArrayBuffer(u8) {
  return u8.buffer.slice(u8.byteOffset, u8.byteOffset + u8.byteLength);
}

function hexToBytes(hex) {
  const out = [];
  for (let i = 0; i < hex.length; i += 2)
    out.push(parseInt(hex.slice(i, i + 2), 16));
  return out;
}

function totp(secret) {
  const keyBytes = base32ToBytes(secret);
  const counter = Math.floor(Date.now() / 1000 / 30);
  const msg = new ArrayBuffer(8);
  const dv = new DataView(msg);
  dv.setUint32(0, 0);
  dv.setUint32(4, counter);
  const hmacHex = crypto.hmac("sha1", toArrayBuffer(keyBytes), msg, "hex");
  const hb = hexToBytes(hmacHex);
  const offset = hb[hb.length - 1] & 0x0f;
  const code =
    ((hb[offset] & 0x7f) << 24) |
    ((hb[offset + 1] & 0xff) << 16) |
    ((hb[offset + 2] & 0xff) << 8) |
    (hb[offset + 3] & 0xff);
  return String(code % 1e6).padStart(6, "0");
}

// ─── Auth primitives ────────────────────────────────────────────────────────

function loginHeader(username, password) {
  const res = postJson(
    `${BASE_URL}/auth/login/`,
    { username, password },
    { "Content-Type": "application/json", "X-Auth-Transport": "header" },
    { name: "auth_login" },
  );
  const body = jsonOrNull(res);
  if (res.status === 200 && body && body.access) {
    return { access: body.access, refresh: body.refresh };
  }
  return null;
}

function refreshToken(token) {
  return postJson(
    `${BASE_URL}/auth/refresh/`,
    { refresh: token },
    { "Content-Type": "application/json", "X-Auth-Transport": "header" },
    { name: "auth_refresh" },
  );
}

function logout(accessToken, refreshToken) {
  return http.post(
    `${BASE_URL}/auth/logout/`,
    JSON.stringify({ refresh: refreshToken }),
    {
      headers: authHeaders(accessToken),
      tags: { name: "auth_logout" },
    },
  );
}

// ─── Setup (runs once before VUs) ───────────────────────────────────────────

export function setup() {
  if (!BOOT_PASSWORD) {
    fail("BOOT_PASSWORD / ADMIN_PASSWORD is required");
  }

  const ctx = {
    adminToken: null,
    companyId: null,
    branchId: null,
    employees: [],
  };

  // 1. Check bootstrap status
  const statusRes = http.get(`${BASE_URL}/auth/bootstrap/status/`, {
    tags: { name: "bootstrap_status" },
  });
  const statusBody = jsonOrNull(statusRes);
  const isFresh = statusBody && statusBody.is_fresh;

  if (isFresh) {
    // 1a. Create root admin
    const initStart = Date.now();
    const initRes = postJson(
      `${BASE_URL}/auth/bootstrap/init/`,
      {
        username: BOOT_USERNAME,
        email: BOOT_EMAIL,
        password: BOOT_PASSWORD,
      },
      { "Content-Type": "application/json" },
      { name: "bootstrap_init" },
    );
    bootstrapMs.add(Date.now() - initStart);
    if (!ok(initRes, "bootstrap_init", [201])) {
      console.warn("Bootstrap init failed – system may already be seeded");
    }
  }

  // 2. Login as admin
  const tokens = loginHeader(ADMIN_USERNAME, ADMIN_PASSWORD);
  if (!tokens) {
    fail("Cannot login as admin – check credentials");
  }
  ctx.adminToken = tokens.access;

  // 3. Bootstrap org (if needed)
  const setupRequired = statusBody && statusBody.setup_required;
  if (isFresh || setupRequired) {
    const orgStart = Date.now();
    const orgRes = postJson(
      `${BASE_URL}/auth/bootstrap/org/`,
      {
        holding_name: "K6 Holding",
        company_name: "K6 Company",
        company_trade_name: "K6 Trade",
        company_tax_id: `K6-${uid()}`,
        branch_name: "K6 HQ",
      },
      authHeaders(ctx.adminToken),
      { name: "bootstrap_org" },
    );
    bootstrapMs.add(Date.now() - orgStart);
    const orgBody = jsonOrNull(orgRes);
    if (orgRes.status === 201 && orgBody) {
      ctx.companyId = orgBody.company_id || orgBody.company;
      ctx.branchId = orgBody.branch_id || orgBody.branch;
    }
  }

  // 4. Discover company/branch if not from bootstrap
  if (!ctx.companyId) {
    const companiesRes = http.get(`${BASE_URL}/org/companies/`, {
      headers: authHeaders(ctx.adminToken),
      tags: { name: "org_companies_list" },
    });
    const companiesBody = jsonOrNull(companiesRes);
    const companies =
      (companiesBody && companiesBody.results) || companiesBody || [];
    if (Array.isArray(companies) && companies.length > 0) {
      ctx.companyId = companies[0].id;
    }
  }

  if (!ctx.branchId && ctx.companyId) {
    const branchesRes = http.get(`${BASE_URL}/org/branches/`, {
      headers: authHeaders(ctx.adminToken, {
        "X-Company-Id": String(ctx.companyId),
      }),
      tags: { name: "org_branches_list" },
    });
    const branchesBody = jsonOrNull(branchesRes);
    const branches =
      (branchesBody && branchesBody.results) || branchesBody || [];
    if (Array.isArray(branches) && branches.length > 0) {
      ctx.branchId = branches[0].id;
    }
  }

  // 5. Create HR positions + employees + provision users
  const ctxHeaders = authHeaders(ctx.adminToken, {
    "X-Company-Id": String(ctx.companyId || ""),
    "X-Branch-Id": String(ctx.branchId || ""),
  });

  // Create a position
  const posStart = Date.now();
  const posRes = postJson(
    `${BASE_URL}/hr/positions/`,
    { name: `K6 Operator ${uid()}`, description: "Load-test position" },
    ctxHeaders,
    { name: "hr_position_create" },
  );
  hrProvisionMs.add(Date.now() - posStart);
  const posBody = jsonOrNull(posRes);
  const positionId = posBody && posBody.id ? posBody.id : null;

  // Create employees and provision users
  for (let i = 0; i < EMPLOYEE_COUNT; i++) {
    const empSuffix = `${EMPLOYEE_PREFIX}_${uid()}_${i}`;
    const empStart = Date.now();

    // Create employee
    const empRes = postJson(
      `${BASE_URL}/hr/employees/`,
      {
        first_name: `K6_${i}`,
        last_name: `Load_${empSuffix}`,
        email: `${empSuffix}@k6test.local`,
        hire_date: "2025-01-01",
      },
      ctxHeaders,
      { name: "hr_employee_create" },
    );
    const empBody = jsonOrNull(empRes);
    const empId = empBody && empBody.id ? empBody.id : null;

    if (empId && positionId) {
      // Assign to position
      postJson(
        `${BASE_URL}/hr/employees/${empId}/assignments/`,
        { position_id: positionId, start_date: "2025-01-01" },
        ctxHeaders,
        { name: "hr_employee_assign" },
      );

      // Provision user account
      const provRes = postJson(
        `${BASE_URL}/hr/employees/${empId}/provision-user/`,
        { temp_password: EMPLOYEE_TEMP_PW },
        ctxHeaders,
        { name: "hr_employee_provision" },
      );
      const provBody = jsonOrNull(provRes);

      hrProvisionMs.add(Date.now() - empStart);

      if (provBody && provBody.username) {
        ctx.employees.push({
          id: empId,
          username: provBody.username,
          tempPassword: EMPLOYEE_TEMP_PW,
          newPassword: EMPLOYEE_NEW_PW,
        });
        usersCreated.add(1);
      }
    }
  }

  console.log(
    `[setup] admin=${ADMIN_USERNAME} company=${ctx.companyId} branch=${ctx.branchId} employees=${ctx.employees.length}`,
  );

  return ctx;
}

// ─── Scenario: Auth churn ───────────────────────────────────────────────────

export function authChurnFlow(data) {
  const start = Date.now();
  const emp =
    data.employees && data.employees.length > 0
      ? data.employees[
          Math.floor(Math.random() * data.employees.length)
        ]
      : null;

  // Use admin if no employees were provisioned
  const username = emp ? emp.username : ADMIN_USERNAME;
  const password = emp
    ? emp.newPassword || emp.tempPassword
    : ADMIN_PASSWORD;

  const tokens = loginHeader(username, password);
  if (!tokens) {
    lifecycleErrors.add(true, { name: "auth_churn_login" });
    sleep(0.2);
    return;
  }

  // GET /me
  const meRes = http.get(`${BASE_URL}/auth/me/`, {
    headers: authHeaders(tokens.access),
    tags: { name: "auth_me" },
  });
  check(meRes, { "me 200": (r) => r && r.status === 200 });

  // GET /me/acl
  const aclRes = http.get(`${BASE_URL}/auth/me/acl/`, {
    headers: authHeaders(tokens.access),
    tags: { name: "auth_acl" },
  });
  check(aclRes, { "acl 200": (r) => r && r.status === 200 });

  // Refresh
  const refRes = refreshToken(tokens.refresh);
  check(refRes, { "refresh 200": (r) => r && r.status === 200 });
  const refBody = jsonOrNull(refRes);
  const newAccess = (refBody && refBody.access) || tokens.access;
  const newRefresh = (refBody && refBody.refresh) || tokens.refresh;

  // Logout
  const logRes = logout(newAccess, newRefresh);
  check(logRes, { "logout 204": (r) => r && r.status === 204 });

  authCycleMs.add(Date.now() - start);
  sleep(Number(__ENV.SLEEP || 0.3));
}

// ─── Scenario: RBAC permission gate ─────────────────────────────────────────

export function rbacGateFlow(data) {
  const start = Date.now();
  const tokens = loginHeader(ADMIN_USERNAME, ADMIN_PASSWORD);
  if (!tokens) {
    lifecycleErrors.add(true, { name: "rbac_login" });
    sleep(0.3);
    return;
  }

  const hdrs = authHeaders(tokens.access, {
    "X-Company-Id": String(data.companyId || ""),
    "X-Branch-Id": String(data.branchId || ""),
  });

  // List roles
  const rolesRes = http.get(`${BASE_URL}/rbac/roles/`, {
    headers: hdrs,
    tags: { name: "rbac_roles" },
  });
  check(rolesRes, { "roles 200": (r) => r && r.status === 200 });

  // List permissions
  const permsRes = http.get(`${BASE_URL}/rbac/permissions/`, {
    headers: hdrs,
    tags: { name: "rbac_permissions" },
  });
  check(permsRes, { "perms 200": (r) => r && r.status === 200 });

  // Demo endpoint – should succeed for admin, fail for unprivileged
  const demoRes = http.get(`${BASE_URL}/rbac/demo/inventory-read/`, {
    headers: hdrs,
    tags: { name: "rbac_demo" },
  });
  check(demoRes, {
    "rbac demo authorized": (r) => r && (r.status === 200 || r.status === 403),
  });

  // Org companies (permission: org.company.read)
  const orgRes = http.get(`${BASE_URL}/org/companies/`, {
    headers: hdrs,
    tags: { name: "org_companies" },
  });
  check(orgRes, { "org companies 200": (r) => r && r.status === 200 });

  // Audit trail (permission: audit.read)
  const auditRes = http.get(`${BASE_URL}/audit/bitacora/?page_size=5`, {
    headers: hdrs,
    tags: { name: "audit_list" },
  });
  check(auditRes, {
    "audit 200 or 403": (r) => r && (r.status === 200 || r.status === 403),
  });

  rbacCheckMs.add(Date.now() - start);
  logout(tokens.access, tokens.refresh);
  sleep(Number(__ENV.SLEEP || 0.5));
}

// ─── Scenario: Password change flow ────────────────────────────────────────

export function passwordChangeFlow(data) {
  if (!data.employees || data.employees.length === 0) {
    sleep(1);
    return;
  }

  const start = Date.now();
  const emp =
    data.employees[Math.floor(Math.random() * data.employees.length)];

  // Login with temp password (may fail if already changed)
  let tokens = loginHeader(emp.username, emp.tempPassword);
  let currentPw = emp.tempPassword;
  let newPw = emp.newPassword;

  if (!tokens) {
    // Try with new password (already changed in previous iteration)
    tokens = loginHeader(emp.username, emp.newPassword);
    currentPw = emp.newPassword;
    newPw = emp.tempPassword; // swap back
  }

  if (!tokens) {
    lifecycleErrors.add(true, { name: "pw_change_login" });
    sleep(0.5);
    return;
  }

  const chgRes = postJson(
    `${BASE_URL}/auth/password/`,
    { old_password: currentPw, new_password: newPw },
    authHeaders(tokens.access),
    { name: "auth_password_change" },
  );

  check(chgRes, {
    "password changed": (r) => r && (r.status === 200 || r.status === 204),
  });

  passwordChangeMs.add(Date.now() - start);
  logout(tokens.access, tokens.refresh);
  sleep(Number(__ENV.SLEEP || 1));
}

// ─── Scenario: 2FA toggle flow ──────────────────────────────────────────────

export function twofaToggleFlow(data) {
  const start = Date.now();
  const tokens = loginHeader(ADMIN_USERNAME, ADMIN_PASSWORD);
  if (!tokens) {
    lifecycleErrors.add(true, { name: "2fa_login" });
    sleep(1);
    return;
  }

  const hdrs = authHeaders(tokens.access);

  // Enable 2FA → returns provisioning_uri with secret
  const enableRes = postJson(
    `${BASE_URL}/auth/2fa/enable/`,
    {},
    hdrs,
    { name: "twofa_enable" },
  );

  if (enableRes.status === 200 || enableRes.status === 201) {
    const enableBody = jsonOrNull(enableRes);
    const provUri = enableBody && enableBody.provisioning_uri;
    // Extract secret from otpauth URI
    let secret = null;
    if (provUri) {
      const match = String(provUri).match(/secret=([A-Z2-7]+)/i);
      if (match) secret = match[1];
    }

    if (secret) {
      // Wait for TOTP window to ensure fresh code
      sleep(2);

      // Confirm 2FA
      const code = totp(secret);
      const confirmRes = postJson(
        `${BASE_URL}/auth/2fa/confirm/`,
        { code },
        hdrs,
        { name: "twofa_confirm" },
      );
      check(confirmRes, {
        "2fa confirmed": (r) =>
          r && (r.status === 200 || r.status === 204),
      });

      if (confirmRes.status === 200 || confirmRes.status === 204) {
        // Disable 2FA (requires valid TOTP code)
        sleep(2);
        const disableCode = totp(secret);
        const disableRes = postJson(
          `${BASE_URL}/auth/2fa/disable/`,
          { code: disableCode },
          hdrs,
          { name: "twofa_disable" },
        );
        check(disableRes, {
          "2fa disabled": (r) =>
            r && (r.status === 200 || r.status === 204),
        });
      }
    }
  }

  twoFaCycleMs.add(Date.now() - start);
  logout(tokens.access, tokens.refresh);

  // Long sleep to avoid TOTP time-step collision
  sleep(Number(__ENV.SLEEP_2FA || 15));
}
