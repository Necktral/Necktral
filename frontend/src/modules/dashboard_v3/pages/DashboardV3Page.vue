<template>
  <q-page>
    <AppContainer>
      <AppPageHeader
        title="Analítica avanzada v3"
        subtitle="Dashboards composicionales, cross-filter, drill-down y comparativos enterprise."
      >
        <template #badges>
          <q-badge outline class="q-mr-sm">Empresa: {{ companyLabel }}</q-badge>
          <q-badge outline>Sucursal: {{ branchLabel }}</q-badge>
        </template>
        <template #actions>
          <q-btn
            color="primary"
            icon="play_circle"
            label="Consultar"
            :loading="dashboard.loading"
            @click="() => void runQuery()"
          />
          <q-btn
            flat
            icon="refresh"
            label="Refrescar"
            :disable="dashboard.loading"
            @click="() => void runQuery(true)"
          />
        </template>
      </AppPageHeader>

      <q-banner v-if="!canRead" dense rounded class="q-mt-md">
        No tienes permiso <b>report.dashboard.read</b> o <b>dashboard.workspace.read</b> para usar analítica avanzada.
      </q-banner>

      <q-banner v-else-if="dashboard.error" dense rounded class="q-mt-md bg-red-1 text-negative">
        {{ dashboard.error }}
      </q-banner>

      <template v-else>
        <q-card class="app-card q-mt-md">
          <q-card-section class="row q-col-gutter-md">
            <div class="col-12 col-md-4">
              <q-select
                v-model="workspaceCode"
                label="Workspace"
                dense
                outlined
                emit-value
                map-options
                :options="workspaceOptions"
              />
            </div>
            <div class="col-12 col-md-4">
              <q-select
                v-model="widgetCode"
                label="Widget"
                dense
                outlined
                emit-value
                map-options
                :options="widgetOptions"
                :disable="!workspaceReady"
              />
            </div>
            <div class="col-12 col-md-4">
              <q-input
                v-model="statusFilter"
                label="Filtro rápido (status)"
                dense
                outlined
                clearable
              />
            </div>
          </q-card-section>
          <q-card-section class="row q-col-gutter-md q-pt-none">
            <div class="col-12 col-md-4">
              <q-input
                v-model="quickFilter"
                label="Filtro grilla / cross-filter"
                dense
                outlined
                clearable
              />
            </div>
            <div class="col-12 col-md-4">
              <q-input
                v-model="comparisonMode"
                label="Comparativo"
                dense
                outlined
                hint="Ej: prev_period"
              />
            </div>
            <div class="col-12 col-md-4">
              <q-toggle
                v-model="intercompany"
                label="Intercompany (si está habilitado)"
              />
            </div>
          </q-card-section>
        </q-card>

        <div class="row q-col-gutter-md q-mt-sm">
          <div class="col-12 col-lg-6">
            <q-card class="app-card">
              <q-card-section>
                <div class="text-subtitle1">Visual interactiva</div>
                <div class="text-caption text-grey-7">
                  Click en un punto para disparar cross-filter y drill-down.
                </div>
              </q-card-section>
              <q-separator />
              <q-card-section>
                <q-banner
                  v-if="!isChartVisualSupported"
                  dense
                  rounded
                  class="bg-amber-1 text-warning q-mb-md"
                >
                  {{ unsupportedVisualMessage }}
                </q-banner>
                <Suspense v-else>
                  <template #default>
                    <InteractiveChart
                      :option="chartOption"
                      height="360px"
                      @point-click="onChartPoint"
                    />
                  </template>
                  <template #fallback>
                    <q-skeleton type="rect" height="360px" />
                  </template>
                </Suspense>
              </q-card-section>
            </q-card>
          </div>

          <div class="col-12 col-lg-6">
            <q-card class="app-card">
              <q-card-section>
                <div class="text-subtitle1">Datos tabulares</div>
                <div class="text-caption text-grey-7">
                  Grid analítica con filtros y ordenamiento multi-columna.
                </div>
              </q-card-section>
              <q-separator />
              <q-card-section>
                <Suspense>
                  <template #default>
                    <DataGridPanel :rows="gridRows" :quick-filter="quickFilter" />
                  </template>
                  <template #fallback>
                    <q-skeleton type="rect" height="420px" />
                  </template>
                </Suspense>
              </q-card-section>
            </q-card>
          </div>
        </div>

        <q-card class="app-card q-mt-md">
          <q-card-section>
            <div class="text-subtitle1">Drill-down resultante</div>
            <div class="text-caption text-grey-7">
              Nivel de detalle según el punto seleccionado y ruta de drill.
            </div>
          </q-card-section>
          <q-separator />
          <q-card-section>
            <Suspense>
              <template #default>
                <DataGridPanel :rows="drillRows" :quick-filter="quickFilter" />
              </template>
              <template #fallback>
                <q-skeleton type="rect" height="420px" />
              </template>
            </Suspense>
          </q-card-section>
        </q-card>
      </template>
    </AppContainer>
  </q-page>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';

