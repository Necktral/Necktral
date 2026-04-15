import type { InventoryCommitPayload } from 'src/services/inventory.service';
import {
  buildInventoryOfflineDedupeKey,
  enqueueInventoryOfflineCommand,
} from 'src/services/inventory-offline-queue';

export type InventoryCommitKind = 'RECEIVE' | 'ISSUE';

export type InventoryCommitOutcome =
  | { mode: 'ONLINE_APPLIED' }
  | { mode: 'OFFLINE_QUEUED'; duplicate: boolean };

function normalizeApiErrorMessage(cause: unknown): string {
  if (typeof cause === 'object' && cause !== null) {
    const response = (cause as { response?: { data?: { error?: { message?: string } } } }).response;
    const msg = response?.data?.error?.message;
    if (msg) return msg;
  }
  if (cause instanceof Error) return cause.message;
  return String(cause);
}

export function shouldQueueInventoryCommitOffline(cause: unknown, isOnline: boolean): boolean {
  if (!isOnline) return true;
  if (typeof cause === 'object' && cause !== null) {
    const status = Number((cause as { response?: { status?: number } }).response?.status || 0);
    if (!status) return true;
    if (status >= 500 || status === 429) return true;
  }
  return false;
}

export async function commitInventoryWithOfflineFallback(options: {
  kind: InventoryCommitKind;
  payload: InventoryCommitPayload;
  companyId: number;
  branchId: number;
  isOnline: boolean;
  onlineCommit: (kind: InventoryCommitKind, payload: InventoryCommitPayload) => Promise<void>;
}): Promise<InventoryCommitOutcome> {
  try {
    await options.onlineCommit(options.kind, options.payload);
    return { mode: 'ONLINE_APPLIED' };
  } catch (cause) {
    if (!shouldQueueInventoryCommitOffline(cause, options.isOnline)) {
      throw cause;
    }

    if (options.companyId <= 0 || options.branchId <= 0) {
      throw new Error(`${normalizeApiErrorMessage(cause)} (sin contexto valido para encolar)`);
    }

    const dedupeKey = buildInventoryOfflineDedupeKey({
      kind: options.kind,
      company_id: options.companyId,
      branch_id: options.branchId,
      idempotency_key: options.payload.idempotency_key,
    });

    const { duplicate } = enqueueInventoryOfflineCommand({
      kind: options.kind,
      company_id: options.companyId,
      branch_id: options.branchId,
      dedupe_key: dedupeKey,
      payload: options.payload,
    });

    return { mode: 'OFFLINE_QUEUED', duplicate };
  }
}
