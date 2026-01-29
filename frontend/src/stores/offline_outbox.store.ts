import { defineStore } from 'pinia';
import { api } from 'src/boot/axios';
import { countOutboxByStatus } from 'src/core/offline/outbox';
import { flushOutbox } from 'src/core/offline/processor';

export const useOfflineOutboxStore = defineStore('offlineOutbox', {
  state: () => ({
    pending: 0 as number,
    failed: 0 as number,
    lastFlush: null as null | { sent: number; failed: number; remaining: number; at: number },
  }),

  actions: {
    async refreshCounts() {
      this.pending = await countOutboxByStatus('pending');
      this.failed = await countOutboxByStatus('failed');
    },

    async flush() {
      const res = await flushOutbox(api, 25);
      this.lastFlush = {
        sent: res.sent,
        failed: res.failed,
        remaining: res.remaining,
        at: Date.now(),
      };
      await this.refreshCounts();
      return res;
    },
  },
});
