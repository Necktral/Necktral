import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';

import { useAccountingDashboardStore } from './accounting-dashboard.store';

const services = vi.hoisted(() => ({
  fetchExecutiveSummary: vi.fn(),
  fetchRevenueVsExpense: vi.fn(),
  fetchCashPosition: vi.fn(),
  fetchReconciliationHealth: vi.fn(),
  fetchBranchPerformance: vi.fn(),
  fetchMonthlyTrends: vi.fn(),
}));

vi.mock('../services/dashboard.service', () => services);

describe('accounting-dashboard.store', () => {
  beforeEach(() => {
    setActivePinia(createPinia());
    services.fetchExecutiveSummary.mockReset();
    services.fetchRevenueVsExpense.mockReset();
    services.fetchCashPosition.mockReset();
    services.fetchReconciliationHealth.mockReset();
    services.fetchBranchPerformance.mockReset();
    services.fetchMonthlyTrends.mockReset();
  });

  it('carga todos los datasets del tablero en una sola acción', async () => {
    services.fetchExecutiveSummary.mockResolvedValueOnce({ meta: {}, summary: {}, results: {}, pagination: {} });
    services.fetchRevenueVsExpense.mockResolvedValueOnce({ meta: {}, summary: {}, results: [], pagination: {} });
    services.fetchCashPosition.mockResolvedValueOnce({ meta: {}, summary: {}, results: {}, pagination: {} });
    services.fetchReconciliationHealth.mockResolvedValueOnce({ meta: {}, summary: {}, results: {}, pagination: {} });
    services.fetchBranchPerformance.mockResolvedValueOnce({ meta: {}, summary: {}, results: [], pagination: {} });
    services.fetchMonthlyTrends.mockResolvedValueOnce({ meta: {}, summary: {}, results: [], pagination: {} });

    const store = useAccountingDashboardStore();
    await store.load({ month: 3, year: 2026 });

    expect(store.loaded).toBe(true);
    expect(store.error).toBe(null);
    expect(services.fetchExecutiveSummary).toHaveBeenCalledWith({ month: 3, year: 2026 });
    expect(services.fetchMonthlyTrends).toHaveBeenCalledWith({ month: 3, year: 2026 });
  });
});

