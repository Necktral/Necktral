import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { InventoryOfflineCommand } from 'src/services/inventory-offline-queue';
import { executeInventoryOfflineCommandSync } from 'src/services/inventory-offline-sync';

const syncBatchApi = vi.hoisted(() => ({
  submitSyncV2Batch: vi.fn(),
}));

vi.mock('src/services/sync-batch.service', () => ({
  submitSyncV2Batch: syncBatchApi.submitSyncV2Batch,
}));

function sampleCommand(): InventoryOfflineCommand {
  return {
    id: 'row-1',
    version: 1,
    command_id: '11111111-1111-4111-8111-111111111111',
    kind: 'RECEIVE',
    status: 'PENDING',
    company_id: 10,
    branch_id: 20,
    dedupe_key: 'inventory:RECEIVE:10:20:key-1',
    payload: {
      warehouse_id: 1,
      item_id: 2,
      qty: '1.0000',
      unit_cost: '1.000000',
      idempotency_key: 'key-1',
    },
    attempts: 0,
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
    processed_at: null,
    next_retry_at: null,
    last_attempt_at: null,
    last_error: '',
    last_reason: '',
  };
}

describe('inventory-offline-sync', () => {
  beforeEach(() => {
    syncBatchApi.submitSyncV2Batch.mockReset();
  });

  it('considera APPLIED/DUPLICATE como aplicado', async () => {
    syncBatchApi.submitSyncV2Batch.mockResolvedValueOnce({
      results: [{ command_id: '11111111-1111-4111-8111-111111111111', status: 'APPLIED' }],
    });

    const applied = await executeInventoryOfflineCommandSync(sampleCommand());
    expect(applied.applied).toBe(true);

    syncBatchApi.submitSyncV2Batch.mockResolvedValueOnce({
      results: [{ command_id: '11111111-1111-4111-8111-111111111111', status: 'DUPLICATE' }],
    });
    const duplicate = await executeInventoryOfflineCommandSync(sampleCommand());
    expect(duplicate.applied).toBe(true);
  });

  it('mapea REJECTED con retryable según reason', async () => {
    syncBatchApi.submitSyncV2Batch.mockResolvedValueOnce({
      results: [
        {
          command_id: '11111111-1111-4111-8111-111111111111',
          status: 'REJECTED',
          reason: 'INVENTORY_INSUFFICIENT_STOCK',
        },
      ],
    });

    const out = await executeInventoryOfflineCommandSync(sampleCommand());
    expect(out.applied).toBe(false);
    expect(out.reason).toBe('INVENTORY_INSUFFICIENT_STOCK');
    expect(out.retryable).toBe(false);
  });

  it('propaga error retryable en fallos de transporte', async () => {
    const err = new Error('network down') as Error & { response?: { status?: number } };
    err.response = { status: 503 };
    syncBatchApi.submitSyncV2Batch.mockRejectedValueOnce(err);

    await expect(executeInventoryOfflineCommandSync(sampleCommand())).rejects.toMatchObject({
      message: 'network down',
      retryable: true,
    });
  });
});
