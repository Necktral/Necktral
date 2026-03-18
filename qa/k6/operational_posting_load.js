import http from "k6/http";
import { check, fail, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000/api";
const USERNAME = __ENV.USERNAME || "k6_operational";
const PASSWORD = __ENV.PASSWORD || "";
const AUTH_TRANSPORT = (__ENV.AUTH_TRANSPORT || "header").toLowerCase() === "cookie" ? "cookie" : "header";

const COMPANY_ID = Number(__ENV.COMPANY_ID || 0);
const BRANCH_ID = Number(__ENV.BRANCH_ID || 0);

const WAREHOUSE_ID_ENV = Number(__ENV.WAREHOUSE_ID || 0);
const ITEM_ID_ENV = Number(__ENV.ITEM_ID || 0);
const UNIT_COST = Number(__ENV.UNIT_COST || 2.5);
const POSTING_LIMIT = Number(__ENV.POSTING_LIMIT || 100);

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

function commonHeaders(token) {
  return {
    Authorization: `Bearer ${token}`,
    "X-Company-Id": String(COMPANY_ID),
    "X-Branch-Id": String(BRANCH_ID),
  };
}

function recordOutcome(res, { name, flow, okStatuses }) {
  const ok = okStatuses.includes(res.status);
  operationalErrorRate.add(!ok, { flow });
  check(res, {
    [`${name} status valid`]: () => ok,
  });
  if (!ok) {
    console.error(`${name} status=${res.status} body=${res.body ? String(res.body).slice(0, 350) : ""}`);
  }
  return ok;
}

function login() {
  const loginRes = http.post(
    `${BASE_URL}/backend/auth/login/`,
    JSON.stringify({ username: USERNAME, password: PASSWORD }),
    {
      headers: {
        "Content-Type": "application/json",
        "X-Auth-Transport": AUTH_TRANSPORT,
      },
      tags: { name: "auth_login", flow: "auth" },
    },
  );
  const body = toJson(loginRes) || {};
  const token = body.access || "";
  const ok = recordOutcome(loginRes, {
    name: "auth_login",
    flow: "auth",
    okStatuses: [200],
  });
  if (!ok) {
    fail("No fue posible autenticarse para la suite operacional (verifica usuario/password y 2FA deshabilitado).");
  }
  if (!token) {
    fail(
      `Login devolvio 200 sin access token (AUTH_TRANSPORT=${AUTH_TRANSPORT}). ` +
        "Verifica AUTH_TOKEN_TRANSPORT en backend y AUTH_ALLOW_TRANSPORT_OVERRIDE=1.",
    );
  }
  return token;
}

function postJson(path, token, payload, tags = {}) {
  const res = http.post(`${BASE_URL}${path}`, JSON.stringify(payload), {
    headers: {
      ...commonHeaders(token),
      "Content-Type": "application/json",
    },
    tags,
  });
  return res;
}

function ensureWarehouse(token) {
  if (WAREHOUSE_ID_ENV > 0) {
    return WAREHOUSE_ID_ENV;
  }
  const code = `K6WH${Date.now().toString().slice(-6)}`;
  const res = postJson(
    "/inventory/warehouses/",
    token,
    {
      name: `K6 Warehouse ${code}`,
      code,
    },
    { name: "inventory_warehouse_create", flow: "inventory_setup" },
  );
  if (!recordOutcome(res, { name: "inventory_warehouse_create", flow: "inventory_setup", okStatuses: [201] })) {
    fail("No fue posible crear warehouse para carga operacional.");
  }
  const body = toJson(res) || {};
  const warehouseId = Number(body.id || 0);
  if (!warehouseId) {
    fail("Respuesta inválida al crear warehouse (sin id).");
  }
  return warehouseId;
}

function ensureItem(token) {
  if (ITEM_ID_ENV > 0) {
    return ITEM_ID_ENV;
  }
  const sku = `K6SKU-${Date.now().toString().slice(-8)}`;
  const res = postJson(
    "/inventory/items/",
    token,
    {
      sku,
      name: `K6 Item ${sku}`,
      uom: "UNIT",
    },
    { name: "inventory_item_create", flow: "inventory_setup" },
  );
  if (!recordOutcome(res, { name: "inventory_item_create", flow: "inventory_setup", okStatuses: [201] })) {
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
  if (AUTH_TRANSPORT !== "header") {
    fail(
      `operational_posting_load.js requiere AUTH_TRANSPORT=header (actual=${AUTH_TRANSPORT}). ` +
        "Este perfil usa access token en body + Authorization Bearer para carga operacional.",
    );
  }
  if (!PASSWORD) {
    fail("PASSWORD es requerido.");
  }
  if (COMPANY_ID <= 0 || BRANCH_ID <= 0) {
    fail("COMPANY_ID y BRANCH_ID son requeridos.");
  }

  const token = login();
  const warehouseId = ensureWarehouse(token);
  const itemId = ensureItem(token);

  const seedReceive = postJson(
    "/inventory/movements/receive/",
    token,
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
    token,
    warehouseId,
    itemId,
  };
}

export function billingIssueVoidFlow(data) {
  const token = data.token;
  const createRes = postJson(
    "/billing/docs/",
    token,
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
  if (!recordOutcome(createRes, { name: "billing_doc_create", flow: "billing", okStatuses: [201] })) {
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

  const issueRes = postJson(
    `/billing/docs/${docId}/issue/`,
    token,
    {
      apply_inventory: false,
      print_after_issue: false,
      idempotency_key: randomId("billing-issue"),
    },
    { name: "billing_doc_issue", flow: "billing" },
  );
  billingWriteMs.add(issueRes.timings.duration);
  if (!recordOutcome(issueRes, { name: "billing_doc_issue", flow: "billing", okStatuses: [200] })) {
    sleep(0.1);
    return;
  }

  const voidRes = postJson(
    `/billing/docs/${docId}/void/`,
    token,
    { reason: "K6 load void" },
    { name: "billing_doc_void", flow: "billing" },
  );
  billingWriteMs.add(voidRes.timings.duration);
  recordOutcome(voidRes, { name: "billing_doc_void", flow: "billing", okStatuses: [200] });
  sleep(Number(__ENV.SLEEP || 0.05));
}

export function inventoryReceiveIssueFlow(data) {
  const token = data.token;
  const receiveRes = postJson(
    "/inventory/movements/receive/",
    token,
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
  if (!recordOutcome(receiveRes, { name: "inventory_receive", flow: "inventory", okStatuses: [201] })) {
    sleep(0.1);
    return;
  }

  const issueRes = postJson(
    "/inventory/movements/issue/",
    token,
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
  recordOutcome(issueRes, { name: "inventory_issue", flow: "inventory", okStatuses: [201] });
  sleep(Number(__ENV.SLEEP || 0.05));
}

export function postingCycleFlow(data) {
  const token = data.token;
  const approveRes = postJson(
    "/accounting/journal-drafts/approve/",
    token,
    {
      run_id: "",
      limit: POSTING_LIMIT,
      require_passed_validation: true,
      strict: false,
    },
    { name: "accounting_draft_approve", flow: "posting" },
  );
  postingCycleMs.add(approveRes.timings.duration);
  if (!recordOutcome(approveRes, { name: "accounting_draft_approve", flow: "posting", okStatuses: [200] })) {
    sleep(0.1);
    return;
  }

  const postRes = postJson(
    "/accounting/journal-drafts/post/",
    token,
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
  recordOutcome(postRes, { name: "accounting_draft_post", flow: "posting", okStatuses: [200] });
  sleep(Number(__ENV.SLEEP || 0.15));
}
