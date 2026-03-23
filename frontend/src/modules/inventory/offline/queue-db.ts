export type OfflineQueueStatus = 'PENDING' | 'RETRYING' | 'CONFLICT' | 'DONE';

export type OfflineQueuedCommand = {
  id: string;
  command_id: string;
  company_id: string;
  branch_id: string | null;
  scope_key: string;
  type: string;
  payload: Record<string, unknown>;
  idempotency_key: string;
  status: OfflineQueueStatus;
  attempts: number;
  next_attempt_at: string;
  last_error_code: string;
  last_error_detail: string;
  created_at: string;
  updated_at: string;
};

const DB_NAME = 'necktral_inventory_offline_v1';
const STORE_NAME = 'command_queue';
const DB_VERSION = 1;

function nowIso(): string {
  return new Date().toISOString();
}

function toScopeKey(companyId: string, branchId: string | null): string {
  return companyId + ':' + (branchId ?? '');
}

function randomId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return String(Date.now()) + '-' + Math.random().toString(16).slice(2);
}

function openDb(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      if (!db.objectStoreNames.contains(STORE_NAME)) {
        const store = db.createObjectStore(STORE_NAME, { keyPath: 'id' });
        store.createIndex('scope_key', 'scope_key', { unique: false });
        store.createIndex('status', 'status', { unique: false });
        store.createIndex('updated_at', 'updated_at', { unique: false });
      }
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error('No se pudo abrir IndexedDB'));
  });
}

async function withStore<T>(mode: IDBTransactionMode, fn: (store: IDBObjectStore) => Promise<T>): Promise<T> {
  const db = await openDb();
  return new Promise<T>((resolve, reject) => {
    const tx = db.transaction(STORE_NAME, mode);
    const store = tx.objectStore(STORE_NAME);

    fn(store)
      .then((value) => {
        tx.oncomplete = () => resolve(value);
        tx.onerror = () => reject(tx.error ?? new Error('Transacción fallida'));
        tx.onabort = () => reject(tx.error ?? new Error('Transacción abortada'));
      })
      .catch((error: unknown) => {
        tx.abort();
        reject(error instanceof Error ? error : new Error(String(error)));
      });
  }).finally(() => {
    db.close();
  });
}

function requestToPromise<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error('Error de IndexedDB'));
  });
}

export async function enqueueOfflineCommand(input: {
  company_id: string;
  branch_id: string | null;
  command_id?: string;
  type: string;
  payload: Record<string, unknown>;
  idempotency_key: string;
}): Promise<OfflineQueuedCommand> {
  const created = nowIso();
  const scope_key = toScopeKey(input.company_id, input.branch_id);
  const command_id = input.command_id ?? randomId();

  return withStore('readwrite', async (store) => {
    const rows = (await requestToPromise(store.index('scope_key').getAll(scope_key))) as OfflineQueuedCommand[];
    const existing = rows.find(
      (row) => row.idempotency_key === input.idempotency_key && row.status !== 'DONE',
    );
    if (existing) {
      return existing;
    }

    const row: OfflineQueuedCommand = {
      id: randomId(),
      command_id,
      company_id: input.company_id,
      branch_id: input.branch_id,
      scope_key,
      type: input.type,
      payload: input.payload,
      idempotency_key: input.idempotency_key,
      status: 'PENDING',
      attempts: 0,
      next_attempt_at: created,
      last_error_code: '',
      last_error_detail: '',
      created_at: created,
      updated_at: created,
    };

    await requestToPromise(store.put(row));
    return row;
  });
}

export async function listOfflineCommandsByScope(
  company_id: string,
  branch_id: string | null,
): Promise<OfflineQueuedCommand[]> {
  const scope_key = toScopeKey(company_id, branch_id);
  return withStore('readonly', async (store) => {
    const rows = (await requestToPromise(store.index('scope_key').getAll(scope_key))) as OfflineQueuedCommand[];
    return rows.sort((a, b) => a.created_at.localeCompare(b.created_at));
  });
}

export async function updateOfflineCommand(
  id: string,
  patch: Partial<OfflineQueuedCommand>,
): Promise<OfflineQueuedCommand | null> {
  return withStore('readwrite', async (store) => {
    const row = (await requestToPromise(store.get(id))) as OfflineQueuedCommand | undefined;
    if (!row) return null;
    const updated: OfflineQueuedCommand = {
      ...row,
      ...patch,
      updated_at: nowIso(),
    };
    await requestToPromise(store.put(updated));
    return updated;
  });
}

export async function removeOfflineCommand(id: string): Promise<void> {
  await withStore('readwrite', async (store) => {
    await requestToPromise(store.delete(id));
  });
}

export async function clearDoneOfflineCommands(
  company_id: string,
  branch_id: string | null,
): Promise<number> {
  const rows = await listOfflineCommandsByScope(company_id, branch_id);
  const doneRows = rows.filter((row) => row.status === 'DONE');
  for (const row of doneRows) {
    await removeOfflineCommand(row.id);
  }
  return doneRows.length;
}

export function isCommandReadyToRetry(row: OfflineQueuedCommand, now = new Date()): boolean {
  if (row.status !== 'PENDING' && row.status !== 'RETRYING') return false;
  return new Date(row.next_attempt_at).getTime() <= now.getTime();
}
