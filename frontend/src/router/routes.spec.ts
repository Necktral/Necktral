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
      UI_ROUTE_PATHS.analyticsV3,
      UI_ROUTE_PATHS.analyticsElite,
      UI_ROUTE_PATHS.accountingDashboard,
      UI_ROUTE_PATHS.inventoryDashboard,
      UI_ROUTE_PATHS.inventoryItems,
      UI_ROUTE_PATHS.inventoryItemNew,
      UI_ROUTE_PATHS.inventoryItemEdit,
      UI_ROUTE_PATHS.inventoryWarehouses,
      UI_ROUTE_PATHS.inventoryMovements,
      UI_ROUTE_PATHS.inventoryBalances,
      UI_ROUTE_PATHS.inventoryKardex,
      UI_ROUTE_PATHS.fuelDashboard,
      UI_ROUTE_PATHS.fuelHealth,
      UI_ROUTE_PATHS.retailPos,
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
        legacy: LEGACY_ROUTE_PATHS.retailPos,
        canonical: UI_ROUTE_PATHS.retailPos,
      },
      {
        legacy: LEGACY_ROUTE_PATHS.inventoryDashboard,
        canonical: UI_ROUTE_PATHS.inventoryDashboard,
      },
      {
        legacy: LEGACY_ROUTE_PATHS.inventoryItems,
        canonical: UI_ROUTE_PATHS.inventoryItems,
      },
      {
        legacy: LEGACY_ROUTE_PATHS.inventoryWarehouses,
        canonical: UI_ROUTE_PATHS.inventoryWarehouses,
      },
      {
        legacy: LEGACY_ROUTE_PATHS.inventoryMovements,
        canonical: UI_ROUTE_PATHS.inventoryMovements,
      },
      {
        legacy: LEGACY_ROUTE_PATHS.inventoryBalances,
        canonical: UI_ROUTE_PATHS.inventoryBalances,
      },
      {
        legacy: LEGACY_ROUTE_PATHS.inventoryKardex,
        canonical: UI_ROUTE_PATHS.inventoryKardex,
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

  it('protege analítica avanzada con permisos kernel+legacy (any)', () => {
    const route = findChild(UI_ROUTE_PATHS.analyticsV3);
    expect(route).toBeDefined();
    expect(route?.meta?.requiredAnyPermissions).toEqual(['report.dashboard.read', 'dashboard.workspace.read']);
  });

  it('protege analytics engine con permisos kernel+legacy (any)', () => {
    const route = findChild(UI_ROUTE_PATHS.analyticsElite);
    expect(route).toBeDefined();
    expect(route?.meta?.requiredAnyPermissions).toEqual(['report.dashboard.read', 'dashboard.workspace.read']);
  });

  it('protege inventario tablero con permiso inventory.balance.read', () => {
    const route = findChild(UI_ROUTE_PATHS.inventoryDashboard);
    expect(route).toBeDefined();
    expect(route?.meta?.requiredPermissions).toEqual(['inventory.balance.read']);
  });

  it('protege retail pos con permiso retail.pos.use', () => {
    const route = findChild(UI_ROUTE_PATHS.retailPos);
    expect(route).toBeDefined();
    expect(route?.meta?.requiredPermissions).toEqual(['retail.pos.use']);
  });

  it('protege alta de item master con permisos read + create', () => {
    const route = findChild(UI_ROUTE_PATHS.inventoryItemNew);
    expect(route).toBeDefined();
    expect(route?.meta?.requiredPermissions).toEqual(['inventory.item.read', 'inventory.item.create']);
  });

  it('protege edición de item master con permisos read + update', () => {
    const route = findChild(UI_ROUTE_PATHS.inventoryItemEdit);
    expect(route).toBeDefined();
    expect(route?.meta?.requiredPermissions).toEqual(['inventory.item.read', 'inventory.item.update']);
  });
});
