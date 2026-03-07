<template>
  <q-page>
    <AppContainer>
      <AppPageHeader title="FUEL · Dashboard" subtitle="Módulo Estación de Servicios (base)">
        <template #actions>
          <q-btn
            outline
            icon="monitor_heart"
            label="Health"
            :disable="!canFuelRead"
            to="/fuel/health"
          />
        </template>
      </AppPageHeader>

      <q-banner v-if="!canFuelRead" dense rounded class="q-mb-md">
        No tienes permiso <b>fuel.shift.read</b> o no hay contexto de company.
      </q-banner>

      <div v-else class="row q-col-gutter-md">
        <div class="col-12 col-md-6 col-lg-4">
          <q-card class="app-card">
            <q-card-section>
              <div class="text-subtitle1">Health</div>
              <div class="text-caption text-grey-7">Verifica conectividad y auth del módulo.</div>
            </q-card-section>
            <q-card-actions align="right">
              <q-btn flat label="Abrir" to="/fuel/health" />
            </q-card-actions>
          </q-card>
        </div>

        <div class="col-12 col-md-6 col-lg-4">
          <q-card class="app-card">
            <q-card-section>
              <div class="text-subtitle1">Operación</div>
              <div class="text-caption text-grey-7">
                Ciclo completo de la estación: turno → despacho → venta → cierre.
              </div>
            </q-card-section>
            <q-card-section class="text-caption">
              <ul class="q-pl-md q-my-none">
                <li>Turnos — apertura y cierre por sucursal</li>
                <li>Despachos — combustible (litros o galones)</li>
                <li>Ventas — pública / interna / empleado</li>
                <li>Anulaciones de venta</li>
                <li>Preferencias de UoM por usuario</li>
              </ul>
            </q-card-section>
          </q-card>
        </div>

        <div class="col-12 col-md-6 col-lg-4">
          <q-card class="app-card">
            <q-card-section>
              <div class="text-subtitle1">Integraciones</div>
              <div class="text-caption text-grey-7">
                El módulo Fuel se integra con el resto del kernel.
              </div>
            </q-card-section>
            <q-card-section class="text-caption">
              <ul class="q-pl-md q-my-none">
                <li>Inventarios — movimientos de stock por venta/anulación</li>
                <li>Facturación — FK a BillingDocument por venta fiscal</li>
                <li>RBAC — permisos <code>fuel.*</code> por sucursal</li>
                <li>Auditoría — eventos <code>FUEL_*</code> trazables</li>
              </ul>
            </q-card-section>
          </q-card>
        </div>
      </div>
    </AppContainer>
  </q-page>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import AppContainer from 'src/ui/AppContainer.vue';
import AppPageHeader from 'src/ui/AppPageHeader.vue';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const acl = useAclStore();
const ctx = useContextStore();

const canFuelRead = computed(() => {
  const companyId = ctx.activeCompanyId;
  if (!companyId) return false;
  return acl.hasPermission(companyId, 'fuel.shift.read');
});
</script>
