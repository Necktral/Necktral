<template>
  <AppContainer>
    <AppPageHeader
      :title="labels.inventory + ' · Dashboard operativo'"
      subtitle="Operación avanzada de inventario con cola offline, atajos y acciones rápidas."
    >
      <template #badges>
        <q-badge outline color="primary">Permiso lectura: inventory.balance.read</q-badge>
        <q-badge outline v-if="canItemRead">Permiso ítems: inventory.item.read</q-badge>
        <q-badge outline v-if="canWarehouseManage">Permiso almacenes: inventory.warehouse.create</q-badge>
      </template>

      <template #actions>
        <q-btn flat icon="keyboard_command_key" label="Comandos (Ctrl/Cmd+K)" @click="paletteOpen = true" />
        <q-btn color="primary" icon="bolt" label="Acción rápida" :disable="!canOperate" @click="quickOpen = true" />
      </template>
    </AppPageHeader>

    <q-banner v-if="!canRead" class="q-mt-md" dense rounded>
      No tienes permiso de lectura de inventario en la empresa activa.
    </q-banner>

    <div v-else class="row q-col-gutter-md q-mt-md">
      <div class="col-12 col-md-6 col-lg-4">
        <q-card class="app-card">
          <q-card-section>
            <div class="text-subtitle1">Catálogo de ítems</div>
            <div class="text-caption text-grey-7">Gestión, filtro avanzado, vistas guardadas y acciones masivas.</div>
          </q-card-section>
          <q-card-actions align="right">
            <q-btn flat icon="category" label="Abrir" :to="routes.inventoryItems" />
          </q-card-actions>
        </q-card>
      </div>

      <div class="col-12 col-md-6 col-lg-4">
        <q-card class="app-card">
          <q-card-section>
            <div class="text-subtitle1">Almacenes y balances</div>
            <div class="text-caption text-grey-7">Monitorea stock, costo promedio y estado por sucursal.</div>
          </q-card-section>
          <q-card-actions align="right">
            <q-btn flat icon="warehouse" label="Almacenes" :to="routes.inventoryWarehouses" />
            <q-btn flat icon="balance" label="Balances" :to="routes.inventoryBalances" />
          </q-card-actions>
        </q-card>
      </div>

      <div class="col-12 col-md-6 col-lg-4">
        <q-card class="app-card">
          <q-card-section>
            <div class="text-subtitle1">Movimientos y Kardex</div>
            <div class="text-caption text-grey-7">Entradas, salidas, ajustes, transferencias y trazabilidad contable.</div>
          </q-card-section>
          <q-card-actions align="right">
            <q-btn flat icon="swap_horiz" label="Movimientos" :to="routes.inventoryMovements" />
            <q-btn flat icon="receipt_long" label="Kardex" :to="routes.inventoryKardex" />
          </q-card-actions>
        </q-card>
      </div>

      <div class="col-12">
        <InventoryQueueCenter />
      </div>
    </div>

    <q-dialog v-model="quickOpen">
      <q-card style="width: 760px; max-width: 96vw" class="app-card">
        <q-card-section class="row items-center justify-between">
          <div class="text-h6">Acción rápida inventario</div>
          <q-btn flat icon="close" v-close-popup />
        </q-card-section>

        <q-separator />

        <q-card-section>
          <q-tabs v-model="quickType" dense align="justify" active-color="primary" indicator-color="primary">
            <q-tab name="INVENTORY.MOVEMENT.RECEIVE" label="Entrada" />
            <q-tab name="INVENTORY.MOVEMENT.ISSUE" label="Salida" />
            <q-tab name="INVENTORY.MOVEMENT.ADJUST" label="Ajuste" />
            <q-tab name="INVENTORY.TRANSFER" label="Transferencia" />
          </q-tabs>

          <q-form class="q-mt-md" @submit.prevent="queueQuickCommand">
            <div class="row q-col-gutter-md">
              <div class="col-12 col-md-6" v-if="quickType !== 'INVENTORY.TRANSFER'">
                <q-select
                  v-model="quickForm.warehouse_id"
                  :options="warehouseOptions"
                  emit-value
                  map-options
                  outlined
                  option-label="label"
                  option-value="value"
                  label="Almacén"
                />
              </div>
              <div class="col-12 col-md-6" v-if="quickType === 'INVENTORY.TRANSFER'">
                <q-select
                  v-model="quickForm.from_warehouse_id"
                  :options="warehouseOptions"
                  emit-value
                  map-options
                  outlined
                  option-label="label"
                  option-value="value"
                  label="Desde almacén"
                />
              </div>
              <div class="col-12 col-md-6" v-if="quickType === 'INVENTORY.TRANSFER'">
                <q-select
                  v-model="quickForm.to_warehouse_id"
                  :options="warehouseOptions"
                  emit-value
                  map-options
                  outlined
                  option-label="label"
                  option-value="value"
                  label="Hacia almacén"
                />
              </div>

              <div class="col-12 col-md-6">
                <q-select
                  v-model="quickForm.item_id"
                  :options="itemOptions"
                  emit-value
                  map-options
                  outlined
                  option-label="label"
                  option-value="value"
                  label="Ítem"
                />
              </div>
            </div>

            <div class="row q-col-gutter-md q-mt-sm">
              <div class="col-12 col-md-4" v-if="quickType !== 'INVENTORY.MOVEMENT.ADJUST'">
                <q-input v-model="quickForm.qty" outlined label="Cantidad" />
              </div>
              <div class="col-12 col-md-4" v-if="quickType === 'INVENTORY.MOVEMENT.RECEIVE'">
                <q-input v-model="quickForm.unit_cost" outlined label="Costo unitario" />
              </div>
              <div class="col-12 col-md-4" v-if="quickType === 'INVENTORY.MOVEMENT.ADJUST'">
                <q-input v-model="quickForm.new_qty_on_hand" outlined label="Nuevo qty en mano" />
              </div>
            </div>

            <div class="q-mt-md inventory-sticky-actionbar">
              <q-btn color="primary" type="submit" icon="queue" label="Enviar a cola" class="inventory-touch-target" />
              <q-btn flat icon="sync" label="Flush" class="inventory-touch-target" @click.prevent="flushNow" />
            </div>
          </q-form>
        </q-card-section>
      </q-card>
    </q-dialog>

    <InventoryCommandPalette v-model="paletteOpen" />
  </AppContainer>
