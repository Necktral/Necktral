import http from "k6/http";
import { check, fail, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000/api";
const USERNAME = __ENV.USERNAME || "k6_operational";
const PASSWORD = __ENV.PASSWORD || "";
const REQUESTED_AUTH_TRANSPORT =
  (__ENV.AUTH_TRANSPORT || "header").toLowerCase() === "cookie"
    ? "cookie"
    : "header";

const COMPANY_ID = Number(__ENV.COMPANY_ID || 0);
const BRANCH_ID = Number(__ENV.BRANCH_ID || 0);

const WAREHOUSE_ID_ENV = Number(__ENV.WAREHOUSE_ID || 0);
const ITEM_ID_ENV = Number(__ENV.ITEM_ID || 0);
const UNIT_COST = Number(__ENV.UNIT_COST || 2.5);
const POSTING_LIMIT = Number(__ENV.POSTING_LIMIT || 100);
const LOGIN_MAX_RETRIES = Number(__ENV.LOGIN_MAX_RETRIES || 6);
const LOGIN_BASE_BACKOFF = Number(__ENV.LOGIN_BASE_BACKOFF || 0.5);
const LOGIN_MAX_BACKOFF = Number(__ENV.LOGIN_MAX_BACKOFF || 4);

const billingWriteMs = new Trend("billing_write_ms", true);
const inventoryWriteMs = new Trend("inventory_write_ms", true);
const postingCycleMs = new Trend("posting_cycle_ms", true);
const operationalErrorRate = new Rate("operational_error_rate");

export const options = {
  scenarios: {
    billing_issue_void: {
      executor: "constant-vus",
      vus: Number(__ENV.BILLING_VUS || 6),
      duration: __ENV.DURATION || "2m",
      exec: "billingIssueVoidFlow",
    },
    inventory_receive_issue: {
      executor: "constant-vus",
      vus: Number(__ENV.INVENTORY_VUS || 6),
      duration: __ENV.DURATION || "2m",
      exec: "inventoryReceiveIssueFlow",
    },
    accounting_posting_cycle: {
      executor: "constant-vus",
      vus: Number(__ENV.POSTING_VUS || 1),
      duration: __ENV.DURATION || "2m",
      exec: "postingCycleFlow",
    },
  },
  thresholds: {
    operational_error_rate: ["rate<0.01"],
    billing_write_ms: ["p(95)<400"],
    inventory_write_ms: ["p(95)<400"],
    posting_cycle_ms: ["p(95)<400"],
  },
};

function randomId(prefix) {
  const vu = typeof __VU !== "undefined" ? __VU : 0;
  const iter = typeof __ITER !== "undefined" ? __ITER : 0;
  return `${prefix}-${vu}-${iter}-${Date.now()}-${Math.floor(Math.random() * 100000)}`;
}

function toJson(res) {
  try {
    return res.json();
  } catch (_) {
    return null;
  }
}

function readCookieValue(name) {
  const jar = http.cookieJar();
  const cookies = jar.cookiesForURL(BASE_URL) || {};
  const raw = cookies[name];
  if (Array.isArray(raw)) {
    return raw[0] || "";
  }
  if (typeof raw === "string") {
    return raw;
  }
  return "";
}

function resolveCsrfToken() {
  return readCookieValue("nt_csrf");
}

function commonHeaders(state) {
  const headers = {
    "X-Company-Id": String(COMPANY_ID),
    "X-Branch-Id": String(BRANCH_ID),
  };
  if (state.authTransport === "header") {
    headers.Authorization = `Bearer ${state.token}`;
    return headers;
  }
  const csrf = resolveCsrfToken() || state.csrf || "";
  if (csrf) {
    headers["X-CSRF-Token"] = csrf;
    headers["X-CSRFToken"] = csrf;
    state.csrf = csrf;
  }
  return headers;
}

function recordOutcome(res, { name, flow, okStatuses }) {
  const ok = okStatuses.includes(res.status);
  operationalErrorRate.add(!ok, { flow });
  check(res, {
    [`${name} status valid`]: () => ok,
  });
  if (!ok) {
    console.error(
      `${name} status=${res.status} body=${res.body ? String(res.body).slice(0, 350) : ""}`,
    );
  }
  return ok;
}

function login(state) {
  let lastRes = null;
  if (!state.loginJitterApplied) {
    const vu = typeof __VU !== "undefined" ? __VU : 1;
    const jitter = Math.random() * 0.2 + Math.min((vu - 1) * 0.05, 0.5);
    sleep(jitter);
    state.loginJitterApplied = true;
  }

  for (let attempt = 0; attempt < LOGIN_MAX_RETRIES; attempt += 1) {
    const loginRes = http.post(
      `${BASE_URL}/backend/auth/login/`,
      JSON.stringify({ username: USERNAME, password: PASSWORD }),
      {
        headers: {
          "Content-Type": "application/json",
          "X-Auth-Transport": REQUESTED_AUTH_TRANSPORT,
        },
        tags: { name: "auth_login", flow: "auth" },
      },
    );
    lastRes = loginRes;
    const body = toJson(loginRes) || {};
    const token = body.access || "";

    if (loginRes.status === 200) {
      const csrf = resolveCsrfToken();
      if (token) {
        state.authTransport = "header";
        state.token = token;
        state.csrf = csrf;
        return state;
      }
      if (csrf) {
        state.authTransport = "cookie";
        state.token = "";
        state.csrf = csrf;
        return state;
      }
      fail(
        `Login devolvio 200 sin token ni cookie CSRF utilizable. requested_transport=${REQUESTED_AUTH_TRANSPORT}.`,
      );
    }

    if (loginRes.status === 429 && attempt < LOGIN_MAX_RETRIES - 1) {
      const backoff = Math.min(
        LOGIN_MAX_BACKOFF,
        LOGIN_BASE_BACKOFF * Math.pow(2, attempt),
      );
      sleep(backoff + Math.random() * 0.35);
      continue;
    }
    console.error(
      `auth_login status=${loginRes.status} body=${loginRes.body ? String(loginRes.body).slice(0, 350) : ""}`,
    );
    fail(
      "No fue posible autenticarse para la suite operacional (verifica usuario/password, 2FA y throttling).",
    );
  }

  if (lastRes) {
    console.error(
      `auth_login status=${lastRes.status} body=${lastRes.body ? String(lastRes.body).slice(0, 350) : ""}`,
    );
  }
  fail("Login no disponible tras reintentos.");
  return state;
}

function refreshCookieSession(state) {
  if (state.authTransport !== "cookie") {
    return false;
  }
  for (let attempt = 0; attempt < 2; attempt += 1) {
    const csrf = resolveCsrfToken() || state.csrf || "";
    const res = http.post(
      `${BASE_URL}/backend/auth/refresh/`,
      JSON.stringify({}),
      {
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrf,
          "X-CSRFToken": csrf,
        },
        tags: { name: "auth_refresh", flow: "auth" },
      },
    );
    if (res.status === 200) {
      const nextCsrf = resolveCsrfToken();
      if (nextCsrf) {
        state.csrf = nextCsrf;
      }
      return true;
    }
    if (res.status === 429 && attempt < 1) {
      sleep(1);
      continue;
    }
    break;
  }
  return false;
}

