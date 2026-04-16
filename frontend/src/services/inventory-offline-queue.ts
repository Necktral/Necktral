import { STORAGE_KEYS } from 'src/core/storage/keys';

const INVENTORY_OFFLINE_QUEUE_VERSION = 1;
const INVENTORY_OFFLINE_MAX_ATTEMPTS = 8;
const INVENTORY_OFFLINE_DONE_KEEP = 100;
const INVENTORY_OFFLINE_BACKOFF_CAP_MS = 15 * 60 * 1000;
const INVENTORY_OFFLINE_RECOVERY_MAX_CHARS = 4000;

export type InventoryOfflineCommandKind = 'RECEIVE' | 'ISSUE';

export type InventoryOfflineCommandStatus =
  | 'PENDING'
  | 'SYNCING'
  | 'APPLIED'
  | 'FAILED_RETRYABLE'
  | 'FAILED_FINAL';

const INVENTORY_OFFLINE_ALLOWED_TRANSITIONS: Record<
  InventoryOfflineCommandStatus,
  readonly InventoryOfflineCommandStatus[]
> = {
  PENDING: ['SYNCING'],
  SYNCING: ['APPLIED', 'FAILED_RETRYABLE', 'FAILED_FINAL'],
  FAILED_RETRYABLE: ['SYNCING'],
  FAILED_FINAL: ['PENDING'],
  APPLIED: [],
};

export type InventoryOfflineCommandPayload = {
  warehouse_id: number;
  item_id: number;
  qty: string;
  idempotency_key: string;
  note?: string;
  unit_cost?: string;
};

export type InventoryOfflineCommand = {
  id: string;
  version: number;
  command_id: string;
  kind: InventoryOfflineCommandKind;
  status: InventoryOfflineCommandStatus;
  company_id: number;
  branch_id: number;
  dedupe_key: string;
  payload: InventoryOfflineCommandPayload;
  attempts: number;
  created_at: string;
  updated_at: string;
  processed_at: string | null;
  next_retry_at: string | null;
  last_attempt_at: string | null;
  last_error: string;
  last_reason: string;
};

export type InventoryOfflineQueueStats = {
  total: number;
  pending: number;
  syncing: number;
  applied: number;
  failed_retryable: number;
  failed_final: number;
  due_now: number;
};

export type InventoryOfflineDrainResult = {
  attempted: number;
  succeeded: number;
  failed_retryable: number;
  failed_final: number;
};

export type InventoryOfflineCommandExecutionResult = {
  applied: boolean;
  reason?: string;
  retryable?: boolean;
};

type InventoryOfflineQueueState = {
  version: number;
  commands: InventoryOfflineCommand[];
};

type InventoryOfflineDrainOptions = {
  executor: (command: InventoryOfflineCommand) => Promise<InventoryOfflineCommandExecutionResult>;
  nowMs?: number;
  maxCommands?: number;
};

function nowIso(nowMs = Date.now()): string {
  return new Date(nowMs).toISOString();
}

function parseIsoMs(value: string | null | undefined): number {
  if (!value) return 0;
  const ms = Date.parse(value);
  return Number.isFinite(ms) ? ms : 0;
}

function nextBackoffMs(attempt: number): number {
  const step = Math.max(1, Math.min(12, attempt));
  const base = 2 ** step * 1000;
  return Math.min(base, INVENTORY_OFFLINE_BACKOFF_CAP_MS);
}

function randomId(): string {
  const g = globalThis as unknown as { crypto?: { randomUUID?: () => string } };
  if (g.crypto?.randomUUID) return g.crypto.randomUUID();
  return `invq_${Math.random().toString(36).slice(2)}_${Date.now()}`;
}

function randomUuid(): string {
  const g = globalThis as unknown as { crypto?: { randomUUID?: () => string } };
  if (g.crypto?.randomUUID) return g.crypto.randomUUID();
  let d = Date.now();
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (c) => {
    const r = (d + Math.random() * 16) % 16 | 0;
    d = Math.floor(d / 16);
    const v = c === 'x' ? r : (r & 0x3) | 0x8;
    return v.toString(16);
  });
}

function safeString(value: unknown, fallback = ''): string {
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean') return String(value);
  return fallback;
}

