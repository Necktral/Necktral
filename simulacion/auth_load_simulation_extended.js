import http from "k6/http";
import { check, sleep } from "k6";
import crypto from "k6/crypto";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000/api";
const ROOT_URL = BASE_URL.replace(/\/api\/?$/, "");
const DURATION = __ENV.DURATION || "40s";
const TOTAL_VUS = Number(__ENV.VUS || 10);

const ADMIN_USERNAME = __ENV.ADMIN_USERNAME || "k6_admin";
const ADMIN_PASSWORD = __ENV.ADMIN_PASSWORD || "";
const ADMIN_TOTP_SECRET = __ENV.ADMIN_TOTP_SECRET || "";

const USER_USERNAME = __ENV.USER_USERNAME || "k6_user";
const USER_PASSWORD = __ENV.USER_PASSWORD || "";

const CSRF_COOKIE_NAME = __ENV.CSRF_COOKIE_NAME || "nt_csrf";
const ADMIN_2FA_VUS = Number(__ENV.ADMIN_2FA_VUS || 1);
const ADMIN_2FA_SLEEP = Number(__ENV.ADMIN_2FA_SLEEP || 15);

const TRANSPORT_COOKIE = "cookie";
const TRANSPORT_HEADER = "header";

// Helper to check if response clears critical auth cookies
function checkCookiesCleared(res) {
  const setCookies = res.headers["Set-Cookie"];
  if (!setCookies) return false;

  // Normalize to string array (k6 can return string or array)
  const headers = Array.isArray(setCookies) ? setCookies : [setCookies];

  // We check for nt_access and nt_refresh being cleared (Max-Age=0 or Expires in past)
  const targets = ["nt_access", "nt_refresh"];
  const isCleared = (name) =>
    headers.some(
      (h) =>
        h.includes(`${name}=`) &&
        (h.includes("Max-Age=0") || h.includes("Expires=Thu, 01 Jan 1970")),
    );

  return targets.every(isCleared);
}

function share(vus, ratio, minVal) {
  const computed = Math.floor(vus * ratio);
  return Math.max(minVal, computed);
}

export const options = {
  scenarios: {
    cookie_flow: {
      executor: "constant-vus",
      exec: "cookieLoginFlow",
      vus: share(TOTAL_VUS, 0.3, 1),
      duration: DURATION,
    },
    cookie_logout_idempotent: {
      executor: "constant-vus",
      exec: "cookieIdempotentLogoutFlow",
      vus: share(TOTAL_VUS, 0.1, 1),
      duration: DURATION,
    },
    admin_2fa: {
      executor: "constant-vus",
      exec: "adminTwoFaFlow",
      vus: ADMIN_2FA_VUS,
      duration: DURATION,
    },
    refresh_rotation: {
      executor: "constant-vus",
      exec: "refreshRotationFlow",
      vus: share(TOTAL_VUS, 0.2, 1),
      duration: DURATION,
    },
    logout_idempotent: {
      executor: "constant-vus",
      exec: "logoutFlow",
      vus: share(TOTAL_VUS, 0.1, 1),
      duration: DURATION,
    },
    attacks: {
      executor: "constant-vus",
      exec: "attackFlow",
      vus: share(TOTAL_VUS, 0.1, 1),
      duration: DURATION,
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],
    "http_req_duration{scenario:cookie_flow,name:auth_login_cookie}": [
      "p(95)<600",
    ],
    "http_req_duration{scenario:cookie_flow,name:auth_refresh_cookie}": [
      "p(95)<450",
    ],
    "http_req_duration{scenario:cookie_flow,name:auth_logout_cookie}": [
      "p(95)<450",
    ],
    "http_req_duration{scenario:cookie_logout_idempotent,name:auth_logout_cookie_invalid}":
      ["p(95)<450"],
    "http_req_duration{scenario:admin_2fa,name:auth_2fa_verify}": ["p(95)<700"],
    "http_req_duration{scenario:refresh_rotation,name:auth_refresh_header}": [
      "p(95)<400",
    ],
    "http_req_duration{scenario:logout_idempotent,name:auth_logout_header}": [
      "p(95)<400",
    ],
    "http_req_duration{scenario:attacks,name:auth_attack}": ["p(95)<500"],
  },
};

