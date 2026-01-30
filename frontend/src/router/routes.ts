import type { RouteRecordRaw } from 'vue-router';
import MainLayout from 'layouts/MainLayout.vue';

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
    ],
  },

  {
    path: '/',
    component: MainLayout,
    meta: { requiresAuth: true },
    children: [
      { path: '', redirect: '/dashboard' },
      {
        path: 'select-context',
        component: () => import('pages/SelectContextPage.vue'),
        meta: { requiresAuth: true, requiresContext: false },
      },
      {
        path: 'dashboard',
        component: () => import('pages/DashboardPage.vue'),
        meta: { requiresAuth: true, requiresContext: true },
      },
      {
        path: '403',
        component: () => import('pages/ForbiddenPage.vue'),
        meta: { requiresAuth: true, requiresContext: false },
      },
      {
        path: 'org/companies',
        component: () => import('pages/OrgCompaniesPage.vue'),
        meta: {
          requiresAuth: true,
          requiresContext: true,
          requiredPermissions: ['org.company.read'],
        },
      },
      {
        path: 'org/company-profile',
        component: () => import('pages/OrgCompanyProfilePage.vue'),
        meta: {
          requiresAuth: true,
          requiresContext: true,
          requiredPermissions: ['org.company.read'],
        },
      },
      {
        path: 'org/branches',
        component: () => import('pages/OrgBranchesPage.vue'),
        meta: {
          requiresAuth: true,
          requiresContext: true,
          requiredPermissions: ['org.branch.read'],
        },
      },
      {
        path: 'hr/positions',
        component: () => import('pages/HrPositionsPage.vue'),
        meta: {
          requiresAuth: true,
          requiresContext: true,
          requiredPermissions: ['hr.position.read'],
        },
      },
      {
        path: 'hr/employees',
        component: () => import('pages/HrEmployeesPage.vue'),
        meta: {
          requiresAuth: true,
          requiresContext: true,
          requiredPermissions: ['hr.employee.read'],
        },
      },
      {
        path: 'audit/bitacora',
        component: () => import('pages/AuditBitacoraPage.vue'),
        meta: {
          requiresAuth: true,
          requiresContext: true,
          requiredPermissions: ['audit.read'],
        },
      },
      {
        path: 'sync/offline',
        component: () => import('pages/SyncOfflinePage.vue'),
        meta: {
          requiresAuth: true,
          requiresContext: true,
        },
      },
      {
        path: 'fuel',
        component: () => import('pages/FuelDashboardPage.vue'),
        meta: {
          requiresAuth: true,
          requiresContext: true,
          requiredPermissions: ['fuel.shift.read'],
        },
      },
      {
        path: 'fuel/health',
        component: () => import('pages/FuelHealthPage.vue'),
        meta: {
          requiresAuth: true,
          requiresContext: true,
          requiredPermissions: ['fuel.shift.read'],
        },
      },
    ],
  },

  {
    path: '/:catchAll(.*)*',
    component: () => import('pages/ErrorNotFound.vue'),
  },
];

export default routes;
