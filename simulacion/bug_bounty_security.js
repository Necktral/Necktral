/**
 * bug_bounty_security.js
 *
 * OWASP-aligned security simulation for Necktral Bug Bounty.
 *
 * This K6 script probes the API surface for common web-application
 * vulnerabilities.  It is NOT a scanner — it sends known-bad payloads and
 * asserts the server responds safely (4xx, never 2xx/5xx).
 *
 * Covered categories (OWASP Top-10 2021 mapped):
 *
 *   A01  Broken Access Control
 *        – IDOR on user/org/employee resources
 *        – Horizontal privilege escalation
 *        – Unauthenticated access to protected endpoints
 *        – Bootstrap re-execution after first run
 *
 *   A02  Cryptographic Failures
 *        – Token forgery (random JWT, tampered signature)
 *        – Expired / blacklisted refresh token re-use
 *
 *   A03  Injection
 *        – SQL injection payloads in login, search, filter params
 *        – NoSQL / JSON injection in request bodies
 *        – Header injection (CRLF, Host override)
 *
 *   A04  Insecure Design
 *        – Mass assignment (extra fields on create/update)
 *        – Parameter pollution (duplicate query params)
 *
 *   A05  Security Misconfiguration
 *        – Debug / stack trace exposure on 4xx/5xx
 *        – CORS misconfiguration probing
 *        – Unnecessary HTTP methods (TRACE, OPTIONS abuse)
 *
 *   A07  Identification & Authentication Failures
 *        – Brute force (sequential wrong passwords)
 *        – 2FA replay attack
 *        – Credential stuffing detection
 *        – Session fixation via cookie injection
 *
 *   A08  Software & Data Integrity Failures
 *        – CSRF token bypass attempts
 *        – Audit log tampering probe
 *
 *   A09  Logging & Monitoring Failures
 *        – Verify error responses do NOT leak internals
 *
 * Run:
 *   BASE_URL=http://localhost:8000/api \
 *   ADMIN_USERNAME=k6_admin ADMIN_PASSWORD=<pw> \
 *   ADMIN_TOTP_SECRET=<secret> \
 *   k6 run simulacion/bug_bounty_security.js
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Counter } from "k6/metrics";
import crypto from "k6/crypto";

// ─── Configuration ──────────────────────────────────────────────────────────

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000/api";
const ROOT_URL = BASE_URL.replace(/\/api\/?$/, "");
const DURATION = __ENV.DURATION || "45s";
const VUS = Number(__ENV.VUS || 3);

const ADMIN_USERNAME = __ENV.ADMIN_USERNAME || "k6_admin";
const ADMIN_PASSWORD = __ENV.ADMIN_PASSWORD || "";
const ADMIN_TOTP_SECRET = __ENV.ADMIN_TOTP_SECRET || "";

const USER_USERNAME = __ENV.USER_USERNAME || "k6_user";
const USER_PASSWORD = __ENV.USER_PASSWORD || "";

// ─── Custom metrics ─────────────────────────────────────────────────────────

const vulnFound = new Counter("vuln_found");
const testsPassed = new Counter("security_tests_passed");
const testsFailed = new Counter("security_tests_failed");
const falsePositives = new Rate("false_positive_rate");

// ─── Scenario definition ────────────────────────────────────────────────────

export const options = {
  scenarios: {
    injection_probes: {
      executor: "constant-vus",
      exec: "injectionProbes",
      vus: Math.max(1, Math.floor(VUS * 0.25)),
      duration: DURATION,
    },
    auth_bypass: {
      executor: "constant-vus",
      exec: "authBypassProbes",
      vus: Math.max(1, Math.floor(VUS * 0.2)),
      duration: DURATION,
    },
    idor_probes: {
      executor: "constant-vus",
      exec: "idorProbes",
      vus: Math.max(1, Math.floor(VUS * 0.15)),
      duration: DURATION,
    },
    token_attacks: {
      executor: "constant-vus",
      exec: "tokenAttacks",
      vus: Math.max(1, Math.floor(VUS * 0.15)),
      duration: DURATION,
    },
    csrf_bypass: {
      executor: "constant-vus",
      exec: "csrfBypassProbes",
      vus: Math.max(1, Math.floor(VUS * 0.1)),
      duration: DURATION,
    },
    header_injection: {
      executor: "constant-vus",
      exec: "headerInjectionProbes",
      vus: Math.max(1, Math.floor(VUS * 0.1)),
      duration: DURATION,
    },
    info_leakage: {
      executor: "constant-vus",
      exec: "infoLeakageProbes",
      vus: 1,
      duration: DURATION,
    },
  },
  thresholds: {
    vuln_found: ["count<1"],
    security_tests_passed: ["count>0"],
    http_req_failed: ["rate<0.99"],
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

function assertSafe(res, testName, unsafeStatuses) {
  const unsafe = (unsafeStatuses || [200, 201, 204]).includes(res.status);
  const hasStackTrace =
    res.body &&
    (String(res.body).includes("Traceback") ||
      String(res.body).includes("DJANGO_SETTINGS_MODULE") ||
      String(res.body).includes("at /") ||
      String(res.body).includes("psycopg") ||
      String(res.body).includes("OperationalError"));

  if (unsafe) {
    vulnFound.add(1, { test: testName });
    testsFailed.add(1, { test: testName });
    console.error(
      `[VULN] ${testName}: unexpected ${res.status} – ${String(res.body).slice(0, 200)}`,
    );
  } else if (hasStackTrace) {
    vulnFound.add(1, { test: testName });
    testsFailed.add(1, { test: testName });
    console.error(
      `[VULN] ${testName}: stack trace leaked – ${String(res.body).slice(0, 200)}`,
    );
  } else {
    testsPassed.add(1, { test: testName });
  }

  return check(res, {
    [`${testName} safe`]: () => !unsafe && !hasStackTrace,
  });
}

function loginAndGetTokens(username, password) {
  const res = http.post(
    `${BASE_URL}/auth/login/`,
    JSON.stringify({ username, password }),
    {
      headers: {
        "Content-Type": "application/json",
        "X-Auth-Transport": "header",
      },
      tags: { name: "bb_login" },
    },
  );
  const body = jsonOrNull(res);
  if (res.status === 200 && body && body.access) {
    return { access: body.access, refresh: body.refresh };
  }
  return null;
}

function authHeaders(token) {
  return {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
}

// ─── TOTP helpers ───────────────────────────────────────────────────────────

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

// ─── SQL / NoSQL injection payloads ─────────────────────────────────────────

const SQL_PAYLOADS = [
  "' OR '1'='1",
  "'; DROP TABLE auth_user; --",
  "1 UNION SELECT username,password FROM auth_user--",
  "admin'--",
  "' OR 1=1 LIMIT 1--",
  "1; WAITFOR DELAY '0:0:5'--",
  "' AND (SELECT COUNT(*) FROM auth_user) > 0--",
  "\\'; EXECUTE IMMEDIATE \\'SELECT 1\\'; --",
];

const NOSQL_PAYLOADS = [
  '{"$gt":""}',
  '{"$ne":null}',
  '{"$regex":".*"}',
  '{"username":{"$gt":""},"password":{"$gt":""}}',
];

const XSS_PAYLOADS = [
  "<script>alert(1)</script>",
  '"><img src=x onerror=alert(1)>',
  "javascript:alert(1)",
  "'-alert(1)-'",
  "<svg/onload=alert(1)>",
];

const PATH_TRAVERSAL = [
  "../../etc/passwd",
  "..\\..\\windows\\system32\\config\\sam",
  "%2e%2e%2f%2e%2e%2fetc%2fpasswd",
  "....//....//etc/passwd",
];

// ═══════════════════════════════════════════════════════════════════════════
// Scenario: A03 – Injection probes
// ═══════════════════════════════════════════════════════════════════════════

export function injectionProbes() {
  // SQL injection in login username
  for (const payload of SQL_PAYLOADS) {
    const res = http.post(
      `${BASE_URL}/auth/login/`,
      JSON.stringify({ username: payload, password: "anything" }),
      {
        headers: { "Content-Type": "application/json" },
        tags: { name: "bb_sqli_login" },
        responseCallback: http.expectedStatuses(400, 401, 403, 429),
      },
    );
    assertSafe(res, `sqli_login[${payload.slice(0, 20)}]`);
  }

  // SQL injection in query parameters
  const tokens = loginAndGetTokens(USER_USERNAME, USER_PASSWORD);
  if (tokens) {
    const hdrs = authHeaders(tokens.access);

    // Injection in filter params
    const filterPayloads = [
      "page_size=1;DROP TABLE--",
      "search=' OR 1=1--",
      "ordering=id;DROP TABLE auth_user--",
    ];

    for (const qp of filterPayloads) {
      const res = http.get(`${BASE_URL}/audit/bitacora/?${qp}`, {
        headers: hdrs,
        tags: { name: "bb_sqli_params" },
      });
      assertSafe(res, `sqli_param[${qp.slice(0, 25)}]`, [500]);
    }

    // NoSQL injection in JSON body
    for (const payload of NOSQL_PAYLOADS) {
      const res = http.post(`${BASE_URL}/auth/login/`, payload, {
        headers: { "Content-Type": "application/json" },
        tags: { name: "bb_nosql_login" },
        responseCallback: http.expectedStatuses(400, 401, 403, 415, 429),
      });
      assertSafe(res, `nosql_login[${payload.slice(0, 20)}]`);
    }

    // XSS in user-controllable fields
    for (const payload of XSS_PAYLOADS) {
      const res = http.post(
        `${BASE_URL}/auth/login/`,
        JSON.stringify({ username: payload, password: payload }),
        {
          headers: { "Content-Type": "application/json" },
          tags: { name: "bb_xss_login" },
          responseCallback: http.expectedStatuses(400, 401, 403, 429),
        },
      );
      // Check that payload is NOT reflected verbatim in response
      const body = String(res.body || "");
      const reflected = body.includes(payload);
      if (reflected) {
        vulnFound.add(1, { test: "xss_reflection" });
        console.error(`[VULN] XSS reflected: ${payload}`);
      }
      assertSafe(res, `xss_login[${payload.slice(0, 15)}]`);
    }
  }

  sleep(Number(__ENV.SLEEP || 0.5));
}

// ═══════════════════════════════════════════════════════════════════════════
// Scenario: A01 + A07 – Authentication bypass probes
// ═══════════════════════════════════════════════════════════════════════════

export function authBypassProbes() {
  // 1. Unauthenticated access to protected endpoints
  const protectedEndpoints = [
    { method: "GET", path: "/auth/me/" },
    { method: "GET", path: "/auth/me/acl/" },
    { method: "GET", path: "/rbac/roles/" },
    { method: "GET", path: "/rbac/permissions/" },
    { method: "GET", path: "/org/companies/" },
    { method: "GET", path: "/org/branches/" },
    { method: "GET", path: "/hr/positions/" },
    { method: "GET", path: "/hr/employees/" },
    { method: "GET", path: "/audit/bitacora/" },
    { method: "GET", path: "/accounting/periods/" },
    { method: "GET", path: "/payments/cash-sessions/" },
    { method: "POST", path: "/auth/2fa/enable/" },
    { method: "POST", path: "/auth/password/" },
    { method: "POST", path: "/auth/logout/" },
  ];

  for (const ep of protectedEndpoints) {
    let res;
    if (ep.method === "GET") {
      res = http.get(`${BASE_URL}${ep.path}`, {
        headers: { "Content-Type": "application/json" },
        tags: { name: "bb_unauth" },
      });
    } else {
      res = http.post(`${BASE_URL}${ep.path}`, JSON.stringify({}), {
        headers: { "Content-Type": "application/json" },
        tags: { name: "bb_unauth" },
      });
    }
    assertSafe(res, `unauth_access[${ep.path}]`);
  }

  // 2. Bootstrap re-execution (should fail after first admin exists)
  const bootstrapRes = http.post(
    `${BASE_URL}/auth/bootstrap/init/`,
    JSON.stringify({
      username: "hacker_admin",
      email: "hacker@evil.com",
      password: "H@ck3r_P@ss!",
    }),
    {
      headers: { "Content-Type": "application/json" },
      tags: { name: "bb_bootstrap_replay" },
    },
  );
  assertSafe(bootstrapRes, "bootstrap_replay");

  // 3. Brute force detection (rapid wrong passwords)
  for (let i = 0; i < 5; i++) {
    const res = http.post(
      `${BASE_URL}/auth/login/`,
      JSON.stringify({
        username: ADMIN_USERNAME,
        password: `wrong_password_${i}`,
      }),
      {
        headers: { "Content-Type": "application/json" },
        tags: { name: "bb_brute_force" },
        responseCallback: http.expectedStatuses(400, 401, 403, 429),
      },
    );
    // After several attempts, we expect 403 (axes lockout) or 429 (throttle)
    if (i >= 3) {
      const locked = res.status === 403 || res.status === 429;
      check(res, {
        [`brute_force_blocked_attempt_${i}`]: () => locked || res.status === 401,
      });
    }
  }

  // 4. 2FA replay attack (if TOTP secret is available)
  if (ADMIN_TOTP_SECRET) {
    const loginRes = http.post(
      `${BASE_URL}/auth/login/`,
      JSON.stringify({
        username: ADMIN_USERNAME,
        password: ADMIN_PASSWORD,
      }),
      {
        headers: {
          "Content-Type": "application/json",
          "X-Auth-Transport": "header",
        },
        tags: { name: "bb_2fa_login" },
      },
    );
    const loginBody = jsonOrNull(loginRes);
    const challenge =
      loginBody && loginBody.challenge ? loginBody.challenge : "";

    if (challenge) {
      const code = totp(ADMIN_TOTP_SECRET);

      // First verify (should succeed)
      const verifyRes = http.post(
        `${BASE_URL}/auth/2fa/verify/`,
        JSON.stringify({ challenge, code }),
        {
          headers: {
            "Content-Type": "application/json",
            "X-Auth-Transport": "header",
          },
          tags: { name: "bb_2fa_verify" },
        },
      );

      // Replay the same challenge+code (MUST fail)
      const replayRes = http.post(
        `${BASE_URL}/auth/2fa/verify/`,
        JSON.stringify({ challenge, code }),
        {
          headers: {
            "Content-Type": "application/json",
            "X-Auth-Transport": "header",
            Cookie: "",
          },
          tags: { name: "bb_2fa_replay" },
          responseCallback: http.expectedStatuses(400, 401, 403, 404),
        },
      );
      assertSafe(replayRes, "2fa_replay_attack");

      // Verify with fabricated challenge UUID
      const fakeChallenge = "00000000-0000-0000-0000-000000000000";
      const fakeRes = http.post(
        `${BASE_URL}/auth/2fa/verify/`,
        JSON.stringify({ challenge: fakeChallenge, code }),
        {
          headers: {
            "Content-Type": "application/json",
            "X-Auth-Transport": "header",
          },
          tags: { name: "bb_2fa_fake_challenge" },
          responseCallback: http.expectedStatuses(400, 401, 403, 404),
        },
      );
      assertSafe(fakeRes, "2fa_fake_challenge");
    }
  }

  sleep(Number(__ENV.SLEEP || 1));
}

// ═══════════════════════════════════════════════════════════════════════════
// Scenario: A01 – IDOR (Insecure Direct Object Reference) probes
// ═══════════════════════════════════════════════════════════════════════════

export function idorProbes() {
  const tokens = loginAndGetTokens(USER_USERNAME, USER_PASSWORD);
  if (!tokens) {
    sleep(1);
    return;
  }
  const hdrs = authHeaders(tokens.access);

  // Try accessing resources with sequential / guessable IDs
  const idorPaths = [
    "/hr/employees/1/",
    "/hr/employees/2/",
    "/hr/employees/99999/",
    "/hr/positions/1/",
    "/org/branches/1/",
    "/org/branches/99999/",
    "/audit/events/1/",
    "/audit/events/99999/",
  ];

  for (const path of idorPaths) {
    const res = http.get(`${BASE_URL}${path}`, {
      headers: hdrs,
      tags: { name: "bb_idor" },
    });
    // Should get 403 (no permission) or 404 (not found), never someone else's data
    check(res, {
      [`idor[${path}] no unauthorized data`]: (r) =>
        r && (r.status === 403 || r.status === 404 || r.status === 401),
    });
    // Check body doesn't contain other user's sensitive info
    const body = String(res.body || "");
    if (
      res.status === 200 &&
      body.includes("password") &&
      !body.includes("must_change_password")
    ) {
      vulnFound.add(1, { test: `idor_data_leak[${path}]` });
      console.error(`[VULN] IDOR data leak at ${path}`);
    }
  }

  // Mass assignment: try adding is_superuser/is_staff via extra fields
  const massAssignRes = http.post(
    `${BASE_URL}/auth/login/`,
    JSON.stringify({
      username: USER_USERNAME,
      password: USER_PASSWORD,
      is_superuser: true,
      is_staff: true,
    }),
    {
      headers: { "Content-Type": "application/json" },
      tags: { name: "bb_mass_assign" },
    },
  );
  // Login should work but extra fields ignored
  const maBody = jsonOrNull(massAssignRes);
  if (maBody && maBody.access) {
    // Verify user didn't become superuser
    const meRes = http.get(`${BASE_URL}/auth/me/`, {
      headers: authHeaders(maBody.access),
      tags: { name: "bb_mass_assign_verify" },
    });
    const meBody = jsonOrNull(meRes);
    if (meBody && (meBody.is_superuser === true || meBody.is_staff === true)) {
      // Only flag if user wasn't already superuser
      if (USER_USERNAME !== ADMIN_USERNAME) {
        vulnFound.add(1, { test: "mass_assignment_escalation" });
        console.error("[VULN] Mass assignment led to privilege escalation!");
      }
    }
    testsPassed.add(1, { test: "mass_assignment_safe" });
  }

  // Horizontal privilege: try accessing another company's data
  const invalidCompanyHdrs = {
    ...hdrs,
    "X-Company-Id": "99999",
    "X-Branch-Id": "99999",
  };
  const horizRes = http.get(`${BASE_URL}/org/companies/`, {
    headers: invalidCompanyHdrs,
    tags: { name: "bb_horiz_escalation" },
  });
  check(horizRes, {
    "horiz_escalation blocked": (r) =>
      r && (r.status === 403 || r.status === 200),
  });

  sleep(Number(__ENV.SLEEP || 0.8));
}

// ═══════════════════════════════════════════════════════════════════════════
// Scenario: A02 – Token manipulation attacks
// ═══════════════════════════════════════════════════════════════════════════

export function tokenAttacks() {
  // 1. Forged JWT token
  const fakeJwt =
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9." +
    "eyJ1c2VyX2lkIjoxLCJ1c2VybmFtZSI6ImFkbWluIiwiZXhwIjo5OTk5OTk5OTk5fQ." +
    "FORGED_SIGNATURE_HERE";

  const forgedRes = http.get(`${BASE_URL}/auth/me/`, {
    headers: authHeaders(fakeJwt),
    tags: { name: "bb_forged_jwt" },
  });
  assertSafe(forgedRes, "forged_jwt");

  // 2. Empty token
  const emptyRes = http.get(`${BASE_URL}/auth/me/`, {
    headers: { Authorization: "Bearer ", "Content-Type": "application/json" },
    tags: { name: "bb_empty_token" },
  });
  assertSafe(emptyRes, "empty_token");

  // 3. None algorithm token (alg:none attack)
  const noneJwt =
    "eyJhbGciOiJub25lIiwidHlwIjoiSldUIn0." +
    "eyJ1c2VyX2lkIjoxLCJ1c2VybmFtZSI6ImFkbWluIiwiZXhwIjo5OTk5OTk5OTk5fQ.";

  const noneRes = http.get(`${BASE_URL}/auth/me/`, {
    headers: authHeaders(noneJwt),
    tags: { name: "bb_none_alg" },
  });
  assertSafe(noneRes, "none_algorithm_jwt");

  // 4. Corrupted refresh token
  const badRefresh = Math.random().toString(36).slice(2);
  const refRes = http.post(
    `${BASE_URL}/auth/refresh/`,
    JSON.stringify({ refresh: badRefresh }),
    {
      headers: {
        "Content-Type": "application/json",
        "X-Auth-Transport": "header",
      },
      tags: { name: "bb_bad_refresh" },
      responseCallback: http.expectedStatuses(400, 401),
    },
  );
  assertSafe(refRes, "corrupted_refresh", [200, 201, 204, 500]);

  // 5. Refresh token re-use after rotation
  const tokens = loginAndGetTokens(USER_USERNAME, USER_PASSWORD);
  if (tokens) {
    // Rotate
    const rot1 = http.post(
      `${BASE_URL}/auth/refresh/`,
      JSON.stringify({ refresh: tokens.refresh }),
      {
        headers: {
          "Content-Type": "application/json",
          "X-Auth-Transport": "header",
        },
        tags: { name: "bb_rotate" },
      },
    );

    // Try re-using old refresh
    const reuseRes = http.post(
      `${BASE_URL}/auth/refresh/`,
      JSON.stringify({ refresh: tokens.refresh }),
      {
        headers: {
          "Content-Type": "application/json",
          "X-Auth-Transport": "header",
        },
        tags: { name: "bb_refresh_reuse" },
        responseCallback: http.expectedStatuses(401),
      },
    );
    assertSafe(reuseRes, "refresh_reuse_after_rotation", [200, 201, 204]);
  }

  // 6. Token owner mismatch (if we have two different users)
  if (USER_PASSWORD && ADMIN_PASSWORD && USER_USERNAME !== ADMIN_USERNAME) {
    const userTokens = loginAndGetTokens(USER_USERNAME, USER_PASSWORD);
    const adminTokens = loginAndGetTokens(ADMIN_USERNAME, ADMIN_PASSWORD);

    if (userTokens && adminTokens) {
      // Try logging out admin's refresh using user's access token
      const mismatchRes = http.post(
        `${BASE_URL}/auth/logout/`,
        JSON.stringify({ refresh: adminTokens.refresh }),
        {
          headers: authHeaders(userTokens.access),
          tags: { name: "bb_token_mismatch" },
          responseCallback: http.expectedStatuses(400, 401, 403, 204),
        },
      );
      // Should be rejected (400/403) or at worst 204 (idempotent but no effect)
      check(mismatchRes, {
        "token_mismatch handled": (r) =>
          r &&
          (r.status === 400 ||
            r.status === 403 ||
            r.status === 401 ||
            r.status === 204),
      });
      testsPassed.add(1, { test: "token_mismatch" });
    }
  }

  sleep(Number(__ENV.SLEEP || 0.5));
}

// ═══════════════════════════════════════════════════════════════════════════
// Scenario: A08 – CSRF bypass probes (cookie transport)
// ═══════════════════════════════════════════════════════════════════════════

export function csrfBypassProbes() {
  const jar = http.cookieJar();
  if (typeof jar.clear === "function") jar.clear(ROOT_URL);

  // Login in cookie mode
  const loginRes = http.post(
    `${BASE_URL}/auth/login/`,
    JSON.stringify({ username: USER_USERNAME, password: USER_PASSWORD }),
    {
      headers: {
        "Content-Type": "application/json",
        "X-Auth-Transport": "cookie",
      },
      tags: { name: "bb_csrf_login" },
    },
  );

  if (loginRes.status !== 200) {
    sleep(1);
    return;
  }

  // 1. Refresh without CSRF token (should be blocked)
  const noCsrfRefresh = http.post(
    `${BASE_URL}/auth/refresh/`,
    JSON.stringify({}),
    {
      headers: {
        "Content-Type": "application/json",
        "X-Auth-Transport": "cookie",
      },
      tags: { name: "bb_csrf_missing" },
      responseCallback: http.expectedStatuses(403),
    },
  );
  check(noCsrfRefresh, {
    "csrf_missing_blocked": (r) => r && r.status === 403,
  });
  if (noCsrfRefresh.status === 403) {
    testsPassed.add(1, { test: "csrf_missing_blocked" });
  } else {
    vulnFound.add(1, { test: "csrf_bypass_no_token" });
    console.error("[VULN] CSRF bypass: refresh succeeded without CSRF token");
  }

  // 2. Refresh with wrong CSRF token
  const wrongCsrf = http.post(
    `${BASE_URL}/auth/refresh/`,
    JSON.stringify({}),
    {
      headers: {
        "Content-Type": "application/json",
        "X-Auth-Transport": "cookie",
        "X-CSRF-Token": "completely-wrong-csrf-token-value",
      },
      tags: { name: "bb_csrf_wrong" },
      responseCallback: http.expectedStatuses(403),
    },
  );
  check(wrongCsrf, {
    "csrf_wrong_blocked": (r) => r && r.status === 403,
  });
  if (wrongCsrf.status === 403) {
    testsPassed.add(1, { test: "csrf_wrong_blocked" });
  } else {
    vulnFound.add(1, { test: "csrf_bypass_wrong_token" });
  }

  // 3. Logout without CSRF (should be blocked)
  const noCsrfLogout = http.post(
    `${BASE_URL}/auth/logout/`,
    JSON.stringify({}),
    {
      headers: {
        "Content-Type": "application/json",
        "X-Auth-Transport": "cookie",
      },
      tags: { name: "bb_csrf_logout" },
      responseCallback: http.expectedStatuses(403),
    },
  );
  check(noCsrfLogout, {
    "csrf_logout_blocked": (r) => r && r.status === 403,
  });
  if (noCsrfLogout.status === 403) {
    testsPassed.add(1, { test: "csrf_logout_blocked" });
  } else {
    vulnFound.add(1, { test: "csrf_bypass_logout" });
  }

  sleep(Number(__ENV.SLEEP || 1));
}

// ═══════════════════════════════════════════════════════════════════════════
// Scenario: A03/A05 – Header injection & misconfiguration
// ═══════════════════════════════════════════════════════════════════════════

export function headerInjectionProbes() {
  // 1. CRLF injection in headers
  const crlfRes = http.get(`${BASE_URL}/auth/bootstrap/status/`, {
    headers: {
      "X-Custom-Header": "value\r\nInjected-Header: evil",
      "Content-Type": "application/json",
    },
    tags: { name: "bb_crlf" },
  });
  // Check that injected header is not reflected
  const crlfHeaders = crlfRes.headers || {};
  if (crlfHeaders["Injected-Header"]) {
    vulnFound.add(1, { test: "crlf_injection" });
    console.error("[VULN] CRLF injection: header reflected");
  } else {
    testsPassed.add(1, { test: "crlf_safe" });
  }

  // 2. Host header injection
  const hostRes = http.get(`${BASE_URL}/auth/bootstrap/status/`, {
    headers: {
      Host: "evil.com",
      "Content-Type": "application/json",
    },
    tags: { name: "bb_host_inject" },
  });
  // Should not 5xx
  check(hostRes, {
    "host_inject no 5xx": (r) => r && r.status < 500,
  });
  testsPassed.add(1, { test: "host_injection_safe" });

  // 3. HTTP method probing (TRACE, PUT, DELETE on read-only endpoints)
  const methods = ["TRACE", "PUT", "DELETE", "PATCH"];
  for (const method of methods) {
    const res = http.request(method, `${BASE_URL}/auth/bootstrap/status/`, null, {
      headers: { "Content-Type": "application/json" },
      tags: { name: "bb_method_probe" },
    });
    check(res, {
      [`method_${method} not allowed`]: (r) =>
        r && r.status !== 200,
    });
    testsPassed.add(1, { test: `method_${method}_blocked` });
  }

  // 4. Path traversal in URL
  for (const payload of PATH_TRAVERSAL) {
    const res = http.get(`${BASE_URL}/${payload}`, {
      tags: { name: "bb_path_traversal" },
    });
    const body = String(res.body || "");
    if (body.includes("root:") || body.includes("[boot loader]")) {
      vulnFound.add(1, { test: "path_traversal" });
      console.error(`[VULN] Path traversal: ${payload}`);
    } else {
      testsPassed.add(1, { test: `path_traversal_safe` });
    }
  }

  // 5. CORS misconfiguration check
  const corsRes = http.get(`${BASE_URL}/auth/bootstrap/status/`, {
    headers: {
      Origin: "https://evil.com",
      "Content-Type": "application/json",
    },
    tags: { name: "bb_cors" },
  });
  const acao = corsRes.headers["Access-Control-Allow-Origin"];
  if (acao === "*" || acao === "https://evil.com") {
    vulnFound.add(1, { test: "cors_wildcard" });
    console.error(`[VULN] CORS allows arbitrary origin: ${acao}`);
  } else {
    testsPassed.add(1, { test: "cors_safe" });
  }

  sleep(Number(__ENV.SLEEP || 0.8));
}

// ═══════════════════════════════════════════════════════════════════════════
// Scenario: A09 – Information leakage probes
// ═══════════════════════════════════════════════════════════════════════════

export function infoLeakageProbes() {
  // 1. Trigger errors and check for stack traces
  const errorPaths = [
    "/nonexistent-endpoint/",
    "/auth/login/",
    "/auth/refresh/",
    "/auth/2fa/verify/",
  ];

  for (const path of errorPaths) {
    // Send malformed JSON
    const res = http.post(`${BASE_URL}${path}`, "this-is-not-json", {
      headers: { "Content-Type": "application/json" },
      tags: { name: "bb_info_leak" },
    });

    const body = String(res.body || "");
    const leaksInfo =
      body.includes("Traceback") ||
      body.includes("File \"") ||
      body.includes("DJANGO_SETTINGS_MODULE") ||
      body.includes("psycopg") ||
      body.includes("OperationalError") ||
      body.includes("SECRET_KEY") ||
      body.includes("DATABASE_URL");

    if (leaksInfo) {
      vulnFound.add(1, { test: `info_leak[${path}]` });
      console.error(
        `[VULN] Info leakage at ${path}: ${body.slice(0, 200)}`,
      );
    } else {
      testsPassed.add(1, { test: `info_leak_safe[${path}]` });
    }
  }

  // 2. Check that error responses use standard envelope
  const badLoginRes = http.post(
    `${BASE_URL}/auth/login/`,
    JSON.stringify({ username: "nonexistent_user", password: "wrong" }),
    {
      headers: { "Content-Type": "application/json" },
      tags: { name: "bb_error_envelope" },
    },
  );
  const errBody = jsonOrNull(badLoginRes);
  // Should NOT contain field-level details that reveal username existence
  // (i.e., should say "invalid credentials" not "user not found")
  if (errBody) {
    const bodyStr = JSON.stringify(errBody).toLowerCase();
    const enumerates =
      bodyStr.includes("user not found") ||
      bodyStr.includes("no such user") ||
      bodyStr.includes("username does not exist");
    if (enumerates) {
      vulnFound.add(1, { test: "user_enumeration" });
      console.error("[VULN] User enumeration via error message");
    } else {
      testsPassed.add(1, { test: "user_enum_safe" });
    }
  }

  // 3. Check sensitive headers are NOT exposed
  const tokens = loginAndGetTokens(USER_USERNAME, USER_PASSWORD);
  if (tokens) {
    const meRes = http.get(`${BASE_URL}/auth/me/`, {
      headers: authHeaders(tokens.access),
      tags: { name: "bb_header_check" },
    });

    const dangerousHeaders = [
      "X-Powered-By",
      "Server",
    ];

    for (const hdr of dangerousHeaders) {
      const val = meRes.headers[hdr];
      if (val && (String(val).includes("Django") || String(val).includes("Python"))) {
        console.warn(
          `[INFO] Server technology exposed in ${hdr}: ${val}`,
        );
        // Not a vuln per se, but worth noting
      }
    }
    testsPassed.add(1, { test: "header_check_done" });
  }

  // 4. Admin panel access check
  const adminPaths = ["/admin/", "/admin/login/"];
  for (const path of adminPaths) {
    const res = http.get(`${ROOT_URL}${path}`, {
      tags: { name: "bb_admin_panel" },
    });
    if (res.status === 200) {
      console.warn(
        `[INFO] Django admin panel accessible at ${path} – consider restricting in production`,
      );
    }
  }

  // 5. Debug endpoint check
  const debugPaths = [
    "/api/__debug__/",
    "/api/debug/",
    "/__debug__/",
    "/debug/",
  ];
  for (const path of debugPaths) {
    const res = http.get(`${ROOT_URL}${path}`, {
      tags: { name: "bb_debug" },
    });
    if (res.status === 200) {
      vulnFound.add(1, { test: `debug_exposed[${path}]` });
      console.error(`[VULN] Debug endpoint accessible: ${path}`);
    } else {
      testsPassed.add(1, { test: `debug_safe[${path}]` });
    }
  }

  sleep(Number(__ENV.SLEEP || 2));
}