function jsonOrNull(res) {
  try {
    return res && res.json ? res.json() : null;
  } catch (_) {
    return null;
  }
}

function base32ToBytes(input) {
  const clean = String(input || "")
    .replace(/=+$/g, "")
    .toUpperCase()
    .replace(/[^A-Z2-7]/g, "");
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = 0;
  let value = 0;
  const out = [];

  for (let i = 0; i < clean.length; i += 1) {
    const idx = alphabet.indexOf(clean[i]);
    if (idx === -1) {
      continue;
    }
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
  for (let i = 0; i < hex.length; i += 2) {
    out.push(parseInt(hex.slice(i, i + 2), 16));
  }
  return out;
}

function totp(secret, stepSeconds, digits) {
  const step = stepSeconds || 30;
  const otpDigits = digits || 6;
  const keyBytes = base32ToBytes(secret);
  const counter = Math.floor(Date.now() / 1000 / step);
  const msg = new ArrayBuffer(8);
  const view = new DataView(msg);
  view.setUint32(0, 0);
  view.setUint32(4, counter);

  const hmacHex = crypto.hmac("sha1", toArrayBuffer(keyBytes), msg, "hex");
  const hmacBytes = hexToBytes(hmacHex);
  const offset = hmacBytes[hmacBytes.length - 1] & 0x0f;
  const code =
    ((hmacBytes[offset] & 0x7f) << 24) |
    ((hmacBytes[offset + 1] & 0xff) << 16) |
    ((hmacBytes[offset + 2] & 0xff) << 8) |
    (hmacBytes[offset + 3] & 0xff);

  return String(code % 10 ** otpDigits).padStart(otpDigits, "0");
}

function getCookieValue(jar, name) {
  const cookies = jar.cookiesForURL(ROOT_URL);
  const entry = cookies && cookies[name] ? cookies[name] : null;
  if (!entry || !entry.length) {
    return null;
  }
  return entry[0].value;
}

function clearJar(jar) {
  if (typeof jar.clear === "function") {
    jar.clear(ROOT_URL);
  } else if (typeof jar.clearAll === "function") {
    jar.clearAll();
  }
}

function loginCookie(username, password) {
  return http.post(
    `${BASE_URL}/backend/auth/login/`,
    JSON.stringify({ username, password }),
    {
      headers: {
        "Content-Type": "application/json",
        "X-Auth-Transport": TRANSPORT_COOKIE,
      },
      tags: { name: "auth_login_cookie" },
    },
  );
}

function loginHeader(username, password) {
  const res = http.post(
    `${BASE_URL}/backend/auth/login/`,
    JSON.stringify({ username, password }),
    {
      headers: {
        "Content-Type": "application/json",
        "X-Auth-Transport": TRANSPORT_HEADER,
      },
      tags: { name: "auth_login_header" },
    },
  );
  const body = jsonOrNull(res);
  const ok = check(res, {
    "login header 200": (r) => r && r.status === 200,
  });
  if (!ok || !body || !body.access || !body.refresh) {
    return null;
  }
  return { access: body.access, refresh: body.refresh };
}

function refreshHeader(refreshToken) {
  return http.post(
    `${BASE_URL}/backend/auth/refresh/`,
    JSON.stringify({ refresh: refreshToken }),
    {
      headers: {
        "Content-Type": "application/json",
        "X-Auth-Transport": TRANSPORT_HEADER,
      },
      tags: { name: "auth_refresh_header" },
    },
  );
}

function logoutHeader(accessToken, refreshToken) {
  return http.post(
    `${BASE_URL}/backend/auth/logout/`,
    JSON.stringify({ refresh: refreshToken }),
    {
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${accessToken}`,
      },
      tags: { name: "auth_logout_header" },
    },
  );
}

function refreshCookie(csrfToken) {
  return http.post(`${BASE_URL}/backend/auth/refresh/`, JSON.stringify({}), {
    headers: {
      "Content-Type": "application/json",
      "X-Auth-Transport": TRANSPORT_COOKIE,
      "X-CSRF-Token": csrfToken || "",
    },
    tags: { name: "auth_refresh_cookie" },
  });
}

function logoutCookie(csrfToken, tags) {
  return http.post(`${BASE_URL}/backend/auth/logout/`, JSON.stringify({}), {
    headers: {
      "Content-Type": "application/json",
      "X-Auth-Transport": TRANSPORT_COOKIE,
      "X-CSRF-Token": csrfToken || "",
    },
    tags: tags || { name: "auth_logout_cookie" },
  });
}

function verifyTwoFa(challenge, code) {
  return http.post(
    `${BASE_URL}/backend/auth/2fa/verify/`,
    JSON.stringify({ challenge, code }),
    {
      headers: {
        "Content-Type": "application/json",
        "X-Auth-Transport": TRANSPORT_COOKIE,
      },
      tags: { name: "auth_2fa_verify" },
    },
  );
}

export function cookieLoginFlow() {
  const jar = http.cookieJar();
  clearJar(jar);

  const loginRes = loginCookie(USER_USERNAME, USER_PASSWORD);
  check(loginRes, {
    "login cookie 200": (r) => r && r.status === 200,
  });

  const csrfToken = getCookieValue(jar, CSRF_COOKIE_NAME);
  if (!csrfToken) {
    sleep(0.2);
    return;
  }

  const refreshNoCsrf = http.post(
    `${BASE_URL}/backend/auth/refresh/`,
    JSON.stringify({}),
    {
      headers: {
        "Content-Type": "application/json",
        "X-Auth-Transport": TRANSPORT_COOKIE,
      },
      responseCallback: http.expectedStatuses(403),
      tags: { name: "auth_refresh_cookie" },
    },
  );
  check(refreshNoCsrf, {
    "refresh missing csrf 403": (r) => r && r.status === 403,
  });

  const refreshRes = refreshCookie(csrfToken);
  check(refreshRes, {
    "refresh cookie 200": (r) => r && r.status === 200,
  });

  const logoutNoCsrf = http.post(
    `${BASE_URL}/backend/auth/logout/`,
    JSON.stringify({}),
    {
      headers: {
        "Content-Type": "application/json",
        "X-Auth-Transport": TRANSPORT_COOKIE,
      },
      responseCallback: http.expectedStatuses(403),
      tags: { name: "auth_logout_cookie" },
    },
  );
  check(logoutNoCsrf, {
    "logout missing csrf 403": (r) => r && r.status === 403,
  });

  const logoutRes = logoutCookie(csrfToken);
  check(logoutRes, {
    "logout cookie 204": (r) => r && r.status === 204,
    "logout cookie cleared": (r) => checkCookiesCleared(r),
  });

  sleep(ADMIN_2FA_SLEEP);
}

export function cookieIdempotentLogoutFlow() {
  const jar = http.cookieJar();
  clearJar(jar);

  const loginRes = loginCookie(USER_USERNAME, USER_PASSWORD);
  check(loginRes, {
    "login cookie 200": (r) => r && r.status === 200,
  });

  const csrfToken = getCookieValue(jar, CSRF_COOKIE_NAME);
  if (!csrfToken) {
    sleep(0.2);
    return;
  }

  // Corrupt the refresh cookie in the jar to simulate invalid token
  // Note: we can't easily 'modify' a cookie in the jar directly in k6 without overwriting it.
  // We overwrite it with an invalid value.
  jar.set(ROOT_URL, "nt_refresh", "invalid_refresh_token_value", {
    secure: false, // assuming local dev env behaves this way or matches setup
    path: "/",
  });

  const logoutRes = logoutCookie(csrfToken, {
    name: "auth_logout_cookie_invalid",
  });
  check(logoutRes, {
    "logout invalid cookie 204": (r) => r && r.status === 204,
    "logout invalid cookie cleared": (r) => checkCookiesCleared(r),
  });

  sleep(Number(__ENV.SLEEP || 0.2));
}

export function adminTwoFaFlow() {
  if (!ADMIN_TOTP_SECRET) {
    sleep(0.5);
    return;
  }

  const jar = http.cookieJar();
  clearJar(jar);

  const loginRes = loginCookie(ADMIN_USERNAME, ADMIN_PASSWORD);
  check(loginRes, {
    "admin login 202": (r) => r && r.status === 202,
  });

  const body = jsonOrNull(loginRes);
  const challenge = body && body.challenge ? body.challenge : "";
  if (!challenge) {
    sleep(0.2);
    return;
  }

  const code = totp(ADMIN_TOTP_SECRET, 30, 6);
  const verifyRes = verifyTwoFa(challenge, code);
  check(verifyRes, {
    "2fa verify 200": (r) => r && r.status === 200,
  });

  // Replay Attack Test: Try to reuse the same challenge/code
  // We explicitly strip cookies to simulate a replay from a different context/browser/tool
  // and to avoid CSRF 403 failure masking the logic check.
  const replayRes = http.post(
    `${BASE_URL}/backend/auth/2fa/verify/`,
    JSON.stringify({ challenge, code }),
    {
      headers: {
        "Content-Type": "application/json",
        "X-Auth-Transport": TRANSPORT_COOKIE,
        Cookie: "", // Ensure no cookies are sent
      },
      responseCallback: http.expectedStatuses(400),
      tags: { name: "auth_2fa_verify" },
    },
  );
  check(replayRes, {
    "2fa replay rejected": (r) => r && r.status === 400,
  });

  const csrfToken = getCookieValue(jar, CSRF_COOKIE_NAME);
  if (csrfToken) {
    const logoutRes = logoutCookie(csrfToken);
    check(logoutRes, {
      "logout after 2fa 204": (r) => r && r.status === 204,
    });
  }

  sleep(Number(__ENV.SLEEP || 0.2));
}

export function refreshRotationFlow() {
  const tokens = loginHeader(USER_USERNAME, USER_PASSWORD);
  if (!tokens) {
    sleep(0.2);
    return;
  }

  const firstRefresh = tokens.refresh;
  const res1 = refreshHeader(firstRefresh);
  const body1 = jsonOrNull(res1);
  const secondRefresh = body1 && body1.refresh ? body1.refresh : null;

  check(res1, {
    "refresh 1 200": (r) => r && r.status === 200,
  });
  check(res1, {
    "refresh 1 rotated": () =>
      !!secondRefresh && secondRefresh !== firstRefresh,
  });

  const resReuse = http.post(
    `${BASE_URL}/backend/auth/refresh/`,
    JSON.stringify({ refresh: firstRefresh }),
    {
      headers: {
        "Content-Type": "application/json",
        "X-Auth-Transport": TRANSPORT_HEADER,
      },
      responseCallback: http.expectedStatuses(401),
      tags: { name: "auth_refresh_header" },
    },
  );
  check(resReuse, {
    "old refresh rejected": (r) => r && r.status === 401,
  });

  if (secondRefresh) {
    const res2 = refreshHeader(secondRefresh);
    const body2 = jsonOrNull(res2);
    const thirdRefresh = body2 && body2.refresh ? body2.refresh : null;
    check(res2, {
      "refresh 2 200": (r) => r && r.status === 200,
    });
    check(res2, {
      "refresh 2 rotated": () =>
        !!thirdRefresh && thirdRefresh !== secondRefresh,
    });
  }

  sleep(Number(__ENV.SLEEP || 0.2));
}

export function logoutFlow() {
  const tokens = loginHeader(USER_USERNAME, USER_PASSWORD);
  if (!tokens) {
    sleep(0.2);
    return;
  }

  const res1 = logoutHeader(tokens.access, tokens.refresh);
  check(res1, {
    "logout 1 204": (r) => r && r.status === 204,
  });

  const res2 = logoutHeader(tokens.access, tokens.refresh);
  check(res2, {
    "logout 2 idempotent": (r) => r && r.status === 204,
  });

  sleep(Number(__ENV.SLEEP || 0.2));
}

export function attackFlow() {
  const badToken = Math.random().toString(36).slice(2);
  const res = http.post(
    `${BASE_URL}/backend/auth/refresh/`,
    JSON.stringify({ refresh: badToken }),
    {
      headers: {
        "Content-Type": "application/json",
        "X-Auth-Transport": TRANSPORT_HEADER,
      },
      responseCallback: http.expectedStatuses(401),
      tags: { name: "auth_attack" },
    },
  );
  check(res, {
    "corrupt refresh rejected": (r) => r && r.status === 401,
  });

  sleep(0.4);
}
