<template>
  <q-page class="q-pa-md inventory-page">
    <div class="row items-center q-col-gutter-md q-mb-md">
      <div class="col-12 col-md-8">
        <div class="text-h5">Inventarios</div>
        <div class="text-caption text-grey-7">
          {{ isMobileExperience ? 'Taskflow movil' : 'Workbench desktop' }} · flujo `read/capture/commit`
        </div>
      </div>
      <div class="col-12 col-md-4 text-right">
        <q-btn color="primary" icon="refresh" :loading="loadingRead" @click="onRead">Recargar</q-btn>
      </div>
    </div>

    <q-banner v-if="errorMessage" class="bg-red-1 text-red-10 q-mb-md" rounded>
      {{ errorMessage }}
    </q-banner>

    <div class="row q-col-gutter-md q-mb-md">
      <div class="col-12 col-md-4">
        <q-select
          v-model="selectedWarehouseId"
          :options="warehouseOptions"
          option-value="value"
          option-label="label"
          emit-value
          map-options
          label="Bodega"
          dense
        />
      </div>
      <div class="col-12 col-md-5">
        <q-select
          v-model="selectedItemId"
          :options="itemOptions"
          option-value="value"
          option-label="label"
          emit-value
          map-options
          use-input
          input-debounce="250"
          label="Item"
          dense
          @filter="onItemFilter"
        />
      </div>
      <div class="col-12 col-md-3">
        <q-input v-model="historyLimit" type="number" min="1" max="50" label="Historial (max 50)" dense />
      </div>
    </div>

    <template v-if="!isMobileExperience">
      <div class="row q-col-gutter-md">
        <div class="col-12 col-lg-4">
          <q-card flat bordered>
            <q-card-section>
              <div class="text-subtitle1 q-mb-sm">Balance actual</div>
              <div class="text-h6">{{ balance.qty_on_hand }}</div>
              <div class="text-caption text-grey-7">Costo promedio: {{ balance.avg_cost }}</div>
            </q-card-section>
          </q-card>

          <q-card flat bordered class="q-mt-md">
            <q-card-section>
              <div class="text-subtitle1 q-mb-sm">Captura de movimiento</div>
              <q-btn-toggle
                v-model="captureType"
                class="q-mb-md"
                spread
                dense
                toggle-color="primary"
                :options="[
                  { label: 'Receive', value: 'RECEIVE' },
                  { label: 'Issue', value: 'ISSUE' },
                ]"
              />

              <q-input v-model="captureQty" label="Cantidad" dense class="q-mb-sm" />
              <q-input
                v-if="captureType === 'RECEIVE'"
                v-model="captureUnitCost"
                label="Costo unitario"
                dense
                class="q-mb-sm"
              />
              <q-input v-model="captureNote" label="Nota" dense class="q-mb-md" />

              <q-btn
                color="primary"
                icon="check"
                :loading="loadingCommit"
                :disable="!canCommit"
                @click="onCommit"
              >
                Confirmar commit
              </q-btn>
            </q-card-section>
          </q-card>
        </div>

        <div class="col-12 col-lg-8">
          <q-card flat bordered>
            <q-card-section>
              <div class="text-subtitle1">Historial corto</div>
            </q-card-section>
            <q-separator />
            <q-table
              flat
              dense
              :rows="movements"
              :columns="movementColumns"
              row-key="id"
              :rows-per-page-options="[10, 20, 50]"
            />
          </q-card>
        </div>
      </div>
    </template>

    <template v-else>
      <q-stepper v-model="taskflowStep" flat bordered animated>
        <q-step :name="1" title="Seleccion" icon="inventory_2" :done="taskflowStep > 1">
          <div class="text-body2 q-mb-md">Selecciona bodega e item y carga lectura operativa.</div>
          <q-btn color="primary" :loading="loadingRead" :disable="!canRead" @click="onRead">Continuar</q-btn>
        </q-step>

        <q-step :name="2" title="Captura" icon="edit_note" :done="taskflowStep > 2">
          <q-btn-toggle
            v-model="captureType"
            class="q-mb-md"
            spread
            dense
            toggle-color="primary"
            :options="[
              { label: 'Receive', value: 'RECEIVE' },
              { label: 'Issue', value: 'ISSUE' },
            ]"
          />
          <q-input v-model="captureQty" label="Cantidad" dense class="q-mb-sm" />
          <q-input
            v-if="captureType === 'RECEIVE'"
            v-model="captureUnitCost"
            label="Costo unitario"
            dense
            class="q-mb-sm"
          />
          <q-input v-model="captureNote" label="Nota" dense class="q-mb-md" />
          <q-btn color="primary" :disable="!canCommit" @click="taskflowStep = 3">Revisar</q-btn>
        </q-step>

        <q-step :name="3" title="Confirmacion" icon="verified">
          <q-list dense bordered>
            <q-item><q-item-section>Operacion: {{ captureType }}</q-item-section></q-item>
            <q-item><q-item-section>Cantidad: {{ captureQty || '-' }}</q-item-section></q-item>
            <q-item v-if="captureType === 'RECEIVE'">
              <q-item-section>Costo unitario: {{ captureUnitCost || '-' }}</q-item-section>
            </q-item>
            <q-item><q-item-section>Nota: {{ captureNote || '-' }}</q-item-section></q-item>
            <q-item><q-item-section>Balance actual: {{ balance.qty_on_hand }}</q-item-section></q-item>
          </q-list>

          <div class="q-mt-md row q-col-gutter-sm">
            <div class="col-auto">
              <q-btn flat @click="taskflowStep = 2">Volver</q-btn>
            </div>
            <div class="col-auto">
              <q-btn color="primary" :loading="loadingCommit" :disable="!canCommit" @click="onCommit">
                Ejecutar commit
              </q-btn>
            </div>
          </div>
        </q-step>
      </q-stepper>
    </template>

    <q-card flat bordered class="q-mt-md">
      <q-card-section class="row items-center q-col-gutter-sm">
        <div class="col">
          <div class="text-subtitle1">Sincronización offline</div>
          <div class="text-caption text-grey-7">
            Pendientes: {{ offlineStats.pending }} · Reintento: {{ offlineStats.failed_retryable }} ·
            Final: {{ offlineStats.failed_final }}
          </div>
        </div>
        <div class="col-auto">
          <q-btn
            color="primary"
            icon="sync"
            :loading="queueLoading"
            :disable="offlineStats.due_now === 0 && offlineStats.failed_final === 0"
            @click="processOfflineQueueAction"
          >
            Procesar cola
          </q-btn>
        </div>
      </q-card-section>
      <q-separator />
      <q-card-section>
        <q-markup-table flat dense>
          <thead>
            <tr>
              <th class="text-left">Creado</th>
              <th class="text-left">Tipo</th>
              <th class="text-left">Estado</th>
              <th class="text-left">Error</th>
              <th class="text-right">Acción</th>
            </tr>
          </thead>
          <tbody>
            <tr v-for="row in offlineCommands.slice(0, 8)" :key="row.id">
              <td class="text-left">{{ row.created_at }}</td>
              <td class="text-left">{{ row.kind }}</td>
              <td class="text-left">
                <q-badge :color="offlineStatusColor(row.status)" outline>{{ row.status }}</q-badge>
              </td>
              <td class="text-left">{{ row.last_error || '-' }}</td>
              <td class="text-right">
                <q-btn
                  flat
                  dense
                  color="primary"
                  label="Reintentar"
                  :disable="row.status !== 'FAILED_FINAL'"
                  @click="retryFailedFinalAction(row.id)"
                />
              </td>
            </tr>
            <tr v-if="offlineCommands.length === 0">
              <td colspan="5" class="text-center text-grey-7 q-pa-sm">Sin comandos offline.</td>
            </tr>
          </tbody>
        </q-markup-table>
      </q-card-section>
    </q-card>

    <q-banner v-if="lastCommitMessage" class="bg-green-1 text-green-10 q-mt-md" rounded>
      {{ lastCommitMessage }}
    </q-banner>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { useSessionBootstrapStore } from 'src/stores/session-bootstrap.store';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';
