<template>
  <AppContainer>
    <AppPageHeader
      :title="labels.inventory + ' · Movimientos'"
      subtitle="Registro táctil y por teclado de entradas, salidas, ajustes y transferencias."
    >
      <template #actions>
        <q-btn flat icon="sync" label="Sincronizar" :loading="offline.syncing" @click="flushNow" />
      </template>
    </AppPageHeader>

    <div class="q-mt-md">
      <q-card class="app-card">
        <q-card-section>
          <q-tabs v-model="movementType" dense align="justify" active-color="primary" indicator-color="primary">
            <q-tab name="INVENTORY.MOVEMENT.RECEIVE" label="Entrada" />
            <q-tab name="INVENTORY.MOVEMENT.ISSUE" label="Salida" />
            <q-tab name="INVENTORY.MOVEMENT.ADJUST" label="Ajuste" />
            <q-tab name="INVENTORY.TRANSFER" label="Transferencia" />
          </q-tabs>

          <q-form class="q-mt-md" @submit.prevent="queueMovement">
            <div class="row q-col-gutter-md">
              <div class="col-12 col-md-4" v-if="movementType !== 'INVENTORY.TRANSFER'">
                <q-select
                  v-model="form.warehouse_id"
                  :options="warehouseOptions"
                  emit-value
                  map-options
                  outlined
                  option-label="label"
                  option-value="value"
                  label="Almacén"
                />
              </div>
              <div class="col-12 col-md-4" v-if="movementType === 'INVENTORY.TRANSFER'">
                <q-select
                  v-model="form.from_warehouse_id"
                  :options="warehouseOptions"
                  emit-value
                  map-options
                  outlined
                  option-label="label"
                  option-value="value"
                  label="Desde almacén"
                />
              </div>
              <div class="col-12 col-md-4" v-if="movementType === 'INVENTORY.TRANSFER'">
                <q-select
                  v-model="form.to_warehouse_id"
                  :options="warehouseOptions"
                  emit-value
                  map-options
                  outlined
                  option-label="label"
                  option-value="value"
                  label="Hacia almacén"
                />
              </div>
              <div class="col-12 col-md-4">
                <q-select
                  v-model="form.item_id"
                  :options="itemOptions"
                  emit-value
                  map-options
                  outlined
                  option-label="label"
                  option-value="value"
                  label="Ítem"
                />
              </div>
              <div class="col-12 col-md-4" v-if="movementType !== 'INVENTORY.MOVEMENT.ADJUST'">
                <q-input v-model="form.qty" outlined label="Cantidad" />
              </div>
              <div class="col-12 col-md-4" v-if="movementType === 'INVENTORY.MOVEMENT.RECEIVE'">
                <q-input v-model="form.unit_cost" outlined label="Costo unitario" />
              </div>
              <div class="col-12 col-md-4" v-if="movementType === 'INVENTORY.MOVEMENT.ADJUST'">
                <q-input v-model="form.new_qty_on_hand" outlined label="Nuevo qty en mano" />
              </div>
            </div>

            <div class="q-mt-sm">
              <q-input v-model="form.note" outlined label="Nota (opcional)" />
            </div>

            <div class="q-mt-md inventory-sticky-actionbar">
              <q-btn color="primary" icon="queue" type="submit" label="Enviar a cola (Ctrl+Enter)" class="inventory-touch-target" @keydown.ctrl.enter.prevent="queueMovement" />
              <q-btn flat icon="undo" label="Deshacer último pendiente" :disable="!lastPendingId" class="inventory-touch-target" @click="undoLastPending" />
            </div>
          </q-form>
        </q-card-section>
      </q-card>
    </div>

    <div class="q-mt-md">
      <AppDataTable
        title="Cola de movimientos"
        caption="Reintentos automáticos con deduplicación por idempotency_key."
        :rows="offline.queue"
        :columns="queueColumns"
        row-key="id"
        :rows-per-page-options="[20, 50]"
      >
        <template #body-cell-status="props">
          <q-td :props="props">
            <q-badge
              outline
              :color="
                props.row.status === 'CONFLICT'
                  ? 'negative'
                  : props.row.status === 'DONE'
                    ? 'positive'
                    : 'primary'
              "
            >
              {{ props.row.status }}
            </q-badge>
          </q-td>
        </template>

        <template #body-cell-actions="props">
          <q-td :props="props" class="text-right">
            <q-btn dense flat icon="replay" :disable="props.row.status !== 'CONFLICT'" @click="retry(props.row.id)" />
            <q-btn dense flat icon="task_alt" :disable="props.row.status !== 'CONFLICT'" @click="markDone(props.row.id)" />
            <q-btn dense flat icon="delete" :disable="props.row.status !== 'PENDING' && props.row.status !== 'RETRYING'" @click="removePending(props.row.id)" />
          </q-td>
        </template>
      </AppDataTable>
    </div>
  </AppContainer>
</template>

