<template>
  <q-layout view="hHh lpR fFf" :class="layoutClasses">
    <q-header elevated>
      <q-toolbar>
        <q-btn flat dense round icon="menu" @click="leftDrawerOpen = !leftDrawerOpen" />
        <q-toolbar-title>Necktral Console</q-toolbar-title>

        <q-badge v-if="contextLabel" outline class="q-mr-sm">
          {{ contextLabel }}
        </q-badge>

        <!-- UI Controls -->
        <q-btn flat dense round icon="tune" aria-label="Ajustes de interfaz">
          <q-menu>
            <q-list style="min-width: 280px">
              <q-item-label header>Interfaz</q-item-label>

              <q-item>
                <q-item-section>
                  <q-item-label>Tema</q-item-label>
                  <q-item-label caption>Light / Dark / System</q-item-label>
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
                  <q-item-label caption>Comfortable / Compact</q-item-label>
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

        <!-- User menu -->
        <q-btn flat dense round icon="account_circle" aria-label="Usuario">
          <q-menu>
            <q-list style="min-width: 240px">
              <q-item>
                <q-item-section>
                  <q-item-label>{{ usernameLabel }}</q-item-label>
                  <q-item-label caption v-if="acl.aclVersion"
                    >ACL {{ acl.aclVersion }}</q-item-label
                  >
                </q-item-section>
              </q-item>
              <q-separator />
              <q-item clickable v-close-popup @click="onLogout">
                <q-item-section avatar>
                  <q-icon name="logout" />
                </q-item-section>
                <q-item-section>Cerrar sesión</q-item-section>
              </q-item>
            </q-list>
          </q-menu>
        </q-btn>
      </q-toolbar>
    </q-header>

    <q-drawer v-model="leftDrawerOpen" show-if-above bordered>
      <q-list padding>
        <q-item-label header>Navegación</q-item-label>

        <q-item clickable to="/dashboard" exact>
          <q-item-section avatar>
            <q-icon name="dashboard" />
          </q-item-section>
          <q-item-section>Dashboard</q-item-section>
        </q-item>

        <q-item clickable to="/select-context">
          <q-item-section avatar>
            <q-icon name="business" />
          </q-item-section>
          <q-item-section>Contexto</q-item-section>
        </q-item>

        <q-separator spaced />

        <q-item-label header>Módulos</q-item-label>

        <q-item clickable to="/org/companies">
          <q-item-section avatar><q-icon name="domain" /></q-item-section>
          <q-item-section>ORG Compañías</q-item-section>
        </q-item>

        <q-item clickable to="/org/company-profile">
          <q-item-section avatar><q-icon name="apartment" /></q-item-section>
          <q-item-section>ORG Profile</q-item-section>
        </q-item>

        <q-item clickable to="/org/branches">
          <q-item-section avatar><q-icon name="store" /></q-item-section>
          <q-item-section>ORG Branches</q-item-section>
        </q-item>

        <q-item clickable to="/hr/positions">
          <q-item-section avatar><q-icon name="work" /></q-item-section>
          <q-item-section>HR Posiciones</q-item-section>
        </q-item>

        <q-item clickable to="/hr/employees">
          <q-item-section avatar><q-icon name="badge" /></q-item-section>
          <q-item-section>HR Empleados</q-item-section>
        </q-item>

        <q-item clickable to="/audit/bitacora" :disable="!canAuditRead">
          <q-item-section avatar><q-icon name="receipt_long" /></q-item-section>
          <q-item-section>Auditoría</q-item-section>
        </q-item>

        <q-separator spaced />

        <q-item-label header>SYNC</q-item-label>

        <q-item clickable to="/sync/offline">
          <q-item-section avatar><q-icon name="sync" /></q-item-section>
          <q-item-section>Offline</q-item-section>
        </q-item>

        <q-separator spaced />

        <q-item-label header>FUEL</q-item-label>

        <q-item clickable to="/fuel" :disable="!canFuelRead">
          <q-item-section avatar><q-icon name="local_gas_station" /></q-item-section>
          <q-item-section>Dashboard</q-item-section>
        </q-item>

        <q-item clickable to="/fuel/health" :disable="!canFuelRead">
          <q-item-section avatar><q-icon name="local_gas_station" /></q-item-section>
          <q-item-section>FUEL Health</q-item-section>
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
// import { Notify } from 'quasar'; // Si no se usa, quitar

import { useAuthStore } from 'src/stores/auth.store';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';
import { useUiStore } from 'src/stores/ui.store';

const router = useRouter();
const auth = useAuthStore();
const acl = useAclStore();
const ctx = useContextStore();
const ui = useUiStore();

// Seguridad: cargar estado UI y Contexto
ui.initFromStorage();
ctx.initFromStorage();

const leftDrawerOpen = ref(true);

const usernameLabel = computed(() => acl.snapshot?.username ?? 'Usuario');

const theme = computed({
  get: () => ui.theme,
  set: (v) => ui.setTheme(v),
});

const density = computed({
  get: () => ui.density,
  set: (v) => ui.setDensity(v),
});

const themeOptions = [
  { label: 'Sistema', value: 'system' },
  { label: 'Light', value: 'light' },
  { label: 'Dark', value: 'dark' },
];

const densityOptions = [
  { label: 'Std', value: 'comfortable' }, // "Std" para que quepa mejor si es btn-toggle
  { label: 'Compact', value: 'compact' },
];

const layoutClasses = computed(() => {
  return {
    'density-compact': ui.density === 'compact',
    'density-comfortable': ui.density === 'comfortable',
  };
});

const contextLabel = computed(() => {
  const c = ctx.activeCompanyId;
  if (!c) return null;
  const companyName = acl.companyName(c) ?? c;
  const b = ctx.activeBranchId;
  if (!b) return companyName;
  const branchName = acl.branchName(c, b) ?? b;
  return `${companyName} · ${branchName}`;
});

const canAuditRead = computed(() => {
  const companyId = ctx.activeCompanyId;
  if (!companyId) return false;
  return acl.hasPermission(companyId, 'audit.read');
});

const canFuelRead = computed(() => {
  const companyId = ctx.activeCompanyId;
  if (!companyId) return false;
  return acl.hasPermission(companyId, 'fuel.shift.read');
});

async function onLogout() {
  await auth.logout();
  await router.replace('/login');
}
</script>
