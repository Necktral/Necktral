import { defineStore } from 'pinia';
import { useContextStore } from 'src/stores/context.store';

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
import { useRetailOfflineQueueStore } from './useRetailOfflineQueueStore';
import { useRetailTelemetryStore } from './useRetailTelemetryStore';

function makeIdempotencyKey(prefix: string): string {
  const fn = globalThis.crypto?.randomUUID?.bind(globalThis.crypto);
  if (fn) return `${prefix}-${fn()}`;
  return `${prefix}-${Date.now()}-${Math.random().toString(16).slice(2, 10)}`;
}

function nowMs(): number {
  if (typeof performance !== 'undefined' && typeof performance.now === 'function') return performance.now();
  return Date.now();
}

async function ensureOfflineScopeLoaded() {
  const ctx = useContextStore();
  const queue = useRetailOfflineQueueStore();
  if (!ctx.activeCompanyId) return;
  if (queue.companyId === ctx.activeCompanyId && queue.branchId === (ctx.activeBranchId ?? null)) return;
  await queue.loadScope(ctx.activeCompanyId, ctx.activeBranchId ?? null);
}

function shouldQueueMutation(error: unknown): boolean {
  if (!(error instanceof RetailApiError)) return true;
  if (error.status === 409) return false;
  if (error.retryable) return true;
  if (error.status >= 500) return true;
  return false;
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
      return 'Hay un checkout en progreso para este ticket. Esperá unos segundos y reintentá.';
    }
    if (error.code === 'IDEMPOTENCY_KEY_REUSED_WITH_DIFFERENT_PAYLOAD') {
      return 'La llave de idempotencia ya fue usada con otro payload. Abrí un ticket nuevo o reintentá desde la cola.';
    }
  }
  return error.message || fallback;
}

