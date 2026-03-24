import { defineStore } from 'pinia';

import {
  addRetailTicketLine,
  createRetailTicket,
  deleteRetailTicketLine,
  fetchRetailRecentTickets,
  getRetailTicket,
  holdRetailTicket,
  RetailApiError,
  resumeRetailHold,
  type RetailHoldRow,
  type RetailTicketRow,
} from '../services/retail-pos.service';

function retailTicketErrorMessage(error: unknown, fallback: string): string {
  if (!(error instanceof RetailApiError)) {
    return error instanceof Error ? error.message : fallback;
  }
  if (error.status === 409 && error.code === 'TICKET_VERSION_CONFLICT') {
    return 'El ticket cambió en otra terminal. Recargá el ticket y reintentá.';
  }
  return error.message || fallback;
}

export const useRetailTicketStore = defineStore('retail-ticket', {
  state: () => ({
    loading: false as boolean,
    mutating: false as boolean,
    error: null as string | null,
    currentTicket: null as RetailTicketRow | null,
    currentSale: null as Record<string, unknown> | null,
    activeHold: null as RetailHoldRow | null,
    recentTickets: [] as RetailTicketRow[],
  }),

  getters: {
    hasTicket: (state) => Boolean(state.currentTicket),
  },

  actions: {
    async createTicket(payload: { terminal_id?: number; cash_session_id?: number; customer_name?: string; customer_ref?: string }) {
      this.mutating = true;
      this.error = null;
      try {
        this.currentTicket = await createRetailTicket(payload);
        this.currentSale = null;
        this.activeHold = null;
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : 'No se pudo abrir el ticket retail.';
      } finally {
        this.mutating = false;
      }
    },

    async reload(ticketId: number) {
      this.loading = true;
      this.error = null;
      try {
        const data = await getRetailTicket(ticketId);
        this.currentTicket = data.ticket;
        this.currentSale = data.sale;
        this.activeHold = data.active_hold;
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : 'No se pudo recargar el ticket retail.';
      } finally {
        this.loading = false;
      }
    },

    async addItem(itemId: number, qty = '1.0000') {
      if (!this.currentTicket) return;
      this.mutating = true;
      this.error = null;
      try {
        this.currentTicket = await addRetailTicketLine(this.currentTicket.id, {
          expected_version: this.currentTicket.version,
          item_id: itemId,
          qty,
        });
        this.activeHold = null;
      } catch (error: unknown) {
        this.error = retailTicketErrorMessage(error, 'No se pudo agregar la línea retail.');
      } finally {
        this.mutating = false;
      }
    },

    async removeLine(lineId: number) {
      if (!this.currentTicket) return;
      this.mutating = true;
      this.error = null;
      try {
        this.currentTicket = await deleteRetailTicketLine(this.currentTicket.id, lineId, this.currentTicket.version);
      } catch (error: unknown) {
        this.error = retailTicketErrorMessage(error, 'No se pudo quitar la línea retail.');
      } finally {
        this.mutating = false;
      }
    },

    async hold(reason: string) {
      if (!this.currentTicket) return;
      this.mutating = true;
      this.error = null;
      try {
        this.activeHold = await holdRetailTicket(this.currentTicket.id, this.currentTicket.version, reason);
        this.currentTicket = this.activeHold.ticket;
      } catch (error: unknown) {
        this.error = retailTicketErrorMessage(error, 'No se pudo retener el ticket.');
      } finally {
        this.mutating = false;
      }
    },

    async resumeHold() {
      if (!this.activeHold) return;
      this.mutating = true;
      this.error = null;
      try {
        this.activeHold = await resumeRetailHold(this.activeHold.id);
        this.currentTicket = this.activeHold.ticket;
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : 'No se pudo reanudar el ticket.';
      } finally {
        this.mutating = false;
      }
    },

    async loadRecent() {
      this.loading = true;
      this.error = null;
      try {
        const data = await fetchRetailRecentTickets();
        this.recentTickets = data.results;
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : 'No se pudo cargar el histórico reciente.';
      } finally {
        this.loading = false;
      }
    },
  },
});
