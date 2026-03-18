import { beforeEach, describe, expect, it, vi } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';

import { useAuthStore } from 'src/stores/auth.store';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const api = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  request: vi.fn(),
}));

const authApi = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}));

vi.mock('src/boot/axios', () => ({
  api,
  authApi,
}));

const storageMocks = vi.hoisted(() => ({
  clearTokens: vi.fn(),
  readTokens: vi.fn(() => ({ access: null, refresh: null })),
  writeTokens: vi.fn(),
}));

vi.mock('src/core/storage/auth', () => storageMocks);

describe('auth.store', () => {
  beforeEach(() => {
    api.get.mockReset();
    api.post.mockReset();
    api.request.mockReset();
    authApi.get.mockReset();
    authApi.post.mockReset();
    storageMocks.clearTokens.mockReset();

    setActivePinia(createPinia());
  });

  it('entra en modo 2FA cuando el backend lo exige', async () => {
    authApi.post.mockResolvedValueOnce({
      data: { '2fa_required': true, challenge: 'challenge-1' },
    });

    const store = useAuthStore();

    await store.login('user', 'pass');

    expect(store.status).toBe('two_factor');
    expect(store.twoFactor.required).toBe(true);
    expect(store.twoFactor.challenge).toBe('challenge-1');
    expect(api.get).not.toHaveBeenCalled();
  });

  it('logout limpia estado y ejecuta logout best-effort', async () => {
    authApi.post.mockResolvedValueOnce({ data: {} });

    const store = useAuthStore();
    const acl = useAclStore();
    const ctx = useContextStore();

    store.status = 'authenticated';
    store.twoFactor.required = true;
    store.twoFactor.challenge = 'x';
    acl.loaded = true;
    ctx.activeCompanyId = '123';

    await store.logout();

    expect(store.status).toBe('anonymous');
    expect(store.twoFactor.required).toBe(false);
    expect(store.twoFactor.challenge).toBe(null);
    expect(storageMocks.clearTokens).toHaveBeenCalled();
    expect(acl.loaded).toBe(false);
    expect(ctx.activeCompanyId).toBe(null);
    expect(authApi.post).toHaveBeenCalledWith('/backend/auth/logout/', {});
  });

  it('reusa el refresh en vuelo', async () => {
    let resolveRefresh: (() => void) | undefined;
    const refreshPromise = new Promise<void>((resolve) => {
      resolveRefresh = () => resolve();
    });
    authApi.post.mockReturnValueOnce(refreshPromise);

    const store = useAuthStore();
    const a = store.refresh();
    const b = store.refresh();

    resolveRefresh?.();
    await a;
    await b;
    expect(authApi.post).toHaveBeenCalledTimes(1);
    expect(store.status).toBe('authenticated');
  });
});
