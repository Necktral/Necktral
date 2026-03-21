#!/usr/bin/env node
import fs from 'node:fs';
import path from 'node:path';

const ROUTE_BUDGET_BYTES = 700 * 1024;
const ANALYTICS_BUDGET_BYTES = 500 * 1024;

const projectRoot = process.cwd();
const assetsDir = path.join(projectRoot, 'dist', 'spa', 'assets');

function fail(message) {
  console.error(`[bundle-budget] FAIL: ${message}`);
  process.exit(1);
}

function formatSize(bytes) {
  return `${(bytes / 1024).toFixed(2)} KB`;
}

if (!fs.existsSync(assetsDir)) {
  fail(`assets directory not found: ${assetsDir}`);
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
  fail('no JS assets found in dist/spa/assets');
}

const routeCandidates = jsFiles.filter((file) => /dashboardv3page|dashboard-v3-route/i.test(file.name));
if (routeCandidates.length === 0) {
  fail('route chunk not found (expected DashboardV3Page* or dashboard-v3-route*)');
}
const routeChunk = routeCandidates[0];

const echartsChunks = jsFiles.filter((file) => /analytics-echarts/i.test(file.name));
if (echartsChunks.length === 0) {
  fail('analytics-echarts chunk not found');
}

const aggridChunks = jsFiles.filter((file) => /analytics-aggrid/i.test(file.name));
if (aggridChunks.length === 0) {
  fail('analytics-aggrid chunk not found');
}

const analyticsChunks = [...echartsChunks, ...aggridChunks];

const errors = [];
if (routeChunk.size > ROUTE_BUDGET_BYTES) {
  errors.push(
    `route chunk ${routeChunk.name} is ${formatSize(routeChunk.size)} (budget ${formatSize(ROUTE_BUDGET_BYTES)})`,
  );
}

for (const chunk of analyticsChunks) {
  if (chunk.size > ANALYTICS_BUDGET_BYTES) {
    errors.push(
      `analytics chunk ${chunk.name} is ${formatSize(chunk.size)} (budget ${formatSize(ANALYTICS_BUDGET_BYTES)})`,
    );
  }
}

console.log('[bundle-budget] Dashboard v3 budget check');
console.log(`- route chunk: ${routeChunk.name} (${formatSize(routeChunk.size)})`);
for (const chunk of analyticsChunks) {
  console.log(`- analytics chunk: ${chunk.name} (${formatSize(chunk.size)})`);
}

if (errors.length > 0) {
  for (const error of errors) {
    console.error(`[bundle-budget] ${error}`);
  }
  process.exit(1);
}

console.log('[bundle-budget] PASS');
