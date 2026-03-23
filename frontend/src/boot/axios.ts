import { boot } from 'quasar/wrappers';
import type { AxiosError, AxiosInstance, AxiosRequestConfig } from 'axios';
import axios from 'axios';
import { useAuthStore } from 'src/stores/auth.store';
import { useContextStore } from 'src/stores/context.store';

declare module 'axios' {
  export interface AxiosRequestConfig {
    _retry?: boolean;
    _skipAuthRefresh?: boolean;
  }
}

declare module 'vue' {
  interface ComponentCustomProperties {
    $axios: AxiosInstance;
    $api: AxiosInstance;
  }
}

const API_BASE_URL =
  (import.meta.env.VITE_API_BASE_URL as string | undefined) ?? 'http://localhost:8000/api';
const AUTH_TRANSPORT = 'cookie';
const CSRF_COOKIE_NAME = import.meta.env.VITE_CSRF_COOKIE_NAME || 'nt_csrf';

type RouterLike = {
  replace: (to: string) => Promise<unknown> | void;
};

type AuthLike = {
  refresh: () => Promise<void>;
  hardClearLocal: () => void;
};

export function readCookie(name: string): string | null {
  const m = document.cookie.match(new RegExp('(^|;\\s*)' + name + '=([^;]*)'));
  const value = m?.[2];
  return value ? decodeURIComponent(value) : null;
}

export function isMutatingMethod(method: string | undefined): boolean {
  const normalized = (method || 'get').toLowerCase();
  return normalized === 'post' || normalized === 'put' || normalized === 'patch' || normalized === 'delete';
}

export const api = axios.create({
  baseURL: API_BASE_URL,
  timeout: 25_000,
  withCredentials: AUTH_TRANSPORT === 'cookie',
});

export const authApi = axios.create({
  baseURL: API_BASE_URL,
  timeout: 25_000,
  withCredentials: AUTH_TRANSPORT === 'cookie',
});

// Endpoints exentos de contexto (no requieren X-Company-Id)
const CONTEXT_EXEMPT_PREFIXES = [
  '/backend/auth/login/',
  '/backend/auth/refresh/',
  '/backend/auth/logout/',
  '/backend/auth/me/',
  '/backend/auth/me/acl/',
  '/backend/auth/bootstrap/',
  '/backend/iam/bootstrap/',
  '/backend/org/bootstrap/',
  '/backend/auth/password/',
  '/auth/login/',
  '/auth/refresh/',
  '/auth/logout/',
  '/auth/me/',
  '/auth/me/acl/',
  '/auth/bootstrap/',
  '/iam/bootstrap/',
  '/org/bootstrap/',
  '/auth/password/',
  '/schema/',
];

function getPath(config: AxiosRequestConfig): string {
  const url = config.url ?? '';
  // Si url es relativa ("/auth/login/"), esto ya sirve.
  // Si fuera absoluta, igual soporta parsing.
  try {
    const full = new URL(url, config.baseURL);
    return full.pathname.replace(/\/api\/?/, '/'); // normaliza si aparece /api/
  } catch {
    return url;
  }
}

function isContextExempt(path: string): boolean {
  return CONTEXT_EXEMPT_PREFIXES.some((p) => path.startsWith(p));
}

export function applyCsrfHeader(config: AxiosRequestConfig): AxiosRequestConfig {
  if (AUTH_TRANSPORT !== 'cookie') return config;
  if (!isMutatingMethod(config.method)) return config;
  const csrf = readCookie(CSRF_COOKIE_NAME);
  if (!csrf) return config;

  config.headers = config.headers ?? {};
  config.headers['X-CSRF-Token'] = csrf;
  return config;
}

export async function handleApiResponseError(
  error: AxiosError,
  deps: {
    auth: AuthLike;
    router: RouterLike;
    retryRequest: (config: AxiosRequestConfig) => Promise<unknown>;
  },
): Promise<unknown> {
  const original = error.config as AxiosRequestConfig | undefined;
  if (!original) return Promise.reject(error);

  const status = error.response?.status;

  // 401: intentar refresh una vez, y reintentar request.
  if (status === 401 && !original._retry && !original._skipAuthRefresh) {
    original._retry = true;
    try {
      await deps.auth.refresh();
      return deps.retryRequest(original);
    } catch (e) {
      deps.auth.hardClearLocal();
      await deps.router.replace('/login');
      const reason = e instanceof Error ? e : new Error(String(e));
      return Promise.reject(reason);
    }
  }

  // 403: redirigir a forbidden sin limpiar sesión.
  if (status === 403) {
    await deps.router.replace('/403');
  }

  return Promise.reject(error);
}

function attachRequestInterceptor(client: AxiosInstance, opts: { includeContext: boolean }) {
  client.interceptors.request.use((config) => {
    const auth = useAuthStore();
    const ctx = useContextStore();

    auth.initFromStorage();
    ctx.initFromStorage();

    const path = getPath(config);
    applyCsrfHeader(config);

    if (!opts.includeContext) return config;

    // Context headers (solo si no es endpoint exento).
    if (!isContextExempt(path)) {
      if (!ctx.activeCompanyId) {
        // Dejar que el router guard fuerce /select-context; aquí devolvemos error claro.
        // También evita llamadas operativas sin company.
        const err = new Error('ContextMissing: X-Company-Id is required');
        return Promise.reject(err);
      }

      config.headers = config.headers ?? {};
      config.headers['X-Company-Id'] = ctx.activeCompanyId;
      if (ctx.activeBranchId) config.headers['X-Branch-Id'] = ctx.activeBranchId;
    }

    return config;
  });
}

export default boot(({ app, router }) => {
  app.config.globalProperties.$axios = axios;
  app.config.globalProperties.$api = api;

  attachRequestInterceptor(api, { includeContext: true });
  attachRequestInterceptor(authApi, { includeContext: false });

  api.interceptors.response.use(
    (resp) => resp,
    (error: AxiosError) => {
      const auth = useAuthStore();
      return handleApiResponseError(error, {
        auth,
        router,
        retryRequest: (config) => api.request(config),
      });
    },
  );
});

export { axios };
