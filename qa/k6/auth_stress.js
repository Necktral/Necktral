import http from "k6/http";
import { check, sleep } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000/api";
const ROOT_URL = BASE_URL.replace(/\/api\/?$/, "");
const USERNAME = __ENV.USERNAME || "k6";
const PASSWORD = __ENV.PASSWORD || "";
const ACCESS_COOKIE_NAME = __ENV.ACCESS_COOKIE_NAME || "nt_access";
const REFRESH_COOKIE_NAME = __ENV.REFRESH_COOKIE_NAME || "nt_refresh";
const AUTH_FLOW_MODE_RAW = String(__ENV.AUTH_FLOW_MODE || "auto").toLowerCase();
const AUTH_FLOW_MODE =
  AUTH_FLOW_MODE_RAW === "header" || AUTH_FLOW_MODE_RAW === "cookie"
    ? AUTH_FLOW_MODE_RAW
    : "auto";

// Opcional: bootstrap automático si el entorno está "fresh".
const BOOTSTRAP =
  String(__ENV.BOOTSTRAP || "").toLowerCase() === "1" ||
  String(__ENV.BOOTSTRAP || "").toLowerCase() === "true";

const BOOTSTRAP_USERNAME = __ENV.BOOTSTRAP_USERNAME || "root";
const BOOTSTRAP_EMAIL = __ENV.BOOTSTRAP_EMAIL || "root@test.com";
const BOOTSTRAP_PASSWORD = __ENV.BOOTSTRAP_PASSWORD || "";

export const options = {
  // Modelo de carga realista:
  // 1) tráfico normal: /me + /acl (token reutilizado)
  // 2) churn de login: logins por segundo controlados (arrival-rate)
  scenarios: {
    me_acl: {
      executor: "ramping-vus",
      startVUs: 0,
      stages: [
        {
          duration: __ENV.WARMUP || "15s",
          target: Number(__ENV.VUS_WARMUP || 5),
        },
        {
          duration: __ENV.SUSTAIN || "30s",
          target: Number(__ENV.VUS_TARGET || 20),
        },
        { duration: __ENV.COOLDOWN || "10s", target: 0 },
      ],
      exec: "meAclFlow",
    },
    login_churn: {
      executor: "ramping-arrival-rate",
      timeUnit: "1s",
      startRate: Number(__ENV.LOGIN_RATE_START || 1),
      preAllocatedVUs: Number(__ENV.LOGIN_VUS_PREALLOC || 10),
      maxVUs: Number(__ENV.LOGIN_VUS_MAX || 50),
      stages: [
        {
          duration: __ENV.WARMUP || "15s",
          target: Number(__ENV.LOGIN_RATE_WARMUP || 1),
        },
        {
          duration: __ENV.SUSTAIN || "30s",
          target: Number(__ENV.LOGIN_RATE_TARGET || 2),
        },
        { duration: __ENV.COOLDOWN || "10s", target: 0 },
      ],
      exec: "loginOnly",
    },
  },
  thresholds: {
    http_req_failed: ["rate<0.01"],

    // Por endpoint y por escenario (para que el gate sea interpretable).
    "http_req_duration{scenario:me_acl,name:auth_me}": ["p(95)<500"],
    "http_req_duration{scenario:me_acl,name:auth_acl}": ["p(95)<600"],
    "http_req_duration{scenario:login_churn,name:auth_login}": ["p(95)<600"],
  },
};

function jsonOrNull(res) {
  try {
    return res && res.json ? res.json() : null;
  } catch (_) {
    return null;
  }
}

function authTransportHeader() {
  if (AUTH_FLOW_MODE === "header") {
    return { "X-Auth-Transport": "header" };
  }
  if (AUTH_FLOW_MODE === "cookie") {
    return { "X-Auth-Transport": "cookie" };
  }
  return {};
}

function getCookieValue(name) {
  const jar = http.cookieJar();
  const cookies = jar.cookiesForURL(ROOT_URL);
  const entry = cookies && cookies[name] ? cookies[name] : null;
  if (!entry || !entry.length) {
    return null;
  }
  return entry[0].value;
}

