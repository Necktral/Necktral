<template>
  <q-layout view="hHh lpR fFf" :class="layoutClasses">
    <q-header class="app-topbar" elevated>
      <q-toolbar class="app-topbar__toolbar">
        <div class="app-topbar__context">
          <q-btn
            flat
            dense
            round
            icon="menu"
            aria-label="Abrir navegacion"
            @click="leftDrawerOpen = !leftDrawerOpen"
          />

          <div class="app-brand">
            <div class="app-brand__title">Necktral Console</div>
            <div class="app-brand__subtitle">Plataforma empresarial integrada</div>
          </div>
        </div>

        <div class="app-topbar__actions">
          <q-badge v-if="contextLabel" outline class="q-mr-sm">
            {{ contextLabel }}
          </q-badge>
          <q-badge outline class="q-mr-sm">
            {{ shellBadgeLabel }}
          </q-badge>

          <q-btn flat dense round icon="tune" aria-label="Ajustes de interfaz">
            <q-menu>
              <q-list style="min-width: 280px">
                <q-item-label header>Interfaz</q-item-label>

                <q-item>
                  <q-item-section>
                    <q-item-label>Tema</q-item-label>
                    <q-item-label caption>Claro, oscuro o sistema</q-item-label>
                  </q-item-section>
                </q-item>
                <q-item>
                  <q-item-section>
                    <q-btn-toggle
                      v-model="theme"
                      toggle-color="primary"
                      :options="themeOptions"
                      spread
                      dense
                    />
                  </q-item-section>
                </q-item>

                <q-separator spaced />

                <q-item>
                  <q-item-section>
                    <q-item-label>Densidad</q-item-label>
                    <q-item-label caption>Confortable o compacta</q-item-label>
                  </q-item-section>
                </q-item>
                <q-item>
                  <q-item-section>
                    <q-btn-toggle
                      v-model="density"
                      toggle-color="primary"
                      :options="densityOptions"
                      spread
                      dense
                    />
                  </q-item-section>
                </q-item>
              </q-list>
            </q-menu>
          </q-btn>

          <q-btn flat dense round icon="account_circle" aria-label="Usuario">
            <q-menu>
              <q-list style="min-width: 280px">
                <q-item>
                  <q-item-section>
                    <q-item-label>{{ usernameLabel }}</q-item-label>
                    <q-item-label caption v-if="acl.aclVersion">
                      {{ labels.accessControl }} v{{ acl.aclVersion }}
                    </q-item-label>
                  </q-item-section>
                </q-item>
                <q-separator />
                <q-item clickable v-close-popup @click="onLogout">
                  <q-item-section avatar>
                    <q-icon name="logout" />
                  </q-item-section>
                  <q-item-section>Cerrar sesion</q-item-section>
                </q-item>
              </q-list>
            </q-menu>
          </q-btn>
        </div>
      </q-toolbar>
    </q-header>

    <q-drawer v-model="leftDrawerOpen" show-if-above bordered class="app-drawer">
      <q-list padding>
        <q-item-label header>{{ isMobileShell ? 'Taskflow' : 'Workbench' }}</q-item-label>

        <q-item clickable :to="routes.dashboard" exact :disable="!canDashboardAccess">
          <q-item-section avatar>
            <q-icon name="dashboard" />
          </q-item-section>
          <q-item-section>Tablero</q-item-section>
        </q-item>

        <q-item clickable :to="routes.selectContext">
          <q-item-section avatar>
            <q-icon name="business" />
          </q-item-section>
          <q-item-section>Contexto operativo</q-item-section>
        </q-item>

        <template v-if="!isMobileShell && (canOrganizationAccess || canHumanResourcesAccess || canAuditRead)">
          <q-separator spaced />

          <q-item-label header v-if="canOrganizationAccess">{{ labels.organization }}</q-item-label>
          <q-item clickable :to="routes.organizationCompanies" :disable="!canOrganizationAccess">
            <q-item-section avatar><q-icon name="domain" /></q-item-section>
            <q-item-section>Empresas</q-item-section>
          </q-item>
          <q-item clickable :to="routes.organizationCompanyProfile" :disable="!canOrganizationAccess">
            <q-item-section avatar><q-icon name="apartment" /></q-item-section>
            <q-item-section>Perfil de empresa</q-item-section>
          </q-item>
          <q-item clickable :to="routes.organizationBranches" :disable="!canOrganizationAccess">
            <q-item-section avatar><q-icon name="store" /></q-item-section>
            <q-item-section>Sucursales</q-item-section>
          </q-item>

          <q-separator spaced v-if="canHumanResourcesAccess" />

          <q-item-label header v-if="canHumanResourcesAccess">{{ labels.humanResources }}</q-item-label>
          <q-item clickable :to="routes.humanResourcesPositions" :disable="!canHumanResourcesAccess">
            <q-item-section avatar><q-icon name="work" /></q-item-section>
            <q-item-section>Puestos</q-item-section>
          </q-item>
          <q-item clickable :to="routes.humanResourcesEmployees" :disable="!canHumanResourcesAccess">
            <q-item-section avatar><q-icon name="badge" /></q-item-section>
            <q-item-section>Empleados</q-item-section>
          </q-item>

          <q-separator spaced v-if="canAuditRead" />

          <q-item clickable :to="routes.auditLog" :disable="!canAuditRead">
            <q-item-section avatar><q-icon name="receipt_long" /></q-item-section>
            <q-item-section>Auditoria</q-item-section>
          </q-item>
        </template>

        <q-separator spaced v-if="canFuelRead" />

        <q-item-label header v-if="canFuelRead">{{ labels.fuel }}</q-item-label>
        <q-item clickable :to="routes.fuelDashboard" :disable="!canFuelRead">
          <q-item-section avatar><q-icon name="local_gas_station" /></q-item-section>
          <q-item-section>Tablero de operacion</q-item-section>
        </q-item>
        <q-item clickable :to="routes.fuelHealth" :disable="!canFuelRead">
          <q-item-section avatar><q-icon name="monitor_heart" /></q-item-section>
          <q-item-section>Estado del modulo</q-item-section>
        </q-item>

        <q-separator spaced v-if="canRetailPosRead" />

        <q-item-label header v-if="canRetailPosRead">{{ labels.retailPos }}</q-item-label>
        <q-item clickable :to="routes.retailPosTerminal" :disable="!canRetailPosRead">
          <q-item-section avatar><q-icon name="point_of_sale" /></q-item-section>
          <q-item-section>Terminal POS</q-item-section>
        </q-item>
        <q-item clickable :to="routes.retailPosCockpit" :disable="!canRetailPosRead">
          <q-item-section avatar><q-icon name="monitoring" /></q-item-section>
          <q-item-section>Cockpit operativo</q-item-section>
        </q-item>

        <q-separator spaced v-if="canInventoryAccess" />

        <q-item-label header v-if="canInventoryAccess">{{ labels.inventory }}</q-item-label>
        <q-item clickable :to="routes.inventory" :disable="!canInventoryAccess">
          <q-item-section avatar><q-icon name="inventory_2" /></q-item-section>
          <q-item-section>Operacion de inventario</q-item-section>
        </q-item>

        <template v-if="!isMobileShell && canAnalyticsRead">
          <q-separator spaced />

          <q-item-label header>{{ labels.analytics }}</q-item-label>
          <q-item clickable :to="routes.analytics" :disable="!canAnalyticsRead">
            <q-item-section avatar><q-icon name="insights" /></q-item-section>
            <q-item-section>Workspace analytics</q-item-section>
          </q-item>
        </template>

        <q-separator spaced v-if="canSyncEnroll || canSyncManage" />

        <q-item-label header v-if="canSyncEnroll || canSyncManage">{{ labels.synchronization }}</q-item-label>
        <q-item clickable :to="routes.synchronizationEnrollment" :disable="!canSyncEnroll">
          <q-item-section avatar><q-icon name="qr_code_2" /></q-item-section>
          <q-item-section>Enrolamiento</q-item-section>
        </q-item>
        <q-item clickable :to="routes.synchronizationDevices" :disable="!canSyncManage">
          <q-item-section avatar><q-icon name="devices" /></q-item-section>
          <q-item-section>Dispositivos</q-item-section>
        </q-item>
      </q-list>
    </q-drawer>

    <q-page-container class="app-page-container">
      <router-view />
    </q-page-container>
  </q-layout>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue';