</template>

<script setup lang="ts">
import { isAxiosError } from 'axios';
import { Notify } from 'quasar';
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';

import InventoryCommandPalette from 'src/modules/inventory/components/InventoryCommandPalette.vue';
import InventoryQueueCenter from 'src/modules/inventory/components/InventoryQueueCenter.vue';
import { useInventoryOfflineStore } from 'src/modules/inventory/stores/inventory-offline.store';
import { listInventoryItems, listInventoryWarehouses } from 'src/services/inventory.service';
import { BUSINESS_LABELS, UI_ROUTE_PATHS } from 'src/shared/ui/business-terms';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';
import AppContainer from 'src/ui/AppContainer.vue';
import AppPageHeader from 'src/ui/AppPageHeader.vue';

const labels = BUSINESS_LABELS;
const routes = UI_ROUTE_PATHS;

const acl = useAclStore();
const ctx = useContextStore();
const offline = useInventoryOfflineStore();

const quickOpen = ref(false);
const paletteOpen = ref(false);

type QuickType =
  | 'INVENTORY.MOVEMENT.RECEIVE'
  | 'INVENTORY.MOVEMENT.ISSUE'
  | 'INVENTORY.MOVEMENT.ADJUST'
  | 'INVENTORY.TRANSFER';

const quickType = ref<QuickType>('INVENTORY.MOVEMENT.RECEIVE');

const quickForm = ref({
  warehouse_id: null as number | null,
  from_warehouse_id: null as number | null,
  to_warehouse_id: null as number | null,
  item_id: null as number | null,
  qty: '1.0000',
  unit_cost: '0.000000',
  new_qty_on_hand: '0.0000',
});

const warehouseOptions = ref<Array<{ label: string; value: number }>>([]);
const itemOptions = ref<Array<{ label: string; value: number }>>([]);

