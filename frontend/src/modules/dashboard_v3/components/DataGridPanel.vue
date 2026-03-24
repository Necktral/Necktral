<template>
  <div ref="gridEl" class="ag-theme-quartz dashboard-grid" />
</template>

<script setup lang="ts">
import {
  ClientSideRowModelModule,
  ModuleRegistry,
  createGrid,
  type ColDef,
  type GridApi,
  type GridOptions,
} from 'ag-grid-community';
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';

import 'ag-grid-community/styles/ag-grid.min.css';
import 'ag-grid-community/styles/ag-theme-quartz-no-font.min.css';

const globalScope = globalThis as typeof globalThis & {
  __dashboardV3AgGridModulesRegistered?: boolean;
};

if (!globalScope.__dashboardV3AgGridModulesRegistered) {
  ModuleRegistry.registerModules([ClientSideRowModelModule]);
  globalScope.__dashboardV3AgGridModulesRegistered = true;
}

const props = withDefaults(
  defineProps<{
    rows: Array<Record<string, unknown>>;
    quickFilter?: string;
  }>(),
  {
    quickFilter: '',
  },
);

const api = ref<GridApi | null>(null);
const gridEl = ref<HTMLDivElement | null>(null);

const defaultColDef: ColDef = {
  sortable: true,
  filter: false,
  resizable: true,
  minWidth: 120,
  flex: 1,
};

function normalizeValue(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value.toLocaleLowerCase();
  if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint') {
    return `${value}`.toLocaleLowerCase();
  }
  if (value instanceof Date) return value.toISOString().toLocaleLowerCase();
  return '';
}

const normalizedQuickFilter = computed(() => (props.quickFilter ?? '').trim().toLocaleLowerCase());

const filteredRows = computed<Array<Record<string, unknown>>>(() => {
  const query = normalizedQuickFilter.value;
  if (!query) return props.rows;
  return props.rows.filter((row) => Object.values(row).some((value) => normalizeValue(value).includes(query)));
});

const columnDefs = computed<ColDef[]>(() => {
  const first = filteredRows.value[0] ?? props.rows[0] ?? {};
  return Object.keys(first).map((key) => ({
    field: key,
    headerName: key.replace(/_/g, ' ').toUpperCase(),
  }));
});

function currentGridOptions(): GridOptions {
  return {
    rowData: filteredRows.value,
    columnDefs: columnDefs.value,
    defaultColDef,
    suppressCellFocus: true,
    animateRows: false,
  };
}

watch(
  columnDefs,
  (value) => {
    if (!api.value) return;
    api.value.setGridOption('columnDefs', value);
  },
  { deep: true },
);

watch(
  filteredRows,
  (value) => {
    if (!api.value) return;
    api.value.setGridOption('rowData', value);
  },
  { deep: false },
);

onMounted(() => {
  if (!gridEl.value) return;
  api.value = createGrid(gridEl.value, currentGridOptions());
});

onBeforeUnmount(() => {
  api.value?.destroy();
  api.value = null;
});
</script>

<style scoped>
.dashboard-grid {
  width: 100%;
  height: 420px;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-md);
  overflow: hidden;
}
</style>
