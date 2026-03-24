import { describe, expect, it } from 'vitest';

import { isRetailOfflineEntryReady, nextRetryAtIso, type RetailOfflineQueueEntry } from './queue-db';

function baseEntry(status: RetailOfflineQueueEntry['status'], next_retry_at: string): RetailOfflineQueueEntry {
  return {
    id: '1',
    company_id: '10',
    branch_id: '20',
    scope_key: '10:20',
    action: 'CHECKOUT_COMMIT',
    ticket_id: 123,
    sale_id: null,
    payload: {},
    idempotency_key: 'idem-1',
    status,
    attempts: 0,
    next_retry_at,
    last_error: '',
    created_at: '2026-01-01T00:00:00.000Z',
    updated_at: '2026-01-01T00:00:00.000Z',
  };
}

describe('retail offline queue helpers', () => {
  it('returns true when retrying operation is due', () => {
    const entry = baseEntry('RETRYING', '2026-01-01T00:00:00.000Z');
    expect(isRetailOfflineEntryReady(entry, new Date('2026-01-01T00:00:01.000Z'))).toBe(true);
  });

  it('returns false for failed operation', () => {
    const entry = baseEntry('FAILED', '2026-01-01T00:00:00.000Z');
    expect(isRetailOfflineEntryReady(entry, new Date('2026-01-01T00:00:01.000Z'))).toBe(false);
  });

  it('computes a future retry timestamp', () => {
    const next = nextRetryAtIso(3);
    expect(new Date(next).getTime()).toBeGreaterThan(Date.now());
  });
});