import { useRouter } from 'vue-router';

import { BUSINESS_LABELS, UI_ROUTE_PATHS } from 'src/shared/ui/business-terms';
import { canAccessInventoryModule } from 'src/features/inventory/inventory-shell';
import { useAuthStore } from 'src/stores/auth.store';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';
import { useSessionBootstrapStore } from 'src/stores/session-bootstrap.store';
import { useUiStore } from 'src/stores/ui.store';

const router = useRouter();
const auth = useAuthStore();
const acl = useAclStore();
const ctx = useContextStore();
const sessionBootstrap = useSessionBootstrapStore();
const ui = useUiStore();

const labels = BUSINESS_LABELS;
const routes = UI_ROUTE_PATHS;

ui.initFromStorage();
ctx.initFromStorage();

const leftDrawerOpen = ref(true);

const usernameLabel = computed(() => acl.snapshot?.username ?? 'Usuario');

const theme = computed({
  get: () => ui.theme,
  set: (value) => ui.setTheme(value),
});

const density = computed({
  get: () => ui.density,
  set: (value) => ui.setDensity(value),
});

const themeOptions = [
  { label: 'Sistema', value: 'system' },
  { label: 'Claro', value: 'light' },
  { label: 'Oscuro', value: 'dark' },
];

const densityOptions = [
  { label: 'Confortable', value: 'comfortable' },
  { label: 'Compacta', value: 'compact' },
];

