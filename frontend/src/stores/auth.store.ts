import { defineStore } from 'pinia';
import { isAxiosError } from 'axios';
import { api, authApi } from 'src/boot/axios';
import { clearTokens } from 'src/core/storage/auth';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

export const useAuthStore = defineStore('auth', {
  state: () => ({
    hydrated: false as boolean,
    status: 'anonymous' as 'anonymous' | 'authenticated' | 'refreshing' | 'two_factor',
    user: null as null | {
      id: number;
      username: string;
      must_change_password: boolean;
      is_setup_complete: boolean;
    },
    twoFactor: {
      required: false,
      challenge: null as string | null,
    },
    bootstrapState: {
      is_fresh: false,
      setup_required: false,
    },

    bootstrapChecked: false as boolean,

    // lock interno para refresh concurrente
    refreshInFlight: null as Promise<void> | null,
  }),

  getters: {
    isAuthenticated: (s) => s.status === 'authenticated',
    isTwoFactorRequired: (s) => s.status === 'two_factor',
  },

  actions: {
    initFromStorage() {
      if (this.hydrated) return;
      this.status = 'anonymous';
      this.hydrated = true;
    },

    async ensureSession() {
      if (this.isAuthenticated) return;
      try {
        await this.fetchMe();
        this.status = 'authenticated';
      } catch {
        this.status = 'anonymous';
      }
    },

    async login(username: string, password: string) {
      const { data } = await authApi.post('/backend/auth/login/', { username, password });
      if (data && typeof data === 'object' && '2fa_required' in data) {
        this.status = 'two_factor';
        this.twoFactor.required = true;
        this.twoFactor.challenge = (data as { challenge?: string }).challenge ?? null;
        return;
      }

      this.status = 'authenticated';

      // Fetch user details immediately to check flags
      await this.fetchMe();
    },

    async verifyTwoFactor(code: string) {
      const challenge = this.twoFactor.challenge;
      if (!challenge) throw new Error('2FA challenge missing');
      await authApi.post('/backend/auth/2fa/verify/', { challenge, code });
      this.status = 'authenticated';
      this.twoFactor.required = false;
      this.twoFactor.challenge = null;
      await this.fetchMe();
    },

    async fetchMe() {
      try {
        const { data } = await api.get('/backend/auth/me/');
        this.user = data;
        this.status = 'authenticated';
      } catch (e) {
        // Si hay tokens viejos (DB reseteada), /me devuelve 401.
        // En ese caso limpiamos sesión para evitar loops de refresh/401.
        if (isAxiosError(e)) {
          const status = e.response?.status;
          if (status === 401 || status === 403) {
            this.hardClearLocal();
          }
        }
        throw e;
      }
    },

    async checkBootstrap() {
      try {
        if (this.bootstrapChecked) return this.bootstrapState;
        const { data } = await authApi.get('/backend/iam/bootstrap/status/');
        this.bootstrapState = data;
        this.bootstrapChecked = true;

        // Si el sistema está fresh, aseguramos no mantener tokens/contexto previos.
        if (data?.is_fresh) {
          this.hardClearLocal();
        }
        return data;
      } catch {
        // quiet fail
      }
    },

    async refresh() {
      // lock: si ya hay refresh en progreso, esperar el mismo
      if (this.refreshInFlight) return this.refreshInFlight;

      this.status = 'refreshing';
      this.refreshInFlight = (async () => {
        try {
          await authApi.post('/backend/auth/refresh/', {});
          this.status = 'authenticated';
        } finally {
          this.refreshInFlight = null;
        }
      })();

      return this.refreshInFlight;
    },

    async logout() {
      // limpiar stores primero para cortar UI rapido
      this.hardClearLocal();
      try {
        // Best-effort: avisar al backend aunque no haya refresh en el cliente.
        await authApi.post('/backend/auth/logout/', {});
      } catch {
        // intencional: no bloqueamos el logout local
      }
    },

    hardClearLocal() {
      const acl = useAclStore();
      const ctx = useContextStore();

      this.status = 'anonymous';
      this.twoFactor.required = false;
      this.twoFactor.challenge = null;
      clearTokens();

      acl.clearAcl();
      ctx.clear();
    },
  },
});
