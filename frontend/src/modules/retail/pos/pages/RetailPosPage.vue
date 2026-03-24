<template>
  <AppContainer fluid>
    <AppPageHeader
      :title="`${labels.retail} · POS`"
      subtitle="Caja operativa retail sobre Billing, Inventory y Payments/Cash"
    >
      <template #badges>
        <RetailCashSessionBadge :session="bootstrap.data?.active_cash_session ?? null" />
        <RetailFiscalStatusChip :status="checkout.lastCommit?.billing.status ?? ticket.currentTicket?.status ?? null" />
        <q-chip square dense :color="scannerModeEnabled ? 'primary' : 'grey-6'" text-color="white" icon="qr_code_scanner">
          Scanner {{ scannerModeEnabled ? 'ON' : 'OFF' }}
        </q-chip>
        <q-chip
          square
          dense
          :color="offlineQueue.pendingCount > 0 ? 'warning' : 'grey-6'"
          :text-color="offlineQueue.pendingCount > 0 ? 'black' : 'white'"
          icon="sync_problem"
        >
          Cola {{ offlineQueue.pendingCount }}
        </q-chip>
      </template>
      <template #actions>
        <q-btn
          outline
          icon="sync"
          label="Flush cola"
          :disable="offlineQueue.pendingCount === 0 || offlineQueue.syncing"
          :loading="offlineQueue.syncing"
          @click="flushOfflineQueue"
        />
        <q-btn
          outline
          :icon="scannerModeEnabled ? 'qr_code_scanner' : 'qr_code_2'"
          :label="scannerModeEnabled ? 'Scanner ON' : 'Scanner OFF'"
          @click="scannerModeEnabled = !scannerModeEnabled"
        />
        <q-btn outline icon="history" label="Recientes" @click="openRecent" />
        <q-btn
          outline
          icon="restart_alt"
          label="Nuevo ticket"
          :disable="!bootstrap.data?.active_cash_session"
          @click="startNewTicket"
        />
        <q-btn
          color="primary"
          icon="payments"
          label="Checkout"
          :disable="!ticket.currentTicket"
          @click="checkoutOpen = true"
        />
      </template>
    </AppPageHeader>

    <q-banner v-if="bootstrap.error" rounded dense class="bg-negative text-white q-mt-md">
      {{ bootstrap.error }}
    </q-banner>

    <q-banner v-else-if="!bootstrap.data?.active_cash_session" rounded dense class="bg-warning text-black q-mt-md">
      No hay una caja abierta en esta sucursal. Retail exige `CashSession OPEN` antes de vender.
    </q-banner>

    <q-banner v-if="ticket.error || checkout.error || catalog.error" rounded dense class="bg-negative text-white q-mt-md">
      {{ ticket.error || checkout.error || catalog.error }}
    </q-banner>

    <q-banner v-if="checkout.notice" rounded dense class="bg-blue-2 text-black q-mt-md">
      {{ checkout.notice }}
    </q-banner>

    <q-banner
      v-if="offlineQueue.lastSyncError"
      rounded
      dense
      class="bg-orange-2 text-black q-mt-md"
    >
      Cola offline retail: {{ offlineQueue.lastSyncError }}
    </q-banner>

    <q-banner
      v-if="scannerFeedback.message"
      rounded
      dense
      :class="scannerFeedback.kind === 'ok' ? 'bg-positive text-white q-mt-md' : 'bg-warning text-black q-mt-md'"
    >
      {{ scannerFeedback.message }}
    </q-banner>

    <q-banner
      v-if="checkout.preview && !checkout.preview.ok"
      rounded
      dense
      class="bg-orange-2 text-black q-mt-md"
    >
      {{ checkout.preview.blocking_errors.map((row) => row.detail).join(' · ') }}
    </q-banner>

    <div class="retail-pos q-mt-md">
      <div class="retail-pos__main">
        <RetailCatalogPanel
          ref="catalogPanelRef"
          v-model="catalogQuery"
          :items="catalog.results"
          :loading="catalog.loading"
          :error="catalog.error"
          @search="runCatalogSearch"
          @select-item="addCatalogItem"
        />
      </div>

      <div class="retail-pos__side">
        <RetailTicketPanel
          :ticket="ticket.currentTicket"
          :selected-line-id="selectedLineId"
          @checkout="checkoutOpen = true"
          @hold="holdOpen = true"
          @remove-line="removeLine"
          @select-line="selectedLineId = $event"
        />
        <div class="q-mt-md">
          <RetailTotalsBar :ticket="ticket.currentTicket" />
        </div>
        <div class="row q-gutter-sm q-mt-md">
          <q-btn
            outline
            icon="play_arrow"
            label="Reanudar hold"
            :disable="!ticket.activeHold || ticket.activeHold.status !== 'ACTIVE'"
            @click="resumeHold"
          />
          <q-btn
            outline
            color="secondary"
            icon="reply"
            label="Devolver línea"
            :disable="!canOpenReturn"
            @click="returnOpen = true"
          />
        </div>
      </div>
    </div>

    <RetailCheckoutDrawer
      ref="checkoutDrawerRef"
      v-model="checkoutOpen"
      :ticket="ticket.currentTicket"
      :preview="checkout.preview"
      :loading="checkout.loading"
      @preview="previewCheckout"
      @commit="commitCheckout"
      @void="voidTicket"
    />

    <RetailHoldDialog v-model="holdOpen" :loading="ticket.mutating" @confirm="confirmHold" />
    <RetailRecentTicketsDrawer
      v-model="recentOpen"
      :tickets="ticket.recentTickets"
      :loading="ticket.loading"
      @select-ticket="selectRecentTicket"
    />
    <RetailReturnDialog v-model="returnOpen" :loading="checkout.loading" @confirm="processReturn" />
  </AppContainer>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';

