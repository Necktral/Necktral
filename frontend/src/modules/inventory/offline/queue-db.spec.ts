import { describe, expect, it } from 'vitest';

import { isCommandReadyToRetry, type OfflineQueuedCommand } from 'src/modules/inventory/offline/queue-db';

function baseRow(status: OfflineQueuedCommand['status'], next_attempt_at: string): OfflineQueuedCommand {
  return {
    id: '1',
    command_id: 'cmd-1',
    company_id: '1',
    branch_id: '2',
    scope_key: '1:2',
    type: 'INVENTORY.MOVEMENT.RECEIVE',
    payload: {},
    idempotency_key: 'idem-1',
    status,
    attempts: 0,
    next_attempt_at,
    last_error_code: '',
    last_error_detail: '',
    created_at: '2026-01-01T00:00:00.000Z',
    updated_at: '2026-01-01T00:00:00.000Z',
  };
}

describe('inventory offline queue helpers', () => {
  it('returns true when pending command is due', () => {
    const row = baseRow('PENDING', '2026-01-01T00:00:00.000Z');
    expect(isCommandReadyToRetry(row, new Date('2026-01-01T00:00:01.000Z'))).toBe(true);
  });

  it('returns false when command status is conflict', () => {
    const row = baseRow('CONFLICT', '2026-01-01T00:00:00.000Z');
    expect(isCommandReadyToRetry(row, new Date('2026-01-01T00:00:01.000Z'))).toBe(false);
  });
});
