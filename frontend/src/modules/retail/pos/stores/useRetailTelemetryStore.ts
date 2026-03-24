import { defineStore } from 'pinia';

export type RetailAttemptAction = 'CHECKOUT_COMMIT' | 'VOID' | 'RETURN' | 'OFFLINE_FLUSH';
export type RetailAttemptOutcome = 'SUCCESS' | 'REPLAYED' | 'QUEUED' | 'FAILED';

export type RetailAttemptMetric = {
  id: string;
  action: RetailAttemptAction;
  outcome: RetailAttemptOutcome;
  latency_ms: number;
  started_at: string;
  completed_at: string;
  retryable: boolean;
  replayed: boolean;
  error_code: string;
  correlation_id: string;
};

function randomId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export const useRetailTelemetryStore = defineStore('retail-telemetry', {
  state: () => ({
    attempts: [] as RetailAttemptMetric[],
  }),

  getters: {
    lastAttempt: (s) => s.attempts[0] ?? null,
  },

  actions: {
    recordAttempt(metric: Omit<RetailAttemptMetric, 'id'>) {
      const row: RetailAttemptMetric = {
        id: randomId(),
        ...metric,
      };
      this.attempts.unshift(row);
      if (this.attempts.length > 80) {
        this.attempts.splice(80);
      }
    },
  },
});

