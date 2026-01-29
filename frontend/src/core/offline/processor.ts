import type { AxiosInstance } from 'axios';
import { isAxiosError } from 'axios';

import { extractErrorMessage } from 'src/core/http/errors';
import { readTokens } from 'src/core/storage/auth';
import { readContext } from 'src/core/storage/context';
import { getJwtUserId } from 'src/core/auth/jwt';
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

  for (const item of due) {
    if (typeof navigator !== 'undefined' && navigator.onLine === false) {
      return {
        sent,
        failed,
        remaining: due.length - sent - failed,
        stoppedByOffline: true,
      };
    }

    // Defensa: no permitir que comandos offline se apliquen con otro scope/actor.
    // (Ej: usuario cambió de empresa, o cerró sesión y entró otro operador).
    const ctx = readContext();
    const tokens = readTokens();
    const activeUserId = getJwtUserId(tokens.access);

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

    item.status = 'sending';
    await updateOutboxItem(item);

    try {
      const headers = item.request.headers;
      await api.request({
        method: item.request.method,
        url: item.request.url,
        data: item.request.body,
        ...(headers ? { headers } : {}),
      });

      await removeOutboxItem(item.id);
      sent += 1;
    } catch (e) {
      if (isNetworkError(e)) {
        // Si se cayó red, dejamos el item como failed para reintentar luego, y paramos.
        await markFailed(item, extractErrorMessage(e), true);
        failed += 1;
        return {
          sent,
          failed,
          remaining: due.length - sent - failed,
          stoppedByOffline: true,
        };
      }

      const status = isAxiosError(e) ? e.response?.status : undefined;
      const retryable = typeof status === 'number' ? isRetryableStatus(status) : false;
      await markFailed(item, extractErrorMessage(e), retryable);
      failed += 1;
    }
  }

  const remaining = (await getDueOutboxItems(10_000)).length;
  return { sent, failed, remaining, stoppedByOffline: false };
}
