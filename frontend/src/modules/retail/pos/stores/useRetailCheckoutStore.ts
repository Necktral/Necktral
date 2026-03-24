import { defineStore } from 'pinia';

import {
  commitRetailCheckout,
  createRetailReturn,
  previewRetailCheckout,
  RetailApiError,
  voidRetailTicket,
  type RetailCheckoutCommitResponse,
  type RetailCheckoutPreviewResponse,
  type RetailReturnResponse,
} from '../services/retail-pos.service';

function makeIdempotencyKey(prefix: string): string {
  const fn = globalThis.crypto?.randomUUID?.bind(globalThis.crypto);
  if (fn) return `${prefix}-${fn()}`;
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

function retailMutationErrorMessage(error: unknown, fallback: string): string {
  if (!(error instanceof RetailApiError)) {
    return error instanceof Error ? error.message : fallback;
  }
  if (error.status === 409) {
    if (error.code === 'TICKET_VERSION_CONFLICT') {
      return 'El ticket cambió en otra terminal. Recargá y reintentá.';
    }
    if (error.code === 'TICKET_CHECKOUT_IN_PROGRESS' || error.code === 'IDEMPOTENCY_KEY_IN_PROGRESS') {
      return 'Hay un checkout en progreso para este ticket. Esperá y reintentá.';
    }
    if (error.code === 'IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD') {
      return 'La llave de idempotencia ya fue usada con otro payload.';
    }
  }
  return error.message || fallback;
}

export const useRetailCheckoutStore = defineStore('retail-checkout', {
  state: () => ({
    loading: false as boolean,
    error: null as string | null,
    preview: null as RetailCheckoutPreviewResponse | null,
    lastCommit: null as RetailCheckoutCommitResponse | null,
    lastReturn: null as RetailReturnResponse | null,
  }),

  actions: {
    async runPreview(ticketId: number, expectedVersion: number) {
      this.loading = true;
      this.error = null;
      try {
        this.preview = await previewRetailCheckout(ticketId, expectedVersion);
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : 'No se pudo generar la vista previa del checkout.';
      } finally {
        this.loading = false;
      }
    },

    async commit(ticketId: number, expectedVersion: number, cashReceived: string) {
      this.loading = true;
      this.error = null;
      try {
        this.lastCommit = await commitRetailCheckout(ticketId, {
          expected_version: expectedVersion,
          idempotency_key: makeIdempotencyKey('retail-checkout'),
          cash_received: cashReceived,
        });
      } catch (error: unknown) {
        this.error = retailMutationErrorMessage(error, 'No se pudo confirmar el checkout retail.');
      } finally {
        this.loading = false;
      }
    },

    async voidTicket(ticketId: number, expectedVersion: number, reason = '') {
      this.loading = true;
      this.error = null;
      try {
        await voidRetailTicket(ticketId, {
          expected_version: expectedVersion,
          idempotency_key: makeIdempotencyKey('retail-void'),
          reason,
        });
      } catch (error: unknown) {
        this.error = retailMutationErrorMessage(error, 'No se pudo anular la venta retail.');
      } finally {
        this.loading = false;
      }
    },

    async createReturn(saleId: number, lineId: number, qty: string, reason = '') {
      this.loading = true;
      this.error = null;
      try {
        this.lastReturn = await createRetailReturn({
          sale_id: saleId,
          reason,
          idempotency_key: makeIdempotencyKey('retail-return'),
          lines: [{ line_id: lineId, qty }],
        });
      } catch (error: unknown) {
        this.error = retailMutationErrorMessage(error, 'No se pudo procesar la devolución retail.');
      } finally {
        this.loading = false;
      }
    },

    reset() {
      this.preview = null;
      this.lastCommit = null;
      this.lastReturn = null;
      this.error = null;
    },
  },
});