import {
  canAccessInventoryModule,
  createIdempotencyKey,
  resolveInventoryShellExperience,
} from 'src/features/inventory/inventory-shell';
import { commitInventoryWithOfflineFallback } from 'src/features/inventory/inventory-commit';
import {
  drainInventoryOfflineQueue,
  getInventoryOfflineQueueStats,
  listInventoryOfflineCommands,
  retryFinalInventoryOfflineCommand,
  type InventoryOfflineCommand,
  type InventoryOfflineQueueStats,
} from 'src/services/inventory-offline-queue';
import { executeInventoryOfflineCommandSync } from 'src/services/inventory-offline-sync';
import {
  getInventoryBalance,
  issueInventory,
  listInventoryItems,
  listInventoryMovements,
  listInventoryWarehouses,
  receiveInventory,
  type InventoryBalance,
  type InventoryItem,
  type InventoryMovement,
  type InventoryWarehouse,
} from 'src/services/inventory.service';

const sessionBootstrap = useSessionBootstrapStore();
const acl = useAclStore();
const ctx = useContextStore();

const warehouses = ref<InventoryWarehouse[]>([]);
const items = ref<InventoryItem[]>([]);
const movements = ref<InventoryMovement[]>([]);
const balance = ref<InventoryBalance>({ qty_on_hand: '0.0000', avg_cost: '0.000000' });

