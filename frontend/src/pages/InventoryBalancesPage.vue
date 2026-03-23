<template>
  <AppContainer>
    <AppPageHeader
      :title="labels.inventory + ' · Balances'"
      subtitle="Existencias y costo promedio por almacén e ítem."
    >
      <template #actions>
        <q-btn flat label="Recargar" :loading="loading" @click="reload" />
        <q-btn flat label="Guardar vista" @click="saveView" />
        <q-btn flat label="Cargar vista" @click="loadView" />
      </template>
    </AppPageHeader>

    <div class="q-mt-md">
      <AppDataTable
        title="Balances"
        caption="Atajo: / enfoca búsqueda."
        :rows="rows"
        :columns="columns"
        row-key="id"
        :loading="loading"
        :pagination="pagination"
        :rows-per-page-options="[20, 50, 100]"
        @request="onRequest"
      >
        <template #toolbar>
          <q-input ref="searchInput" v-model="filters.q" dense outlined placeholder="Buscar por almacén, código o SKU..." @update:model-value="reload" />
        </template>
      </AppDataTable>
    </div>

    <q-banner v-if="errorMsg" class="q-mt-md" dense rounded>
      {{ errorMsg }}
    </q-banner>
  </AppContainer>
</template>

<script setup lang="ts">
import { Notify } from 'quasar';
import { onMounted, onUnmounted, ref } from 'vue';
import type { QTableColumn } from 'quasar';

import { listInventoryBalances, type InventoryBalanceRow } from 'src/services/inventory.service';
import { BUSINESS_LABELS } from 'src/shared/ui/business-terms';
import { useContextStore } from 'src/stores/context.store';
import AppContainer from 'src/ui/AppContainer.vue';
import AppDataTable from 'src/ui/AppDataTable.vue';
import AppPageHeader from 'src/ui/AppPageHeader.vue';

type Pagination = {
  page: number;
  rowsPerPage: number;
  rowsNumber: number;
};

const labels = BUSINESS_LABELS;
const ctx = useContextStore();

const rows = ref<InventoryBalanceRow[]>([]);
const loading = ref(false);
const errorMsg = ref('');
const searchInput = ref<{ focus: () => void } | null>(null);

const filters = ref({
  q: '',
  offset: 0,
});

const pagination = ref<Pagination>({
  page: 1,
  rowsPerPage: 20,
  rowsNumber: 0,
});

const columns: QTableColumn[] = [
  { name: 'warehouse_name', label: 'Almacén', field: 'warehouse_name', align: 'left', sortable: true },
  { name: 'warehouse_code', label: 'Código almacén', field: 'warehouse_code', align: 'left' },
  { name: 'item_sku', label: 'SKU', field: 'item_sku', align: 'left', sortable: true },
  { name: 'item_name', label: 'Ítem', field: 'item_name', align: 'left' },
  { name: 'qty_on_hand', label: 'Qty', field: 'qty_on_hand', align: 'right' },
  { name: 'avg_cost', label: 'Costo promedio', field: 'avg_cost', align: 'right' },
  { name: 'updated_at', label: 'Actualizado', field: 'updated_at', align: 'left' },
];

function savedViewKey(): string {
  return 'inventory.balances.view.' + (ctx.activeCompanyId || 'na') + '.' + (ctx.activeBranchId || 'na');
}

async function reload(): Promise<void> {
  loading.value = true;
  errorMsg.value = '';
  try {
    const data = await listInventoryBalances({
      q: filters.value.q,
      limit: pagination.value.rowsPerPage,
      offset: filters.value.offset,
    });
    rows.value = data.results;
    pagination.value.rowsNumber = data.count;
  } catch (error: unknown) {
    errorMsg.value = error instanceof Error ? error.message : String(error);
  } finally {
    loading.value = false;
  }
}

function onRequest(req: { pagination: { page: number; rowsPerPage: number } }): void {
  pagination.value.page = req.pagination.page;
  pagination.value.rowsPerPage = req.pagination.rowsPerPage;
  filters.value.offset = (req.pagination.page - 1) * req.pagination.rowsPerPage;
  void reload();
}

function saveView(): void {
  localStorage.setItem(
    savedViewKey(),
    JSON.stringify({
      q: filters.value.q,
      rowsPerPage: pagination.value.rowsPerPage,
    }),
  );
  Notify.create({ type: 'positive', message: 'Vista guardada.' });
}

function loadView(): void {
  const raw = localStorage.getItem(savedViewKey());
  if (!raw) {
    Notify.create({ type: 'warning', message: 'No hay vista guardada.' });
    return;
  }
  try {
    const parsed = JSON.parse(raw) as { q?: string; rowsPerPage?: number };
    filters.value.q = parsed.q || '';
    pagination.value.rowsPerPage = parsed.rowsPerPage || 20;
    pagination.value.page = 1;
    filters.value.offset = 0;
    void reload();
  } catch {
    Notify.create({ type: 'negative', message: 'Vista guardada inválida.' });
  }
}

function onKeydown(event: KeyboardEvent): void {
  if (event.key === '/' && !event.ctrlKey && !event.metaKey && !event.altKey) {
    const target = event.target as HTMLElement | null;
    if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA')) return;
    event.preventDefault();
    searchInput.value?.focus();
  }
}

onMounted(() => {
  void reload();
  window.addEventListener('keydown', onKeydown);
});

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown);
});
</script>
