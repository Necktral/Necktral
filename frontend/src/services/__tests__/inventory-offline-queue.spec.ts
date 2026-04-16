import { beforeEach, describe, expect, it, vi } from 'vitest';

import {
  buildInventoryOfflineDedupeKey,
  canInventoryOfflineTransition,
  clearInventoryOfflineQueue,
  drainInventoryOfflineQueue,
  enqueueInventoryOfflineCommand,
  getInventoryOfflineQueueStats,
  listInventoryOfflineCommands,
  retryFinalInventoryOfflineCommand,
  toInventorySyncV2Command,
} from 'src/services/inventory-offline-queue';
import { STORAGE_KEYS } from 'src/core/storage/keys';

describe('inventory-offline-queue', () => {
  beforeEach(() => {
    localStorage.clear();
    clearInventoryOfflineQueue();
  });

  it('expone transiciones validas de la maquina de estados', () => {
    expect(canInventoryOfflineTransition('PENDING', 'SYNCING')).toBe(true);
    expect(canInventoryOfflineTransition('SYNCING', 'APPLIED')).toBe(true);
    expect(canInventoryOfflineTransition('FAILED_FINAL', 'PENDING')).toBe(true);
    expect(canInventoryOfflineTransition('PENDING', 'APPLIED')).toBe(false);
    expect(canInventoryOfflineTransition('APPLIED', 'PENDING')).toBe(false);
  });

  it('evita duplicados por dedupe_key activo', () => {
    const dedupe = buildInventoryOfflineDedupeKey({
      kind: 'RECEIVE',
      company_id: 10,
      branch_id: 20,
      idempotency_key: 'inv-idem-001',
    });

    const first = enqueueInventoryOfflineCommand({
      kind: 'RECEIVE',
      company_id: 10,
      branch_id: 20,
      dedupe_key: dedupe,
      payload: {
        warehouse_id: 1,
        item_id: 2,
        qty: '10.0000',
        unit_cost: '1.200000',
        idempotency_key: 'inv-idem-001',
        note: 'offline receive',
      },
    });

    const second = enqueueInventoryOfflineCommand({
      kind: 'RECEIVE',
      company_id: 10,
      branch_id: 20,
      dedupe_key: dedupe,
      payload: {
        warehouse_id: 1,
        item_id: 2,
        qty: '10.0000',
        unit_cost: '1.200000',
        idempotency_key: 'inv-idem-001',
      },
    });

    expect(first.duplicate).toBe(false);
    expect(second.duplicate).toBe(true);
    expect(second.command.id).toBe(first.command.id);
    expect(listInventoryOfflineCommands()).toHaveLength(1);
  });

  it('convierte comando local a Sync v2 con idempotency estable', () => {
    const dedupe = buildInventoryOfflineDedupeKey({
      kind: 'ISSUE',
      company_id: 11,
      branch_id: 21,
      idempotency_key: 'inv-idem-002',
    });

    const row = enqueueInventoryOfflineCommand({
      kind: 'ISSUE',
      company_id: 11,
      branch_id: 21,
      dedupe_key: dedupe,
      payload: {
        warehouse_id: 3,
        item_id: 4,
        qty: '2.0000',
        idempotency_key: 'inv-idem-002',
        note: 'offline issue',
      },
    }).command;

    const syncCmd = toInventorySyncV2Command(row);
    expect(syncCmd.type).toBe('INVENTORY.MOVEMENT.ISSUE');
    expect(syncCmd.scope.company_id).toBe(11);
    expect(syncCmd.scope.branch_id).toBe(21);
    expect(syncCmd.payload.idempotency_key).toBe('inv-idem-002');
  });

  it('drena cola y marca APPLIED cuando executor aplica', async () => {
    const dedupe = buildInventoryOfflineDedupeKey({
      kind: 'RECEIVE',
      company_id: 12,
      branch_id: 22,
      idempotency_key: 'inv-idem-003',
    });

    enqueueInventoryOfflineCommand({
      kind: 'RECEIVE',
      company_id: 12,
      branch_id: 22,
      dedupe_key: dedupe,
      payload: {
        warehouse_id: 1,
        item_id: 1,
        qty: '5.0000',
        unit_cost: '1.000000',
        idempotency_key: 'inv-idem-003',
      },
    });

    const executor = vi.fn(() => Promise.resolve({ applied: true as const }));
    const result = await drainInventoryOfflineQueue({ executor, maxCommands: 5 });

    expect(result.succeeded).toBe(1);
    expect(executor).toHaveBeenCalledTimes(1);

    const rows = listInventoryOfflineCommands();
    expect(rows).toHaveLength(1);
    expect(rows[0]?.status).toBe('APPLIED');

    const stats = getInventoryOfflineQueueStats();
    expect(stats.applied).toBe(1);
  });

  it('marca FAILED_RETRYABLE en rechazo retryable', async () => {
    const dedupe = buildInventoryOfflineDedupeKey({
      kind: 'ISSUE',
      company_id: 13,
      branch_id: 23,
      idempotency_key: 'inv-idem-004',
    });

    enqueueInventoryOfflineCommand({
      kind: 'ISSUE',
      company_id: 13,
      branch_id: 23,
      dedupe_key: dedupe,
      payload: {
        warehouse_id: 9,
        item_id: 8,
        qty: '1.0000',
        idempotency_key: 'inv-idem-004',
      },
    });

    const result = await drainInventoryOfflineQueue({
      executor: () => Promise.resolve({ applied: false, reason: 'SYNC_INTERNAL_ERROR', retryable: true }),
      maxCommands: 5,
    });

    expect(result.failed_retryable).toBe(1);
    const row = listInventoryOfflineCommands()[0];
    expect(row?.status).toBe('FAILED_RETRYABLE');
    expect(row?.attempts).toBe(1);
    expect(row?.next_retry_at).not.toBeNull();
  });

  it('flujo offline->reconexion: retryable luego APPLIED', async () => {
    const dedupe = buildInventoryOfflineDedupeKey({
      kind: 'RECEIVE',
      company_id: 15,
      branch_id: 25,
      idempotency_key: 'inv-idem-006',
    });

    enqueueInventoryOfflineCommand({
      kind: 'RECEIVE',
      company_id: 15,
      branch_id: 25,
      dedupe_key: dedupe,
      payload: {
        warehouse_id: 1,
        item_id: 2,
        qty: '7.0000',
        unit_cost: '1.500000',
        idempotency_key: 'inv-idem-006',
      },
    });

    await drainInventoryOfflineQueue({
      executor: () => Promise.resolve({ applied: false, reason: 'SYNC_INTERNAL_ERROR', retryable: true }),
      maxCommands: 5,
    });

    const afterFail = listInventoryOfflineCommands()[0];
    expect(afterFail?.status).toBe('FAILED_RETRYABLE');

    const afterFailTs = Date.parse(afterFail?.next_retry_at || '');
    expect(Number.isFinite(afterFailTs)).toBe(true);

    await drainInventoryOfflineQueue({
      executor: () => Promise.resolve({ applied: true }),
      maxCommands: 5,
      nowMs: afterFailTs + 1000,
    });

    const afterSync = listInventoryOfflineCommands()[0];
    expect(afterSync?.status).toBe('APPLIED');
  });

  it('marca FAILED_FINAL y permite retry manual', async () => {
    const dedupe = buildInventoryOfflineDedupeKey({
      kind: 'ISSUE',
      company_id: 14,
      branch_id: 24,
      idempotency_key: 'inv-idem-005',
    });

    const command = enqueueInventoryOfflineCommand({
      kind: 'ISSUE',
      company_id: 14,
      branch_id: 24,
      dedupe_key: dedupe,
      payload: {
        warehouse_id: 5,
        item_id: 6,
        qty: '3.0000',
        idempotency_key: 'inv-idem-005',
      },
    }).command;

    const result = await drainInventoryOfflineQueue({
      executor: () =>
        Promise.resolve({ applied: false, reason: 'INVENTORY_INSUFFICIENT_STOCK', retryable: false }),
      maxCommands: 5,
    });

    expect(result.failed_final).toBe(1);
    const failed = listInventoryOfflineCommands().find((row) => row.id === command.id);
    expect(failed?.status).toBe('FAILED_FINAL');

    const retried = retryFinalInventoryOfflineCommand(command.id);
    expect(retried?.status).toBe('PENDING');
  });

  it('recupera cola corrupta sin romper y guarda snapshot de recovery', () => {
    localStorage.setItem(STORAGE_KEYS.INVENTORY_OFFLINE_QUEUE, '{mal-json');
    expect(listInventoryOfflineCommands()).toEqual([]);

    const recoveryRaw = localStorage.getItem(STORAGE_KEYS.INVENTORY_OFFLINE_QUEUE_RECOVERY);
    expect(typeof recoveryRaw).toBe('string');
    const recovery = JSON.parse(recoveryRaw || '{}') as { reason?: string; raw?: string };
    expect(recovery.reason).toBe('QUEUE_JSON_PARSE_ERROR');
    expect(recovery.raw).toContain('{mal-json');
  });

  it('resetea cola con version futura desconocida y conserva snapshot de recovery', () => {
    localStorage.setItem(
      STORAGE_KEYS.INVENTORY_OFFLINE_QUEUE,
      JSON.stringify({ version: 999, commands: [{ id: 'x' }] }),
    );
    expect(listInventoryOfflineCommands()).toEqual([]);

    const recoveryRaw = localStorage.getItem(STORAGE_KEYS.INVENTORY_OFFLINE_QUEUE_RECOVERY);
    const recovery = JSON.parse(recoveryRaw || '{}') as { reason?: string };
    expect(recovery.reason).toBe('UNSUPPORTED_QUEUE_VERSION_999');
  });
});