export const useRetailCheckoutStore = defineStore('retail-checkout', {
  state: () => ({
    loading: false as boolean,
    error: null as string | null,
    notice: null as string | null,
    preview: null as RetailCheckoutPreviewResponse | null,
    lastCommit: null as RetailCheckoutCommitResponse | null,
    lastReturn: null as RetailReturnResponse | null,
  }),

  actions: {
    async runPreview(ticketId: number, expectedVersion: number) {
      this.loading = true;
      this.error = null;
      this.notice = null;
      try {
        this.preview = await previewRetailCheckout(ticketId, expectedVersion);
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : 'No se pudo generar la vista previa del checkout.';
      } finally {
        this.loading = false;
      }
    },

    async commit(
      ticketId: number,
      expectedVersion: number,
      cashReceived: string,
    ): Promise<'COMPLETED' | 'QUEUED' | 'FAILED'> {
      const queue = useRetailOfflineQueueStore();
      const telemetry = useRetailTelemetryStore();
      const startedAt = new Date().toISOString();
      const started = nowMs();
      const idempotencyKey = makeIdempotencyKey('retail-checkout');

      this.loading = true;
      this.error = null;
      this.notice = null;
      this.lastCommit = null;
      try {
        this.lastCommit = await commitRetailCheckout(ticketId, {
          expected_version: expectedVersion,
          idempotency_key: idempotencyKey,
          cash_received: cashReceived,
        });
        telemetry.recordAttempt({
          action: 'CHECKOUT_COMMIT',
          outcome: this.lastCommit.idempotency_replayed ? 'REPLAYED' : 'SUCCESS',
          latency_ms: Math.max(0, Math.round(nowMs() - started)),
          started_at: startedAt,
          completed_at: new Date().toISOString(),
          retryable: false,
          replayed: Boolean(this.lastCommit.idempotency_replayed),
          error_code: '',
          correlation_id: this.lastCommit.correlation_id,
        });
        return 'COMPLETED';
      } catch (error: unknown) {
        if (shouldQueueMutation(error)) {
          try {
            await ensureOfflineScopeLoaded();
            await queue.enqueueMutation({
              action: 'CHECKOUT_COMMIT',
              ticketId,
              payload: {
                expected_version: expectedVersion,
                idempotency_key: idempotencyKey,
                cash_received: cashReceived,
              },
              idempotencyKey,
            });
            this.notice = 'Checkout encolado por conectividad. Se reintentará automáticamente.';
            telemetry.recordAttempt({
              action: 'CHECKOUT_COMMIT',
              outcome: 'QUEUED',
              latency_ms: Math.max(0, Math.round(nowMs() - started)),
              started_at: startedAt,
              completed_at: new Date().toISOString(),
              retryable: true,
              replayed: false,
              error_code: error instanceof RetailApiError ? error.code : 'NETWORK_OR_TIMEOUT',
              correlation_id: error instanceof RetailApiError ? error.correlationId : '',
            });
            return 'QUEUED';
          } catch {
            // si no se puede encolar, cae a error normal
          }
        }
        this.error = retailMutationErrorMessage(error, 'No se pudo confirmar el checkout retail.');
        telemetry.recordAttempt({
          action: 'CHECKOUT_COMMIT',
          outcome: 'FAILED',
          latency_ms: Math.max(0, Math.round(nowMs() - started)),
          started_at: startedAt,
          completed_at: new Date().toISOString(),
          retryable: error instanceof RetailApiError ? error.retryable : false,
          replayed: false,
          error_code: error instanceof RetailApiError ? error.code : 'CHECKOUT_FAILED',
          correlation_id: error instanceof RetailApiError ? error.correlationId : '',
        });
        return 'FAILED';
      } finally {
        this.loading = false;
      }
    },

    async voidTicket(ticketId: number, expectedVersion: number, reason = ''): Promise<'COMPLETED' | 'QUEUED' | 'FAILED'> {
      const queue = useRetailOfflineQueueStore();
      const telemetry = useRetailTelemetryStore();
      const startedAt = new Date().toISOString();
      const started = nowMs();
      const idempotencyKey = makeIdempotencyKey('retail-void');

      this.loading = true;
      this.error = null;
      this.notice = null;
      try {
        await voidRetailTicket(ticketId, {
          expected_version: expectedVersion,
          idempotency_key: idempotencyKey,
          reason,
        });
        telemetry.recordAttempt({
          action: 'VOID',
          outcome: 'SUCCESS',
          latency_ms: Math.max(0, Math.round(nowMs() - started)),
          started_at: startedAt,
          completed_at: new Date().toISOString(),
          retryable: false,
          replayed: false,
          error_code: '',
          correlation_id: '',
        });
        return 'COMPLETED';
      } catch (error: unknown) {
        if (shouldQueueMutation(error)) {
          try {
            await ensureOfflineScopeLoaded();
            await queue.enqueueMutation({
              action: 'VOID',
              ticketId,
              payload: {
                expected_version: expectedVersion,
                idempotency_key: idempotencyKey,
                reason,
              },
              idempotencyKey,
            });
            this.notice = 'Anulación encolada por conectividad. Se reintentará automáticamente.';
            telemetry.recordAttempt({
              action: 'VOID',
              outcome: 'QUEUED',
              latency_ms: Math.max(0, Math.round(nowMs() - started)),
              started_at: startedAt,
              completed_at: new Date().toISOString(),
              retryable: true,
              replayed: false,
              error_code: error instanceof RetailApiError ? error.code : 'NETWORK_OR_TIMEOUT',
              correlation_id: error instanceof RetailApiError ? error.correlationId : '',
            });
            return 'QUEUED';
          } catch {
            // fallback a error tradicional
          }
        }
        this.error = retailMutationErrorMessage(error, 'No se pudo anular la venta retail.');
        telemetry.recordAttempt({
          action: 'VOID',
          outcome: 'FAILED',
          latency_ms: Math.max(0, Math.round(nowMs() - started)),
          started_at: startedAt,
          completed_at: new Date().toISOString(),
          retryable: error instanceof RetailApiError ? error.retryable : false,
          replayed: false,
          error_code: error instanceof RetailApiError ? error.code : 'VOID_FAILED',
          correlation_id: error instanceof RetailApiError ? error.correlationId : '',
        });
        return 'FAILED';
      } finally {
        this.loading = false;
      }
    },

    async createReturn(
      saleId: number,
      lineId: number,
      qty: string,
      reason = '',
    ): Promise<'COMPLETED' | 'QUEUED' | 'FAILED'> {
      const queue = useRetailOfflineQueueStore();
      const telemetry = useRetailTelemetryStore();
      const startedAt = new Date().toISOString();
      const started = nowMs();
      const idempotencyKey = makeIdempotencyKey('retail-return');

      this.loading = true;
      this.error = null;
      this.notice = null;
      this.lastReturn = null;
      try {
        this.lastReturn = await createRetailReturn({
          sale_id: saleId,
          reason,
          idempotency_key: idempotencyKey,
          lines: [{ line_id: lineId, qty }],
        });
        telemetry.recordAttempt({
          action: 'RETURN',
          outcome: this.lastReturn.idempotency_replayed ? 'REPLAYED' : 'SUCCESS',
          latency_ms: Math.max(0, Math.round(nowMs() - started)),
          started_at: startedAt,
          completed_at: new Date().toISOString(),
          retryable: false,
          replayed: Boolean(this.lastReturn.idempotency_replayed),
          error_code: '',
          correlation_id: this.lastReturn.flow_correlation_id,
        });
        return 'COMPLETED';
      } catch (error: unknown) {
        if (shouldQueueMutation(error)) {
          try {
            await ensureOfflineScopeLoaded();
            await queue.enqueueMutation({
              action: 'RETURN',
              saleId,
              payload: {
                sale_id: saleId,
                reason,
                idempotency_key: idempotencyKey,
                lines: [{ line_id: lineId, qty }],
              },
              idempotencyKey,
            });
            this.notice = 'Devolución encolada por conectividad. Se reintentará automáticamente.';
            telemetry.recordAttempt({
              action: 'RETURN',
              outcome: 'QUEUED',
              latency_ms: Math.max(0, Math.round(nowMs() - started)),
              started_at: startedAt,
              completed_at: new Date().toISOString(),
              retryable: true,
              replayed: false,
              error_code: error instanceof RetailApiError ? error.code : 'NETWORK_OR_TIMEOUT',
              correlation_id: error instanceof RetailApiError ? error.correlationId : '',
            });
            return 'QUEUED';
          } catch {
            // fallback a error tradicional
          }
        }
        this.error = retailMutationErrorMessage(error, 'No se pudo procesar la devolución retail.');
        telemetry.recordAttempt({
          action: 'RETURN',
          outcome: 'FAILED',
          latency_ms: Math.max(0, Math.round(nowMs() - started)),
          started_at: startedAt,
          completed_at: new Date().toISOString(),
          retryable: error instanceof RetailApiError ? error.retryable : false,
          replayed: false,
          error_code: error instanceof RetailApiError ? error.code : 'RETURN_FAILED',
          correlation_id: error instanceof RetailApiError ? error.correlationId : '',
        });
        return 'FAILED';
      } finally {
        this.loading = false;
      }
    },

    reset() {
      this.preview = null;
      this.lastCommit = null;
      this.lastReturn = null;
      this.error = null;
      this.notice = null;
    },
  },
});
