export type RetailOfflineAction = 'CHECKOUT_COMMIT' | 'VOID' | 'RETURN';
export type RetailOfflineQueueStatus = 'PENDING' | 'RETRYING' | 'FAILED' | 'DONE';

export type RetailOfflineQueueEntry = {
  id: string;
  company_id: string;
  branch_id: string | null;
  scope_key: string;
  action: RetailOfflineAction;
  ticket_id: number | null;
  sale_id: number | null;
  payload: Record<string, unknown>;
  idempotency_key: string;
  status: RetailOfflineQueueStatus;
  attempts: number;
  next_retry_at: string;
  last_error: string;
  created_at: string;
  updated_at: string;
};

const DB_NAME = 'necktral_retail_offline_v1';
const STORE_NAME = 'retail_operation_queue';
const DB_VERSION = 1;

function nowIso(): string {
  return new Date().toISOString();
}

function randomId(): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return crypto.randomUUID();
  }
  return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
}

function scopeKey(companyId: string, branchId: string | null): string {
  return `${companyId}:${branchId ?? ''}`;
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
    req.onerror = () => reject(req.error ?? new Error('No se pudo abrir IndexedDB retail'));
  });
}

function requestToPromise<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error ?? new Error('Error de IndexedDB retail'));
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
        tx.onerror = () => reject(tx.error ?? new Error('Transacción retail fallida'));
        tx.onabort = () => reject(tx.error ?? new Error('Transacción retail abortada'));
      })
      .catch((error: unknown) => {
        tx.abort();
        reject(error instanceof Error ? error : new Error(String(error)));
      });
  }).finally(() => {
    db.close();
  });
}

export async function enqueueRetailOfflineOperation(input: {
  company_id: string;
  branch_id: string | null;
  action: RetailOfflineAction;
  ticket_id?: number | null;
  sale_id?: number | null;
  payload: Record<string, unknown>;
  idempotency_key: string;
}): Promise<RetailOfflineQueueEntry> {
  const createdAt = nowIso();
  const key = scopeKey(input.company_id, input.branch_id);
  return withStore('readwrite', async (store) => {
    const rows = (await requestToPromise(store.index('scope_key').getAll(key))) as RetailOfflineQueueEntry[];
    const existing = rows.find(
      (row) =>
        row.action === input.action &&
        row.idempotency_key === input.idempotency_key &&
        row.status !== 'DONE',
    );
    if (existing) return existing;

    const row: RetailOfflineQueueEntry = {
      id: randomId(),
      company_id: input.company_id,
      branch_id: input.branch_id,
      scope_key: key,
      action: input.action,
      ticket_id: input.ticket_id ?? null,
      sale_id: input.sale_id ?? null,
      payload: input.payload,
      idempotency_key: input.idempotency_key,
      status: 'PENDING',
      attempts: 0,
      next_retry_at: createdAt,
      last_error: '',
      created_at: createdAt,
      updated_at: createdAt,
    };
    await requestToPromise(store.put(row));
    return row;
  });
}

export async function listRetailOfflineOperationsByScope(
  company_id: string,
  branch_id: string | null,
): Promise<RetailOfflineQueueEntry[]> {
  const key = scopeKey(company_id, branch_id);
  return withStore('readonly', async (store) => {
    const rows = (await requestToPromise(store.index('scope_key').getAll(key))) as RetailOfflineQueueEntry[];
    return rows.sort((a, b) => a.created_at.localeCompare(b.created_at));
  });
}

export async function updateRetailOfflineOperation(
  id: string,
  patch: Partial<RetailOfflineQueueEntry>,
): Promise<RetailOfflineQueueEntry | null> {
  return withStore('readwrite', async (store) => {
    const row = (await requestToPromise(store.get(id))) as RetailOfflineQueueEntry | undefined;
    if (!row) return null;
    const updated: RetailOfflineQueueEntry = {
      ...row,
      ...patch,
      updated_at: nowIso(),
    };
    await requestToPromise(store.put(updated));
    return updated;
  });
}

export async function removeRetailOfflineOperation(id: string): Promise<void> {
  await withStore('readwrite', async (store) => {
    await requestToPromise(store.delete(id));
  });
}

export function isRetailOfflineEntryReady(entry: RetailOfflineQueueEntry, now = new Date()): boolean {
  if (entry.status !== 'PENDING' && entry.status !== 'RETRYING') return false;
  return new Date(entry.next_retry_at).getTime() <= now.getTime();
}

export function nextRetryAtIso(attempts: number): string {
  const seconds = Math.min(300, Math.max(2, 2 ** attempts));
  return new Date(Date.now() + seconds * 1000).toISOString();
}