const selectedWarehouseId = ref<number | null>(null);
const selectedItemId = ref<number | null>(null);
const historyLimit = ref<string>('20');

const captureType = ref<'RECEIVE' | 'ISSUE'>('RECEIVE');
const captureQty = ref('');
const captureUnitCost = ref('');
const captureNote = ref('');

const loadingRead = ref(false);
const loadingCommit = ref(false);
const queueLoading = ref(false);
const errorMessage = ref('');
const lastCommitMessage = ref('');
const taskflowStep = ref(1);
const offlineCommands = ref<InventoryOfflineCommand[]>([]);
const offlineStats = ref<InventoryOfflineQueueStats>({
  total: 0,
  pending: 0,
  syncing: 0,
  applied: 0,
  failed_retryable: 0,
  failed_final: 0,
  due_now: 0,
});

const queueIntervalMs = 15000;
let queueTimer: number | null = null;

const shellExperience = computed(() =>
  resolveInventoryShellExperience(sessionBootstrap.payload?.shell_mode ?? 'desktop'),
);
const isMobileExperience = computed(() => shellExperience.value === 'taskflow');

const canRead = computed(() => !!selectedWarehouseId.value && !!selectedItemId.value);
const canCommit = computed(() => {
  if (!canRead.value || !captureQty.value) return false;
  if (captureType.value === 'RECEIVE') return !!captureUnitCost.value;
  return true;
});

const warehouseOptions = computed(() =>
  warehouses.value.map((row) => ({ value: row.id, label: `${row.code || 'WH'} · ${row.name}` })),
);
const itemOptions = computed(() =>
  items.value.map((row) => ({ value: row.id, label: `${row.sku} · ${row.name}` })),
);

const movementColumns = [
  { name: 'created_at', label: 'Fecha', field: 'created_at', align: 'left' as const },
  { name: 'movement_type', label: 'Tipo', field: 'movement_type', align: 'left' as const },
  { name: 'qty_delta', label: 'Cantidad', field: 'qty_delta', align: 'right' as const },
  { name: 'unit_cost', label: 'Costo', field: 'unit_cost', align: 'right' as const },
  { name: 'note', label: 'Nota', field: 'note', align: 'left' as const },
];

function asErrorMessage(cause: unknown): string {
  if (typeof cause === 'object' && cause !== null) {
    const response = (cause as { response?: { data?: { error?: { message?: string } } } }).response;
    const msg = response?.data?.error?.message;
    if (msg) return msg;
  }
  if (cause instanceof Error) return cause.message;
  return String(cause);
}

function offlineStatusColor(status: InventoryOfflineCommand['status']): string {
  if (status === 'APPLIED') return 'positive';
  if (status === 'SYNCING') return 'info';
  if (status === 'FAILED_RETRYABLE') return 'warning';
  if (status === 'FAILED_FINAL') return 'negative';
  return 'grey-8';
}

function refreshOfflineQueueSnapshot() {
  offlineCommands.value = listInventoryOfflineCommands();
  offlineStats.value = getInventoryOfflineQueueStats();
}

function buildCommitPayload() {
  const warehouseId = Number(selectedWarehouseId.value);
  const itemId = Number(selectedItemId.value);
  if (!warehouseId || !itemId) {
    throw new Error('Selecciona bodega e item antes de confirmar.');
  }

  return {
    warehouse_id: warehouseId,
    item_id: itemId,
    qty: captureQty.value,
    note: captureNote.value,
    idempotency_key: createIdempotencyKey(captureType.value === 'RECEIVE' ? 'receive' : 'issue'),
    ...(captureType.value === 'RECEIVE' ? { unit_cost: captureUnitCost.value } : {}),
  };
}

async function loadCatalog(): Promise<void> {
  const [warehouseRows, itemRows] = await Promise.all([
    listInventoryWarehouses(),
    listInventoryItems({ limit: 20 }),
  ]);
  warehouses.value = warehouseRows;
  items.value = itemRows;

  if (!selectedWarehouseId.value && warehouseRows.length > 0) {
    selectedWarehouseId.value = warehouseRows[0]?.id ?? null;
  }
  if (!selectedItemId.value && itemRows.length > 0) {
    selectedItemId.value = itemRows[0]?.id ?? null;
  }
}

async function onItemFilter(value: string, update: (callbackFn: () => void) => void) {
  update(() => {
    void listInventoryItems({ q: value, limit: 20 }).then((rows) => {
      items.value = rows;
    });
  });
}

