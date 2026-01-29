import { isAxiosError } from 'axios';
import { api } from 'src/boot/axios';
import { enqueueOutboxItem, newUuid } from 'src/core/offline/outbox';
import { readContext } from 'src/core/storage/context';

export type InventoryHealth = {
  ok: boolean;
  module: string;
};

export type InventoryQueued = {
  queued: true;
  outbox_id: string;
  idempotency_key: string;
};

function isNetworkError(e: unknown): boolean {
  return isAxiosError(e) && !e.response;
}

async function postOrQueue<TOnline, TBody extends Record<string, unknown>>(
  kind: string,
  url: string,
  body: TBody,
): Promise<TOnline | InventoryQueued> {
  // Invariante: inventario operativo requiere sucursal.
  // Mejor fallar temprano que encolar basura que el backend rechazará.
  const ctx = readContext();
  if (!ctx.branchId) {
    throw new Error('ContextMissing: X-Branch-Id is required for inventory operations');
  }

  const idempotency_key = (body.idempotency_key as string | undefined) || newUuid();
  const finalBody = { ...body, idempotency_key } as TBody & { idempotency_key: string };

  if (typeof navigator !== 'undefined' && navigator.onLine === false) {
    const item = await enqueueOutboxItem({
      kind,
      request: { method: 'POST', url, body: finalBody },
    });
    return { queued: true, outbox_id: item.id, idempotency_key };
  }

  try {
    const { data } = await api.post<TOnline>(url, finalBody);
    return data;
  } catch (e) {
    if (isNetworkError(e)) {
      const item = await enqueueOutboxItem({
        kind,
        request: { method: 'POST', url, body: finalBody },
      });
      return { queued: true, outbox_id: item.id, idempotency_key };
    }
    throw e;
  }
}

export async function getInventoryHealth() {
  const { data } = await api.get<InventoryHealth>('/inventory/health/');
  return data;
}

export type MovementReceiveIn = {
  warehouse_id: number;
  item_id: number;
  qty: string | number;
  unit_cost: string | number;
  note?: string;
  idempotency_key?: string;
};

export type MovementIssueIn = {
  warehouse_id: number;
  item_id: number;
  qty: string | number;
  allow_negative?: boolean;
  note?: string;
  idempotency_key?: string;
};

export type MovementAdjustIn = {
  warehouse_id: number;
  item_id: number;
  new_qty_on_hand: string | number;
  note?: string;
  idempotency_key?: string;
};

export type TransferIn = {
  from_warehouse_id: number;
  to_warehouse_id: number;
  item_id: number;
  qty: string | number;
  note?: string;
  idempotency_key?: string;
};

export type MovementOut = {
  movement_id: number;
  qty_on_hand: string;
  avg_cost: string;
};

export type TransferOut = {
  transfer_out_movement_id: number;
  transfer_in_movement_id: number;
};

export async function postReceive(body: MovementReceiveIn) {
  return await postOrQueue<MovementOut, MovementReceiveIn>(
    'inventory.movement.receive',
    '/inventory/movements/receive/',
    body,
  );
}

export async function postIssue(body: MovementIssueIn) {
  return await postOrQueue<MovementOut, MovementIssueIn>(
    'inventory.movement.issue',
    '/inventory/movements/issue/',
    body,
  );
}

export async function postAdjust(body: MovementAdjustIn) {
  return await postOrQueue<MovementOut, MovementAdjustIn>(
    'inventory.movement.adjust',
    '/inventory/movements/adjust/',
    body,
  );
}

export async function postTransfer(body: TransferIn) {
  return await postOrQueue<TransferOut, TransferIn>(
    'inventory.transfer.create',
    '/inventory/transfers/',
    body,
  );
}
