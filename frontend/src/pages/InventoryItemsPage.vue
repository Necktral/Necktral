<template>
  <AppContainer>
    <AppPageHeader
      :title="labels.inventory + ' · Ítems'"
      subtitle="Catálogo operativo con filtros avanzados, vistas guardadas y acciones masivas."
    >
      <template #actions>
        <q-btn flat label="Recargar" :loading="loading" @click="reload" />
        <q-btn flat label="Guardar vista" @click="saveView" />
        <q-btn flat label="Cargar vista" @click="loadView" />
        <q-btn flat icon="checklist" label="Activar" :disable="!selected.length || !canUpdate" @click="bulkSetActive(true)" />
        <q-btn flat icon="block" label="Desactivar" :disable="!selected.length || !canUpdate" @click="bulkSetActive(false)" />
        <q-btn color="primary" icon="add" label="Nuevo ítem" :disable="!canCreate" @click="openCreate" />
      </template>
    </AppPageHeader>

    <div class="q-mt-md">
      <AppDataTable
        title="Listado"
        caption="Atajo: / enfoca búsqueda de la tabla."
        :rows="rows"
        :columns="columns"
        row-key="id"
        :loading="loading"
        :pagination="pagination"
        :rows-per-page-options="[20, 50, 100]"
        selection="multiple"
        v-model:selected="selected"
        @request="onRequest"
      >
        <template #toolbar>
          <q-input
            ref="searchInput"
            v-model="filters.q"
            dense
            outlined
            placeholder="Buscar por SKU o nombre..."
            @update:model-value="reload"
          />
          <q-toggle v-model="onlyActive" label="Solo activos" @update:model-value="reload" />
        </template>

        <template #body-cell-is_active="props">
          <q-td :props="props">
            <q-badge :color="props.row.is_active ? 'positive' : 'negative'" outline>
              {{ props.row.is_active ? 'ACTIVO' : 'INACTIVO' }}
            </q-badge>
          </q-td>
        </template>

        <template #body-cell-actions="props">
          <q-td :props="props" class="text-right">
            <q-btn dense flat icon="edit" :disable="!canUpdate" @click="openEdit(props.row)" />
          </q-td>
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
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import type { QTableColumn } from 'quasar';

import {
  listInventoryItems,
  patchInventoryItem,
  type InventoryItemRow,
} from 'src/services/inventory.service';
import { BUSINESS_LABELS, UI_ROUTE_PATHS } from 'src/shared/ui/business-terms';
import { useAclStore } from 'src/stores/acl.store';
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
const routes = UI_ROUTE_PATHS;
const acl = useAclStore();
const ctx = useContextStore();
const router = useRouter();

const rows = ref<InventoryItemRow[]>([]);
const loading = ref(false);
const errorMsg = ref('');
const selected = ref<InventoryItemRow[]>([]);
const searchInput = ref<{ focus: () => void } | null>(null);
const onlyActive = ref(true);

const filters = ref({
  q: '',
  limit: 20,
  offset: 0,
});

const pagination = ref<Pagination>({
  page: 1,
  rowsPerPage: 20,
  rowsNumber: 0,
});

const columns: QTableColumn[] = [
  { name: 'sku', label: 'SKU', field: 'sku', align: 'left', sortable: true },
  { name: 'name', label: 'Nombre', field: 'name', align: 'left', sortable: true },
  { name: 'item_type', label: 'Tipo', field: 'item_type', align: 'left' },
  { name: 'uom_base', label: 'UoM Base', field: 'uom_base', align: 'left' },
  { name: 'is_active', label: 'Estado', field: 'is_active', align: 'left' },
  { name: 'updated_at', label: 'Actualizado', field: 'updated_at', align: 'left' },
  { name: 'actions', label: 'Acciones', field: 'actions', align: 'right' },
];

const canCreate = computed(() => {
  const companyId = ctx.activeCompanyId;
  if (!companyId) return false;
  return acl.hasPermission(companyId, 'inventory.item.create');
});

const canUpdate = computed(() => {
  const companyId = ctx.activeCompanyId;
  if (!companyId) return false;
  return acl.hasPermission(companyId, 'inventory.item.update');
});

function savedViewKey(): string {
  return 'inventory.items.view.' + (ctx.activeCompanyId || 'na') + '.' + (ctx.activeBranchId || 'na');
}

async function reload(): Promise<void> {
  loading.value = true;
  errorMsg.value = '';
  try {
    const params: {
      q?: string;
      is_active?: boolean;
      limit?: number;
      offset?: number;
    } = {
      q: filters.value.q,
      limit: pagination.value.rowsPerPage,
      offset: filters.value.offset,
    };
    if (onlyActive.value) params.is_active = true;
    const data = await listInventoryItems(params);
    rows.value = data.results;
    pagination.value.rowsNumber = data.count;
    selected.value = [];
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

function openCreate(): void {
  void router.push(routes.inventoryItemNew);
}

function openEdit(row: InventoryItemRow): void {
  void router.push(`/inventario/items/${row.id}/editar`);
}

async function bulkSetActive(isActive: boolean): Promise<void> {
  if (!selected.value.length) return;
  await Promise.all(selected.value.map((row) => patchInventoryItem(row.id, { is_active: isActive })));
  Notify.create({
    type: 'positive',
    message: isActive ? 'Ítems activados.' : 'Ítems desactivados.',
  });
  await reload();
}

function saveView(): void {
  const payload = {
    q: filters.value.q,
    onlyActive: onlyActive.value,
    rowsPerPage: pagination.value.rowsPerPage,
  };
  localStorage.setItem(savedViewKey(), JSON.stringify(payload));
  Notify.create({ type: 'positive', message: 'Vista guardada.' });
}

function loadView(): void {
  const raw = localStorage.getItem(savedViewKey());
  if (!raw) {
    Notify.create({ type: 'warning', message: 'No hay vista guardada.' });
    return;
  }
  try {
    const parsed = JSON.parse(raw) as { q?: string; onlyActive?: boolean; rowsPerPage?: number };
    filters.value.q = parsed.q || '';
    onlyActive.value = parsed.onlyActive !== false;
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

watch(onlyActive, () => {
  pagination.value.page = 1;
  filters.value.offset = 0;
  void reload();
});

onMounted(() => {
  void reload();
  window.addEventListener('keydown', onKeydown);
});

onUnmounted(() => {
  window.removeEventListener('keydown', onKeydown);
});
</script>
