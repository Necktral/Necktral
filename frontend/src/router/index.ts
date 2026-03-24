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

    // 1) Si requiere auth, asegurar sesión por cookies antes de decidir
    if (!auth.isAuthenticated) {
      await auth.ensureSession();
    }

    // 1.1) Si requiere auth y no hay sesión → login
    if (!auth.isAuthenticated) {
      if (to.path !== '/login') return { path: '/login' };
      return true;
    }

    // Ensure user details are loaded if authenticated (solo cuando se requiere auth)
    if (!auth.user) {
      try {
        await auth.fetchMe();
      } catch {
        return { path: '/login' };
      }
    }

    // --- Onboarding / Bootstrap Logic ---

    // 0.5) Authenticated: Security & Setup checks
    if (auth.isAuthenticated) {
      // Enforce password change
      if (auth.user?.must_change_password) {
        if (to.path !== '/password-change' && to.path !== '/logout') {
          return { path: '/password-change' };
        }
      }

      // Enforce setup completion (if user has no companies or explicit flag)
      // We need ACL loaded to know companies.
      if (acl.loaded) {
        // ACL is loaded in step 2 usually, but we check here if loaded
        if (auth.user?.is_setup_complete === false) {
          if (!to.path.startsWith('/bootstrap') && to.path !== '/logout') {
            return { path: '/bootstrap' };
          }
        }
      }
    }

    // 2) Si hay sesión y ACL no está cargado, cargarlo
    if (auth.isAuthenticated && !acl.loaded) {
      try {
        await acl.loadAcl();
      } catch {
        // Si no podemos cargar ACL, forzamos logout
        await auth.logout();
        return { path: '/login' };
      }
    }

    // 3) Si tenemos ACL y no hay contexto, intentar autoselección si el ACL lo recomienda
    if (auth.isAuthenticated && acl.loaded && !ctx.activeCompanyId) {
      const recCompany = acl.recommendedCompanyId;
      const recBranch = acl.recommendedBranchId;

      if (recCompany) ctx.setContext(recCompany, recBranch ?? null);
    }

    // 4) Si la ruta requiere contexto y no hay company → select-context
    if (requiresContext && !ctx.activeCompanyId) {
      if (to.path !== '/select-context') return { path: '/select-context' };
      return true;
    }

    const required = to.meta?.requiredPermissions as string[] | undefined;
    if (required && required.length > 0) {
      const companyId = ctx.activeCompanyId;
      if (!companyId) return { path: '/select-context' };

      const ok = required.every((p) => acl.hasPermission(companyId, p));
      if (!ok) return { path: '/403' };
    }

    const requiredAny = to.meta?.requiredAnyPermissions as string[] | undefined;
    if (requiredAny && requiredAny.length > 0) {
      const companyId = ctx.activeCompanyId;
      if (!companyId) return { path: '/select-context' };
      const okAny = requiredAny.some((p) => acl.hasPermission(companyId, p));
      if (!okAny) return { path: '/403' };
    }

    return true;
  });

  return Router;
});