function ensureAuthenticated(state) {
  if (state.authTransport === "header" && state.token) {
    return;
  }
  if (state.authTransport === "cookie") {
    if (state.csrf) {
      return;
    }
    const csrf = resolveCsrfToken();
    if (csrf) {
      state.csrf = csrf;
      return;
    }
  }
  login(state);
}

function postJson(path, state, payload, tags = {}) {
  const res = http.post(`${BASE_URL}${path}`, JSON.stringify(payload), {
    headers: {
      ...commonHeaders(state),
      "Content-Type": "application/json",
    },
    tags,
  });
  return res;
}

function postJsonWithRefresh(path, state, payload, tags = {}) {
  ensureAuthenticated(state);
  let res = postJson(path, state, payload, tags);
  const body = toJson(res) || {};
  const errCode = ((body.error || {}).code || "").toUpperCase();
  const needsRefresh =
    res.status === 401 ||
    (state.authTransport === "cookie" &&
      res.status === 403 &&
      errCode === "AUTH_CSRF_FAILED");
  if (needsRefresh) {
    if (state.authTransport === "cookie" && refreshCookieSession(state)) {
      res = postJson(path, state, payload, tags);
      return res;
    }
    login(state);
    res = postJson(path, state, payload, tags);
  }
  return res;
}

