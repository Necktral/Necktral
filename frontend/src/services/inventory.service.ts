import { api } from 'src/boot/axios';

export type PaginatedResponse<T> = {
  count: number;
  limit: number;
  offset: number;
  has_next?: boolean;
  has_prev?: boolean;
  results: T[];
};

export type UomCode = 'UNIT' | 'LITER' | 'KILOGRAM' | 'BOX' | 'GALLON' | 'METER';
export type ItemType = 'INVENTARIABLE' | 'NO_INVENTARIABLE' | 'SERVICIO';
export type ItemStatus = 'ACTIVO' | 'INACTIVO' | 'BLOQUEADO';
export type BarcodeType = 'EAN13' | 'UPCA' | 'CODE128' | 'INTERNO';
export type TaxTreatment = 'GRAVADO' | 'EXENTO' | 'EXONERADO';

export type InventoryUomOption = {
  code: UomCode;
  label: string;
};

export type InventoryBrandRow = {
  id: number;
  name: string;
  is_active: boolean;
};

export type InventoryCategoryRow = {
  id: number;
  name: string;
  parent_id: number | null;
  is_active: boolean;
};

export type InventoryTaxProfileRow = {
  id: number;
  code: string;
  name: string;
  tax_treatment: TaxTreatment;
  is_active: boolean;
};

export type InventoryUomConversion = {
  to_uom: UomCode;
  factor: string;
};

export type InventoryItemRow = {
  id: number;
  sku: string;
  name: string;
  uom: UomCode;
  item_type: ItemType;
  status: ItemStatus;
  short_name: string;
  invoice_name: string;
  description: string;
  brand_id: number | null;
  brand_name: string;
  category_id: number | null;
  category_name: string;
  subcategory_id: number | null;
  subcategory_name: string;
  barcode: string;
  barcode_type: BarcodeType | '';
  alternate_code: string;
  search_tags: string[];
  purchase_enabled: boolean;
  sales_enabled: boolean;
  controls_stock: boolean;
  transfer_enabled: boolean;
  allow_returns: boolean;
  uom_base: UomCode;
  uom_purchase: UomCode;
  uom_sale: UomCode;
  uom_conversions: InventoryUomConversion[];
  allow_fraction: boolean;
  min_qty: string;
  rounding_increment: string;
  enabled_branch_ids: number[];
  default_branch_id: number | null;
  default_warehouse_id: number | null;
  min_stock: string;
  max_stock: string;
  reorder_point: string;
  reorder_qty: string;
  allow_negative_stock: boolean;
  reserve_enabled: boolean;
  internal_location: string;
  costing_method: 'MOVING_WEIGHTED_AVG';
  initial_cost: string;
  standard_cost: string;
  currency: string;
  last_known_cost: string;
  preferred_supplier_id: number | null;
  supplier_item_code: string;
  lead_time_days: number | null;
  purchase_moq: string;
  purchase_multiple: string;
  suggested_price: string;
  min_sale_price: string;
  allow_discount: boolean;
  visible_pos: boolean;
  visible_quote: boolean;
  visible_invoice: boolean;
  tax_profile_id: number | null;
  tax_profile_name: string;
  tax_treatment: TaxTreatment;
  invoice_description: string;
  use_lot: boolean;
  use_serial: boolean;
  use_expiry: boolean;
  shelf_life_days: number | null;
  quality_control_required: boolean;
  allow_return_to_stock: boolean;
  is_active: boolean;
  version: number;
  created_at: string;
  updated_at: string;
};

export type InventoryItemUpsertPayload = {
  sku: string;
  name: string;
  uom?: UomCode;
  item_type?: ItemType;
  status?: ItemStatus;
  short_name?: string;
  invoice_name?: string;
  description?: string;
  brand_id?: number | null;
  category_id?: number | null;
  subcategory_id?: number | null;
  barcode?: string;
  barcode_type?: BarcodeType | '';
  alternate_code?: string;
  search_tags?: string[];
  purchase_enabled?: boolean;
  sales_enabled?: boolean;
  controls_stock?: boolean;
  transfer_enabled?: boolean;
  allow_returns?: boolean;
  uom_base?: UomCode;
  uom_purchase?: UomCode;
  uom_sale?: UomCode;
  uom_conversions?: InventoryUomConversion[];
  allow_fraction?: boolean;
  min_qty?: string;
  rounding_increment?: string;
  enabled_branch_ids?: number[];
  default_branch_id?: number | null;
  default_warehouse_id?: number | null;
  min_stock?: string;
  max_stock?: string;
  reorder_point?: string;
  reorder_qty?: string;
  allow_negative_stock?: boolean;
  reserve_enabled?: boolean;
  internal_location?: string;
  costing_method?: 'MOVING_WEIGHTED_AVG';
  initial_cost?: string;
  standard_cost?: string;
  currency?: string;
  last_known_cost?: string;
  preferred_supplier_id?: number | null;
  supplier_item_code?: string;
  lead_time_days?: number | null;
  purchase_moq?: string;
  purchase_multiple?: string;
  suggested_price?: string;
  min_sale_price?: string;
  allow_discount?: boolean;
  visible_pos?: boolean;
  visible_quote?: boolean;
  visible_invoice?: boolean;
  tax_profile_id?: number | null;
  tax_treatment?: TaxTreatment;
  invoice_description?: string;
  use_lot?: boolean;
  use_serial?: boolean;
  use_expiry?: boolean;
  shelf_life_days?: number | null;
  quality_control_required?: boolean;
  allow_return_to_stock?: boolean;
  is_active?: boolean;
};

