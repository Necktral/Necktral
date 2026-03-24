#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';

const ROUTE_BUDGET_BYTES = 700 * 1024;
const ANALYTICS_BUDGET_BYTES = 500 * 1024;

const projectRoot = process.cwd();
const assetsDir = path.join(projectRoot, 'dist', 'spa', 'assets');
const reportsDir = path.resolve(process.env.QA_REPORTS_DIR || path.join(projectRoot, '..', 'qa', 'reports'));
const jsonReportPath = path.join(reportsDir, 'frontend_bundle_budget.json');
const mdReportPath = path.join(reportsDir, 'frontend_bundle_budget.md');

function formatSize(bytes) {
  return `${(bytes / 1024).toFixed(2)} KB`;
}

function ensureReportsDir() {
  fs.mkdirSync(reportsDir, { recursive: true });
}

function writeReports(payload) {
  ensureReportsDir();
  fs.writeFileSync(jsonReportPath, `${JSON.stringify(payload, null, 2)}\n`, 'utf-8');

  const markdown = [
    '# Frontend Bundle Budget (Dashboard v3)',
    '',
    `- generated_at: ${payload.generated_at}`,
    `- status: ${payload.status.toUpperCase()}`,
    `- route_budget: ${formatSize(payload.budgets.route_budget_bytes)}`,
    `- analytics_budget: ${formatSize(payload.budgets.analytics_budget_bytes)}`,
    '',
    '## Route chunk',
    '',
    '| chunk | size | budget | status |',
    '|---|---:|---:|---|',
  ];

  if (payload.route_chunk) {
    markdown.push(
      `| ${payload.route_chunk.name} | ${formatSize(payload.route_chunk.size_bytes)} | ${formatSize(payload.route_chunk.budget_bytes)} | ${payload.route_chunk.status} |`,
    );
  } else {
    markdown.push('| - | - | - | FAIL |');
  }

  markdown.push('', '## Analytics chunks', '', '| chunk | size | budget | status |', '|---|---:|---:|---|');
  if (payload.analytics_chunks.length > 0) {
    for (const chunk of payload.analytics_chunks) {
      markdown.push(
        `| ${chunk.name} | ${formatSize(chunk.size_bytes)} | ${formatSize(chunk.budget_bytes)} | ${chunk.status} |`,
      );
    }
  } else {
    markdown.push('| - | - | - | FAIL |');
  }

  if (payload.errors.length > 0) {
    markdown.push('', '## Errors', '');
    for (const error of payload.errors) {
      markdown.push(`- ${error}`);
    }
  }

  fs.writeFileSync(mdReportPath, `${markdown.join('\n')}\n`, 'utf-8');
}

function fail(payload, message) {
  payload.status = 'failed';
  payload.errors.push(String(message));
  writeReports(payload);
  console.error(`[bundle-budget] FAIL: ${message}`);
  process.exit(1);
}

const payload = {
  generated_at: new Date().toISOString(),
  status: 'unknown',
  budgets: {
    route_budget_bytes: ROUTE_BUDGET_BYTES,
    analytics_budget_bytes: ANALYTICS_BUDGET_BYTES,
  },
  route_chunk: null,
  analytics_chunks: [],
  errors: [],
};

if (!fs.existsSync(assetsDir)) {
  fail(payload, `assets directory not found: ${assetsDir}`);
}

const entries = fs.readdirSync(assetsDir, { withFileTypes: true });
const jsFiles = entries
  .filter((entry) => entry.isFile() && entry.name.endsWith('.js'))
  .map((entry) => {
    const fullPath = path.join(assetsDir, entry.name);
    return {
      name: entry.name,
      size: fs.statSync(fullPath).size,
    };
  })
  .sort((a, b) => b.size - a.size);

if (jsFiles.length === 0) {
  fail(payload, 'no JS assets found in dist/spa/assets');
}

const routeCandidates = jsFiles.filter((file) => /dashboardv3page|dashboard-v3-route/i.test(file.name));
if (routeCandidates.length === 0) {
  fail(payload, 'route chunk not found (expected DashboardV3Page* or dashboard-v3-route*)');
}
const routeChunk = routeCandidates[0];
if (!routeChunk) {
  fail(payload, 'route chunk resolution failed');
}
payload.route_chunk = {
  name: routeChunk.name,
  size_bytes: routeChunk.size,
  budget_bytes: ROUTE_BUDGET_BYTES,
  status: routeChunk.size <= ROUTE_BUDGET_BYTES ? 'PASS' : 'FAIL',
};

const echartsChunks = jsFiles.filter((file) => /analytics-echarts/i.test(file.name));
if (echartsChunks.length === 0) {
  fail(payload, 'analytics-echarts chunk not found');
}

const aggridChunks = jsFiles.filter((file) => /analytics-aggrid/i.test(file.name));
if (aggridChunks.length === 0) {
  fail(payload, 'analytics-aggrid chunk not found');
}

const analyticsChunks = [...echartsChunks, ...aggridChunks];
payload.analytics_chunks = analyticsChunks.map((chunk) => ({
  name: chunk.name,
  size_bytes: chunk.size,
  budget_bytes: ANALYTICS_BUDGET_BYTES,
  status: chunk.size <= ANALYTICS_BUDGET_BYTES ? 'PASS' : 'FAIL',
}));

if (routeChunk.size > ROUTE_BUDGET_BYTES) {
  payload.errors.push(
    `route chunk ${routeChunk.name} is ${formatSize(routeChunk.size)} (budget ${formatSize(ROUTE_BUDGET_BYTES)})`,
  );
}
for (const chunk of analyticsChunks) {
  if (chunk.size > ANALYTICS_BUDGET_BYTES) {
    payload.errors.push(
      `analytics chunk ${chunk.name} is ${formatSize(chunk.size)} (budget ${formatSize(ANALYTICS_BUDGET_BYTES)})`,
    );
  }
}

payload.status = payload.errors.length > 0 ? 'failed' : 'passed';
writeReports(payload);

console.log('[bundle-budget] Dashboard v3 budget check');
console.log(`- route chunk: ${routeChunk.name} (${formatSize(routeChunk.size)})`);
for (const chunk of analyticsChunks) {
  console.log(`- analytics chunk: ${chunk.name} (${formatSize(chunk.size)})`);
}
console.log(`- report json: ${jsonReportPath}`);
console.log(`- report md: ${mdReportPath}`);

if (payload.errors.length > 0) {
  for (const error of payload.errors) {
    console.error(`[bundle-budget] ${error}`);
  }
  process.exit(1);
}

console.log('[bundle-budget] PASS');
