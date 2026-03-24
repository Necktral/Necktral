<template>
  <AppContainer fluid>
    <AppPageHeader
      :title="`${labels.retail} · POS`"
      subtitle="Caja operativa retail sobre Billing, Inventory y Payments/Cash"
    >
      <template #badges>
        <RetailCashSessionBadge :session="bootstrap.data?.active_cash_session ?? null" />
        <RetailFiscalStatusChip :status="checkout.lastCommit?.billing.status ?? ticket.currentTicket?.status ?? null" />
      </template>
      <template #actions>
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
import { computed, onMounted, ref } from 'vue';

import AppContainer from 'src/ui/AppContainer.vue';
import AppPageHeader from 'src/ui/AppPageHeader.vue';
import { BUSINESS_LABELS } from 'src/shared/ui/business-terms';

import RetailCatalogPanel from '../components/RetailCatalogPanel.vue';
import RetailCashSessionBadge from '../components/RetailCashSessionBadge.vue';
import RetailCheckoutDrawer from '../components/RetailCheckoutDrawer.vue';
import RetailFiscalStatusChip from '../components/RetailFiscalStatusChip.vue';
import RetailHoldDialog from '../components/RetailHoldDialog.vue';
import RetailRecentTicketsDrawer from '../components/RetailRecentTicketsDrawer.vue';
import RetailReturnDialog from '../components/RetailReturnDialog.vue';
import RetailTicketPanel from '../components/RetailTicketPanel.vue';
import RetailTotalsBar from '../components/RetailTotalsBar.vue';
import { useRetailShortcuts } from '../composables/useRetailShortcuts';
import type { RetailCatalogItem } from '../services/retail-pos.service';
import { useRetailBootstrapStore } from '../stores/useRetailBootstrapStore';
import { useRetailCatalogStore } from '../stores/useRetailCatalogStore';
import { useRetailCheckoutStore } from '../stores/useRetailCheckoutStore';
import { useRetailTicketStore } from '../stores/useRetailTicketStore';

const labels = BUSINESS_LABELS;
const bootstrap = useRetailBootstrapStore();
const catalog = useRetailCatalogStore();
const ticket = useRetailTicketStore();
const checkout = useRetailCheckoutStore();

const catalogQuery = ref('');
const checkoutOpen = ref(false);
const holdOpen = ref(false);
const recentOpen = ref(false);
const returnOpen = ref(false);
const selectedLineId = ref<number | null>(null);

const catalogPanelRef = ref<InstanceType<typeof RetailCatalogPanel> | null>(null);
const checkoutDrawerRef = ref<InstanceType<typeof RetailCheckoutDrawer> | null>(null);

const canOpenReturn = computed(
  () => Boolean(ticket.currentSale && selectedLineId.value && ticket.currentTicket?.status === 'CLOSED'),
);

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
  await checkout.commit(ticket.currentTicket.id, ticket.currentTicket.version, cashReceived || ticket.currentTicket.total);
  if (checkout.lastCommit) {
    await ticket.reload(checkout.lastCommit.ticket_id);
    await ticket.loadRecent();
    checkoutOpen.value = false;
  }
}

async function voidTicket() {
  if (!ticket.currentTicket) return;
  await checkout.voidTicket(ticket.currentTicket.id, ticket.currentTicket.version, 'Anulación POS');
  await ticket.reload(ticket.currentTicket.id);
  await ticket.loadRecent();
  checkoutOpen.value = false;
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
  await checkout.createReturn(saleId, selectedLineId.value, qty, reason);
  if (ticket.currentTicket) {
    await ticket.reload(ticket.currentTicket.id);
  }
  returnOpen.value = false;
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
});

onMounted(async () => {
  await bootstrap.load();
  await runCatalogSearch();
  await ensureTicket();
  await ticket.loadRecent();
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
