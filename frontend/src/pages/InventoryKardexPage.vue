<template>
  <AppContainer>
    <AppPageHeader
      :title="labels.inventory + ' · Kardex'"
      subtitle="Trazabilidad de movimientos con filtros operativos y contables."
    >
      <template #actions>
        <q-btn flat label="Recargar" :loading="loading" @click="reload" />
        <q-btn flat label="Guardar vista" @click="saveView" />
        <q-btn flat label="Cargar vista" @click="loadView" />
      </template>
    </AppPageHeader>

    <q-card class="app-card q-mt-md">
      <q-card-section class="row q-col-gutter-md">
        <div class="col-12 col-md-3">
          <q-select
            v-model="filters.movement_type"
            outlined
            clearable
            label="Tipo movimiento"
            :options="movementTypeOptions"
            emit-value
            map-options
          />
        </div>
        <div class="col-12 col-md-3">
          <q-input v-model="filters.source_module" outlined label="Source module" />
        </div>
        <div class="col-12 col-md-3">
          <q-input v-model="filters.date_from" outlined type="datetime-local" label="Desde" />
        </div>
        <div class="col-12 col-md-3">
          <q-input v-model="filters.date_to" outlined type="datetime-local" label="Hasta" />
        </div>
      </q-card-section>
      <q-card-actions align="right">
        <q-btn flat icon="filter_alt" label="Aplicar filtros" @click="applyFilters" />
      </q-card-actions>
    </q-card>

    <div class="q-mt-md">
      <AppDataTable
        title="Kardex"
        caption="Atajo: / enfoca búsqueda por source."
        :rows="rows"
        :columns="columns"
        row-key="id"
        :loading="loading"
        :pagination="pagination"
        :rows-per-page-options="[20, 50, 100]"
        @request="onRequest"
      >
        <template #toolbar>
          <q-input ref="searchInput" v-model="filters.source_q" dense outlined placeholder="Buscar por source_type / source_id..." @update:model-value="reload" />
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
import { computed, onMounted, onUnmounted, ref } from 'vue';
import type { QTableColumn } from 'quasar';

import { listInventoryLedger, type InventoryMovementRow } from 'src/services/inventory.service';
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

const rows = ref<InventoryMovementRow[]>([]);
const loading = ref(false);
const errorMsg = ref('');
const searchInput = ref<{ focus: () => void } | null>(null);

const pagination = ref<Pagination>({
  page: 1,
  rowsPerPage: 20,
  rowsNumber: 0,
});

const filters = ref({
  movement_type: '' as string,
  source_module: '',
  date_from: '',
  date_to: '',
  source_q: '',
  offset: 0,
});

const columns: QTableColumn[] = [
  { name: 'created_at', label: 'Fecha', field: 'created_at', align: 'left', sortable: true },
  { name: 'movement_type', label: 'Tipo', field: 'movement_type', align: 'left' },
  { name: 'warehouse_id', label: 'Almacén', field: 'warehouse_id', align: 'left' },
  { name: 'item_id', label: 'Ítem', field: 'item_id', align: 'left' },
  { name: 'qty_delta', label: 'Qty Δ', field: 'qty_delta', align: 'right' },
  { name: 'unit_cost', label: 'Costo unit.', field: 'unit_cost', align: 'right' },
  { name: 'source_module', label: 'Source module', field: 'source_module', align: 'left' },
  { name: 'source_type', label: 'Source type', field: 'source_type', align: 'left' },
  { name: 'source_id', label: 'Source id', field: 'source_id', align: 'left' },
  { name: 'accounting_status', label: 'Estado contable', field: 'accounting_status', align: 'left' },
];

const movementTypeOptions = [
  { label: 'RECEIVE', value: 'RECEIVE' },
  { label: 'ISSUE', value: 'ISSUE' },
  { label: 'ADJUST', value: 'ADJUST' },
  { label: 'TRANSFER_OUT', value: 'TRANSFER_OUT' },
  { label: 'TRANSFER_IN', value: 'TRANSFER_IN' },
];

const sourceTypeFromQ = computed(() => {
  const value = filters.value.source_q.trim();
  return value || undefined;
});

function savedViewKey(): string {
  return 'inventory.kardex.view.' + (ctx.activeCompanyId || 'na') + '.' + (ctx.activeBranchId || 'na');
}

function toIsoOrUndefined(localDateTime: string): string | undefined {
  const trimmed = localDateTime.trim();
  if (!trimmed) return undefined;
  return new Date(trimmed).toISOString();
}

async function reload(): Promise<void> {
  loading.value = true;
  errorMsg.value = '';
  try {
    const params: {
      movement_type?: string;
      source_module?: string;
      source_type?: string;
      source_id?: string;
      date_from?: string;
      date_to?: string;
      limit: number;
      offset: number;
    } = {
      limit: pagination.value.rowsPerPage,
      offset: filters.value.offset,
    };
    if (filters.value.movement_type) params.movement_type = filters.value.movement_type;
    if (filters.value.source_module) params.source_module = filters.value.source_module;
    if (sourceTypeFromQ.value) {
      params.source_type = sourceTypeFromQ.value;
      params.source_id = sourceTypeFromQ.value;
    }
    const from = toIsoOrUndefined(filters.value.date_from);
    const to = toIsoOrUndefined(filters.value.date_to);
    if (from) params.date_from = from;
    if (to) params.date_to = to;
    const data = await listInventoryLedger(params);
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

function applyFilters() {
  pagination.value.page = 1;
  filters.value.offset = 0;
  void reload();
}

function saveView(): void {
  localStorage.setItem(savedViewKey(), JSON.stringify(filters.value));
  Notify.create({ type: 'positive', message: 'Vista guardada.' });
}

function loadView(): void {
  const raw = localStorage.getItem(savedViewKey());
  if (!raw) {
    Notify.create({ type: 'warning', message: 'No hay vista guardada.' });
    return;
  }
  try {
    const parsed = JSON.parse(raw) as typeof filters.value;
    filters.value = {
      ...filters.value,
      ...parsed,
    };
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
