import { defineStore } from 'pinia';

import {
  commitRetailCheckout,
  createRetailReturn,
  RetailApiError,
  voidRetailTicket,
} from '../services/retail-pos.service';
import {
  enqueueRetailOfflineOperation,
  isRetailOfflineEntryReady,
  listRetailOfflineOperationsByScope,
  nextRetryAtIso,
  removeRetailOfflineOperation,
  type RetailOfflineAction,
  type RetailOfflineQueueEntry,
  updateRetailOfflineOperation,
} from '../offline/queue-db';
import { useRetailTelemetryStore } from './useRetailTelemetryStore';

function byCreatedAtAsc(a: RetailOfflineQueueEntry, b: RetailOfflineQueueEntry): number {
  return a.created_at.localeCompare(b.created_at);
}

function isRetryableRetailError(error: unknown): boolean {
  if (!(error instanceof RetailApiError)) return true;
  if (error.retryable) return true;
  if (error.status >= 500) return true;
  return false;
}

function retailErrorMessage(error: unknown): string {
  if (error instanceof RetailApiError) return error.message;
  if (error instanceof Error) return error.message;
  return String(error);
}

function asOptionalString(value: unknown): string {
  if (typeof value === 'string') return value;
  if (typeof value === 'number') return String(value);
  return '';
}

function nowMs(): number {
  if (typeof performance !== 'undefined' && typeof performance.now === 'function') return performance.now();
  return Date.now();
}