<script setup lang="ts">
import { Notify } from 'quasar';
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import type { QTableColumn } from 'quasar';

import { useInventoryOfflineStore } from 'src/modules/inventory/stores/inventory-offline.store';
import { listInventoryItems, listInventoryWarehouses } from 'src/services/inventory.service';
import { BUSINESS_LABELS } from 'src/shared/ui/business-terms';
import { useContextStore } from 'src/stores/context.store';
import AppContainer from 'src/ui/AppContainer.vue';
import AppDataTable from 'src/ui/AppDataTable.vue';
import AppPageHeader from 'src/ui/AppPageHeader.vue';

type MovementType =
  | 'INVENTORY.MOVEMENT.RECEIVE'
  | 'INVENTORY.MOVEMENT.ISSUE'
  | 'INVENTORY.MOVEMENT.ADJUST'
  | 'INVENTORY.TRANSFER';

const labels = BUSINESS_LABELS;
const ctx = useContextStore();
const offline = useInventoryOfflineStore();

const movementType = ref<MovementType>('INVENTORY.MOVEMENT.RECEIVE');

const form = ref({
  warehouse_id: null as number | null,
  from_warehouse_id: null as number | null,
  to_warehouse_id: null as number | null,
  item_id: null as number | null,
  qty: '1.0000',
  unit_cost: '0.000000',
  new_qty_on_hand: '0.0000',
  note: '',
});

const warehouseOptions = ref<Array<{ label: string; value: number }>>([]);
const itemOptions = ref<Array<{ label: string; value: number }>>([]);

const queueColumns: QTableColumn[] = [
  { name: 'type', label: 'Tipo', field: 'type', align: 'left' },
  { name: 'status', label: 'Estado', field: 'status', align: 'left' },
  { name: 'attempts', label: 'Intentos', field: 'attempts', align: 'left' },
  { name: 'last_error_code', label: 'Error', field: 'last_error_code', align: 'left' },
  { name: 'updated_at', label: 'Actualizado', field: 'updated_at', align: 'left' },
  { name: 'actions', label: 'Acciones', field: 'actions', align: 'right' },
];

const lastPendingId = computed(() => {
  const pending = offline.queue.filter((row) => row.status === 'PENDING' || row.status === 'RETRYING');
  const last = pending[pending.length - 1];
  return last ? last.id : '';
});

function randomKey(prefix: string): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return prefix + '-' + crypto.randomUUID();
  }
  return prefix + '-' + String(Date.now()) + '-' + Math.random().toString(16).slice(2);
}

function movementPayload(): Record<string, unknown> {
  switch (movementType.value) {
    case 'INVENTORY.MOVEMENT.RECEIVE':
      return {
        warehouse_id: Number(form.value.warehouse_id),
        item_id: Number(form.value.item_id),
        qty: form.value.qty,
        unit_cost: form.value.unit_cost,
        note: form.value.note,
      };
    case 'INVENTORY.MOVEMENT.ISSUE':
      return {
        warehouse_id: Number(form.value.warehouse_id),
        item_id: Number(form.value.item_id),
        qty: form.value.qty,
        note: form.value.note,
      };
    case 'INVENTORY.MOVEMENT.ADJUST':
      return {
        warehouse_id: Number(form.value.warehouse_id),
        item_id: Number(form.value.item_id),
        new_qty_on_hand: form.value.new_qty_on_hand,
        note: form.value.note,
      };
    default:
      return {
        from_warehouse_id: Number(form.value.from_warehouse_id),
        to_warehouse_id: Number(form.value.to_warehouse_id),
        item_id: Number(form.value.item_id),
        qty: form.value.qty,
        note: form.value.note,
      };
  }
}

async function queueMovement() {
  if (!ctx.activeCompanyId) return;
  const idempotency = randomKey('inv');
  await offline.enqueue({
    type: movementType.value,
    payload: movementPayload(),
    idempotency_key: idempotency,
  });
  Notify.create({ type: 'positive', message: 'Movimiento en cola offline.' });
  if (navigator.onLine) {
    await offline.flush();
  }
}

async function flushNow() {
  await offline.flush();
}

async function loadOptions() {
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
}

function undoLastPending() {
  if (!lastPendingId.value) return;
  void offline.removePending(lastPendingId.value);
  Notify.create({ type: 'info', message: 'Último comando pendiente removido.' });
}

function retry(id: string) {
  void offline.retryConflict(id);
}

function markDone(id: string) {
  void offline.markConflictAsDone(id);
}

function removePending(id: string) {
  void offline.removePending(id);
}

function onOnline() {
  void offline.flush();
}

watch(movementType, () => {
  form.value.note = '';
});

onMounted(() => {
  if (ctx.activeCompanyId) {
    void offline.loadScope(ctx.activeCompanyId, ctx.activeBranchId);
  }
  void loadOptions();
  window.addEventListener('online', onOnline);
});

onUnmounted(() => {
  window.removeEventListener('online', onOnline);
});
</script>