import AppContainer from 'src/ui/AppContainer.vue';
import AppPageHeader from 'src/ui/AppPageHeader.vue';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

import { useDashboardV3Store } from '../stores/dashboard-v3.store';
import type { DashboardQueryParams } from '../types';

const DataGridPanel = defineAsyncComponent(() => import('../components/DataGridPanel.vue'));
const InteractiveChart = defineAsyncComponent(() => import('../components/InteractiveChart.vue'));

const SUPPORTED_CHART_VISUALS = new Set(['bar', 'stacked_bar', 'line', 'area']);

const route = useRoute();
const router = useRouter();
const acl = useAclStore();
const ctx = useContextStore();
const dashboard = useDashboardV3Store();

const workspaceCode = ref(typeof route.query.w === 'string' ? route.query.w : '');
const widgetCode = ref(typeof route.query.g === 'string' ? route.query.g : '');
const statusFilter = ref(typeof route.query.s === 'string' ? route.query.s : '');
const quickFilter = ref('');
const comparisonMode = ref('prev_period');
const intercompany = ref(false);

const companyLabel = computed(
  () => acl.companyName(ctx.activeCompanyId) ?? ctx.activeCompanyId ?? '—',
);
const branchLabel = computed(
  () => acl.branchName(ctx.activeCompanyId, ctx.activeBranchId) ?? ctx.activeBranchId ?? '—',
);

const canRead = computed(() => {
  const companyId = ctx.activeCompanyId;
  if (!companyId) return false;
  return acl.hasPermission(companyId, 'report.dashboard.read') || acl.hasPermission(companyId, 'dashboard.workspace.read');
});

const workspaceReady = computed(() => !!dashboard.workspace);

const workspaceOptions = computed(() =>
  (dashboard.catalog ?? []).map((entry) => ({
    label: `${entry.title} (${entry.widget_count})`,
    value: entry.workspace_code,
  })),
);

const widgetOptions = computed(() =>
  (dashboard.workspace?.widgets ?? []).map((widget) => ({
    label: `${widget.title} · ${widget.domain}`,
    value: widget.widget_code,
  })),
);

const queryWidgets = computed(() => dashboard.queryResult?.results.widgets ?? []);

const activeWidget = computed(() => {
  if (!queryWidgets.value.length) return null;
  return queryWidgets.value.find((widget) => widget.widget_code === widgetCode.value) ?? queryWidgets.value[0];
});

const activeVisual = computed(() => {
  const visual = activeWidget.value?.visual;
  return typeof visual === 'string' ? visual.trim() : '';
});

const gridRows = computed(() => activeWidget.value?.rows ?? []);

const drillRows = computed(() =>
  (dashboard.drilldownResult?.results.drilldown ?? []).flatMap((entry) => entry.rows ?? []),
);

const isChartVisualSupported = computed(() => {
  if (!activeVisual.value) return true;
  return SUPPORTED_CHART_VISUALS.has(activeVisual.value);
});

const unsupportedVisualMessage = computed(() => {
  if (isChartVisualSupported.value) return '';
  return `La visual "${activeVisual.value}" no está soportada en esta ola. Se mantiene fallback tabular sin bloquear la consulta.`;
});

function toSafeLabel(value: unknown, fallback: string): string {
  if (value === null || value === undefined) return fallback;
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint') {
    return String(value);
  }
  return fallback;
}

function toSafeNumber(value: unknown, fallback = 0): number {
  const num = Number(value);
  return Number.isFinite(num) ? num : fallback;
}

function metricValue(row: Record<string, unknown>, candidates: string[]): number {
  for (const key of candidates) {
    if (!(key in row)) continue;
    const raw = row[key];
    if (raw === null || raw === undefined || raw === '') continue;
    return toSafeNumber(raw, 0);
  }
  return 0;
}