function buildAuthHeaders(session) {
  const headers = { ...authTransportHeader() };
  if (session && session.access) {
    headers.Authorization = `Bearer ${session.access}`;
  }
  return headers;
}

function ensureBootstrapped() {
  const statusRes = http.get(`${BASE_URL}/backend/iam/bootstrap/status/`, {
    tags: { name: "auth_bootstrap_status" },
  });
  if (!statusRes || statusRes.status !== 200) {
    return null;
  }

  const statusBody = jsonOrNull(statusRes);
  const isFresh = statusBody ? statusBody.is_fresh : false;
  if (!isFresh) {
    return null;
  }

  const initRes = http.post(
    `${BASE_URL}/backend/iam/bootstrap/init-admin/`,
    JSON.stringify({
      username: BOOTSTRAP_USERNAME,
      email: BOOTSTRAP_EMAIL,
      password: BOOTSTRAP_PASSWORD,
    }),
    {
      headers: { "Content-Type": "application/json" },
      tags: { name: "auth_bootstrap_init" },
    },
  );

  check(initRes, {
    "bootstrap init status 201": (r) => r && r.status === 201,
  });

  return { username: BOOTSTRAP_USERNAME, password: BOOTSTRAP_PASSWORD };
}

function login(username, password) {
  const res = http.post(
    `${BASE_URL}/backend/auth/login/`,
    JSON.stringify({ username, password }),
    {
      headers: {
        "Content-Type": "application/json",
        ...authTransportHeader(),
      },
      tags: { name: "auth_login" },
    },
  );

  const body = jsonOrNull(res);
  const access = body && body.access ? body.access : null;
  const hasCookieSession =
    !!getCookieValue(ACCESS_COOKIE_NAME) || !!getCookieValue(REFRESH_COOKIE_NAME);

  let usable = false;
  if (AUTH_FLOW_MODE === "header") {
    usable = !!access;
  } else if (AUTH_FLOW_MODE === "cookie") {
    usable = hasCookieSession;
  } else {
    usable = !!access || hasCookieSession;
  }

  check(res, {
    "login status 200": (r) => r && r.status === 200,
    "login usable session": () => usable,
  });

  return { access, hasCookieSession, usable };
}

let cachedSession = null;
let cachedAtMs = 0;

function getSession() {
  const now = Date.now();
  const ttlMs = Number(__ENV.TOKEN_TTL_MS || 9 * 60 * 1000); // por defecto ~9 min
  if (cachedSession && cachedSession.usable && now - cachedAtMs < ttlMs) {
    return cachedSession;
  }

  const session = login(USERNAME, PASSWORD);
  if (session && session.usable) {
    cachedSession = session;
    cachedAtMs = now;
  } else {
    cachedSession = null;
  }
  return session;
}

export function setup() {
  if (!BOOTSTRAP) {
    return null;
  }
  return ensureBootstrapped();
}

export function loginOnly() {
  const session = login(USERNAME, PASSWORD);
  if (!session || !session.usable) {
    sleep(0.1);
  }
}

export function meAclFlow() {
  const session = getSession();
  if (!session || !session.usable) {
    sleep(0.2);
    return;
  }

  const authHeaders = buildAuthHeaders(session);

  const me = http.get(`${BASE_URL}/backend/auth/me/`, {
    headers: authHeaders,
    tags: { name: "auth_me" },
  });
  const meOk = check(me, { "me status 200": (r) => r && r.status === 200 });

  const acl = http.get(`${BASE_URL}/backend/auth/me/acl/`, {
    headers: authHeaders,
    tags: { name: "auth_acl" },
  });
  const aclOk = check(acl, { "acl status 200": (r) => r && r.status === 200 });

  if (!meOk || !aclOk) {
    cachedSession = null;
    cachedAtMs = 0;
  }

  sleep(Number(__ENV.SLEEP || 0.1));
}
