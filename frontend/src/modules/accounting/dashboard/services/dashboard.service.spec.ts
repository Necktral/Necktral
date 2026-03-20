import { beforeEach, describe, expect, it, vi } from 'vitest';

import { fetchExecutiveSummary } from './dashboard.service';

const api = vi.hoisted(() => ({
  get: vi.fn(),
}));

vi.mock('src/boot/axios', () => ({ api }));

describe('accounting dashboard service', () => {
  beforeEach(() => {
    api.get.mockReset();
  });

  it('consulta executive-summary en endpoint canónico backend', async () => {
    api.get.mockResolvedValueOnce({ data: { ok: true } });

    const data = await fetchExecutiveSummary({ year: 2026, month: 3, refresh: true });

    expect(api.get).toHaveBeenCalledWith('/backend/accounting/dashboard/executive-summary/', {
      params: { year: 2026, month: 3, refresh: true },
    });
    expect(data).toEqual({ ok: true });
  });
});

