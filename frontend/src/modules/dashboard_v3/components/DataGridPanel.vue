<template>
  <q-table
    class="dashboard-grid"
    flat
    bordered
    dense
    :rows="tableRows"
    :columns="tableColumns"
    row-key="__row_id"
    :pagination="pagination"
    :rows-per-page-options="[10, 25, 50, 100]"
  />
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';

import {
  dashboardGridHeaderLabel,
  dashboardGridValueIncludes,
  formatDashboardGridValue,
} from '../chunks/analytics-aggrid-runtime';

const props = withDefaults(
  defineProps<{
    rows: Array<Record<string, unknown>>;
    quickFilter?: string;
  }>(),
  {
    quickFilter: '',
  },
);

type GridRow = Record<string, unknown>;

const normalizedQuickFilter = computed(() => (props.quickFilter ?? '').trim().toLocaleLowerCase());

const filteredRows = computed<GridRow[]>(() => {
  const query = normalizedQuickFilter.value;
  if (!query) return props.rows;
  return props.rows.filter((row) =>
    Object.values(row).some((value) => dashboardGridValueIncludes(value, query)),
  );
});

const tableColumns = computed(() =>
  Object.keys(filteredRows.value[0] ?? props.rows[0] ?? {}).map((key) => ({
    name: key,
    field: key,
    label: dashboardGridHeaderLabel(key),
    sortable: true,
    align: 'left' as const,
    format: (value: unknown) => formatDashboardGridValue(value),
  })),
);

const tableRows = computed(() =>
  filteredRows.value.map((row, index) => ({
    ...row,
    __row_id: `${index}`,
  })),
);

const pagination = ref({
  page: 1,
  rowsPerPage: 25,
  sortBy: '',
  descending: false,
});

const activeColumnCount = computed(() => tableColumns.value.length);

watch(
  activeColumnCount,
  () => {
    pagination.value.page = 1;
  },
  { flush: 'sync' },
);

const currentRowCount = computed(() => tableRows.value.length);

watch(
  currentRowCount,
  () => {
    if (pagination.value.page < 1) {
      pagination.value.page = 1;
    }
  },
  { flush: 'sync' },
);

</script>

<style scoped>
.dashboard-grid {
  width: 100%;
  min-height: 420px;
  border: 1px solid var(--app-border);
  border-radius: var(--app-radius-md);
  overflow: hidden;
}

:deep(.q-table__middle) {
  max-height: 420px;
}
</style>
