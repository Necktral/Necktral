import { defineStore } from 'pinia';

import { directInventoryAdapter } from 'src/modules/inventory/adapters/direct-inventory.adapter';
import type { InventoryCommandGateway } from 'src/modules/inventory/contracts/command-gateway';
import {
  clearDoneOfflineCommands,
  enqueueOfflineCommand,
  isCommandReadyToRetry,
  listOfflineCommandsByScope,
  removeOfflineCommand,
  type OfflineQueuedCommand,
  updateOfflineCommand,
} from 'src/modules/inventory/offline/queue-db';
import type { InventoryBatchCommand } from 'src/services/inventory.service';

function byCreatedAtAsc(a: OfflineQueuedCommand, b: OfflineQueuedCommand): number {
  return a.created_at.localeCompare(b.created_at);
}

function nextAttemptIso(attempts: number): string {
  const seconds = Math.min(300, Math.max(2, 2 ** attempts));
  return new Date(Date.now() + seconds * 1000).toISOString();
}

export const useInventoryOfflineStore = defineStore('inventory_offline', {
  state: () => ({
    companyId: null as string | null,
    branchId: null as string | null,
    queue: [] as OfflineQueuedCommand[],
    loading: false as boolean,
    syncing: false as boolean,
    lastSyncError: '' as string,
  }),

  getters: {
    pendingCount: (s) => s.queue.filter((row) => row.status === 'PENDING' || row.status === 'RETRYING').length,
    conflictCount: (s) => s.queue.filter((row) => row.status === 'CONFLICT').length,
    doneCount: (s) => s.queue.filter((row) => row.status === 'DONE').length,
    activeScope: (s) => (s.companyId ? { companyId: s.companyId, branchId: s.branchId } : null),
  },

  actions: {
    async loadScope(companyId: string, branchId: string | null) {
      this.loading = true;
      this.companyId = companyId;
      this.branchId = branchId;
      try {
        const rows = await listOfflineCommandsByScope(companyId, branchId);
        this.queue = rows.sort(byCreatedAtAsc);
      } finally {
        this.loading = false;
      }
    },

    async enqueue(input: {
      type: string;
      payload: Record<string, unknown>;
      idempotency_key: string;
      command_id?: string;
    }) {
      if (!this.companyId) {
        throw new Error('INVENTORY_CONTEXT_REQUIRED');
      }
      const request: {
        company_id: string;
        branch_id: string | null;
        command_id?: string;
        type: string;
        payload: Record<string, unknown>;
        idempotency_key: string;
      } = {
        company_id: this.companyId,
        branch_id: this.branchId,
        type: input.type,
        payload: input.payload,
        idempotency_key: input.idempotency_key,
      };
      if (input.command_id) request.command_id = input.command_id;

      const row = await enqueueOfflineCommand(request);
      const idx = this.queue.findIndex((x) => x.id === row.id);
      if (idx >= 0) this.queue.splice(idx, 1, row);
      else this.queue.push(row);
      this.queue.sort(byCreatedAtAsc);
      return row;
    },

    async markConflictAsDone(id: string) {
      const updated = await updateOfflineCommand(id, {
        status: 'DONE',
        last_error_code: '',
        last_error_detail: '',
      });
      if (!updated) return;
      const idx = this.queue.findIndex((x) => x.id === id);
      if (idx >= 0) this.queue.splice(idx, 1, updated);
    },

    async retryConflict(id: string) {
      const updated = await updateOfflineCommand(id, {
        status: 'RETRYING',
        next_attempt_at: new Date().toISOString(),
        last_error_code: '',
        last_error_detail: '',
      });
      if (!updated) return;
      const idx = this.queue.findIndex((x) => x.id === id);
      if (idx >= 0) this.queue.splice(idx, 1, updated);
    },

    async purgeDone() {
      if (!this.companyId) return 0;
      const removed = await clearDoneOfflineCommands(this.companyId, this.branchId);
      this.queue = this.queue.filter((row) => row.status !== 'DONE');
      return removed;
    },

    async removePending(id: string) {
      const row = this.queue.find((x) => x.id === id);
      if (!row) return;
      if (row.status !== 'PENDING' && row.status !== 'RETRYING') return;
      await removeOfflineCommand(id);
      this.queue = this.queue.filter((x) => x.id !== id);
    },

    async flush(gateway: InventoryCommandGateway = directInventoryAdapter) {
      if (!this.companyId || this.syncing) return;
      if (typeof navigator !== 'undefined' && !navigator.onLine) return;

      const ready = this.queue.filter((row) => isCommandReadyToRetry(row));
      if (!ready.length) return;

      this.syncing = true;
      this.lastSyncError = '';

      const commands: InventoryBatchCommand[] = ready.map((row) => ({
        command_id: row.command_id,
        type: row.type,
        payload: {
          ...row.payload,
          idempotency_key: row.idempotency_key,
        },
      }));

      try {
        const response = await gateway.submitBatch(commands);
        const byCommandId = new Map(response.results.map((row) => [row.command_id, row]));

        for (const row of ready) {
          const result = byCommandId.get(row.command_id);
          if (!result) {
            const attempts = row.attempts + 1;
            const updated = await updateOfflineCommand(row.id, {
              status: 'RETRYING',
              attempts,
              next_attempt_at: nextAttemptIso(attempts),
              last_error_code: 'OFFLINE_BATCH_RESULT_MISSING',
              last_error_detail: 'No se recibió resultado para el comando.',
            });
            if (updated) {
              const idx = this.queue.findIndex((x) => x.id === updated.id);
              if (idx >= 0) this.queue.splice(idx, 1, updated);
            }
            continue;
          }

          if (result.status === 'APPLIED' || result.status === 'DUPLICATE') {
            const updated = await updateOfflineCommand(row.id, {
              status: 'DONE',
              last_error_code: '',
              last_error_detail: '',
            });
            if (updated) {
              const idx = this.queue.findIndex((x) => x.id === updated.id);
              if (idx >= 0) this.queue.splice(idx, 1, updated);
            }
            continue;
          }

          const updated = await updateOfflineCommand(row.id, {
            status: 'CONFLICT',
            last_error_code: result.error_code ?? 'INVENTORY_COMMAND_REJECTED',
            last_error_detail: result.error_detail ?? 'Comando rechazado por servidor.',
          });
          if (updated) {
            const idx = this.queue.findIndex((x) => x.id === updated.id);
            if (idx >= 0) this.queue.splice(idx, 1, updated);
          }
        }
      } catch (error: unknown) {
        const message = error instanceof Error ? error.message : String(error);
        this.lastSyncError = message;

        for (const row of ready) {
          const attempts = row.attempts + 1;
          const updated = await updateOfflineCommand(row.id, {
            status: 'RETRYING',
            attempts,
            next_attempt_at: nextAttemptIso(attempts),
            last_error_code: 'OFFLINE_NETWORK_ERROR',
            last_error_detail: message,
          });
          if (updated) {
            const idx = this.queue.findIndex((x) => x.id === updated.id);
            if (idx >= 0) this.queue.splice(idx, 1, updated);
          }
        }
      } finally {
        this.syncing = false;
        this.queue.sort(byCreatedAtAsc);
      }
    },
  },
});
