import http from "k6/http";
import { check, sleep } from "k6";
import crypto from "k6/crypto";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000/api";
const ROOT_URL = BASE_URL.replace(/\/api\/?$/, "");

const ADMIN_USERNAME = __ENV.ADMIN_USERNAME || "k6_admin";
const ADMIN_PASSWORD = __ENV.ADMIN_PASSWORD || "";
const ADMIN_TOTP_SECRET = __ENV.ADMIN_TOTP_SECRET || "";

const USER_USERNAME = __ENV.USER_USERNAME || "k6_user";
const USER_PASSWORD = __ENV.USER_PASSWORD || "";

const CSRF_COOKIE_NAME = __ENV.CSRF_COOKIE_NAME || "nt_csrf";
const AUTH_TRANSPORT = "cookie";

export const options = {
  scenarios: {
    cookie_2fa_cycle: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        {
          duration: __ENV.WARMUP || "10s",
          target: Number(__ENV.VUS_WARMUP || 2),
        },
        {
          duration: __ENV.SUSTAIN || "30s",
          target: Number(__ENV.VUS_TARGET || 6),
        },
        { duration: __ENV.COOLDOWN || "10s", target: 0 },
      ],
      exec: "twoFaCookieCycle",
    },
    cookie_basic_cycle: {
      executor: "constant-arrival-rate",
      rate: Number(__ENV.BASIC_RATE || 2),
      timeUnit: "1s",
      duration: __ENV.BASIC_DURATION || "40s",
      preAllocatedVUs: Number(__ENV.BASIC_VUS_PREALLOC || 10),
      maxVUs: Number(__ENV.BASIC_VUS_MAX || 30),
      exec: "basicCookieCycle",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.02"],
    "http_req_duration{scenario:cookie_2fa_cycle,name:auth_login_cookie}": [
      "p(95)<900",
    ],
    "http_req_duration{scenario:cookie_2fa_cycle,name:auth_2fa_verify}": [
      "p(95)<900",
    ],
    "http_req_duration{scenario:cookie_2fa_cycle,name:auth_refresh_cookie}": [
      "p(95)<800",
    ],
    "http_req_duration{scenario:cookie_2fa_cycle,name:auth_logout_cookie}": [
      "p(95)<800",
    ],
    "http_req_duration{scenario:cookie_basic_cycle,name:auth_login_cookie}": [
      "p(95)<800",
    ],
    "http_req_duration{scenario:cookie_basic_cycle,name:auth_refresh_cookie}": [
      "p(95)<700",
    ],
    "http_req_duration{scenario:cookie_basic_cycle,name:auth_logout_cookie}": [
      "p(95)<700",
    ],
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

  const otp = String(code % 10 ** otpDigits).padStart(otpDigits, "0");
  return otp;
}

function getCookieValue(jar, name) {
  const cookies = jar.cookiesForURL(ROOT_URL);
  const entry = cookies && cookies[name] ? cookies[name] : null;
  if (!entry || !entry.length) {
    return null;
  }
  return entry[0].value;
}

function loginCookie(username, password) {
  const res = http.post(
    `${BASE_URL}/backend/auth/login/`,
    JSON.stringify({ username, password }),
    {
      headers: {
        "Content-Type": "application/json",
        "X-Auth-Transport": AUTH_TRANSPORT,
      },
      tags: { name: "auth_login_cookie" },
    },
  );
  return res;
}

function verifyTwoFa(challenge, code) {
  const res = http.post(
    `${BASE_URL}/backend/auth/2fa/verify/`,
    JSON.stringify({ challenge, code }),
    {
      headers: {
        "Content-Type": "application/json",
        "X-Auth-Transport": AUTH_TRANSPORT,
      },
      tags: { name: "auth_2fa_verify" },
    },
  );
  return res;
}

function refreshWithCookies(csrfToken) {
  return http.post(`${BASE_URL}/backend/auth/refresh/`, JSON.stringify({}), {
    headers: {
      "Content-Type": "application/json",
      "X-Auth-Transport": AUTH_TRANSPORT,
      "X-CSRF-Token": csrfToken || "",
    },
    tags: { name: "auth_refresh_cookie" },
  });
}

function logoutWithCookies(csrfToken) {
  return http.post(`${BASE_URL}/backend/auth/logout/`, JSON.stringify({}), {
    headers: {
      "Content-Type": "application/json",
      "X-Auth-Transport": AUTH_TRANSPORT,
      "X-CSRF-Token": csrfToken || "",
    },
    tags: { name: "auth_logout_cookie" },
  });
}

export function twoFaCookieCycle() {
  if (!ADMIN_TOTP_SECRET) {
    sleep(0.5);
    return;
  }

  const jar = http.cookieJar();
  if (typeof jar.clear === "function") {
    jar.clear(ROOT_URL);
  } else if (typeof jar.clearAll === "function") {
    jar.clearAll();
  }

  const loginRes = loginCookie(ADMIN_USERNAME, ADMIN_PASSWORD);
  check(loginRes, {
    "login 2fa status 202": (r) => r && r.status === 202,
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
    "2fa verify status 200": (r) => r && r.status === 200,
  });

  const csrfToken = getCookieValue(jar, CSRF_COOKIE_NAME);
  if (!csrfToken) {
    sleep(0.1);
    return;
  }

  const refreshRes = refreshWithCookies(csrfToken);
  check(refreshRes, {
    "refresh status 200": (r) => r && r.status === 200,
  });

  const logoutRes = logoutWithCookies(csrfToken);
  check(logoutRes, {
    "logout status 204": (r) => r && r.status === 204,
  });

  sleep(Number(__ENV.SLEEP || 0.2));
}

export default function () {
  basicCookieCycle();
}

export function basicCookieCycle() {
  const jar = http.cookieJar();
  if (typeof jar.clear === "function") {
    jar.clear(ROOT_URL);
  } else if (typeof jar.clearAll === "function") {
    jar.clearAll();
  }

  const loginRes = loginCookie(USER_USERNAME, USER_PASSWORD);
  check(loginRes, {
    "login status 200": (r) => r && r.status === 200,
  });

  const csrfToken = getCookieValue(jar, CSRF_COOKIE_NAME);
  if (!csrfToken) {
    sleep(0.1);
    return;
  }

  const refreshRes = refreshWithCookies(csrfToken);
  check(refreshRes, {
    "refresh status 200": (r) => r && r.status === 200,
  });

  const logoutRes = logoutWithCookies(csrfToken);
  check(logoutRes, {
    "logout status 204": (r) => r && r.status === 204,
  });

  sleep(Number(__ENV.SLEEP || 0.2));
}
