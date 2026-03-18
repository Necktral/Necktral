import http from "k6/http";
import { check, sleep } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000/api";
const ROOT_URL = BASE_URL.replace(/\/api\/?$/, "");
const USERNAME = __ENV.USERNAME || "admin";
const PASSWORD = __ENV.PASSWORD || "admin";
const BOOTSTRAP =
  String(__ENV.BOOTSTRAP || "").toLowerCase() === "1" ||
  String(__ENV.BOOTSTRAP || "").toLowerCase() === "true";

const BOOTSTRAP_USERNAME = __ENV.BOOTSTRAP_USERNAME || "root";
const BOOTSTRAP_EMAIL = __ENV.BOOTSTRAP_EMAIL || "root@test.com";
const BOOTSTRAP_PASSWORD = __ENV.BOOTSTRAP_PASSWORD || "";
const ACCESS_COOKIE_NAME = __ENV.ACCESS_COOKIE_NAME || "nt_access";
const REFRESH_COOKIE_NAME = __ENV.REFRESH_COOKIE_NAME || "nt_refresh";
const CSRF_COOKIE_NAME = __ENV.CSRF_COOKIE_NAME || "nt_csrf";
const AUTH_FLOW_MODE_RAW = String(__ENV.AUTH_FLOW_MODE || "auto").toLowerCase();
const AUTH_FLOW_MODE =
  AUTH_FLOW_MODE_RAW === "header" || AUTH_FLOW_MODE_RAW === "cookie"
    ? AUTH_FLOW_MODE_RAW
    : "auto";

export const options = {
  vus: Number(__ENV.VUS || 5),
  duration: __ENV.DURATION || "30s",
  thresholds: {
    http_req_failed: ["rate<0.01"],
    http_req_duration: ["p(95)<800"],
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

function buildAuthHeaders(session, { method = "GET", json = false } = {}) {
  const headers = { ...authTransportHeader() };
  if (session && session.access) {
    headers.Authorization = `Bearer ${session.access}`;
  }
  if (json) {
    headers["Content-Type"] = "application/json";
  }

  const upperMethod = String(method).toUpperCase();
  const mutating =
    upperMethod !== "GET" &&
    upperMethod !== "HEAD" &&
    upperMethod !== "OPTIONS" &&
    upperMethod !== "TRACE";
  if (mutating && session && !session.access && session.csrfToken) {
    headers["X-CSRF-Token"] = session.csrfToken;
  }

  return headers;
}

function ensureBootstrapped() {
  const statusRes = http.get(`${BASE_URL}/backend/iam/bootstrap/status/`);
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
    { headers: { "Content-Type": "application/json" } },
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
    },
  );

  const body = jsonOrNull(res);
  const access = body && body.access ? body.access : null;
  const hasCookieSession =
    !!getCookieValue(ACCESS_COOKIE_NAME) || !!getCookieValue(REFRESH_COOKIE_NAME);
  const csrfToken = getCookieValue(CSRF_COOKIE_NAME);

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

  if ((!res || res.status !== 200 || !usable) && __VU === 1 && __ITER === 0) {
    const bodyPreview =
      res && res.body ? String(res.body).slice(0, 500) : "<no-body>";
    // eslint-disable-next-line no-console
    console.error(
      `login unusable: mode=${AUTH_FLOW_MODE} status=${res ? res.status : "<no-res>"} body=${bodyPreview}`,
    );
  }

  return { access, hasCookieSession, csrfToken, usable };
}

export function setup() {
  if (!BOOTSTRAP) {
    return null;
  }

  const creds = ensureBootstrapped();
  if (!creds) {
    return null;
  }

  // Si el sistema estaba fresh, cerramos el circuito con bootstrap org.
  sleep(0.1);
  const session = login(creds.username, creds.password);
  if (!session || !session.usable) {
    return creds;
  }

  const orgRes = http.post(
    `${BASE_URL}/backend/org/bootstrap/organization/`,
    JSON.stringify({
      holding_name: __ENV.HOLDING_NAME || "HOLDING",
      company_name: __ENV.COMPANY_NAME || "ACME",
      company_tax_id: __ENV.COMPANY_TAX_ID || "J-123",
      branch_name: __ENV.BRANCH_NAME || "ACME-1",
      branch_address: __ENV.BRANCH_ADDRESS || "Main street",
    }),
    { headers: buildAuthHeaders(session, { method: "POST", json: true }) },
  );
  // Puede ser 200 (creado) o 400/409 si ya existe; no bloqueamos el smoke por esto.
  check(orgRes, {
    "bootstrap org status 200/400/409": (r) =>
      r && (r.status === 200 || r.status === 400 || r.status === 409),
  });

  return creds;
}

export default function (data) {
  const username = data && data.username ? data.username : USERNAME;
  const password = data && data.password ? data.password : PASSWORD;

  const session = login(username, password);
  if (!session || !session.usable) {
    sleep(0.2);
    return;
  }
  const authHeaders = buildAuthHeaders(session, { method: "GET" });

  const me = http.get(`${BASE_URL}/backend/auth/me/`, { headers: authHeaders });
  check(me, { "me status 200": (r) => r.status === 200 });

  const acl = http.get(`${BASE_URL}/backend/auth/me/acl/`, { headers: authHeaders });
  check(acl, { "acl status 200": (r) => r.status === 200 });

  // Si el ACL trae recomendación de contexto, validamos un endpoint que requiere contexto.
  const aclBody = jsonOrNull(acl);
  const recommendedCompanyId = aclBody ? aclBody.recommended_company_id : null;
  if (recommendedCompanyId) {
    const withCtx = {
      headers: {
        ...authHeaders,
        "X-Company-Id": String(recommendedCompanyId),
      },
    };
    const org = http.get(`${BASE_URL}/backend/org/companies/`, withCtx);
    check(org, {
      "org companies status 200/403": (r) =>
        r.status === 200 || r.status === 403,
    });
  }

  sleep(0.2);
}