const layoutClasses = computed(() => ({
  'density-compact': ui.density === 'compact',
  'density-comfortable': ui.density === 'comfortable',
}));

const isMobileShell = computed(() => sessionBootstrap.isMobileShell);
const shellBadgeLabel = computed(() => (isMobileShell.value ? 'Taskflow móvil' : 'Workbench desktop'));
const allowedModules = computed(() => new Set(sessionBootstrap.payload?.allowed_modules ?? []));

function hasModuleEnabled(moduleCode: string): boolean {
  return allowedModules.value.has(moduleCode);
}

function hasCompanyPermission(permissionCode: string): boolean {
  const companyId = ctx.activeCompanyId;
  if (!companyId) return false;
  return acl.hasPermission(companyId, permissionCode);
}

const contextLabel = computed(() => {
  const companyId = ctx.activeCompanyId;
  if (!companyId) return null;

  const companyName = acl.companyName(companyId) ?? companyId;
  const branchId = ctx.activeBranchId;
  if (!branchId) return companyName;

  const branchName = acl.branchName(companyId, branchId) ?? branchId;
  return `${companyName} · ${branchName}`;
});

const canDashboardAccess = computed(() => hasModuleEnabled('dashboard'));
const canOrganizationAccess = computed(
  () => hasModuleEnabled('organization') && hasCompanyPermission('org.company.read'),
);
const canHumanResourcesAccess = computed(
  () => hasModuleEnabled('human_resources') && hasCompanyPermission('hr.employee.read'),
);
const canAuditRead = computed(() => hasModuleEnabled('audit') && hasCompanyPermission('audit.read'));

const canFuelRead = computed(() => {
  return hasModuleEnabled('fuel') && hasCompanyPermission('fuel.shift.read');
});

const canRetailPosRead = computed(() => {
  return hasModuleEnabled('retail_pos') && hasCompanyPermission('retail.pos.ticket.read');
});

const canInventoryAccess = computed(() => {
  return canAccessInventoryModule({
    allowedModules: sessionBootstrap.payload?.allowed_modules ?? [],
    hasBasePermission: hasCompanyPermission('inventory.balance.read'),
  });
});

const canAnalyticsRead = computed(() => {
  const analyticsEnabled = hasModuleEnabled('analytics') || hasModuleEnabled('reporting');
  return analyticsEnabled && hasCompanyPermission('report.dashboard.read');
});

const canSyncEnroll = computed(() => {
  return hasModuleEnabled('synchronization') && hasCompanyPermission('sync.device.enroll');
});

const canSyncManage = computed(() => {
  return hasModuleEnabled('synchronization') && hasCompanyPermission('sync.device.revoke');
});

async function onLogout() {
  await auth.logout();
  await router.replace('/login');
}
</script>
