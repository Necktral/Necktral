import { readTokens } from 'src/core/storage/auth';
import { readContext } from 'src/core/storage/context';
import { getJwtUserId } from 'src/core/auth/jwt';

import { getOfflineDb, type OutboxItem, type OutboxRequest, type OutboxStatus } from './db';

export function newUuid(): string {
  if (typeof crypto !== 'undefined' && 'randomUUID' in crypto) {
    return crypto.randomUUID();
  }
  // Fallback best-effort: mantener charset permitido por RequestIdMiddleware
  return `req-${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

export type EnqueueOutboxInput<Kind extends string> = {
  kind: Kind;
  request: OutboxRequest;
};

function buildRequestId(): string {
  // header contractual: X-Request-Id (regex: ^[A-Za-z0-9._:-]{1,128}$)
  return newUuid()
    .replace(/[^A-Za-z0-9._:-]/g, '_')
    .slice(0, 128);
}

export async function enqueueOutboxItem<Kind extends string>(
  input: EnqueueOutboxInput<Kind>,
): Promise<OutboxItem<Kind>> {
  const now = Date.now();

  const ctx = readContext();
  const tokens = readTokens();
  const queuedUserId = getJwtUserId(tokens.access);
  const requestId = buildRequestId();

  const headers: Record<string, string> = {
    ...(input.request.headers ?? {}),
    'X-Request-Id': requestId,
  };
  if (ctx.companyId) headers['X-Company-Id'] = ctx.companyId;
  if (ctx.branchId) headers['X-Branch-Id'] = ctx.branchId;

  const item: OutboxItem<Kind> = {
    id: newUuid(),
    kind: input.kind,
    status: 'pending',
    createdAt: now,
    updatedAt: now,
    attemptCount: 0,
    nextAttemptAt: null,
    lastError: null,
    request: {
      ...input.request,
      headers,
    },

    queuedCompanyId: ctx.companyId,
    queuedBranchId: ctx.branchId,
    queuedUserId,
    requestId,
  };

  const db = await getOfflineDb();
  await db.put('outbox', item as OutboxItem);
  return item;
}

export async function listOutboxItems(): Promise<OutboxItem[]> {
  const db = await getOfflineDb();
  return await db.getAll('outbox');
}

export async function countOutboxByStatus(status: OutboxStatus): Promise<number> {
  const db = await getOfflineDb();
  const rows = await db.getAllFromIndex('outbox', 'by_status', status);
  return rows.length;
}

export async function getDueOutboxItems(limit = 50): Promise<OutboxItem[]> {
  const now = Date.now();
  const db = await getOfflineDb();
  const all = await db.getAll('outbox');

  return all
    .filter((x) => {
      if (x.status === 'sending') return false;
      if (x.nextAttemptAt != null && x.nextAttemptAt > now) return false;
      return x.status === 'pending' || x.status === 'failed';
    })
    .sort((a, b) => a.createdAt - b.createdAt)
    .slice(0, Math.max(1, limit));
}

export async function updateOutboxItem(item: OutboxItem): Promise<void> {
  item.updatedAt = Date.now();
  const db = await getOfflineDb();
  await db.put('outbox', item);
}

export async function removeOutboxItem(id: string): Promise<void> {
  const db = await getOfflineDb();
  await db.delete('outbox', id);
}
