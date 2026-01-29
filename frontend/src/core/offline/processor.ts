import type { AxiosInstance } from 'axios';
import { isAxiosError } from 'axios';

import { extractErrorMessage } from 'src/core/http/errors';
import { readTokens } from 'src/core/storage/auth';
import { readContext } from 'src/core/storage/context';
import { getJwtUserId } from 'src/core/auth/jwt';
import { readSyncDevice, writeSyncLastSequence } from 'src/core/storage/sync_device';
import {
  buildCommandSigningMessage,
  canonJson,
  occurredAtCanonical,
  sha256Hex,
  signEd25519Detached,
} from 'src/core/sync/signing';
import { newUuid } from './outbox';
import { getDueOutboxItems, removeOutboxItem, updateOutboxItem } from './outbox';
import type { OutboxItem } from './db';

export type FlushResult = {
  sent: number;
  failed: number;
  remaining: number;
  stoppedByOffline: boolean;
};

function computeBackoffMs(attemptCount: number): number {
  const exp = Math.min(6, Math.max(0, attemptCount));
  const base = 1_000 * 2 ** exp;
  return Math.min(60_000, base);
}

function isRetryableStatus(status: number): boolean {
  return status === 429 || status === 503 || status === 502 || status === 500;
}

function isNetworkError(e: unknown): boolean {
  return isAxiosError(e) && !e.response;
}

function mapKindToCommandType(kind: string): string {
  switch (kind) {
    case 'inventory.movement.receive':
      return 'INVENTORY_MOVEMENT_RECEIVE';
    case 'inventory.movement.issue':
      return 'INVENTORY_MOVEMENT_ISSUE';
    case 'inventory.movement.adjust':
      return 'INVENTORY_MOVEMENT_ADJUST';
    case 'inventory.transfer.create':
      return 'INVENTORY_TRANSFER';
    default:
      return '';
  }
}

function isRetryableSyncReason(reason: string): boolean {
  return (
    reason === 'SYNC_INTERNAL_ERROR' ||
    reason === 'SYNC_DEVICE_QUARANTINED' ||
    reason === 'SYNC_TIME_SKEW'
  );
}

async function markFailed(item: OutboxItem, message: string, retryable: boolean) {
  item.status = 'failed';
  item.lastError = message;
  item.attemptCount += 1;
  item.nextAttemptAt = retryable ? Date.now() + computeBackoffMs(item.attemptCount) : null;
  await updateOutboxItem(item);
}

