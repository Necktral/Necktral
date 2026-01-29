import { openDB, type DBSchema, type IDBPDatabase } from 'idb';

export type OutboxStatus = 'pending' | 'sending' | 'failed';

export type OutboxRequest = {
  method: 'POST' | 'PUT' | 'PATCH' | 'DELETE';
  url: string;
  body: unknown;
  headers?: Record<string, string>;
};

export type OutboxItem<Kind extends string = string> = {
  id: string;
  kind: Kind;
  status: OutboxStatus;
  createdAt: number;
  updatedAt: number;
  attemptCount: number;
  nextAttemptAt: number | null;
  lastError: string | null;
  request: OutboxRequest;

  // Robustez contractual: evitar enviar con scope/actor distintos a los que estaban activos al encolar.
  queuedCompanyId: string | null;
  queuedBranchId: string | null;
  queuedUserId: string | number | null;

  // Trazabilidad: el request_id que se envía como header al backend.
  requestId: string;
};

interface OfflineDb extends DBSchema {
  outbox: {
    key: string;
    value: OutboxItem;
    indexes: {
      by_status: OutboxStatus;
      by_nextAttemptAt: number;
    };
  };
}

let dbPromise: Promise<IDBPDatabase<OfflineDb>> | null = null;

export function getOfflineDb(): Promise<IDBPDatabase<OfflineDb>> {
  if (!dbPromise) {
    dbPromise = openDB<OfflineDb>('necktral_offline', 2, {
      upgrade(db, oldVersion, _newVersion, transaction) {
        if (oldVersion < 1) {
          const store = db.createObjectStore('outbox', { keyPath: 'id' });
          store.createIndex('by_status', 'status');
          store.createIndex('by_nextAttemptAt', 'nextAttemptAt');
        } else {
          // Asegura índices (por si vienen de un estado anterior)
          const store = transaction.objectStore('outbox');
          if (!store.indexNames.contains('by_status')) store.createIndex('by_status', 'status');
          if (!store.indexNames.contains('by_nextAttemptAt'))
            store.createIndex('by_nextAttemptAt', 'nextAttemptAt');
        }
      },
    });
  }
  return dbPromise;
}