function canTransitionStatus(
  from: InventoryOfflineCommandStatus,
  to: InventoryOfflineCommandStatus,
): boolean {
  if (from === to) return true;
  return INVENTORY_OFFLINE_ALLOWED_TRANSITIONS[from].includes(to);
}

function storeQueueRecoverySnapshot(raw: string, reason: string): void {
  try {
    localStorage.setItem(
      STORAGE_KEYS.INVENTORY_OFFLINE_QUEUE_RECOVERY,
      JSON.stringify({
        reason,
        captured_at: nowIso(),
        raw: raw.slice(0, INVENTORY_OFFLINE_RECOVERY_MAX_CHARS),
      }),
    );
  } catch {
    // Non-blocking: la cola debe seguir operativa aunque falle la evidencia de recovery.
  }
}

function cloneCommand(raw: InventoryOfflineCommand): InventoryOfflineCommand {
  return {
    ...raw,
    payload: JSON.parse(JSON.stringify(raw.payload)) as InventoryOfflineCommandPayload,
  };
}

function sanitizeStatus(value: string): InventoryOfflineCommandStatus {
  if (
    value === 'PENDING' ||
    value === 'SYNCING' ||
    value === 'APPLIED' ||
    value === 'FAILED_RETRYABLE' ||
    value === 'FAILED_FINAL'
  ) {
    return value;
  }
  return 'PENDING';
}

function sanitizeKind(value: string): InventoryOfflineCommandKind {
  if (value === 'RECEIVE' || value === 'ISSUE') return value;
  return 'RECEIVE';
}

function normalizeCommand(raw: unknown): InventoryOfflineCommand | null {
  if (typeof raw !== 'object' || raw === null) return null;
  const row = raw as Record<string, unknown>;

  const id = safeString(row.id).trim();
  const commandId = safeString(row.command_id).trim();
  const dedupeKey = safeString(row.dedupe_key).trim();
  const companyId = Number(row.company_id);
  const branchId = Number(row.branch_id);
  if (!id || !commandId || !dedupeKey || !Number.isFinite(companyId) || !Number.isFinite(branchId)) return null;

  const payloadRaw = (row.payload ?? {}) as Record<string, unknown>;
  const warehouseId = Number(payloadRaw.warehouse_id);
  const itemId = Number(payloadRaw.item_id);
  const qty = safeString(payloadRaw.qty).trim();
  const idempotency = safeString(payloadRaw.idempotency_key).trim();
  if (!idempotency || !qty || !Number.isFinite(warehouseId) || !Number.isFinite(itemId)) return null;

  return {
    id,
    version: Number(row.version) || INVENTORY_OFFLINE_QUEUE_VERSION,
    command_id: commandId,
    kind: sanitizeKind(safeString(row.kind, 'RECEIVE')),
    status: sanitizeStatus(safeString(row.status, 'PENDING')),
    company_id: companyId,
    branch_id: branchId,
    dedupe_key: dedupeKey,
    payload: {
      warehouse_id: warehouseId,
      item_id: itemId,
      qty,
      idempotency_key: idempotency,
      ...(payloadRaw.note !== undefined ? { note: safeString(payloadRaw.note) } : {}),
      ...(payloadRaw.unit_cost !== undefined ? { unit_cost: safeString(payloadRaw.unit_cost) } : {}),
    },
    attempts: Math.max(0, Number(row.attempts) || 0),
    created_at: safeString(row.created_at, new Date(0).toISOString()),
    updated_at: safeString(row.updated_at, new Date(0).toISOString()),
    processed_at: row.processed_at ? safeString(row.processed_at) : null,
    next_retry_at: row.next_retry_at ? safeString(row.next_retry_at) : null,
    last_attempt_at: row.last_attempt_at ? safeString(row.last_attempt_at) : null,
    last_error: safeString(row.last_error, ''),
    last_reason: safeString(row.last_reason, ''),
  };
}