function ensureWarehouse(state) {
  if (WAREHOUSE_ID_ENV > 0) {
    return WAREHOUSE_ID_ENV;
  }
  const code = `K6WH${Date.now().toString().slice(-6)}`;
  const res = postJson(
    "/inventory/warehouses/",
    state,
    {
      name: `K6 Warehouse ${code}`,
      code,
    },
    { name: "inventory_warehouse_create", flow: "inventory_setup" },
  );
  if (
    !recordOutcome(res, {
      name: "inventory_warehouse_create",
      flow: "inventory_setup",
      okStatuses: [201],
    })
  ) {
    fail("No fue posible crear warehouse para carga operacional.");
  }
  const body = toJson(res) || {};
  const warehouseId = Number(body.id || 0);
  if (!warehouseId) {
    fail("Respuesta inválida al crear warehouse (sin id).");
  }
  return warehouseId;
}

function ensureItem(state) {
  if (ITEM_ID_ENV > 0) {
    return ITEM_ID_ENV;
  }
  const sku = `K6SKU-${Date.now().toString().slice(-8)}`;
  const res = postJson(
    "/inventory/items/",
    state,
    {
      sku,
      name: `K6 Item ${sku}`,
      uom: "UNIT",
    },
    { name: "inventory_item_create", flow: "inventory_setup" },
  );
  if (
    !recordOutcome(res, {
      name: "inventory_item_create",
      flow: "inventory_setup",
      okStatuses: [201],
    })
  ) {
    fail("No fue posible crear item para carga operacional.");
  }
  const body = toJson(res) || {};
  const itemId = Number(body.id || 0);
  if (!itemId) {
    fail("Respuesta inválida al crear item (sin id).");
  }
  return itemId;
}

export function setup() {
  if (!PASSWORD) {
    fail("PASSWORD es requerido.");
  }
  if (COMPANY_ID <= 0 || BRANCH_ID <= 0) {
    fail("COMPANY_ID y BRANCH_ID son requeridos.");
  }

  const state = { authTransport: REQUESTED_AUTH_TRANSPORT, token: "", csrf: "" };
  login(state);
  const warehouseId = ensureWarehouse(state);
  const itemId = ensureItem(state);

  const seedReceive = postJson(
    "/inventory/movements/receive/",
    state,
    {
      warehouse_id: warehouseId,
      item_id: itemId,
      qty: "2000.0000",
      unit_cost: String(UNIT_COST.toFixed(6)),
      idempotency_key: randomId("k6-seed"),
      note: "K6 seed stock",
    },
    { name: "inventory_seed_receive", flow: "inventory_setup" },
  );
  recordOutcome(seedReceive, {
    name: "inventory_seed_receive",
    flow: "inventory_setup",
    okStatuses: [201],
  });

  return {
    authTransport: state.authTransport,
    // VUs no comparten cookie jar con setup(); forzamos bootstrap auth por VU.
    token: state.authTransport === "header" ? state.token : "",
    csrf: "",
    warehouseId,
    itemId,
  };
}

