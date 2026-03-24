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
        <q-item-label header>Navegacion</q-item-label>

        <q-item clickable :to="routes.dashboard" exact>
          <q-item-section avatar>
            <q-icon name="dashboard" />
          </q-item-section>
          <q-item-section>Tablero</q-item-section>
        </q-item>

        <q-item clickable :to="routes.analyticsV3" :disable="!canDashboardV3Read">
          <q-item-section avatar>
            <q-icon name="analytics" />
          </q-item-section>
          <q-item-section>Analítica avanzada</q-item-section>
        </q-item>

        <q-item clickable :to="routes.selectContext">
          <q-item-section avatar>
            <q-icon name="business" />
          </q-item-section>
          <q-item-section>Contexto operativo</q-item-section>
        </q-item>

        <q-separator spaced />

        <q-item-label header>{{ labels.accounting }}</q-item-label>
        <q-item clickable :to="routes.accountingDashboard" :disable="!canAccountingDashboardRead">
          <q-item-section avatar><q-icon name="insights" /></q-item-section>
          <q-item-section>Tablero financiero</q-item-section>
        </q-item>

        <q-separator spaced />

        <q-item-label header>{{ labels.inventory }}</q-item-label>
        <q-item clickable :to="routes.inventoryDashboard" :disable="!canInventoryRead">
          <q-item-section avatar><q-icon name="inventory_2" /></q-item-section>
          <q-item-section>Dashboard inventario</q-item-section>
        </q-item>
        <q-item clickable :to="routes.inventoryItems" :disable="!canInventoryItemRead">
          <q-item-section avatar><q-icon name="category" /></q-item-section>
          <q-item-section>Ítems</q-item-section>
        </q-item>
        <q-item clickable :to="routes.inventoryWarehouses" :disable="!canInventoryRead">
          <q-item-section avatar><q-icon name="warehouse" /></q-item-section>
          <q-item-section>Almacenes</q-item-section>
        </q-item>
        <q-item clickable :to="routes.inventoryMovements" :disable="!canInventoryRead">
          <q-item-section avatar><q-icon name="swap_horiz" /></q-item-section>
          <q-item-section>Movimientos</q-item-section>
        </q-item>
        <q-item clickable :to="routes.inventoryBalances" :disable="!canInventoryRead">
          <q-item-section avatar><q-icon name="balance" /></q-item-section>
          <q-item-section>Balances</q-item-section>
        </q-item>
        <q-item clickable :to="routes.inventoryKardex" :disable="!canInventoryRead">
          <q-item-section avatar><q-icon name="receipt_long" /></q-item-section>
          <q-item-section>Kardex</q-item-section>
        </q-item>

        <q-separator spaced />

        <q-item-label header>{{ labels.organization }}</q-item-label>
        <q-item clickable :to="routes.organizationCompanies">
          <q-item-section avatar><q-icon name="domain" /></q-item-section>
          <q-item-section>Empresas</q-item-section>
        </q-item>
        <q-item clickable :to="routes.organizationCompanyProfile">
          <q-item-section avatar><q-icon name="apartment" /></q-item-section>
          <q-item-section>Perfil de empresa</q-item-section>
        </q-item>
        <q-item clickable :to="routes.organizationBranches">
          <q-item-section avatar><q-icon name="store" /></q-item-section>
          <q-item-section>Sucursales</q-item-section>
        </q-item>

        <q-separator spaced />

        <q-item-label header>{{ labels.humanResources }}</q-item-label>
        <q-item clickable :to="routes.humanResourcesPositions">
          <q-item-section avatar><q-icon name="work" /></q-item-section>
          <q-item-section>Puestos</q-item-section>
        </q-item>
        <q-item clickable :to="routes.humanResourcesEmployees">
          <q-item-section avatar><q-icon name="badge" /></q-item-section>
          <q-item-section>Empleados</q-item-section>
        </q-item>

        <q-separator spaced />

        <q-item clickable :to="routes.auditLog" :disable="!canAuditRead">
          <q-item-section avatar><q-icon name="receipt_long" /></q-item-section>
          <q-item-section>Auditoria</q-item-section>
        </q-item>

        <q-separator spaced />

        <q-item-label header>{{ labels.fuel }}</q-item-label>
        <q-item clickable :to="routes.fuelDashboard" :disable="!canFuelRead">
          <q-item-section avatar><q-icon name="local_gas_station" /></q-item-section>
          <q-item-section>Tablero de operacion</q-item-section>
        </q-item>
        <q-item clickable :to="routes.fuelHealth" :disable="!canFuelRead">
          <q-item-section avatar><q-icon name="monitor_heart" /></q-item-section>
          <q-item-section>Estado del modulo</q-item-section>
        </q-item>

        <q-separator spaced />

        <q-item-label header>{{ labels.retail }}</q-item-label>
        <q-item clickable :to="routes.retailPos" :disable="!canRetailUse">
          <q-item-section avatar><q-icon name="point_of_sale" /></q-item-section>
          <q-item-section>POS retail</q-item-section>
        </q-item>

        <q-separator spaced />

        <q-item-label header>{{ labels.synchronization }}</q-item-label>
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

    <InventoryCommandPalette v-model="inventoryPaletteOpen" />
  </q-layout>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { useRouter } from 'vue-router';