export type WarehouseRow = {
  id: number;
  name: string;
  code: string;
  is_active: boolean;
  created_at: string;
  branch_id: number;
};

export type InventoryBalanceRow = {
  id: number;
  warehouse_id: number;
  warehouse_name: string;
  warehouse_code: string;
  item_id: number;
  item_sku: string;
  item_name: string;
  qty_on_hand: string;
  avg_cost: string;
  updated_at: string | null;
};

export type InventoryMovementRow = {
  id: number;
  created_at: string;
  movement_type: 'RECEIVE' | 'ISSUE' | 'ADJUST' | 'TRANSFER_OUT' | 'TRANSFER_IN';
  warehouse_id: number;
  item_id: number;
  qty_delta: string;
  unit_cost: string;
  total_cost: string;
  source_module: string;
  source_type: string;
  source_id: string;
  note: string;
  idempotency_key: string;
  accounting_status: string;
  accounting_error: string;
  journal_draft_id: number | null;
  journal_entry_id: number | null;
};

export type InventoryMovementPostResult = {
  movement_id: number;
  qty_on_hand: string;
  avg_cost: string;
  accounting_status: string;
  accounting_error: string;
  journal_draft_id: number | null;
  journal_entry_id: number | null;
};

export type InventoryTransferPostResult = {
  out_movement_id: number;
  in_movement_id: number;
  from_qty_on_hand: string;
  to_qty_on_hand: string;
  avg_cost: string;
  accounting_status: string;
  accounting_error: string;
  journal_draft_id: number | null;
  journal_entry_id: number | null;
};

export type InventoryBatchCommand = {
  command_id: string;
  type: string;
  payload: Record<string, unknown>;
};

export type InventoryBatchCommandResult = {
  command_id: string;
  status: 'APPLIED' | 'DUPLICATE' | 'REJECTED';
  refs?: Record<string, unknown>;
  error_code?: string;
  error_detail?: string;
};

export type InventoryBatchResponse = {
  results: InventoryBatchCommandResult[];
  summary: {
    total: number;
    applied: number;
    duplicate: number;
    rejected: number;
  };
};

export type InventoryHealth = {
  ok: boolean;
  module: string;
};

function buildListQuery(params: Record<string, string | number | boolean | null | undefined>): string {
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v === null || v === undefined || v === '') continue;
    qs.set(k, String(v));
  }
  const encoded = qs.toString();
  return encoded ? `?${encoded}` : '';
}

export async function getInventoryHealth() {
  const { data } = await api.get<InventoryHealth>('/inventory/health/');
  return data;
}

export async function listInventoryUoms() {
  const { data } = await api.get<{ results: InventoryUomOption[] }>('/inventory/lookups/uoms/');
  return data.results;
}

export async function listInventoryBrands(params: {
  q?: string;
  is_active?: boolean;
  limit?: number;
  offset?: number;
} = {}) {
  const qs = buildListQuery(params);
  const { data } = await api.get<PaginatedResponse<InventoryBrandRow>>(`/inventory/lookups/brands/${qs}`);
  return data;
}

export async function createInventoryBrand(payload: { name: string }) {
  const { data } = await api.post<InventoryBrandRow>('/inventory/lookups/brands/', payload);
  return data;
}

export async function listInventoryCategories(params: {
  q?: string;
  is_active?: boolean;
  parent_id?: number;
  limit?: number;
  offset?: number;
} = {}) {
  const qs = buildListQuery(params);
  const { data } = await api.get<PaginatedResponse<InventoryCategoryRow>>(`/inventory/lookups/categories/${qs}`);
  return data;
}

export async function createInventoryCategory(payload: { name: string; parent_id?: number | null }) {
  const { data } = await api.post<InventoryCategoryRow>('/inventory/lookups/categories/', payload);
  return data;
}