async function onRead() {
  if (!canRead.value) return;

  loadingRead.value = true;
  errorMessage.value = '';
  try {
    const warehouse_id = Number(selectedWarehouseId.value);
    const item_id = Number(selectedItemId.value);
    const limit = Math.min(Math.max(Number(historyLimit.value || '20'), 1), 50);

    const [balanceRow, movementRows] = await Promise.all([
      getInventoryBalance({ warehouse_id, item_id }),
      listInventoryMovements({ warehouse_id, item_id, limit }),
    ]);

    balance.value = balanceRow;
    movements.value = movementRows;

    if (isMobileExperience.value) {
      taskflowStep.value = 2;
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'No se pudo cargar inventario.';
  } finally {
    loadingRead.value = false;
  }
}

async function onCommit() {
  if (!canCommit.value) return;

  loadingCommit.value = true;
  errorMessage.value = '';
  lastCommitMessage.value = '';
  try {
    const payload = buildCommitPayload();
    const outcome = await commitInventoryWithOfflineFallback({
      kind: captureType.value,
      payload,
      companyId: Number(ctx.activeCompanyId || 0),
      branchId: Number(ctx.activeBranchId || 0),
      isOnline: navigator.onLine,
      onlineCommit: async (kind, movementPayload) => {
        if (kind === 'RECEIVE') {
          await receiveInventory(movementPayload);
        } else {
          await issueInventory(movementPayload);
        }
      },
    });

    if (outcome.mode === 'OFFLINE_QUEUED') {
      refreshOfflineQueueSnapshot();
      lastCommitMessage.value = outcome.duplicate
        ? `Operacion ya estaba en cola offline (${captureType.value}).`
        : `Operacion encolada offline (${captureType.value}). Se sincronizara al reconectar.`;
      captureQty.value = '';
      captureUnitCost.value = '';
      captureNote.value = '';
      if (isMobileExperience.value) {
        taskflowStep.value = 1;
      }
      return;
    }

    await onRead();
    lastCommitMessage.value = `Commit ejecutado: ${captureType.value} aplicado correctamente.`;

    captureQty.value = '';
    captureUnitCost.value = '';
    captureNote.value = '';
    if (isMobileExperience.value) {
      taskflowStep.value = 1;
    }
  } catch (error) {
    errorMessage.value = asErrorMessage(error);
  } finally {
    loadingCommit.value = false;
  }
}

async function processOfflineQueueAction() {
  if (queueLoading.value) return;
  queueLoading.value = true;
  try {
    const result = await drainInventoryOfflineQueue({
      maxCommands: 20,
      executor: async (command) => executeInventoryOfflineCommandSync(command),
    });
    refreshOfflineQueueSnapshot();
    if (result.succeeded > 0 && canRead.value) {
      await onRead();
    }
    if (result.failed_final > 0) {
      errorMessage.value = `Cola procesada con ${result.failed_final} comando(s) en FAILED_FINAL.`;
    }
  } catch (error) {
    errorMessage.value = asErrorMessage(error);
  } finally {
    queueLoading.value = false;
  }
}

function retryFailedFinalAction(commandId: string) {
  const row = retryFinalInventoryOfflineCommand(commandId);
  if (row) {
    refreshOfflineQueueSnapshot();
    lastCommitMessage.value = 'Comando marcado para reintento manual.';
    void processOfflineQueueAction();
  }
}

function onOnline() {
  refreshOfflineQueueSnapshot();
  if (offlineStats.value.due_now > 0) {
    void processOfflineQueueAction();
  }
}

onMounted(async () => {
  const companyId = ctx.activeCompanyId;
  const canAccess = canAccessInventoryModule({
    allowedModules: sessionBootstrap.payload?.allowed_modules ?? [],
    hasBasePermission: !!companyId && acl.hasPermission(companyId, 'inventory.balance.read'),
  });
  if (!canAccess) {
    errorMessage.value = 'Modulo de inventarios no habilitado en bootstrap.';
    return;
  }

  refreshOfflineQueueSnapshot();
  window.addEventListener('online', onOnline);
  queueTimer = window.setInterval(() => {
    refreshOfflineQueueSnapshot();
    if (offlineStats.value.due_now > 0) {
      void processOfflineQueueAction();
    }
  }, queueIntervalMs);

  loadingRead.value = true;
  errorMessage.value = '';
  try {
    await loadCatalog();
    await processOfflineQueueAction();
    if (canRead.value) {
      await onRead();
    }
  } catch (error) {
    errorMessage.value = error instanceof Error ? error.message : 'No se pudo inicializar inventarios.';
  } finally {
    loadingRead.value = false;
  }
});

onUnmounted(() => {
  window.removeEventListener('online', onOnline);
  if (queueTimer !== null) {
    window.clearInterval(queueTimer);
    queueTimer = null;
  }
});
</script>

<style scoped>
.inventory-page {
  max-width: 1280px;
  margin: 0 auto;
}
</style>