function readQueueState(): InventoryOfflineQueueState {
  const raw = localStorage.getItem(STORAGE_KEYS.INVENTORY_OFFLINE_QUEUE);
  if (!raw) return { version: INVENTORY_OFFLINE_QUEUE_VERSION, commands: [] };

  try {
    const parsed = JSON.parse(raw) as { version?: number; commands?: unknown[] };
    const persistedVersion = Number(parsed.version) || INVENTORY_OFFLINE_QUEUE_VERSION;
    if (persistedVersion > INVENTORY_OFFLINE_QUEUE_VERSION) {
      storeQueueRecoverySnapshot(raw, `UNSUPPORTED_QUEUE_VERSION_${persistedVersion}`);
      localStorage.removeItem(STORAGE_KEYS.INVENTORY_OFFLINE_QUEUE);
      return { version: INVENTORY_OFFLINE_QUEUE_VERSION, commands: [] };
    }
    const commands = Array.isArray(parsed.commands)
      ? parsed.commands.map(normalizeCommand).filter((v): v is InventoryOfflineCommand => Boolean(v))
      : [];

    return {
      version: INVENTORY_OFFLINE_QUEUE_VERSION,
      commands,
    };
  } catch {
    storeQueueRecoverySnapshot(raw, 'QUEUE_JSON_PARSE_ERROR');
    localStorage.removeItem(STORAGE_KEYS.INVENTORY_OFFLINE_QUEUE);
    return { version: INVENTORY_OFFLINE_QUEUE_VERSION, commands: [] };
  }
}

function writeQueueState(state: InventoryOfflineQueueState): void {
  const applied = state.commands
    .filter((row) => row.status === 'APPLIED')
    .sort((a, b) => parseIsoMs(b.processed_at) - parseIsoMs(a.processed_at))
    .slice(0, INVENTORY_OFFLINE_DONE_KEEP);
  const active = state.commands.filter((row) => row.status !== 'APPLIED');
  const compacted = [...active, ...applied].sort((a, b) => parseIsoMs(a.created_at) - parseIsoMs(b.created_at));

  localStorage.setItem(
    STORAGE_KEYS.INVENTORY_OFFLINE_QUEUE,
    JSON.stringify({
      version: INVENTORY_OFFLINE_QUEUE_VERSION,
      commands: compacted,
    }),
  );
}

function updateQueue(mutator: (state: InventoryOfflineQueueState) => InventoryOfflineQueueState): InventoryOfflineQueueState {
  const current = readQueueState();
  const next = mutator(current);
  writeQueueState(next);
  return next;
}

function isDue(command: InventoryOfflineCommand, nowMs: number): boolean {
  if (command.status === 'APPLIED') return false;
  if (command.status === 'SYNCING') return false;
  if (command.status === 'FAILED_FINAL') return false;
  const at = parseIsoMs(command.next_retry_at);
  return !at || at <= nowMs;
}

export function buildInventoryOfflineDedupeKey(params: {
  kind: InventoryOfflineCommandKind;
  company_id: number;
  branch_id: number;
  idempotency_key: string;
}): string {
  return `inventory:${params.kind}:${params.company_id}:${params.branch_id}:${params.idempotency_key}`;
}

export function listInventoryOfflineCommands(): InventoryOfflineCommand[] {
  return readQueueState().commands.map(cloneCommand);
}

export function clearInventoryOfflineQueue(): void {
  localStorage.removeItem(STORAGE_KEYS.INVENTORY_OFFLINE_QUEUE);
  localStorage.removeItem(STORAGE_KEYS.INVENTORY_OFFLINE_QUEUE_RECOVERY);
}

export function getInventoryOfflineQueueStats(nowMs = Date.now()): InventoryOfflineQueueStats {
  const rows = readQueueState().commands;
  let pending = 0;
  let syncing = 0;
  let applied = 0;
  let failedRetryable = 0;
  let failedFinal = 0;
  let dueNow = 0;

  for (const row of rows) {
    if (row.status === 'PENDING') pending += 1;
    else if (row.status === 'SYNCING') syncing += 1;
    else if (row.status === 'APPLIED') applied += 1;
    else if (row.status === 'FAILED_RETRYABLE') failedRetryable += 1;
    else if (row.status === 'FAILED_FINAL') failedFinal += 1;

    if (isDue(row, nowMs)) dueNow += 1;
  }

  return {
    total: rows.length,
    pending,
    syncing,
    applied,
    failed_retryable: failedRetryable,
    failed_final: failedFinal,
    due_now: dueNow,
  };
}

