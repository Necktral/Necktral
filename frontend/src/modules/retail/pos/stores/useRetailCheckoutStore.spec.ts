import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';

import { useRetailCheckoutStore } from './useRetailCheckoutStore';
import {
  RetailApiError,
  commitRetailCheckout,
  createRetailReturn,
  previewRetailCheckout,
  voidRetailTicket,
} from '../services/retail-pos.service';

vi.mock('../services/retail-pos.service', async () => {
  const actual = await vi.importActual('../services/retail-pos.service');
  return {
    ...actual,
    commitRetailCheckout: vi.fn(),
    createRetailReturn: vi.fn(),
    previewRetailCheckout: vi.fn(),
    voidRetailTicket: vi.fn(),
  };
});

describe('useRetailCheckoutStore', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    vi.mocked(commitRetailCheckout).mockReset();
    vi.mocked(createRetailReturn).mockReset();
    vi.mocked(previewRetailCheckout).mockReset();
    vi.mocked(voidRetailTicket).mockReset();
  });

  it('genera idempotency_key con prefijo robusto en commit', async () => {
    vi.mocked(commitRetailCheckout).mockResolvedValue({
      ticket_id: 1,
      sale_id: 1,
      status: 'COMPLETED',
      correlation_id: 'corr-1',
      billing: {
        doc_id: 1,
        number: 1,
        status: 'ISSUED',
        fiscal_status: 'NA',
        fiscal_reference: '',
        evidence_id: '',
        accounting_status: '',
      },
      payment: { payment_id: 'p1', intent_status: 'CAPTURED', cash_movement_id: 1, cash_received: '10.00', change_due: '0.00' },
      inventory: { movement_ids: [1], fulfillment_status: 'STOCK_APPLIED', reversal_movement_ids: [] },
      accounting: { aggregate_status: '', billing_status: '', inventory_statuses: [] },
    });

    const store = useRetailCheckoutStore();
    await store.commit(10, 3, '10.00');

    expect(commitRetailCheckout).toHaveBeenCalledTimes(1);
    const payload = vi.mocked(commitRetailCheckout).mock.calls[0]?.[1];
    expect(String(payload?.idempotency_key || '')).toMatch(/^retail-checkout-/);
  });

  it('mapea conflicto 409 de versión a mensaje operativo', async () => {
    vi.mocked(commitRetailCheckout).mockRejectedValue(
      new RetailApiError({
        status: 409,
        code: 'TICKET_VERSION_CONFLICT',
        detail: 'Versión de ticket desactualizada.',
        retryable: true,
      }),
    );

    const store = useRetailCheckoutStore();
    await store.commit(10, 3, '10.00');

    expect(store.error).toContain('cambió en otra terminal');
  });
});