import AppContainer from 'src/ui/AppContainer.vue';
import AppPageHeader from 'src/ui/AppPageHeader.vue';
import { BUSINESS_LABELS } from 'src/shared/ui/business-terms';
import { useContextStore } from 'src/stores/context.store';

import RetailCatalogPanel from '../components/RetailCatalogPanel.vue';
import RetailCashSessionBadge from '../components/RetailCashSessionBadge.vue';
import RetailCheckoutDrawer from '../components/RetailCheckoutDrawer.vue';
import RetailFiscalStatusChip from '../components/RetailFiscalStatusChip.vue';
import RetailHoldDialog from '../components/RetailHoldDialog.vue';
import RetailRecentTicketsDrawer from '../components/RetailRecentTicketsDrawer.vue';
import RetailReturnDialog from '../components/RetailReturnDialog.vue';
import RetailTicketPanel from '../components/RetailTicketPanel.vue';
import RetailTotalsBar from '../components/RetailTotalsBar.vue';
import { useRetailScannerInput } from '../composables/useRetailScannerInput';
import { useRetailShortcuts } from '../composables/useRetailShortcuts';
import type { RetailCatalogItem } from '../services/retail-pos.service';
import { useRetailBootstrapStore } from '../stores/useRetailBootstrapStore';
import { useRetailCatalogStore } from '../stores/useRetailCatalogStore';
import { useRetailCheckoutStore } from '../stores/useRetailCheckoutStore';
import { useRetailOfflineQueueStore } from '../stores/useRetailOfflineQueueStore';
import { useRetailTicketStore } from '../stores/useRetailTicketStore';

const labels = BUSINESS_LABELS;
const ctx = useContextStore();
const bootstrap = useRetailBootstrapStore();
const catalog = useRetailCatalogStore();
const ticket = useRetailTicketStore();
const checkout = useRetailCheckoutStore();
const offlineQueue = useRetailOfflineQueueStore();