export function enqueueInventoryOfflineCommand(input: {
  kind: InventoryOfflineCommandKind;
  company_id: number;
  branch_id: number;
  dedupe_key: string;
  payload: InventoryOfflineCommandPayload;
}): { command: InventoryOfflineCommand; duplicate: boolean } {
  const dedupeKey = String(input.dedupe_key || '').trim();
  if (!dedupeKey) throw new Error('dedupe_key es requerido para cola offline de Inventarios');

  const payload = {
    warehouse_id: Number(input.payload.warehouse_id),
    item_id: Number(input.payload.item_id),
    qty: String(input.payload.qty || '').trim(),
    idempotency_key: String(input.payload.idempotency_key || '').trim(),
    ...(input.payload.note !== undefined ? { note: String(input.payload.note) } : {}),
    ...(input.payload.unit_cost !== undefined ? { unit_cost: String(input.payload.unit_cost) } : {}),
  };
  if (!payload.idempotency_key) {
    throw new Error('idempotency_key es requerido para cola offline de Inventarios');
  }

  const now = nowIso();
  let result: InventoryOfflineCommand | null = null;
  let duplicate = false;

  updateQueue((state) => {
    const existing = state.commands.find(
      (row) =>
        row.dedupe_key === dedupeKey &&
        row.company_id === Number(input.company_id) &&
        row.branch_id === Number(input.branch_id) &&
        row.status !== 'APPLIED',
    );
    if (existing) {
      duplicate = true;
      result = existing;
      return state;
    }

    const created: InventoryOfflineCommand = {
      id: randomId(),
      version: INVENTORY_OFFLINE_QUEUE_VERSION,
      command_id: randomUuid(),
      kind: input.kind,
      status: 'PENDING',
      company_id: Number(input.company_id),
      branch_id: Number(input.branch_id),
      dedupe_key: dedupeKey,
      payload,
      attempts: 0,
      created_at: now,
      updated_at: now,
      processed_at: null,
      next_retry_at: null,
      last_attempt_at: null,
      last_error: '',
      last_reason: '',
    };
    result = created;
    return { ...state, commands: [...state.commands, created] };
  });

  if (!result) throw new Error('No fue posible registrar comando offline de Inventarios');
  return { command: cloneCommand(result), duplicate };
}

export function retryFinalInventoryOfflineCommand(commandId: string): InventoryOfflineCommand | null {
  const id = String(commandId || '').trim();
  if (!id) return null;

  let output: InventoryOfflineCommand | null = null;
  updateQueue((state) => {
    const commands = state.commands.map((row): InventoryOfflineCommand => {
      if (row.id !== id || row.status !== 'FAILED_FINAL') return row;
      if (!canTransitionStatus(row.status, 'PENDING')) return row;
      const next: InventoryOfflineCommand = {
        ...row,
        status: 'PENDING',
        attempts: 0,
        next_retry_at: null,
        last_error: '',
        last_reason: '',
        updated_at: nowIso(),
      };
      output = next;
      return next;
    });
    return { ...state, commands };
  });

  return output ? cloneCommand(output) : null;
}

export function toInventorySyncV2Command(command: InventoryOfflineCommand): {
  command_id: string;
  type: 'INVENTORY.MOVEMENT.RECEIVE' | 'INVENTORY.MOVEMENT.ISSUE';
  scope: { company_id: number; branch_id: number };
  occurred_at: string;
  payload: Record<string, unknown>;
} {
  const commandType = command.kind === 'RECEIVE' ? 'INVENTORY.MOVEMENT.RECEIVE' : 'INVENTORY.MOVEMENT.ISSUE';
  const payload: Record<string, unknown> = {
    warehouse_id: command.payload.warehouse_id,
    item_id: command.payload.item_id,
    qty: command.payload.qty,
    idempotency_key: command.payload.idempotency_key,
  };
  if (command.payload.note) payload.note = command.payload.note;
  if (command.kind === 'RECEIVE' && command.payload.unit_cost) {
    payload.unit_cost = command.payload.unit_cost;
  }

  return {
    command_id: command.command_id,
    type: commandType,
    scope: {
      company_id: command.company_id,
      branch_id: command.branch_id,
    },
    occurred_at: command.created_at,
    payload,
  };
}

export function canInventoryOfflineTransition(
  from: InventoryOfflineCommandStatus,
  to: InventoryOfflineCommandStatus,
): boolean {
  return canTransitionStatus(from, to);
}

