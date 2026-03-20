import { describe, expect, it } from 'vitest';
import type { RouteRecordRaw } from 'vue-router';

import routes from 'src/router/routes';
import { LEGACY_ROUTE_PATHS, UI_ROUTE_PATHS } from 'src/shared/ui/business-terms';

function childPath(path: string): string {
  return path.startsWith('/') ? path.slice(1) : path;
}

function rootChildren(): RouteRecordRaw[] {
  const root = routes.find((route) => route.path === '/');
  expect(root).toBeDefined();
  expect(Array.isArray(root?.children)).toBe(true);
  return root?.children ?? [];
}

function findChild(path: string): RouteRecordRaw | undefined {
  return rootChildren().find((route) => route.path === childPath(path));
}

describe('router routes', () => {
  it('declares canonical routes for navigation', () => {
    const canonicalRoutes = [
      UI_ROUTE_PATHS.humanResourcesEmployees,
      UI_ROUTE_PATHS.humanResourcesPositions,
      UI_ROUTE_PATHS.organizationCompanies,
      UI_ROUTE_PATHS.organizationCompanyProfile,
      UI_ROUTE_PATHS.organizationBranches,
      UI_ROUTE_PATHS.accountingDashboard,
      UI_ROUTE_PATHS.fuelDashboard,
      UI_ROUTE_PATHS.fuelHealth,
      UI_ROUTE_PATHS.synchronizationEnrollment,
      UI_ROUTE_PATHS.synchronizationDevices,
    ];

    for (const routePath of canonicalRoutes) {
      expect(findChild(routePath)).toBeDefined();
    }
  });

  it('keeps legacy aliases redirected to canonical paths', () => {
    const aliases: Array<{ legacy: string; canonical: string }> = [
      {
        legacy: LEGACY_ROUTE_PATHS.humanResourcesEmployees,
        canonical: UI_ROUTE_PATHS.humanResourcesEmployees,
      },
      {
        legacy: LEGACY_ROUTE_PATHS.humanResourcesPositions,
        canonical: UI_ROUTE_PATHS.humanResourcesPositions,
      },
      {
        legacy: LEGACY_ROUTE_PATHS.organizationCompanies,
        canonical: UI_ROUTE_PATHS.organizationCompanies,
      },
      {
        legacy: LEGACY_ROUTE_PATHS.organizationCompanyProfile,
        canonical: UI_ROUTE_PATHS.organizationCompanyProfile,
      },
      {
        legacy: LEGACY_ROUTE_PATHS.organizationBranches,
        canonical: UI_ROUTE_PATHS.organizationBranches,
      },
      {
        legacy: LEGACY_ROUTE_PATHS.fuelDashboard,
        canonical: UI_ROUTE_PATHS.fuelDashboard,
      },
      {
        legacy: LEGACY_ROUTE_PATHS.fuelHealth,
        canonical: UI_ROUTE_PATHS.fuelHealth,
      },
      {
        legacy: LEGACY_ROUTE_PATHS.synchronizationEnrollment,
        canonical: UI_ROUTE_PATHS.synchronizationEnrollment,
      },
      {
        legacy: LEGACY_ROUTE_PATHS.synchronizationDevices,
        canonical: UI_ROUTE_PATHS.synchronizationDevices,
      },
    ];

    for (const { legacy, canonical } of aliases) {
      const route = findChild(legacy);
      expect(route).toBeDefined();
      expect(typeof route?.redirect).toBe('function');

      const redirect = route?.redirect as (
        to: { query: Record<string, unknown>; hash: string },
        from: unknown,
      ) => { path: string; query: Record<string, unknown>; hash: string };

      const target = redirect({ query: { modo: 'compacto' }, hash: '#bloque' }, null);
      expect(target.path).toBe(canonical);
      expect(target.query).toEqual({ modo: 'compacto' });
      expect(target.hash).toBe('#bloque');
    }
  });

  it('protege tablero contable con permiso accounting.dashboard.read', () => {
    const route = findChild(UI_ROUTE_PATHS.accountingDashboard);
    expect(route).toBeDefined();
    expect(route?.meta?.requiredPermissions).toEqual(['accounting.dashboard.read']);
  });
});