export function billingIssueVoidFlow(data) {
  const createRes = postJsonWithRefresh(
    "/billing/docs/",
    data,
    {
      doc_type: "INVOICE",
      series: "K6",
      currency: "NIO",
      customer_name: "K6 Customer",
      customer_ref: randomId("customer"),
      is_fiscal: false,
      idempotency_key: randomId("billing-draft"),
      lines: [
        {
          description: "Carga operacional",
          quantity: "1",
          unit_price: "120.000000",
          tax_rate: "0.15",
        },
      ],
    },
    { name: "billing_doc_create", flow: "billing" },
  );
  billingWriteMs.add(createRes.timings.duration);
  if (
    !recordOutcome(createRes, {
      name: "billing_doc_create",
      flow: "billing",
      okStatuses: [201],
    })
  ) {
    sleep(0.1);
    return;
  }
  const createBody = toJson(createRes) || {};
  const docId = Number(createBody.id || 0);
  if (!docId) {
    operationalErrorRate.add(true, { flow: "billing" });
    sleep(0.1);
    return;
  }

  const issueRes = postJsonWithRefresh(
    `/billing/docs/${docId}/issue/`,
    data,
    {
      apply_inventory: false,
      print_after_issue: false,
      idempotency_key: randomId("billing-issue"),
    },
    { name: "billing_doc_issue", flow: "billing" },
  );
  billingWriteMs.add(issueRes.timings.duration);
  if (
    !recordOutcome(issueRes, {
      name: "billing_doc_issue",
      flow: "billing",
      okStatuses: [200],
    })
  ) {
    sleep(0.1);
    return;
  }

  const voidRes = postJsonWithRefresh(
    `/billing/docs/${docId}/void/`,
    data,
    { reason: "K6 load void" },
    { name: "billing_doc_void", flow: "billing" },
  );
  billingWriteMs.add(voidRes.timings.duration);
  recordOutcome(voidRes, {
    name: "billing_doc_void",
    flow: "billing",
    okStatuses: [200],
  });
  sleep(Number(__ENV.SLEEP || 0.05));
}

export function inventoryReceiveIssueFlow(data) {
  const receiveRes = postJsonWithRefresh(
    "/inventory/movements/receive/",
    data,
    {
      warehouse_id: data.warehouseId,
      item_id: data.itemId,
      qty: "5.0000",
      unit_cost: String(UNIT_COST.toFixed(6)),
      idempotency_key: randomId("inventory-receive"),
      note: "K6 receive",
    },
    { name: "inventory_receive", flow: "inventory" },
  );
  inventoryWriteMs.add(receiveRes.timings.duration);
  if (
    !recordOutcome(receiveRes, {
      name: "inventory_receive",
      flow: "inventory",
      okStatuses: [201],
    })
  ) {
    sleep(0.1);
    return;
  }

  const issueRes = postJsonWithRefresh(
    "/inventory/movements/issue/",
    data,
    {
      warehouse_id: data.warehouseId,
      item_id: data.itemId,
      qty: "2.0000",
      allow_negative: false,
      idempotency_key: randomId("inventory-issue"),
      note: "K6 issue",
    },
    { name: "inventory_issue", flow: "inventory" },
  );
  inventoryWriteMs.add(issueRes.timings.duration);
  recordOutcome(issueRes, {
    name: "inventory_issue",
    flow: "inventory",
    okStatuses: [201],
  });
  sleep(Number(__ENV.SLEEP || 0.05));
}

export function postingCycleFlow(data) {
  const approveRes = postJsonWithRefresh(
    "/accounting/journal-drafts/approve/",
    data,
    {
      run_id: "",
      limit: POSTING_LIMIT,
      require_passed_validation: true,
      strict: false,
    },
    { name: "accounting_draft_approve", flow: "posting" },
  );
  postingCycleMs.add(approveRes.timings.duration);
  if (
    !recordOutcome(approveRes, {
      name: "accounting_draft_approve",
      flow: "posting",
      okStatuses: [200],
    })
  ) {
    sleep(0.1);
    return;
  }

  const postRes = postJsonWithRefresh(
    "/accounting/journal-drafts/post/",
    data,
    {
      run_id: "",
      limit: POSTING_LIMIT,
      require_approved: true,
      auto_approve: false,
      strict: false,
    },
    { name: "accounting_draft_post", flow: "posting" },
  );
  postingCycleMs.add(postRes.timings.duration);
  recordOutcome(postRes, {
    name: "accounting_draft_post",
    flow: "posting",
    okStatuses: [200],
  });
  sleep(Number(__ENV.SLEEP || 0.15));
}