export async function flushOutbox(api: AxiosInstance, limit = 25): Promise<FlushResult> {
  const due = await getDueOutboxItems(limit);

  let sent = 0;
  let failed = 0;

  if (due.length === 0) {
    return { sent: 0, failed: 0, remaining: 0, stoppedByOffline: false };
  }

  if (typeof navigator !== 'undefined' && navigator.onLine === false) {
    return { sent: 0, failed: 0, remaining: due.length, stoppedByOffline: true };
  }

  const syncDevice = readSyncDevice();
  if (!syncDevice.deviceId || !syncDevice.secretKeyB64) {
    for (const item of due) {
      await markFailed(item, 'SyncDeviceNotEnrolled: enroll device before flushing outbox', false);
      failed += 1;
    }
    return { sent, failed, remaining: 0, stoppedByOffline: false };
  }

  // Filtrar items inválidos (scope/actor/kind)
  const ctx = readContext();
  const tokens = readTokens();
  const activeUserId = getJwtUserId(tokens.access);

  const toSend: OutboxItem[] = [];
  for (const item of due) {
    const scopeChanged =
      item.queuedCompanyId !== ctx.companyId || item.queuedBranchId !== ctx.branchId;
    const userChanged = item.queuedUserId !== activeUserId;
    if (scopeChanged || userChanged) {
      await markFailed(
        item,
        `OutboxScopeChanged: queued(company=${item.queuedCompanyId}, branch=${item.queuedBranchId}, user=${String(
          item.queuedUserId,
        )}) active(company=${ctx.companyId}, branch=${ctx.branchId}, user=${String(activeUserId)})`,
        false,
      );
      failed += 1;
      continue;
    }

    const commandType = mapKindToCommandType(item.kind);
    if (!commandType) {
      await markFailed(item, `SyncUnsupportedKind: ${item.kind}`, false);
      failed += 1;
      continue;
    }
    toSend.push(item);
  }

  if (toSend.length === 0) {
    return {
      sent,
      failed,
      remaining: (await getDueOutboxItems(10_000)).length,
      stoppedByOffline: false,
    };
  }

  // Marcar como sending antes de enviar el batch
  for (const item of toSend) {
    item.status = 'sending';
    await updateOutboxItem(item);
  }

  let nextSeq = Math.max(0, syncDevice.lastSequence || 0);
  const commands = [] as any[];

  for (const item of toSend) {
    const command_type = mapKindToCommandType(item.kind);
    const company_id = Number(item.queuedCompanyId);
    const branch_id = item.queuedBranchId == null ? null : Number(item.queuedBranchId);

    if (!Number.isFinite(company_id) || company_id <= 0) {
      await markFailed(item, 'SyncSchemaInvalid: company_id missing/invalid', false);
      failed += 1;
      continue;
    }
    if (branch_id == null || !Number.isFinite(branch_id) || branch_id <= 0) {
      await markFailed(item, 'SyncSchemaInvalid: branch_id missing/invalid', false);
      failed += 1;
      continue;
    }

    nextSeq += 1;
    const occurred_at = occurredAtCanonical(new Date(item.createdAt));
    const payload = item.request.body;
    const payload_hash = await sha256Hex(canonJson(payload));
    const prev_hash = '';

    const msg = buildCommandSigningMessage({
      command_id: item.id,
      command_type,
      company_id,
      branch_id,
      occurred_at,
      sequence: nextSeq,
      payload_hash,
      prev_hash,
    });

    const signature = signEd25519Detached({ secretKeyB64: syncDevice.secretKeyB64, message: msg });

    commands.push({
      command_id: item.id,
      command_type,
      company_id,
      branch_id,
      occurred_at,
      sequence: nextSeq,
      payload,
      payload_hash,
      prev_hash,
      signature,
    });
  }

  if (commands.length === 0) {
    return {
      sent,
      failed,
      remaining: (await getDueOutboxItems(10_000)).length,
      stoppedByOffline: false,
    };
  }

  const batch_id = newUuid();
  try {
    const { data } = await api.post(
      '/sync/batch/',
      {
        batch_id,
        device_id: syncDevice.deviceId,
        sent_at: new Date().toISOString(),
        commands,
      },
      {
        headers: {
          'X-Device-Id': syncDevice.deviceId,
        },
      },
    );

    const results: Array<{ command_id: string; status: string; reason?: string }> =
      data?.results ?? [];
    const byId = new Map(results.map((r) => [r.command_id, r] as const));

    for (const item of toSend) {
      const r = byId.get(item.id);
      if (!r) {
        await markFailed(item, 'SyncNoResult: server did not return result for command', true);
        failed += 1;
        continue;
      }

      if (r.status === 'APPLIED' || r.status === 'DUPLICATE') {
        await removeOutboxItem(item.id);
        sent += 1;
        continue;
      }

      const reason = r.reason || 'SYNC_REJECTED';
      await markFailed(item, `SyncRejected: ${reason}`, isRetryableSyncReason(reason));
      failed += 1;
    }

    writeSyncLastSequence(nextSeq);
  } catch (e) {
    if (isNetworkError(e)) {
      for (const item of toSend) {
        await markFailed(item, extractErrorMessage(e), true);
        failed += 1;
      }
      return {
        sent,
        failed,
        remaining: due.length - sent - failed,
        stoppedByOffline: true,
      };
    }

    const status = isAxiosError(e) ? e.response?.status : undefined;
    const retryable = typeof status === 'number' ? isRetryableStatus(status) : false;
    for (const item of toSend) {
      await markFailed(item, extractErrorMessage(e), retryable);
      failed += 1;
    }
  }

  const remaining = (await getDueOutboxItems(10_000)).length;
  return { sent, failed, remaining, stoppedByOffline: false };
}
