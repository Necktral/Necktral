import { route } from 'quasar/wrappers';
import {
  createMemoryHistory,
  createRouter,
  createWebHashHistory,
  createWebHistory,
} from 'vue-router';
import routes from './routes';
import { useAuthStore } from 'src/stores/auth.store';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';
import { useSessionBootstrapStore } from 'src/stores/session-bootstrap.store';
import { isAxiosError } from 'axios';

export default route(function () {
  const createHistory = process.env.SERVER
    ? createMemoryHistory
    : process.env.VUE_ROUTER_MODE === 'history'
      ? createWebHistory
      : createWebHashHistory;

  const Router = createRouter({
    scrollBehavior: () => ({ left: 0, top: 0 }),
    routes,
    history: createHistory(process.env.VUE_ROUTER_BASE),
  });

  Router.beforeEach(async (to) => {
    const auth = useAuthStore();
    const acl = useAclStore();
    const ctx = useContextStore();
    const sessionBootstrap = useSessionBootstrapStore();

    auth.initFromStorage();
    ctx.initFromStorage();

    // 0) Bootstrap (BD vacía / setup requerido). Esto debe correr antes de intentar /me o cargar ACL.
    try {
      await auth.checkBootstrap();
    } catch {
      // intencional: si el backend no responde, no bloqueamos navegación
    }

    // Si el sistema está fresh, no debe haber llamadas a endpoints protegidos.
    if (auth.bootstrapState.is_fresh) {
      if (to.path !== '/login' && !to.path.startsWith('/bootstrap')) {
        return { path: '/login' };
      }
      return true;
    }

    const requiresAuth = Boolean(to.meta?.requiresAuth);
    const requiresContext = Boolean(to.meta?.requiresContext);

    // Si la ruta NO requiere auth, no disparamos llamadas protegidas en background.
    // Esto evita 401 molestos en /login cuando hay tokens viejos (DB reseteada).
    if (!requiresAuth) {
      return true;
    }

    // 1) Bootstrap de sesión: fuente única para user/contexto/capabilities/shell.
    if (!sessionBootstrap.loaded) {
      try {
        await sessionBootstrap.loadSession();
      } catch (error) {
        if (isAxiosError(error) && (error.response?.status === 401 || error.response?.status === 403)) {
          auth.hardClearLocal();
        }
        return { path: '/login' };
      }
    }

    // 2) Redirecciones de seguridad y setup se deciden solo desde bootstrap.
    if (auth.user?.must_change_password) {
      if (to.path !== '/password-change' && to.path !== '/logout') {
        return { path: '/password-change' };
      }
    }

    if (sessionBootstrap.payload?.bootstrap_state?.setup_required) {
      if (!to.path.startsWith('/bootstrap') && to.path !== '/logout') {
        return { path: '/bootstrap' };
      }
    }

    if (!acl.loaded) {
      return { path: '/login' };
    }

    // 3) Contexto operativo requerido
    const requiresContextSelection =
      sessionBootstrap.payload?.effective_context?.requires_context_selection ?? false;
    if (requiresContextSelection && !ctx.activeCompanyId && to.path !== '/select-context') {
      return { path: '/select-context' };
    }

    if (requiresContext && !ctx.activeCompanyId) {
      if (to.path !== '/select-context') return { path: '/select-context' };
      return true;
    }

    // 4) ACL por ruta
    const required = to.meta?.requiredPermissions as string[] | undefined;
    if (required && required.length > 0) {
      const companyId = ctx.activeCompanyId;
      if (!companyId) return { path: '/select-context' };

      const ok = required.every((p) => acl.hasPermission(companyId, p));
      if (!ok) return { path: '/403' };
    }

    const requiredModules = to.meta?.requiredModules as string[] | undefined;
    if (requiredModules && requiredModules.length > 0) {
      const allowedModules = new Set(sessionBootstrap.payload?.allowed_modules ?? []);
      const ok = requiredModules.every((m) => allowedModules.has(m));
      if (!ok) return { path: '/403' };
    }

    return true;
  });

  return Router;
});