const canRead = computed(() => {
  const companyId = ctx.activeCompanyId;
  if (!companyId) return false;
  return acl.hasPermission(companyId, 'inventory.balance.read');
});

const canItemRead = computed(() => {
  const companyId = ctx.activeCompanyId;
  if (!companyId) return false;
  return acl.hasPermission(companyId, 'inventory.item.read');
});

const canWarehouseManage = computed(() => {
  const companyId = ctx.activeCompanyId;
  if (!companyId) return false;
  return acl.hasPermission(companyId, 'inventory.warehouse.create');
});

const canOperate = computed(() => {
  const companyId = ctx.activeCompanyId;
  if (!companyId) return false;
  return (
    acl.hasPermission(companyId, 'inventory.movement.receive') ||
    acl.hasPermission(companyId, 'inventory.movement.issue') ||
    acl.hasPermission(companyId, 'inventory.movement.adjust') ||
    acl.hasPermission(companyId, 'inventory.transfer.create') ||
    acl.hasPermission(companyId, 'inventory.movement.post')
  );
});

function randomKey(prefix: string): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return prefix + '-' + crypto.randomUUID();
  }
  return prefix + '-' + String(Date.now()) + '-' + Math.random().toString(16).slice(2);
}

function commandPayload(): Record<string, unknown> {
  switch (quickType.value) {
    case 'INVENTORY.MOVEMENT.RECEIVE':
      return {
        warehouse_id: Number(quickForm.value.warehouse_id),
        item_id: Number(quickForm.value.item_id),
        qty: quickForm.value.qty,
        unit_cost: quickForm.value.unit_cost,
      };
    case 'INVENTORY.MOVEMENT.ISSUE':
      return {
        warehouse_id: Number(quickForm.value.warehouse_id),
        item_id: Number(quickForm.value.item_id),
        qty: quickForm.value.qty,
      };
    case 'INVENTORY.MOVEMENT.ADJUST':
      return {
        warehouse_id: Number(quickForm.value.warehouse_id),
        item_id: Number(quickForm.value.item_id),
        new_qty_on_hand: quickForm.value.new_qty_on_hand,
      };
    default:
      return {
        from_warehouse_id: Number(quickForm.value.from_warehouse_id),
        to_warehouse_id: Number(quickForm.value.to_warehouse_id),
        item_id: Number(quickForm.value.item_id),
        qty: quickForm.value.qty,
      };
  }
}

async function queueQuickCommand() {
  if (!ctx.activeCompanyId) return;
  const idempotency = randomKey('inv');

  await offline.enqueue({
    type: quickType.value,
    payload: commandPayload(),
    idempotency_key: idempotency,
  });

  Notify.create({ type: 'positive', message: 'Comando agregado a cola offline.' });

  if (navigator.onLine) {
    await offline.flush();
  }
}

async function flushNow() {
  await offline.flush();
}

async function loadOptions() {
  if (!ctx.activeCompanyId || !canRead.value) return;

  try {
    const [items, warehouses] = await Promise.all([
      listInventoryItems({ limit: 200, offset: 0, is_active: true }),
      listInventoryWarehouses({ limit: 200, offset: 0, is_active: true }),
    ]);

    itemOptions.value = items.results.map((row) => ({
      label: row.sku + ' · ' + row.name,
      value: row.id,
    }));

    warehouseOptions.value = warehouses.results.map((row) => ({
      label: (row.code || '-') + ' · ' + row.name,
      value: row.id,
    }));
  } catch (error: unknown) {
    if (isAxiosError(error)) {
      const status = error.response?.status;
      if (status === 401 || status === 403) return;
    }
    Notify.create({ type: 'warning', message: 'No se pudieron cargar catálogos de inventario.' });
  }
}

function onOnline() {
  void offline.flush();
}

onMounted(() => {
  window.addEventListener('online', onOnline);
});

onUnmounted(() => {
  window.removeEventListener('online', onOnline);
});

watch(
  () => [ctx.activeCompanyId, ctx.activeBranchId, canRead.value] as const,
  ([companyId, branchId, canReadNow]) => {
    if (!companyId || !canReadNow) return;
    void offline.loadScope(companyId, branchId);
    void loadOptions();
  },
  { immediate: true },
);
</script>