const catalogQuery = ref('');
const checkoutOpen = ref(false);
const holdOpen = ref(false);
const recentOpen = ref(false);
const returnOpen = ref(false);
const selectedLineId = ref<number | null>(null);
const scannerModeEnabled = ref(true);
const scannerFeedback = ref<{ kind: 'ok' | 'warn'; message: string }>({
  kind: 'ok',
  message: '',
});

const catalogPanelRef = ref<InstanceType<typeof RetailCatalogPanel> | null>(null);
const checkoutDrawerRef = ref<InstanceType<typeof RetailCheckoutDrawer> | null>(null);
let offlineFlushTimer: number | null = null;

const canOpenReturn = computed(
  () => Boolean(ticket.currentSale && selectedLineId.value && ticket.currentTicket?.status === 'CLOSED'),
);

const scanner = useRetailScannerInput({
  enabled: () => scannerModeEnabled.value,
  onScan: async (event) => {
    catalogQuery.value = event.normalized;
    await catalog.searchByBarcode(event.normalized);

    const normalized = event.normalized;
    const exactBarcode = catalog.results.find((row) => String(row.barcode || '').trim().toUpperCase() === normalized);
    const exactSku = catalog.results.find((row) => String(row.sku || '').trim().toUpperCase() === normalized);
    const candidate = exactBarcode ?? exactSku ?? (catalog.results.length === 1 ? catalog.results[0] : null);

    if (!candidate) {
      scannerFeedback.value = {
        kind: 'warn',
        message: `Scanner: sin match único para ${normalized}.`,
      };
      playTone(false);
      return;
    }

    await addCatalogItem(candidate);
    scannerFeedback.value = {
      kind: 'ok',
      message: `Scanner: agregado ${candidate.sku}.`,
    };
    playTone(true);
  },
});

function playTone(success: boolean) {
  if (typeof window === 'undefined') return;
  const AudioCtx = window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AudioCtx) return;
  try {
    const ctxAudio = new AudioCtx();
    const osc = ctxAudio.createOscillator();
    const gain = ctxAudio.createGain();
    osc.type = 'sine';
    osc.frequency.value = success ? 880 : 220;
    gain.gain.value = 0.05;
    osc.connect(gain);
    gain.connect(ctxAudio.destination);
    osc.start();
    osc.stop(ctxAudio.currentTime + 0.08);
    window.setTimeout(() => {
      void ctxAudio.close();
    }, 150);
  } catch {
    // tono opcional: no bloquea operación
  }
}

async function ensureTicket() {
  if (!bootstrap.data?.active_cash_session || ticket.currentTicket) return;
  const terminal = bootstrap.data.terminals.find(Boolean);
  const payload: { terminal_id?: number; cash_session_id: number } = {
    cash_session_id: bootstrap.data.active_cash_session.id,
  };
  if (terminal?.id) {
    payload.terminal_id = terminal.id;
  }
  await ticket.createTicket(payload);
}

async function startNewTicket() {
  ticket.currentTicket = null;
  ticket.currentSale = null;
  ticket.activeHold = null;
  selectedLineId.value = null;
  checkout.reset();
  await ensureTicket();
}

async function runCatalogSearch() {
  await catalog.search(catalogQuery.value);
}

async function addCatalogItem(item: RetailCatalogItem) {
  await ensureTicket();
  await ticket.addItem(item.id);
}

async function removeLine(lineId: number) {
  await ticket.removeLine(lineId);
  if (selectedLineId.value === lineId) selectedLineId.value = null;
}

async function previewCheckout() {
  if (!ticket.currentTicket) return;
  await checkout.runPreview(ticket.currentTicket.id, ticket.currentTicket.version);
}

async function commitCheckout(cashReceived: string) {
  if (!ticket.currentTicket) return;
  await bootstrap.load();
  if (!bootstrap.data?.active_cash_session) {
    checkout.error = 'No hay CashSession OPEN para confirmar checkout.';
    return;
  }
  const outcome = await checkout.commit(
    ticket.currentTicket.id,
    ticket.currentTicket.version,
    cashReceived || ticket.currentTicket.total,
  );
  if (outcome === 'COMPLETED' && checkout.lastCommit) {
    await ticket.reload(checkout.lastCommit.ticket_id);
    await ticket.loadRecent();
    checkoutOpen.value = false;
  }
}

