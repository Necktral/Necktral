# Dashboard V3 Bundle Analysis

## Baseline (before optimization)
Build command: `cd frontend && npm run build`

### Route assets (Dashboard V3)
| Asset | Size |
|---|---:|
| `DashboardV3Page-Cg_iJwGE.js` | 1660.58 KB |
| `DashboardV3Page-C6_zk5Tn.css` | 244.52 KB |

### Relevant global assets
| Asset | Size |
|---|---:|
| `index-BHbB07qr.js` | 263.77 KB |
| `index-ByW_8Cmm.css` | 199.81 KB |
| `browser-COI8Ulb7.js` | 24.86 KB |

## Dependency to chunk mapping (baseline)
- `echarts` imported as full package from `InteractiveChart.vue`.
- `ag-grid-community` + `ag-grid-vue3` imported statically from `DataGridPanel.vue`.
- Both components imported statically from `DashboardV3Page.vue`, forcing heavy payload into the route chunk.

## Optimization matrix
| Cause | Baseline impact | Change | Expected gain |
|---|---:|---|---|
| Static chart/grid imports in route page | Very high | `defineAsyncComponent` + suspense fallback | Move heavy code off first route payload |
| Full ECharts bundle | High | `echarts/core` + only `BarChart`, `LineChart`, `GridComponent`, `CanvasRenderer` | Lower chart JS chunk |
| AG Grid monolithic package | High | `ag-grid-community` pinned to `33.0.0` + minimal module registration (`ClientSideRowModel`) | Lower AG Grid JS chunk without replacing AG Grid |
| Heavy theme CSS in route | Medium | `ag-theme-quartz-no-font.min.css` + async grid chunk | Lower critical route CSS/first paint impact |
| No explicit rollup chunk strategy | High | `manualChunks`: `analytics-echarts`, `analytics-aggrid`, `dashboard-v3-route` | Stable split + cacheability |
| No bundle budget enforcement | High risk of regression | post-build budget script + CI integration | Prevent regressions automatically |

## Post-optimization results
Build command: `cd frontend && npm run build`  
Budget check: `cd frontend && npm run bundle:budget:dashboard-v3`

### Route and analytics chunks (final)
| Asset | Size | Budget | Status |
|---|---:|---:|---|
| `dashboard-v3-route-*.js` | 280.36 KB | 700 KB | PASS |
| `analytics-echarts-*.js` | 463.20 KB | 500 KB | PASS |
| `analytics-aggrid-*.js` | 488.13 KB | 500 KB | PASS |

### Delta vs baseline
| Asset | Baseline | Final | Reduction |
|---|---:|---:|---:|
| Main route JS (`DashboardV3Page` -> `dashboard-v3-route`) | 1660.58 KB | 280.36 KB | -1380.22 KB |
| Route CSS (`DashboardV3Page`) | 244.52 KB | 0.07 KB | -244.45 KB |

### Validation summary
- `npm run typecheck`: PASS
- `npm run test -- src/router/routes.spec.ts`: PASS
- `npm run build`: PASS (no chunk warning)
- `npm run bundle:budget:dashboard-v3`: PASS
