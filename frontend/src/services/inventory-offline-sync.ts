import {
  type InventoryOfflineCommand,
  type InventoryOfflineCommandExecutionResult,
  toInventorySyncV2Command,
} from 'src/services/inventory-offline-queue';
import { submitSyncV2Batch } from 'src/services/sync-batch.service';

const RETRYABLE_SYNC_REASONS = new Set<string>(['SYNC_INTERNAL_ERROR']);

function classifyTransportError(error: unknown): { retryable: boolean; message: string } {
  if (typeof error === 'object' && error !== null) {
    const maybe = error as {
      message?: string;
      response?: { status?: number; data?: { error?: { message?: string } } };
      code?: string;
    };
    const status = Number(maybe.response?.status || 0);
    const apiMsg = maybe.response?.data?.error?.message;
    const msg = String(apiMsg || maybe.message || maybe.code || 'SYNC_TRANSPORT_ERROR');

    if (msg.includes('No hay dispositivo enrolado para sincronización offline')) {
      return { retryable: false, message: msg };
    }

    if (!status) return { retryable: true, message: msg };
    if (status >= 500 || status === 429) return { retryable: true, message: msg };
    return { retryable: false, message: msg };
  }

  return {
    retryable: true,
    message: String(error),
  };
}

export function isRetryableSyncReason(reason: string): boolean {
  return RETRYABLE_SYNC_REASONS.has(String(reason || '').trim());
}

export async function executeInventoryOfflineCommandSync(
  command: InventoryOfflineCommand,
): Promise<InventoryOfflineCommandExecutionResult> {
  try {
    const data = await submitSyncV2Batch({
      commands: [toInventorySyncV2Command(command)],
    });

    const row = data.results.find((entry) => String(entry.command_id) === String(command.command_id));
    const status = String(row?.status || '');

    if (status === 'APPLIED' || status === 'DUPLICATE') {
      return { applied: true };
    }

    const reason = String(row?.reason || 'SYNC_REJECTED');
    return {
      applied: false,
      reason,
      retryable: isRetryableSyncReason(reason),
    };
  } catch (error) {
    const verdict = classifyTransportError(error);
    const wrapped = new Error(verdict.message) as Error & { retryable?: boolean };
    wrapped.retryable = verdict.retryable;
    throw wrapped;
  }
}