export async function drainInventoryOfflineQueue(options: InventoryOfflineDrainOptions): Promise<InventoryOfflineDrainResult> {
  const nowMs = Number(options.nowMs || Date.now());
  const maxCommands = Math.max(1, Number(options.maxCommands || 20));
  const snapshot = readQueueState();
  const due = snapshot.commands
    .filter((row) => isDue(row, nowMs))
    .sort((a, b) => parseIsoMs(a.created_at) - parseIsoMs(b.created_at))
    .slice(0, maxCommands);

  let attempted = 0;
  let succeeded = 0;
  let failedRetryable = 0;
  let failedFinal = 0;

  for (const row of due) {
    attempted += 1;
    updateQueue((state) => {
      const commands = state.commands.map((cmd): InventoryOfflineCommand =>
        cmd.id === row.id
          ? canTransitionStatus(cmd.status, 'SYNCING')
            ? {
                ...cmd,
                status: 'SYNCING',
                updated_at: nowIso(),
              }
            : cmd
          : cmd,
      );
      return { ...state, commands };
    });

    try {
      const out = await options.executor(cloneCommand(row));
      if (out.applied) {
        succeeded += 1;
        updateQueue((state) => {
          const commands = state.commands.map((cmd): InventoryOfflineCommand =>
            cmd.id === row.id
              ? canTransitionStatus(cmd.status, 'APPLIED')
                ? {
                    ...cmd,
                    status: 'APPLIED',
                    updated_at: nowIso(),
                    processed_at: nowIso(),
                    next_retry_at: null,
                    last_error: '',
                    last_reason: '',
                  }
                : cmd
              : cmd,
          );
          return { ...state, commands };
        });
      } else {
        const nextAttempts = row.attempts + 1;
        const canRetry = Boolean(out.retryable ?? true) && nextAttempts < INVENTORY_OFFLINE_MAX_ATTEMPTS;
        if (canRetry) failedRetryable += 1;
        else failedFinal += 1;
        updateQueue((state) => {
          const commands = state.commands.map((cmd): InventoryOfflineCommand =>
            cmd.id === row.id
              ? canTransitionStatus(cmd.status, canRetry ? 'FAILED_RETRYABLE' : 'FAILED_FINAL')
                ? {
                    ...cmd,
                    status: canRetry ? 'FAILED_RETRYABLE' : 'FAILED_FINAL',
                    attempts: nextAttempts,
                    updated_at: nowIso(),
                    last_attempt_at: nowIso(),
                    last_error: String(out.reason || 'SYNC_REJECTED').slice(0, 255),
                    last_reason: String(out.reason || 'SYNC_REJECTED').slice(0, 64),
                    next_retry_at: canRetry ? nowIso(Date.now() + nextBackoffMs(nextAttempts)) : null,
                  }
                : cmd
              : cmd,
          );
          return { ...state, commands };
        });
      }
    } catch (error) {
      const nextAttempts = row.attempts + 1;
      const hintedRetryable =
        typeof error === 'object' && error !== null && 'retryable' in error
          ? Boolean((error as { retryable?: boolean }).retryable)
          : true;
      const canRetry = hintedRetryable && nextAttempts < INVENTORY_OFFLINE_MAX_ATTEMPTS;
      if (canRetry) failedRetryable += 1;
      else failedFinal += 1;

      const message = error instanceof Error ? error.message : String(error);
      updateQueue((state) => {
        const commands = state.commands.map((cmd): InventoryOfflineCommand =>
          cmd.id === row.id
            ? canTransitionStatus(cmd.status, canRetry ? 'FAILED_RETRYABLE' : 'FAILED_FINAL')
              ? {
                  ...cmd,
                  status: canRetry ? 'FAILED_RETRYABLE' : 'FAILED_FINAL',
                  attempts: nextAttempts,
                  updated_at: nowIso(),
                  last_attempt_at: nowIso(),
                  last_error: message.slice(0, 255),
                  last_reason: 'EXECUTOR_ERROR',
                  next_retry_at: canRetry ? nowIso(Date.now() + nextBackoffMs(nextAttempts)) : null,
                }
              : cmd
            : cmd,
        );
        return { ...state, commands };
      });
    }
  }

  return {
    attempted,
    succeeded,
    failed_retryable: failedRetryable,
    failed_final: failedFinal,
  };
}
