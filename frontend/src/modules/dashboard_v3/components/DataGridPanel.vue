<template>
  <div ref="gridEl" class="ag-theme-quartz dashboard-grid" />
</template>

<script setup lang="ts">
import {
  ModuleRegistry,
  createGrid,
  type ColDef,
  type GridApi,
  type GridOptions,
  ClientSideRowModelModule,
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
  filter: true,
  resizable: true,
  minWidth: 120,
  flex: 1,
};

const columnDefs = computed<ColDef[]>(() => {
  const first = props.rows[0] ?? {};
  return Object.keys(first).map((key) => ({
    field: key,
    headerName: key.replace(/_/g, ' ').toUpperCase(),
  }));
});

function currentGridOptions(): GridOptions {
  return {
    rowData: props.rows,
    columnDefs: columnDefs.value,
    defaultColDef,
    suppressCellFocus: true,
    animateRows: false,
  };
}

watch(
  () => props.quickFilter,
  (value) => {
    if (!api.value) return;
    api.value.setGridOption('quickFilterText', value ?? '');
  },
);

watch(
  columnDefs,
  (value) => {
    if (!api.value) return;
    api.value.setGridOption('columnDefs', value);
  },
  { deep: true },
);

watch(
  () => props.rows,
  (value) => {
    if (!api.value) return;
    api.value.setGridOption('rowData', value);
  },
  { deep: true },
);

onMounted(() => {
  if (!gridEl.value) return;
  api.value = createGrid(gridEl.value, currentGridOptions());
  if (props.quickFilter) {
    api.value.setGridOption('quickFilterText', props.quickFilter);
  }
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