const chartOption = computed(() => {
  const rows = activeWidget.value?.rows ?? [];
  const labels = rows.map((row, index) =>
    toSafeLabel(row.domain ?? row.severity ?? row.series ?? row.doc_type, `row-${index + 1}`),
  );
  const primaryValues = rows.map((row) =>
    metricValue(row, ['entity_count', 'health_score', 'alert_count', 'critical_count', 'error_count']),
  );
  const secondaryValues = rows.map((row) =>
    metricValue(row, ['alert_count', 'critical_count', 'error_count']),
  );
  const visual = activeVisual.value;
  const widgetTitle = activeWidget.value?.widget_title ?? 'Widget';
  const shouldRenderArea = visual === 'area';
  const hasSecondarySeries = secondaryValues.some((value) => value > 0);

  const baseOption = {
    backgroundColor: 'transparent',
    grid: { left: 42, right: 18, top: 24, bottom: 44 },
    xAxis: {
      type: 'category',
      data: labels,
      axisLabel: { color: '#4d6178' },
      axisLine: { lineStyle: { color: '#b8c6d8' } },
    },
    yAxis: {
      type: 'value',
      axisLabel: { color: '#4d6178' },
      splitLine: { lineStyle: { color: '#dbe5f1' } },
    },
  };

  if (visual === 'line' || visual === 'area') {
    return {
      ...baseOption,
      series: [
        {
          type: 'line',
          smooth: true,
          name: widgetTitle,
          data: primaryValues,
          lineStyle: { color: '#1869a8', width: 3 },
          itemStyle: { color: '#1869a8' },
          areaStyle: shouldRenderArea ? { opacity: 0.22, color: '#1d9b84' } : undefined,
        },
      ],
    };
  }

  if (visual === 'stacked_bar') {
    const stackedSeries: Array<Record<string, unknown>> = [
      {
        type: 'bar',
        stack: 'total',
        name: widgetTitle,
        data: primaryValues,
        itemStyle: { color: '#1869a8' },
      },
    ];
    if (hasSecondarySeries) {
      stackedSeries.push({
        type: 'bar',
        stack: 'total',
        name: 'Alertas',
        data: secondaryValues,
        itemStyle: { color: '#1d9b84' },
      });
    }
    return {
      ...baseOption,
      series: stackedSeries,
    };
  }

  return {
    ...baseOption,
    series: [
      {
        type: 'bar',
        name: widgetTitle,
        data: primaryValues,
        itemStyle: {
          color: '#1869a8',
          borderRadius: [6, 6, 0, 0],
        },
        emphasis: {
          itemStyle: {
            color: '#1d9b84',
          },
        },
      },
    ],
  };
});

function syncRouteState() {
  void router.replace({
    query: {
      ...route.query,
      w: workspaceCode.value || undefined,
      g: widgetCode.value || undefined,
      s: statusFilter.value || undefined,
    },
  });
}

async function ensureWorkspace() {
  if (!workspaceCode.value) return;
  await dashboard.loadWorkspace(workspaceCode.value);
  const widgets = dashboard.workspace?.widgets ?? [];
  if (!widgets.length) return;
  const found = widgets.find((row) => row.widget_code === widgetCode.value);
  if (!found) {
    const firstWidget = widgets[0];
    if (!firstWidget) return;
    widgetCode.value = firstWidget.widget_code;
  }
}

async function runQuery(refresh = false) {
  if (!workspaceCode.value || !widgetCode.value) return;
  syncRouteState();
  const queryPayload: DashboardQueryParams = {
    widget_code: widgetCode.value,
    filters: {
      status: statusFilter.value ? [statusFilter.value] : [],
      clicked_point: quickFilter.value || undefined,
    },
    group_by: ['domain'],
    metrics: ['entity_count', 'health_score', 'alert_count', 'critical_count'],
    comparison: { mode: comparisonMode.value || 'prev_period' },
    drill_path: ['series'],
    use_cache: !refresh,
  };
  if (intercompany.value) {
    queryPayload.company_ids = [];
  }
  await dashboard.queryWorkspace(workspaceCode.value, queryPayload);

  await dashboard.runDrilldown({
    workspace_code: workspaceCode.value,
    widget_code: widgetCode.value,
    drill_path: ['series', 'detail'],
    filters: {
      status: statusFilter.value ? [statusFilter.value] : [],
      clicked_point: quickFilter.value || undefined,
    },
    comparison: { mode: comparisonMode.value || 'prev_period' },
  });
}

async function onChartPoint(payload: Record<string, unknown>) {
  quickFilter.value = toSafeLabel(payload.name ?? payload.value, '');
  await runQuery();
}

onMounted(async () => {
  if (!canRead.value) return;

  await dashboard.loadCatalog();
  if (!workspaceCode.value && dashboard.catalog.length) {
    const firstWorkspace = dashboard.catalog[0];
    if (firstWorkspace) {
      workspaceCode.value = firstWorkspace.workspace_code;
    }
  }
  await ensureWorkspace();
  await runQuery();
});
</script>

<style scoped>
@media (max-width: 1023px) {
  :deep(.dashboard-grid) {
    height: 360px;
  }
}
</style>
