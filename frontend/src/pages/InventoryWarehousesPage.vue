<template>
  <AppContainer>
    <AppPageHeader
      :title="labels.inventory + ' · Almacenes'"
      subtitle="Gestión de almacenes por sucursal con filtros, acciones masivas y vistas guardadas."
    >
      <template #actions>
        <q-btn flat label="Recargar" :loading="loading" @click="reload" />
        <q-btn flat label="Guardar vista" @click="saveView" />
        <q-btn flat label="Cargar vista" @click="loadView" />
        <q-btn flat icon="checklist" label="Activar" :disable="!selected.length" @click="bulkSetActive(true)" />
        <q-btn flat icon="block" label="Desactivar" :disable="!selected.length" @click="bulkSetActive(false)" />
        <q-btn color="primary" icon="add" label="Nuevo almacén" :disable="!canManage" @click="openCreate" />
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
          <q-input ref="searchInput" v-model="filters.q" dense outlined placeholder="Buscar por nombre o código..." @update:model-value="reload" />
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
            <q-btn dense flat icon="edit" :disable="!canManage" @click="openEdit(props.row)" />
          </q-td>
        </template>
      </AppDataTable>
    </div>

    <q-banner v-if="errorMsg" class="q-mt-md" dense rounded>
      {{ errorMsg }}
    </q-banner>

    <q-dialog v-model="dialogOpen">
      <q-card style="width: 720px; max-width: 96vw" class="app-card">
        <q-card-section class="row items-center justify-between">
          <div class="text-h6">{{ editId ? 'Editar almacén' : 'Nuevo almacén' }}</div>
          <q-btn flat icon="close" v-close-popup />
        </q-card-section>
        <q-separator />
        <q-card-section>
          <q-form @submit.prevent="save">
            <div class="row q-col-gutter-md">
              <div class="col-12 col-md-5">
                <q-input v-model="form.name" outlined label="Nombre" />
              </div>
              <div class="col-12 col-md-4">
                <q-input v-model="form.code" outlined label="Código" />
              </div>
            </div>

            <div class="q-mt-sm" v-if="editId">
              <q-toggle v-model="form.is_active" label="Activo" />
            </div>

            <div class="q-mt-md inventory-sticky-actionbar">
              <q-btn color="primary" type="submit" icon="save" label="Guardar (Ctrl+Enter)" class="inventory-touch-target" @keydown.ctrl.enter.prevent="save" />
            </div>
          </q-form>
        </q-card-section>
      </q-card>
    </q-dialog>
  </AppContainer>
</template>

<script setup lang="ts">
import { Notify } from 'quasar';
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import type { QTableColumn } from 'quasar';

import {
  createInventoryWarehouse,
  listInventoryWarehouses,
  patchInventoryWarehouse,
  type WarehouseRow,
} from 'src/services/inventory.service';
import { BUSINESS_LABELS } from 'src/shared/ui/business-terms';
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
const acl = useAclStore();
const ctx = useContextStore();

const rows = ref<WarehouseRow[]>([]);
const loading = ref(false);
const errorMsg = ref('');
const selected = ref<WarehouseRow[]>([]);
const searchInput = ref<{ focus: () => void } | null>(null);
const onlyActive = ref(true);

const filters = ref({
  q: '',
  offset: 0,
});

const pagination = ref<Pagination>({
  page: 1,
  rowsPerPage: 20,
  rowsNumber: 0,
});

const dialogOpen = ref(false);
const editId = ref<number | null>(null);
const form = ref({
  name: '',
  code: '',
  is_active: true,
});

const columns: QTableColumn[] = [
  { name: 'name', label: 'Nombre', field: 'name', align: 'left', sortable: true },
  { name: 'code', label: 'Código', field: 'code', align: 'left', sortable: true },
  { name: 'is_active', label: 'Estado', field: 'is_active', align: 'left' },
  { name: 'created_at', label: 'Creado', field: 'created_at', align: 'left' },
  { name: 'actions', label: 'Acciones', field: 'actions', align: 'right' },
];

const canManage = computed(() => {
  const companyId = ctx.activeCompanyId;
  if (!companyId) return false;
  return acl.hasPermission(companyId, 'inventory.warehouse.create');
});

function savedViewKey(): string {
  return 'inventory.warehouses.view.' + (ctx.activeCompanyId || 'na') + '.' + (ctx.activeBranchId || 'na');
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
    const data = await listInventoryWarehouses(params);
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
  editId.value = null;
  form.value = {
    name: '',
    code: '',
    is_active: true,
  };
  dialogOpen.value = true;
}

function openEdit(row: WarehouseRow): void {
  editId.value = row.id;
  form.value = {
    name: row.name,
    code: row.code,
    is_active: row.is_active,
  };
  dialogOpen.value = true;
}

async function save(): Promise<void> {
  if (!form.value.name.trim()) {
    Notify.create({ type: 'warning', message: 'Nombre requerido.' });
    return;
  }

  if (editId.value) {
    await patchInventoryWarehouse(editId.value, {
      name: form.value.name,
      code: form.value.code,
      is_active: form.value.is_active,
    });
    Notify.create({ type: 'positive', message: 'Almacén actualizado.' });
  } else {
    await createInventoryWarehouse({
      name: form.value.name,
      code: form.value.code,
    });
    Notify.create({ type: 'positive', message: 'Almacén creado.' });
  }
  dialogOpen.value = false;
  await reload();
}

async function bulkSetActive(isActive: boolean): Promise<void> {
  if (!selected.value.length) return;
  await Promise.all(selected.value.map((row) => patchInventoryWarehouse(row.id, { is_active: isActive })));
  Notify.create({
    type: 'positive',
    message: isActive ? 'Almacenes activados.' : 'Almacenes desactivados.',
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