import InventoryCommandPalette from 'src/modules/inventory/components/InventoryCommandPalette.vue';
import { BUSINESS_LABELS, UI_ROUTE_PATHS } from 'src/shared/ui/business-terms';
import { useAuthStore } from 'src/stores/auth.store';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';
import { useUiStore } from 'src/stores/ui.store';

const router = useRouter();
const auth = useAuthStore();
const acl = useAclStore();
const ctx = useContextStore();
const ui = useUiStore();

const labels = BUSINESS_LABELS;
const routes = UI_ROUTE_PATHS;

ui.initFromStorage();
ctx.initFromStorage();

const leftDrawerOpen = ref(true);
const inventoryPaletteOpen = ref(false);

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

const contextLabel = computed(() => {
  const companyId = ctx.activeCompanyId;
  if (!companyId) return null;

  const companyName = acl.companyName(companyId) ?? companyId;
  const branchId = ctx.activeBranchId;
  if (!branchId) return companyName;

  const branchName = acl.branchName(companyId, branchId) ?? branchId;
  return `${companyName} · ${branchName}`;
});

const canAuditRead = computed(() => {
  const companyId = ctx.activeCompanyId;
  if (!companyId) return false;
  return acl.hasPermission(companyId, 'audit.read');
});

const canAccountingDashboardRead = computed(() => {
  const companyId = ctx.activeCompanyId;
  if (!companyId) return false;
  return acl.hasPermission(companyId, 'accounting.dashboard.read');
});

const canDashboardV3Read = computed(() => {
  const companyId = ctx.activeCompanyId;
  if (!companyId) return false;
  return acl.hasPermission(companyId, 'dashboard.workspace.read');
});

const canInventoryRead = computed(() => {
  const companyId = ctx.activeCompanyId;
  if (!companyId) return false;
  return acl.hasPermission(companyId, 'inventory.balance.read');
});

const canInventoryItemRead = computed(() => {
  const companyId = ctx.activeCompanyId;
  if (!companyId) return false;
  return acl.hasPermission(companyId, 'inventory.item.read');
});

const canFuelRead = computed(() => {
  const companyId = ctx.activeCompanyId;
  if (!companyId) return false;
  return acl.hasPermission(companyId, 'fuel.shift.read');
});

const canRetailUse = computed(() => {
  const companyId = ctx.activeCompanyId;
  if (!companyId) return false;
  return acl.hasPermission(companyId, 'retail.pos.use');
});

const canSyncEnroll = computed(() => {
  const companyId = ctx.activeCompanyId;
  if (!companyId) return false;
  return acl.hasPermission(companyId, 'sync.device.enroll');
});

const canSyncManage = computed(() => {
  const companyId = ctx.activeCompanyId;
  if (!companyId) return false;
  return acl.hasPermission(companyId, 'sync.device.revoke');
});

async function onLogout() {
  await auth.logout();
  await router.replace('/login');
}

function onGlobalShortcut(event: KeyboardEvent) {
  if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === 'k') {
    event.preventDefault();
    inventoryPaletteOpen.value = true;
    return;
  }

  if (!event.altKey || event.ctrlKey || event.metaKey) return;
  const key = event.key;
  const routeByAltKey: Record<string, string> = {
    '1': routes.inventoryDashboard,
    '2': routes.inventoryItems,
    '3': routes.inventoryWarehouses,
    '4': routes.inventoryMovements,
    '5': routes.inventoryBalances,
    '6': routes.inventoryKardex,
    '7': routes.retailPos,
  };
  const target = routeByAltKey[key];
  if (!target) return;
  event.preventDefault();
  void router.push(target);
}

onMounted(() => {
  window.addEventListener('keydown', onGlobalShortcut);
});

onUnmounted(() => {
  window.removeEventListener('keydown', onGlobalShortcut);
});
</script>