export const useRetailOfflineQueueStore = defineStore('retail-offline-queue', {
  state: () => ({
    companyId: null as string | null,
    branchId: null as string | null,
    queue: [] as RetailOfflineQueueEntry[],
    syncing: false as boolean,
    lastSyncError: '' as string,
  }),

  getters: {
    pendingCount: (s) => s.queue.filter((row) => row.status === 'PENDING' || row.status === 'RETRYING').length,
    failedCount: (s) => s.queue.filter((row) => row.status === 'FAILED').length,
    doneCount: (s) => s.queue.filter((row) => row.status === 'DONE').length,
  },

  actions: {
    async loadScope(companyId: string, branchId: string | null) {
      this.companyId = companyId;
      this.branchId = branchId;
      const rows = await listRetailOfflineOperationsByScope(companyId, branchId);
      this.queue = rows.sort(byCreatedAtAsc);
    },

    async enqueueMutation(input: {
      action: RetailOfflineAction;
      ticketId?: number | null;
      saleId?: number | null;
      payload: Record<string, unknown>;
      idempotencyKey: string;
    }) {
      if (!this.companyId) {
        throw new Error('RETAIL_CONTEXT_REQUIRED');
      }
      const row = await enqueueRetailOfflineOperation({
        company_id: this.companyId,
        branch_id: this.branchId,
        action: input.action,
        ticket_id: input.ticketId ?? null,
        sale_id: input.saleId ?? null,
        payload: input.payload,
        idempotency_key: input.idempotencyKey,
      });
      const idx = this.queue.findIndex((x) => x.id === row.id);
      if (idx >= 0) this.queue.splice(idx, 1, row);
      else this.queue.push(row);
      this.queue.sort(byCreatedAtAsc);
      return row;
    },

    async markFailedAsPending(id: string) {
      const updated = await updateRetailOfflineOperation(id, {
        status: 'PENDING',
        next_retry_at: new Date().toISOString(),
        last_error: '',
      });
      if (!updated) return;
      const idx = this.queue.findIndex((x) => x.id === updated.id);
      if (idx >= 0) this.queue.splice(idx, 1, updated);
    },

    async purgeDone() {
      const done = this.queue.filter((row) => row.status === 'DONE');
      for (const row of done) {
        await removeRetailOfflineOperation(row.id);
      }
      this.queue = this.queue.filter((row) => row.status !== 'DONE');
      return done.length;
    },

    async flush() {
      if (!this.companyId || this.syncing) return;
      if (typeof navigator !== 'undefined' && !navigator.onLine) return;

      const ready = this.queue.filter((row) => isRetailOfflineEntryReady(row));
      if (!ready.length) return;
      const telemetry = useRetailTelemetryStore();

      this.syncing = true;
      this.lastSyncError = '';

      try {
        for (const row of ready) {
          const startedAt = new Date().toISOString();
          const started = nowMs();
          const updated = await updateRetailOfflineOperation(row.id, { status: 'RETRYING' });
          if (updated) {
            const idx = this.queue.findIndex((x) => x.id === updated.id);
            if (idx >= 0) this.queue.splice(idx, 1, updated);
          }

          try {
            let replayed = false;
            let correlationId = '';
            if (row.action === 'CHECKOUT_COMMIT') {
              const ticketId = Number(row.ticket_id || 0);
              if (!ticketId) throw new Error('RETAIL_QUEUE_INVALID_TICKET');
              const response = await commitRetailCheckout(ticketId, row.payload as {
                expected_version: number;
                idempotency_key: string;
                cash_received: string;
              });
              replayed = Boolean(response.idempotency_replayed);
              correlationId = String(response.correlation_id || '');
            } else if (row.action === 'VOID') {
              const ticketId = Number(row.ticket_id || 0);
              if (!ticketId) throw new Error('RETAIL_QUEUE_INVALID_TICKET');
              const response = await voidRetailTicket(ticketId, row.payload as {
                expected_version: number;
                idempotency_key: string;
                reason?: string;
              });
              if (response && typeof response === 'object') {
                const mapped = response as Record<string, unknown>;
                replayed = Boolean(mapped.idempotency_replayed);
                correlationId = asOptionalString(mapped.correlation_id) || asOptionalString(mapped.flow_correlation_id);
              }
            } else if (row.action === 'RETURN') {
              const response = await createRetailReturn(row.payload as {
                sale_id: number;
                reason?: string;
                idempotency_key: string;
                lines: Array<{ line_id: number; qty: string }>;
              });
              replayed = Boolean(response.idempotency_replayed);
              correlationId = String(response.flow_correlation_id || '');
            }

            const done = await updateRetailOfflineOperation(row.id, {
              status: 'DONE',
              last_error: '',
            });
            if (done) {
              const idx = this.queue.findIndex((x) => x.id === done.id);
              if (idx >= 0) this.queue.splice(idx, 1, done);
            }
            telemetry.recordAttempt({
              action: 'OFFLINE_FLUSH',
              outcome: replayed ? 'REPLAYED' : 'SUCCESS',
              latency_ms: Math.max(0, Math.round(nowMs() - started)),
              started_at: startedAt,
              completed_at: new Date().toISOString(),
              retryable: false,
              replayed,
              error_code: '',
              correlation_id: correlationId,
            });
          } catch (error: unknown) {
            const attempts = row.attempts + 1;
            const retryable = isRetryableRetailError(error);
            const status = retryable ? 'RETRYING' : 'FAILED';
            const patch: Partial<RetailOfflineQueueEntry> = {
              attempts,
              status,
              last_error: retailErrorMessage(error),
            };
            if (retryable) {
              patch.next_retry_at = nextRetryAtIso(attempts);
            }
            const failed = await updateRetailOfflineOperation(row.id, patch);
            if (failed) {
              const idx = this.queue.findIndex((x) => x.id === failed.id);
              if (idx >= 0) this.queue.splice(idx, 1, failed);
            }
            this.lastSyncError = retailErrorMessage(error);
            telemetry.recordAttempt({
              action: 'OFFLINE_FLUSH',
              outcome: 'FAILED',
              latency_ms: Math.max(0, Math.round(nowMs() - started)),
              started_at: startedAt,
              completed_at: new Date().toISOString(),
              retryable,
              replayed: false,
              error_code: error instanceof RetailApiError ? error.code : 'OFFLINE_FLUSH_FAILED',
              correlation_id: error instanceof RetailApiError ? error.correlationId : '',
            });
          }
        }
      } catch (error: unknown) {
        this.lastSyncError = retailErrorMessage(error);
      } finally {
        this.syncing = false;
        this.queue.sort(byCreatedAtAsc);
      }
    },
  },
});
