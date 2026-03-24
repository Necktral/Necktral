import type { RouteRecordRaw, RouteRecordRedirectOption } from 'vue-router';
import { LEGACY_ROUTE_PATHS, UI_ROUTE_PATHS } from 'src/shared/ui/business-terms';

function childPath(path: string): string {
  return path.startsWith('/') ? path.slice(1) : path;
}

function redirectToCanonical(path: string): RouteRecordRedirectOption {
  return (to) => ({
    path,
    query: to.query,
    hash: to.hash,
  });
}

const routes: RouteRecordRaw[] = [
  {
    path: '/bootstrap',
    component: () => import('layouts/AuthLayout.vue'),
    children: [
      {
        path: '',
        component: () => import('pages/BootstrapWizardPage.vue'),
        meta: { requiresAuth: false },
      },
    ],
  },
  {
    path: '/password-change',
    component: () => import('layouts/AuthLayout.vue'),
    children: [
      {
        path: '',
        component: () => import('pages/ForcePasswordChangePage.vue'),
        meta: { requiresAuth: true },
      },
    ],
  },
  {
    path: '/login',
    component: () => import('layouts/AuthLayout.vue'),
    children: [
      {
        path: '',
        component: () => import('pages/LoginPage.vue'),
        meta: { requiresAuth: false },
      },
      {
        path: '2fa',
        component: () => import('pages/TwoFactorPage.vue'),
        meta: { requiresAuth: false },
      },
    ],
  },
  {
    path: '/',
    component: () => import('layouts/MainLayout.vue'),
    meta: { requiresAuth: true },
    children: [
      { path: '', redirect: UI_ROUTE_PATHS.dashboard },
      {
        path: childPath(UI_ROUTE_PATHS.selectContext),
        name: 'seleccion-contexto',
        component: () => import('pages/SelectContextPage.vue'),
        meta: { requiresAuth: true, requiresContext: false },
      },
      {
        path: childPath(UI_ROUTE_PATHS.dashboard),
        name: 'tablero',
        component: () => import('pages/DashboardPage.vue'),
        meta: { requiresAuth: true, requiresContext: true },
      },
      {
        path: childPath(UI_ROUTE_PATHS.analyticsV3),
        name: 'analitica-v3',
        component: () => import('src/modules/dashboard_v3/pages/DashboardV3Page.vue'),
        meta: {
          requiresAuth: true,
          requiresContext: true,
          requiredPermissions: ['dashboard.workspace.read'],
        },
      },
      {
        path: childPath(UI_ROUTE_PATHS.accountingDashboard),
        name: 'contabilidad-tablero',
        component: () => import('src/modules/accounting/dashboard/pages/AccountingDashboardPage.vue'),
        meta: {
          requiresAuth: true,
          requiresContext: true,
          requiredPermissions: ['accounting.dashboard.read'],
        },
      },
      {
        path: childPath(UI_ROUTE_PATHS.inventoryDashboard),
        name: 'inventario-tablero',
        component: () => import('pages/InventoryDashboardPage.vue'),
        meta: {
          requiresAuth: true,
          requiresContext: true,
          requiredPermissions: ['inventory.balance.read'],
        },
      },
      {
        path: childPath(UI_ROUTE_PATHS.inventoryItems),
        name: 'inventario-items',
        component: () => import('pages/InventoryItemsPage.vue'),
        meta: {
          requiresAuth: true,
          requiresContext: true,
          requiredPermissions: ['inventory.item.read'],
        },
      },
      {
        path: childPath(UI_ROUTE_PATHS.inventoryItemNew),
        name: 'inventario-item-nuevo',
        component: () => import('pages/InventoryItemMasterPage.vue'),
        meta: {
          requiresAuth: true,
          requiresContext: true,
          requiredPermissions: ['inventory.item.read', 'inventory.item.create'],
        },
      },
      {
        path: childPath(UI_ROUTE_PATHS.inventoryItemEdit),
        name: 'inventario-item-editar',
        component: () => import('pages/InventoryItemMasterPage.vue'),
        meta: {
          requiresAuth: true,
          requiresContext: true,
          requiredPermissions: ['inventory.item.read', 'inventory.item.update'],
        },
      },
      {
        path: childPath(UI_ROUTE_PATHS.inventoryWarehouses),
        name: 'inventario-almacenes',
        component: () => import('pages/InventoryWarehousesPage.vue'),
        meta: {
          requiresAuth: true,
          requiresContext: true,
          requiredPermissions: ['inventory.balance.read'],
        },
      },
      {
        path: childPath(UI_ROUTE_PATHS.inventoryMovements),
        name: 'inventario-movimientos',
        component: () => import('pages/InventoryMovementsPage.vue'),
        meta: {
          requiresAuth: true,
          requiresContext: true,
          requiredPermissions: ['inventory.balance.read'],
        },
      },
      {
        path: childPath(UI_ROUTE_PATHS.inventoryBalances),
        name: 'inventario-balances',
        component: () => import('pages/InventoryBalancesPage.vue'),
        meta: {
          requiresAuth: true,
          requiresContext: true,
          requiredPermissions: ['inventory.balance.read'],
        },
      },
      {
        path: childPath(UI_ROUTE_PATHS.inventoryKardex),
        name: 'inventario-kardex',
        component: () => import('pages/InventoryKardexPage.vue'),
        meta: {
          requiresAuth: true,
          requiresContext: true,
          requiredPermissions: ['inventory.balance.read'],
        },
      },
      {
        path: '403',
        component: () => import('pages/ForbiddenPage.vue'),
        meta: { requiresAuth: true, requiresContext: false },
      },
      {
        path: childPath(UI_ROUTE_PATHS.organizationCompanies),
        name: 'organizacion-empresas',
        component: () => import('pages/OrgCompaniesPage.vue'),
        meta: {
          requiresAuth: true,
          requiresContext: true,
          requiredPermissions: ['org.company.read'],
        },
      },
      {
        path: childPath(UI_ROUTE_PATHS.organizationCompanyProfile),
        name: 'organizacion-perfil-empresa',
        component: () => import('pages/OrgCompanyProfilePage.vue'),
        meta: {
          requiresAuth: true,
          requiresContext: true,
          requiredPermissions: ['org.company.read'],
        },
      },
      {
        path: childPath(UI_ROUTE_PATHS.organizationBranches),
        name: 'organizacion-sucursales',
        component: () => import('pages/OrgBranchesPage.vue'),
        meta: {
          requiresAuth: true,
          requiresContext: true,
          requiredPermissions: ['org.branch.read'],
        },
      },
      {
        path: childPath(UI_ROUTE_PATHS.humanResourcesPositions),
        name: 'recursos-humanos-puestos',
        component: () => import('pages/HrPositionsPage.vue'),
        meta: {
          requiresAuth: true,
          requiresContext: true,
          requiredPermissions: ['hr.position.read'],
        },
      },
      {
        path: childPath(UI_ROUTE_PATHS.humanResourcesEmployees),
        name: 'recursos-humanos-empleados',
        component: () => import('pages/HrEmployeesPage.vue'),
        meta: {
          requiresAuth: true,
          requiresContext: true,
          requiredPermissions: ['hr.employee.read'],
        },
      },
      {
        path: childPath(UI_ROUTE_PATHS.auditLog),
        component: () => import('pages/AuditBitacoraPage.vue'),
        meta: {
          requiresAuth: true,
          requiresContext: true,
          requiredPermissions: ['audit.read'],
        },
      },
      {
        path: 'settings/2fa',
        component: () => import('pages/TwoFactorSetupPage.vue'),
        meta: {
          requiresAuth: true,
          requiresContext: false,
        },
      },
      {
        path: childPath(UI_ROUTE_PATHS.fuelDashboard),
        name: 'combustible-tablero',
        component: () => import('pages/FuelDashboardPage.vue'),
        meta: {
          requiresAuth: true,
          requiresContext: true,
          requiredPermissions: ['fuel.shift.read'],
        },
      },
      {
        path: childPath(UI_ROUTE_PATHS.fuelHealth),
        name: 'combustible-salud',
        component: () => import('pages/FuelHealthPage.vue'),
        meta: {
          requiresAuth: true,
          requiresContext: true,
          requiredPermissions: ['fuel.shift.read'],
        },
      },
      {
        path: childPath(UI_ROUTE_PATHS.retailPos),
        name: 'retail-pos',
        component: () => import('src/modules/retail/pos/pages/RetailPosPage.vue'),
        meta: {
          requiresAuth: true,
          requiresContext: true,
          requiredPermissions: ['retail.pos.use'],
        },
      },
      {
        path: childPath(UI_ROUTE_PATHS.synchronizationEnrollment),
        name: 'sincronizacion-enrolamiento',
        component: () => import('pages/SyncEnrollmentPage.vue'),
        meta: {
          requiresAuth: true,
          requiresContext: true,
          requiredPermissions: ['sync.device.enroll'],
        },
      },
      {
        path: childPath(UI_ROUTE_PATHS.synchronizationDevices),
        name: 'sincronizacion-dispositivos',
        component: () => import('pages/SyncDevicesPage.vue'),
        meta: {
          requiresAuth: true,
          requiresContext: true,
          requiredPermissions: ['sync.device.revoke'],
        },
      },

      // Alias de compatibilidad retroactiva: mantienen enlaces legacy activos.
      {
        path: childPath(LEGACY_ROUTE_PATHS.organizationCompanies),
        redirect: redirectToCanonical(UI_ROUTE_PATHS.organizationCompanies),
      },
      {
        path: childPath(LEGACY_ROUTE_PATHS.organizationCompanyProfile),
        redirect: redirectToCanonical(UI_ROUTE_PATHS.organizationCompanyProfile),
      },
      {
        path: childPath(LEGACY_ROUTE_PATHS.organizationBranches),
        redirect: redirectToCanonical(UI_ROUTE_PATHS.organizationBranches),
      },
      {
        path: childPath(LEGACY_ROUTE_PATHS.humanResourcesPositions),
        redirect: redirectToCanonical(UI_ROUTE_PATHS.humanResourcesPositions),
      },
      {
        path: childPath(LEGACY_ROUTE_PATHS.humanResourcesEmployees),
        redirect: redirectToCanonical(UI_ROUTE_PATHS.humanResourcesEmployees),
      },
      {
        path: childPath(LEGACY_ROUTE_PATHS.fuelDashboard),
        redirect: redirectToCanonical(UI_ROUTE_PATHS.fuelDashboard),
      },
      {
        path: childPath(LEGACY_ROUTE_PATHS.fuelHealth),
        redirect: redirectToCanonical(UI_ROUTE_PATHS.fuelHealth),
      },
      {
        path: childPath(LEGACY_ROUTE_PATHS.retailPos),
        redirect: redirectToCanonical(UI_ROUTE_PATHS.retailPos),
      },
      {
        path: childPath(LEGACY_ROUTE_PATHS.inventoryDashboard),
        redirect: redirectToCanonical(UI_ROUTE_PATHS.inventoryDashboard),
      },
      {
        path: childPath(LEGACY_ROUTE_PATHS.inventoryItems),
        redirect: redirectToCanonical(UI_ROUTE_PATHS.inventoryItems),
      },
      {
        path: childPath(LEGACY_ROUTE_PATHS.inventoryWarehouses),
        redirect: redirectToCanonical(UI_ROUTE_PATHS.inventoryWarehouses),
      },
      {
        path: childPath(LEGACY_ROUTE_PATHS.inventoryMovements),
        redirect: redirectToCanonical(UI_ROUTE_PATHS.inventoryMovements),
      },
      {
        path: childPath(LEGACY_ROUTE_PATHS.inventoryBalances),
        redirect: redirectToCanonical(UI_ROUTE_PATHS.inventoryBalances),
      },
      {
        path: childPath(LEGACY_ROUTE_PATHS.inventoryKardex),
        redirect: redirectToCanonical(UI_ROUTE_PATHS.inventoryKardex),
      },
      {
        path: childPath(LEGACY_ROUTE_PATHS.synchronizationEnrollment),
        redirect: redirectToCanonical(UI_ROUTE_PATHS.synchronizationEnrollment),
      },
      {
        path: childPath(LEGACY_ROUTE_PATHS.synchronizationDevices),
        redirect: redirectToCanonical(UI_ROUTE_PATHS.synchronizationDevices),
      },
    ],
  },
  {
    path: '/:catchAll(.*)*',
    component: () => import('pages/ErrorNotFound.vue'),
  },
];

export default routes;
