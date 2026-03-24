import { api } from 'src/boot/axios';
import { isAxiosError } from 'axios';

export type RetailMutationErrorPayload = {
  code: string;
  detail: string;
  retryable: boolean;
  correlation_id: string;
  causation_id: string;
  idempotency_replayed: boolean;
};

export class RetailApiError extends Error {
  status: number;
  code: string;
  retryable: boolean;
  correlationId: string;
  causationId: string;
  idempotencyReplayed: boolean;

  constructor(payload: Partial<RetailMutationErrorPayload> & { status?: number }) {
    super(String(payload.detail || 'Error de operación retail.'));
    this.name = 'RetailApiError';
    this.status = Number(payload.status || 0);
    this.code = String(payload.code || 'RETAIL_API_ERROR');
    this.retryable = Boolean(payload.retryable);
    this.correlationId = String(payload.correlation_id || '');
    this.causationId = String(payload.causation_id || '');
    this.idempotencyReplayed = Boolean(payload.idempotency_replayed);
  }
}

function mapRetailError(error: unknown): Error {
  if (!isAxiosError(error)) return error instanceof Error ? error : new Error(String(error));
  const payload = error.response?.data as
    | (Partial<RetailMutationErrorPayload> & {
        error?: {
          code?: string;
          message?: string;
          retryable?: boolean;
          request_id?: string;
          details?: Partial<RetailMutationErrorPayload>;
        };
      })
    | undefined;
  if (payload && typeof payload === 'object') {
    const envelope = typeof payload.error === 'object' && payload.error ? payload.error : undefined;
    const details = envelope?.details && typeof envelope.details === 'object' ? envelope.details : undefined;
    const mapped: Partial<RetailMutationErrorPayload> & { status?: number } = {};
    if (typeof error.response?.status === 'number') mapped.status = error.response.status;
    const code = payload.code || details?.code || envelope?.code;
    if (typeof code === 'string' && code.trim()) mapped.code = code;
    const detail = payload.detail || details?.detail || envelope?.message;
    if (typeof detail === 'string' && detail.trim()) mapped.detail = detail;
    const retryable = payload.retryable ?? details?.retryable ?? envelope?.retryable;
    if (typeof retryable === 'boolean') mapped.retryable = retryable;
    const correlationId = payload.correlation_id || details?.correlation_id || envelope?.request_id;
    if (typeof correlationId === 'string' && correlationId.trim()) mapped.correlation_id = correlationId;
    const causationId = payload.causation_id || details?.causation_id;
    if (typeof causationId === 'string' && causationId.trim()) mapped.causation_id = causationId;
    const replayed = payload.idempotency_replayed ?? details?.idempotency_replayed;
    if (typeof replayed === 'boolean') mapped.idempotency_replayed = replayed;
    return new RetailApiError(mapped);
  }
  return error;
}

async function requestData<T>(requestPromise: Promise<{ data: T }>): Promise<T> {
  try {
    const { data } = await requestPromise;
    return data;
  } catch (error: unknown) {
    throw mapRetailError(error);
  }
}

export type RetailCashSession = {
  id: number;
  status: string;
  opening_amount: string;
  expected_amount: string;
  counted_amount: string;
  difference_amount: string;
  opened_at: string | null;
  closed_at: string | null;
};

export type RetailTerminal = {
  id: number;
  code: string;
  name: string;
  device_ref: string;
  receipt_printer_ref: string;
  is_active: boolean;
};

export type RetailCatalogItem = {
  id: number;
  sku: string;
  name: string;
  invoice_name: string;
  barcode: string;
  uom_sale: string;
  item_type: string;
  controls_stock: boolean;
  allow_fraction: boolean;
  rounding_increment: string;
  suggested_price: string;
  min_sale_price: string;
  allow_discount: boolean;
  tax_treatment: string;
  tax_rate: string;
  visible_pos: boolean;
};

export type RetailTicketLineRow = {
  id: number;
  source_line_id: number | null;
  position: number;
  inventory_item_id: number | null;
  sku_snapshot: string;
  name_snapshot: string;
  invoice_name_snapshot: string;
  uom_snapshot: string;
  tax_profile_snapshot: string;
  tax_rate_snapshot: string;
  qty: string;
  unit_price: string;
  discount_amount: string;
  line_subtotal: string;
  line_tax: string;
  line_total: string;
};

export type RetailTicketRow = {
  id: number;
  ticket_kind: string;
  status: string;
  payment_status: string;
  fulfillment_status: string;
  compensation_status: string;
  version: number;
  terminal_id: number | null;
  terminal_code: string;
  cash_session_id: number | null;
  customer_name: string;
  customer_ref: string;
  subtotal: string;
  tax_total: string;
  discount_total: string;
  total: string;
  billing_doc_id: number | null;
  payment_intent_id: string;
  flow_correlation_id: string;
  checkout_lock_token: string;
  compensation_attempts: number;
  last_error: string;
  closed_at: string | null;
  created_at: string;
  updated_at: string;
  lines: RetailTicketLineRow[];
};

export type RetailHoldRow = {
  id: number;
  ticket_id: number;
  status: string;
  reason: string;
  held_by_id: number | null;
  held_at: string | null;
  resumed_at: string | null;
  expires_at: string | null;
  ticket: RetailTicketRow;
};

