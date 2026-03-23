import type { AxiosError, AxiosRequestConfig } from 'axios';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { applyCsrfHeader, handleApiResponseError } from './axios';

function makeAxiosError(status: number, config: AxiosRequestConfig = {}): AxiosError {
  return {
    config,
    response: {
      status,
      statusText: '',
      headers: {},
      config,
      data: {},
    },
    isAxiosError: true,
    name: 'AxiosError',
    message: `status ${status}`,
    toJSON: () => ({}),
  } as AxiosError;
}

describe('boot/axios helpers', () => {
  beforeEach(() => {
    document.cookie = '';
  });

  it('agrega X-CSRF-Token en metodo mutable', () => {
    document.cookie = 'nt_csrf=token123';

    const config: AxiosRequestConfig = { method: 'post', headers: {} };
    const out = applyCsrfHeader(config);

    expect(out.headers).toBeDefined();
    expect((out.headers as Record<string, string>)['X-CSRF-Token']).toBe('token123');
  });

  it('no agrega CSRF en GET', () => {
    document.cookie = 'nt_csrf=token123';

    const config: AxiosRequestConfig = { method: 'get', headers: {} };
    const out = applyCsrfHeader(config);

    expect((out.headers as Record<string, string>)['X-CSRF-Token']).toBeUndefined();
  });

  it('en 401 hace refresh y reintenta una vez', async () => {
    const error = makeAxiosError(401, { url: '/inventory/items/', method: 'get' });
    const refresh = vi.fn().mockResolvedValue(undefined);
    const hardClearLocal = vi.fn();
    const replace = vi.fn();
    const retryRequest = vi.fn().mockResolvedValue({ ok: true });

    const result = await handleApiResponseError(error, {
      auth: { refresh, hardClearLocal },
      router: { replace },
      retryRequest,
    });

    expect(result).toEqual({ ok: true });
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(retryRequest).toHaveBeenCalledTimes(1);
    expect((error.config as AxiosRequestConfig)._retry).toBe(true);
    expect(hardClearLocal).not.toHaveBeenCalled();
    expect(replace).not.toHaveBeenCalled();
  });

  it('si refresh falla en 401 limpia sesion y redirige a login', async () => {
    const error = makeAxiosError(401, { url: '/inventory/items/', method: 'get' });
    const refresh = vi.fn().mockRejectedValue(new Error('refresh failed'));
    const hardClearLocal = vi.fn();
    const replace = vi.fn().mockResolvedValue(undefined);
    const retryRequest = vi.fn();

    await expect(
      handleApiResponseError(error, {
        auth: { refresh, hardClearLocal },
        router: { replace },
        retryRequest,
      }),
    ).rejects.toThrow('refresh failed');

    expect(refresh).toHaveBeenCalledTimes(1);
    expect(retryRequest).not.toHaveBeenCalled();
    expect(hardClearLocal).toHaveBeenCalledTimes(1);
    expect(replace).toHaveBeenCalledWith('/login');
  });

  it('en 403 redirige a forbidden y rechaza error', async () => {
    const error = makeAxiosError(403, { url: '/inventory/items/', method: 'get' });
    const refresh = vi.fn();
    const hardClearLocal = vi.fn();
    const replace = vi.fn().mockResolvedValue(undefined);
    const retryRequest = vi.fn();

    await expect(
      handleApiResponseError(error, {
        auth: { refresh, hardClearLocal },
        router: { replace },
        retryRequest,
      }),
    ).rejects.toMatchObject({ message: 'status 403' });

    expect(replace).toHaveBeenCalledWith('/403');
    expect(refresh).not.toHaveBeenCalled();
    expect(retryRequest).not.toHaveBeenCalled();
  });
});
