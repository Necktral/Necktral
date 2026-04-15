import { api } from 'src/boot/axios';

export type InventoryWarehouse = {
  id: number;
  name: string;
  code: string;
  is_active: boolean;
  created_at: string;
};

export type InventoryItem = {
  id: number;
  sku: string;
  name: string;
  uom: 'UNIT' | 'LITER';
  is_active: boolean;
  created_at: string;
};

export type InventoryBalance = {
  qty_on_hand: string;
  avg_cost: string;
};

export type InventoryMovement = {
  id: number;
  movement_type: 'RECEIVE' | 'ISSUE' | 'ADJUST' | 'TRANSFER_OUT' | 'TRANSFER_IN';
  qty_delta: string;
  unit_cost: string;
  total_cost: string;
  note: string;
  created_at: string;
};

export type InventoryMovementResult = {
  movement_id: number;
  qty_on_hand: string;
  avg_cost: string;
  accounting_status: string;
  accounting_error: string;
  journal_draft_id: number | null;
  journal_entry_id: number | null;
};

export type InventoryCommitPayload = {
  warehouse_id: number;
  item_id: number;
  qty: string;
  idempotency_key: string;
  note?: string;
  unit_cost?: string;
};

export async function listInventoryWarehouses() {
  const { data } = await api.get<InventoryWarehouse[]>('/inventory/warehouses/');
  return data;
}

export async function listInventoryItems(params?: { q?: string; limit?: number }) {
  const { data } = await api.get<InventoryItem[]>('/inventory/items/', { params });
  return data;
}

export async function getInventoryBalance(params: { warehouse_id: number; item_id: number }) {
  const { data } = await api.get<InventoryBalance>('/inventory/balances/', { params });
  return data;
}

export async function listInventoryMovements(params: {
  warehouse_id: number;
  item_id: number;
  limit?: number;
}) {
  const { data } = await api.get<InventoryMovement[]>('/inventory/movements/', { params });
  return data;
}

export async function receiveInventory(payload: InventoryCommitPayload) {
  const { data } = await api.post<InventoryMovementResult>('/inventory/movements/receive/', {
    warehouse_id: payload.warehouse_id,
    item_id: payload.item_id,
    qty: payload.qty,
    unit_cost: payload.unit_cost,
    idempotency_key: payload.idempotency_key,
    note: payload.note ?? '',
  });
  return data;
}

export async function issueInventory(payload: InventoryCommitPayload) {
  const { data } = await api.post<InventoryMovementResult>('/inventory/movements/issue/', {
    warehouse_id: payload.warehouse_id,
    item_id: payload.item_id,
    qty: payload.qty,
    idempotency_key: payload.idempotency_key,
    note: payload.note ?? '',
  });
  return data;
}