export async function listInventoryTaxProfiles(params: {
  q?: string;
  is_active?: boolean;
  limit?: number;
  offset?: number;
} = {}) {
  const qs = buildListQuery(params);
  const { data } = await api.get<PaginatedResponse<InventoryTaxProfileRow>>(`/inventory/lookups/tax-profiles/${qs}`);
  return data;
}

export async function createInventoryTaxProfile(payload: {
  code: string;
  name: string;
  tax_treatment?: TaxTreatment;
}) {
  const { data } = await api.post<InventoryTaxProfileRow>('/inventory/lookups/tax-profiles/', payload);
  return data;
}

export async function listInventoryItems(params: {
  q?: string;
  sku_exact?: string;
  barcode_exact?: string;
  is_active?: boolean;
  limit?: number;
  offset?: number;
} = {}) {
  const qs = buildListQuery(params);
  const { data } = await api.get<PaginatedResponse<InventoryItemRow>>(`/inventory/items/${qs}`);
  return data;
}

export async function getInventoryItem(itemId: number) {
  const { data } = await api.get<InventoryItemRow>(`/inventory/items/${itemId}/`);
  return data;
}

export async function createInventoryItem(payload: InventoryItemUpsertPayload) {
  const { data } = await api.post<InventoryItemRow>('/inventory/items/', payload);
  return data;
}

export async function patchInventoryItem(itemId: number, payload: Partial<InventoryItemUpsertPayload>) {
  const { data } = await api.patch<InventoryItemRow>(`/inventory/items/${itemId}/`, payload);
  return data;
}

export async function listInventoryWarehouses(params: {
  q?: string;
  is_active?: boolean;
  branch_id?: number;
  limit?: number;
  offset?: number;
} = {}) {
  const qs = buildListQuery(params);
  const { data } = await api.get<PaginatedResponse<WarehouseRow>>(`/inventory/warehouses/${qs}`);
  return data;
}

export async function createInventoryWarehouse(payload: { name: string; code?: string }) {
  const { data } = await api.post<{ id: number }>('/inventory/warehouses/', payload);
  return data;
}

export async function patchInventoryWarehouse(warehouseId: number, payload: Partial<WarehouseRow>) {
  const { data } = await api.patch<WarehouseRow>(`/inventory/warehouses/${warehouseId}/`, payload);
  return data;
}

export async function postInventoryReceive(payload: {
  warehouse_id: number;
  item_id: number;
  qty: string;
  unit_cost: string;
  idempotency_key?: string;
  note?: string;
}) {
  const { data } = await api.post<InventoryMovementPostResult>('/inventory/movements/receive/', payload);
  return data;
}

export async function postInventoryIssue(payload: {
  warehouse_id: number;
  item_id: number;
  qty: string;
  allow_negative?: boolean;
  idempotency_key?: string;
  note?: string;
}) {
  const { data } = await api.post<InventoryMovementPostResult>('/inventory/movements/issue/', payload);
  return data;
}

export async function postInventoryAdjust(payload: {
  warehouse_id: number;
  item_id: number;
  new_qty_on_hand: string;
  idempotency_key?: string;
  note?: string;
}) {
  const { data } = await api.post<InventoryMovementPostResult>('/inventory/movements/adjust/', payload);
  return data;
}

export async function postInventoryTransfer(payload: {
  from_warehouse_id: number;
  to_warehouse_id: number;
  item_id: number;
  qty: string;
  idempotency_key?: string;
  note?: string;
}) {
  const { data } = await api.post<InventoryTransferPostResult>('/inventory/transfers/', payload);
  return data;
}

export async function listInventoryBalances(params: {
  q?: string;
  warehouse_id?: number;
  item_id?: number;
  limit?: number;
  offset?: number;
} = {}) {
  const qs = buildListQuery(params);
  const { data } = await api.get<PaginatedResponse<InventoryBalanceRow>>(`/inventory/balances/${qs}`);
  return data;
}

export async function listInventoryLedger(params: {
  warehouse_id?: number;
  item_id?: number;
  movement_type?: string;
  source_module?: string;
  source_type?: string;
  source_id?: string;
  accounting_status?: string;
  date_from?: string;
  date_to?: string;
  limit?: number;
  offset?: number;
} = {}) {
  const qs = buildListQuery(params);
  const { data } = await api.get<{
    count: number;
    limit: number;
    offset: number;
    results: InventoryMovementRow[];
  }>(`/inventory/ledger/${qs}`);
  return data;
}

export async function postInventoryCommandBatch(commands: InventoryBatchCommand[]) {
  const { data } = await api.post<InventoryBatchResponse>('/inventory/commands/batch/', { commands });
  return data;
}
