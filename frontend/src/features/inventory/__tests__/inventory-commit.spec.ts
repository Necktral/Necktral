import { beforeEach, describe, expect, it, vi } from 'vitest';

import { commitInventoryWithOfflineFallback } from 'src/features/inventory/inventory-commit';
import { clearInventoryOfflineQueue, listInventoryOfflineCommands } from 'src/services/inventory-offline-queue';
import type { InventoryCommitPayload } from 'src/services/inventory.service';

function basePayload(overrides?: Partial<InventoryCommitPayload>): InventoryCommitPayload {
  return {
    warehouse_id: 1,
    item_id: 2,
    qty: '3.0000',
    idempotency_key: 'inventory-issue-stable-1',
    note: 'qa',
    ...overrides,
  };
}

describe('inventory-commit offline fallback', () => {
  beforeEach(() => {
    localStorage.clear();
    clearInventoryOfflineQueue();
  });

  it('aplica online cuando la API responde OK', async () => {
    const onlineCommit = vi.fn(async () => {});
    const out = await commitInventoryWithOfflineFallback({
      kind: 'ISSUE',
      payload: basePayload(),
      companyId: 10,
      branchId: 20,
      isOnline: true,
      onlineCommit,
    });

    expect(out).toEqual({ mode: 'ONLINE_APPLIED' });
    expect(onlineCommit).toHaveBeenCalledTimes(1);
    expect(listInventoryOfflineCommands()).toHaveLength(0);
  });

  it('encola offline cuando no hay internet', async () => {
    const onlineCommit = vi.fn(() => {
      throw new Error('network down');
    });
    const out = await commitInventoryWithOfflineFallback({
      kind: 'RECEIVE',
      payload: basePayload({ idempotency_key: 'inventory-receive-stable-1', unit_cost: '1.200000' }),
      companyId: 11,
      branchId: 21,
      isOnline: false,
      onlineCommit,
    });

    expect(out).toEqual({ mode: 'OFFLINE_QUEUED', duplicate: false });
    const rows = listInventoryOfflineCommands();
    expect(rows).toHaveLength(1);
    expect(rows[0]?.status).toBe('PENDING');
    expect(rows[0]?.kind).toBe('RECEIVE');
  });

  it('deduplica cuando se reenvia el mismo idempotency_key', async () => {
    const onlineCommit = vi.fn(() => {
      throw new Error('network down');
    });
    const payload = basePayload({ idempotency_key: 'inventory-issue-stable-2' });

    const first = await commitInventoryWithOfflineFallback({
      kind: 'ISSUE',
      payload,
      companyId: 12,
      branchId: 22,
      isOnline: false,
      onlineCommit,
    });
    const second = await commitInventoryWithOfflineFallback({
      kind: 'ISSUE',
      payload,
      companyId: 12,
      branchId: 22,
      isOnline: false,
      onlineCommit,
    });

    expect(first).toEqual({ mode: 'OFFLINE_QUEUED', duplicate: false });
    expect(second).toEqual({ mode: 'OFFLINE_QUEUED', duplicate: true });
    expect(listInventoryOfflineCommands()).toHaveLength(1);
  });

  it('propaga error no retryable y no encola', async () => {
    const error = new Error('insufficient stock') as Error & { response?: { status?: number } };
    error.response = { status: 400 };
    const onlineCommit = vi.fn(() => {
      throw error;
    });

    await expect(
      commitInventoryWithOfflineFallback({
        kind: 'ISSUE',
        payload: basePayload({ idempotency_key: 'inventory-issue-stable-3' }),
        companyId: 13,
        branchId: 23,
        isOnline: true,
        onlineCommit,
      }),
    ).rejects.toBe(error);
    expect(listInventoryOfflineCommands()).toHaveLength(0);
  });
});
