export const BUSINESS_LABELS = {
  humanResources: 'Recursos Humanos',
  organization: 'Organizacion',
  accessControl: 'Control de Acceso',
  rolesAndPermissions: 'Roles y Permisos',
  identityAndAccess: 'Identidad y Acceso',
  fuel: 'Combustible',
  synchronization: 'Sincronizacion',
} as const;

export const UI_ROUTE_PATHS = {
  dashboard: '/dashboard',
  selectContext: '/select-context',
  organizationCompanies: '/organizacion/empresas',
  organizationCompanyProfile: '/organizacion/perfil-empresa',
  organizationBranches: '/organizacion/sucursales',
  humanResourcesPositions: '/recursos-humanos/puestos',
  humanResourcesEmployees: '/recursos-humanos/empleados',
  fuelDashboard: '/combustible',
  fuelHealth: '/combustible/salud',
  auditLog: '/audit/bitacora',
  synchronizationEnrollment: '/sincronizacion/enrolamiento',
  synchronizationDevices: '/sincronizacion/dispositivos',
} as const;

export const LEGACY_ROUTE_PATHS = {
  organizationCompanies: '/backend/org/companies',
  organizationCompanyProfile: '/backend/org/company-profile',
  organizationBranches: '/backend/org/branches',
  humanResourcesPositions: '/hr/positions',
  humanResourcesEmployees: '/hr/employees',
  fuelDashboard: '/fuel',
  fuelHealth: '/fuel/health',
  synchronizationEnrollment: '/sync/enrollment',
  synchronizationDevices: '/sync/devices',
} as const;