export type RetailBootstrapResponse = {
  branch_config: {
    series: string;
    default_warehouse_id: number | null;
    price_includes_tax: boolean;
    hold_expiry_minutes: number;
    print_after_issue: boolean;
    require_customer_for_fiscal: boolean;
    allow_manual_reprice: boolean;
    active: boolean;
  };
  default_series: string;
  default_warehouse: { id: number; code: string; name: string } | null;
  terminals: Array<RetailTerminal | null>;
  active_cash_session: RetailCashSession | null;
  fiscal_mode: string;
  shortcuts_enabled: boolean;
};

export type RetailCheckoutPreviewResponse = {
  ok: boolean;
  blocking_errors: Array<{ code: string; detail: string }>;
  warnings: Array<{ code: string; detail: string }>;
  totals: {
    subtotal: string;
    tax_total: string;
    discount_total: string;
    total: string;
  };
  line_checks: Array<Record<string, unknown>>;
  cash_session: RetailCashSession | null;
  warehouse: { id: number; code: string; name: string } | null;
  config: RetailBootstrapResponse['branch_config'];
};

export type RetailCheckoutCommitResponse = {
  ticket_id: number;
  sale_id: number;
  status: string;
  correlation_id: string;
  idempotency_replayed?: boolean;
  billing: {
    doc_id: number | null;
    number: number | null;
    status: string;
    fiscal_status: string;
    fiscal_reference: string;
    evidence_id: string;
    accounting_status: string;
  };
  payment: {
    payment_id: string;
    intent_status: string;
    cash_movement_id: number | null;
    cash_received: string;
    change_due: string;
  };
  inventory: {
    movement_ids: number[];
    fulfillment_status: string;
    reversal_movement_ids: number[];
  };
  accounting: {
    aggregate_status: string;
    billing_status: string;
    inventory_statuses: string[];
  };
};

export type RetailReturnResponse = {
  id: number;
  sale_id: number;
  ticket_id: number;
  credit_note_doc_id: number | null;
  refund_payment_id: string;
  refund_cash_movement_id: number | null;
  inventory_movement_ids: number[];
  status: string;
  reason: string;
  refund_amount: string;
  flow_correlation_id: string;
  idempotency_key: string;
  created_at: string | null;
  completed_at: string | null;
  idempotency_replayed?: boolean;
  ticket: RetailTicketRow;
};

export async function fetchRetailBootstrap() {
  return requestData(api.get<RetailBootstrapResponse>('/backend/retail/bootstrap/'));
}

export async function searchRetailCatalog(query: string) {
  return requestData(
    api.get<{ count: number; limit: number; offset: number; results: RetailCatalogItem[] }>(
      '/backend/retail/catalog/search/',
      { params: { q: query, limit: 24 } },
    ),
  );
}

export async function createRetailTicket(payload: {
  terminal_id?: number;
  cash_session_id?: number;
  customer_name?: string;
  customer_ref?: string;
}) {
  return requestData(api.post<RetailTicketRow>('/backend/retail/tickets/', payload));
}

export async function getRetailTicket(ticketId: number) {
  return requestData(
    api.get<{
      ticket: RetailTicketRow;
      sale: Record<string, unknown> | null;
      active_hold: RetailHoldRow | null;
    }>(`/backend/retail/tickets/${ticketId}/`),
  );
}

export async function addRetailTicketLine(ticketId: number, payload: {
  expected_version: number;
  item_id: number;
  qty: string;
  unit_price?: string;
  discount_amount?: string;
}) {
  return requestData(api.post<RetailTicketRow>(`/backend/retail/tickets/${ticketId}/lines/`, payload));
}

export async function deleteRetailTicketLine(ticketId: number, lineId: number, expectedVersion: number) {
  return requestData(
    api.delete<RetailTicketRow>(`/backend/retail/tickets/${ticketId}/lines/${lineId}/`, {
      data: { expected_version: expectedVersion },
    }),
  );
}

export async function holdRetailTicket(ticketId: number, expectedVersion: number, reason: string) {
  return requestData(
    api.post<RetailHoldRow>(`/backend/retail/tickets/${ticketId}/hold/`, {
      expected_version: expectedVersion,
      reason,
    }),
  );
}

export async function resumeRetailHold(holdId: number) {
  return requestData(api.post<RetailHoldRow>(`/backend/retail/holds/${holdId}/resume/`, {}));
}

export async function fetchRetailRecentTickets() {
  return requestData(
    api.get<{ count: number; limit: number; offset: number; results: RetailTicketRow[] }>(
      '/backend/retail/tickets/recent/',
      { params: { limit: 12 } },
    ),
  );
}

export async function previewRetailCheckout(ticketId: number, expectedVersion: number) {
  return requestData(
    api.post<RetailCheckoutPreviewResponse>(`/backend/retail/tickets/${ticketId}/checkout/preview/`, {
      expected_version: expectedVersion,
    }),
  );
}

export async function commitRetailCheckout(ticketId: number, payload: {
  expected_version: number;
  idempotency_key: string;
  cash_received: string;
}) {
  return requestData(api.post<RetailCheckoutCommitResponse>(`/backend/retail/tickets/${ticketId}/checkout/commit/`, payload));
}

export async function voidRetailTicket(ticketId: number, payload: {
  expected_version: number;
  idempotency_key: string;
  reason?: string;
}) {
  return requestData(api.post(`/backend/retail/tickets/${ticketId}/void/`, payload));
}

export async function createRetailReturn(payload: {
  sale_id: number;
  reason?: string;
  idempotency_key: string;
  lines: Array<{ line_id: number; qty: string }>;
}) {
  return requestData(api.post<RetailReturnResponse>('/backend/retail/returns/', payload));
}