async function voidTicket() {
  if (!ticket.currentTicket) return;
  const outcome = await checkout.voidTicket(ticket.currentTicket.id, ticket.currentTicket.version, 'Anulación POS');
  if (outcome === 'COMPLETED') {
    await ticket.reload(ticket.currentTicket.id);
    await ticket.loadRecent();
    checkoutOpen.value = false;
  }
}

async function confirmHold(reason: string) {
  await ticket.hold(reason);
  holdOpen.value = false;
}

async function resumeHold() {
  await ticket.resumeHold();
}

async function openRecent() {
  recentOpen.value = true;
  await ticket.loadRecent();
}

async function selectRecentTicket(ticketId: number) {
  await ticket.reload(ticketId);
  recentOpen.value = false;
}

async function processReturn(qty: string, reason: string) {
  if (!ticket.currentSale || !selectedLineId.value) return;
  const saleId = Number(ticket.currentSale.sale_id || checkout.lastCommit?.sale_id || 0);
  if (!saleId) return;
  await bootstrap.load();
  if (!bootstrap.data?.active_cash_session) {
    checkout.error = 'No hay CashSession OPEN para procesar devolución.';
    return;
  }
  const outcome = await checkout.createReturn(saleId, selectedLineId.value, qty, reason);
  if (outcome === 'COMPLETED' && ticket.currentTicket) {
    await ticket.reload(ticket.currentTicket.id);
  }
  if (outcome === 'COMPLETED') {
    returnOpen.value = false;
  }
}

async function flushOfflineQueue() {
  await offlineQueue.flush();
  await offlineQueue.purgeDone();
}

function onOnline() {
  void flushOfflineQueue();
}

useRetailShortcuts({
  focusSearch: () => catalogPanelRef.value?.focusInput(),
  openCheckout: () => {
    if (ticket.currentTicket) checkoutOpen.value = true;
  },
  openHold: () => {
    if (ticket.currentTicket) holdOpen.value = true;
  },
  removeLine: () => {
    if (selectedLineId.value) void removeLine(selectedLineId.value);
  },
  confirm: () => {
    if (checkoutOpen.value) checkoutDrawerRef.value?.confirm();
  },
  cancel: () => {
    checkoutOpen.value = false;
    holdOpen.value = false;
    recentOpen.value = false;
    returnOpen.value = false;
  },
  isSuspended: () => scannerModeEnabled.value && scanner.isCapturing.value,
});

watch(
  () => [ctx.activeCompanyId, ctx.activeBranchId] as const,
  async ([companyId, branchId]) => {
    if (!companyId) {
      offlineQueue.$patch({
        companyId: null,
        branchId: null,
        queue: [],
        syncing: false,
        lastSyncError: '',
      });
      return;
    }
    await offlineQueue.loadScope(companyId, branchId ?? null);
  },
  { immediate: true },
);

onMounted(async () => {
  await bootstrap.load();
  await runCatalogSearch();
  await ensureTicket();
  await ticket.loadRecent();
  await flushOfflineQueue();

  window.addEventListener('online', onOnline);
  offlineFlushTimer = window.setInterval(() => {
    void flushOfflineQueue();
  }, 15000);
});

onBeforeUnmount(() => {
  window.removeEventListener('online', onOnline);
  if (offlineFlushTimer !== null) {
    window.clearInterval(offlineFlushTimer);
    offlineFlushTimer = null;
  }
});
</script>

<style scoped>
.retail-pos {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(360px, 0.9fr);
  gap: 16px;
}

.retail-pos__main,
.retail-pos__side {
  min-width: 0;
}

@media (max-width: 1024px) {
  .retail-pos {
    grid-template-columns: 1fr;
  }
}
</style>
