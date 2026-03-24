import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { useContextStore } from 'src/stores/context.store';

import { useRetailCheckoutStore } from './useRetailCheckoutStore';
import { useRetailOfflineQueueStore } from './useRetailOfflineQueueStore';
import { useRetailTelemetryStore } from './useRetailTelemetryStore';
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
    useRetailTelemetryStore().$patch({ attempts: [] });
    useRetailOfflineQueueStore().$patch({
      companyId: null,
      branchId: null,
      queue: [],
      syncing: false,
      lastSyncError: '',
    });
    useContextStore().$patch({
      activeCompanyId: null,
      activeBranchId: null,
    });
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
    const outcome = await store.commit(10, 3, '10.00');

    expect(outcome).toBe('COMPLETED');
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

    const queue = useRetailOfflineQueueStore();
    const enqueueSpy = vi.spyOn(queue, 'enqueueMutation');
    const store = useRetailCheckoutStore();
    const outcome = await store.commit(10, 3, '10.00');

    expect(outcome).toBe('FAILED');
    expect(enqueueSpy).not.toHaveBeenCalled();
    expect(store.error).toContain('cambió en otra terminal');
  });

  it('encola checkout cuando falla por conectividad/retryable', async () => {
    vi.mocked(commitRetailCheckout).mockRejectedValue(new Error('Network Error'));

    const ctx = useContextStore();
    ctx.$patch({ activeCompanyId: '10', activeBranchId: '20' });

    const queue = useRetailOfflineQueueStore();
    queue.$patch({ companyId: '10', branchId: '20' });
    const enqueueSpy = vi.spyOn(queue, 'enqueueMutation').mockResolvedValue({
      id: 'q1',
      company_id: '10',
      branch_id: '20',
      scope_key: '10:20',
      action: 'CHECKOUT_COMMIT',
      ticket_id: 10,
      sale_id: null,
      payload: {},
      idempotency_key: 'retail-checkout-test',
      status: 'PENDING',
      attempts: 0,
      next_retry_at: new Date().toISOString(),
      last_error: '',
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    });

    const store = useRetailCheckoutStore();
    const outcome = await store.commit(10, 3, '10.00');

    expect(outcome).toBe('QUEUED');
    expect(store.notice).toContain('encolado');
    expect(store.error).toBeNull();
    expect(enqueueSpy).toHaveBeenCalledTimes(1);
    expect(enqueueSpy.mock.calls[0]?.[0]?.action).toBe('CHECKOUT_COMMIT');
    expect(String(enqueueSpy.mock.calls[0]?.[0]?.idempotencyKey || '')).toMatch(/^retail-checkout-/);

    const telemetry = useRetailTelemetryStore();
    expect(telemetry.lastAttempt?.outcome).toBe('QUEUED');
    expect(telemetry.lastAttempt?.action).toBe('CHECKOUT_COMMIT');
  });

  it('no encola checkout en error de negocio 4xx no retryable', async () => {
    vi.mocked(commitRetailCheckout).mockRejectedValue(
      new RetailApiError({
        status: 400,
        code: 'RETAIL_VALIDATION',
        detail: 'Payload inválido.',
        retryable: false,
      }),
    );

    const queue = useRetailOfflineQueueStore();
    const enqueueSpy = vi.spyOn(queue, 'enqueueMutation');

    const store = useRetailCheckoutStore();
    const outcome = await store.commit(10, 3, '10.00');

    expect(outcome).toBe('FAILED');
    expect(enqueueSpy).not.toHaveBeenCalled();
    expect(store.error).toContain('Payload inválido');

    const telemetry = useRetailTelemetryStore();
    expect(telemetry.lastAttempt?.outcome).toBe('FAILED');
    expect(telemetry.lastAttempt?.action).toBe('CHECKOUT_COMMIT');
  });
});
