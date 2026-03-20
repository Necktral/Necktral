<template>
  <q-page>
    <AppContainer>
      <AppPageHeader
        title="Contabilidad · Tablero ejecutivo"
        subtitle="KPIs operativos y financieros derivados de la API contable canónica."
      >
        <template #badges>
          <q-badge outline class="q-mr-sm">Empresa: {{ companyLabel }}</q-badge>
          <q-badge outline>Sucursal: {{ branchLabel }}</q-badge>
        </template>
        <template #actions>
          <q-btn
            color="primary"
            icon="refresh"
            label="Actualizar"
            :loading="dashboard.loading"
            @click="reload"
          />
        </template>
      </AppPageHeader>

      <q-banner v-if="!canRead" dense rounded class="q-mt-md">
        No tienes permiso <b>accounting.dashboard.read</b> para ver este tablero.
      </q-banner>

      <q-banner v-else-if="dashboard.error" dense rounded class="q-mt-md bg-red-1 text-negative">
        {{ dashboard.error }}
      </q-banner>

      <div v-else class="q-mt-md">
        <div class="row q-col-gutter-md">
          <div class="col-12 col-sm-6 col-lg-3">
            <KpiCard
              label="Ingresos"
              :value="money(executiveSummary?.summary.revenue)"
              hint="Periodo actual"
            />
          </div>
          <div class="col-12 col-sm-6 col-lg-3">
            <KpiCard
              label="Gastos"
              :value="money(executiveSummary?.summary.expense)"
              hint="Periodo actual"
            />
          </div>
          <div class="col-12 col-sm-6 col-lg-3">
            <KpiCard
              label="Utilidad neta"
              :value="money(executiveSummary?.summary.net_income)"
              hint="Periodo actual"
            />
          </div>
          <div class="col-12 col-sm-6 col-lg-3">
            <KpiCard
              label="Posición de caja"
              :value="money(cashPosition?.summary.total_cash_position)"
              hint="Consolidado caja+bancos"
            />
          </div>
        </div>

        <div class="row q-col-gutter-md q-mt-sm">
          <div class="col-12 col-lg-6">
            <q-card class="app-card">
              <q-card-section>
                <div class="text-subtitle1">Salud de conciliación</div>
                <div class="text-caption text-grey-7">
                  Ratio de eventos operativos enlazados con accounting.
                </div>
              </q-card-section>
              <q-separator />
              <q-card-section>
                <div class="row q-col-gutter-sm">
                  <div class="col-4">
                    <div class="text-caption text-grey-7">Operativos</div>
                    <div class="text-subtitle1">
                      {{ reconciliationHealth?.summary.operational_events ?? 0 }}
                    </div>
                  </div>
                  <div class="col-4">
                    <div class="text-caption text-grey-7">Enlazados</div>
                    <div class="text-subtitle1">
                      {{ reconciliationHealth?.summary.linked_events ?? 0 }}
                    </div>
                  </div>
                  <div class="col-4">
                    <div class="text-caption text-grey-7">Pendientes</div>
                    <div class="text-subtitle1">
                      {{ reconciliationHealth?.summary.pending_events ?? 0 }}
                    </div>
                  </div>
                </div>
              </q-card-section>
            </q-card>
          </div>

          <div class="col-12 col-lg-6">
            <q-card class="app-card">
              <q-card-section>
                <div class="text-subtitle1">Tendencia mensual (utilidad neta)</div>
                <div class="text-caption text-grey-7">Últimos {{ monthlyTrends?.summary.months ?? 0 }} meses</div>
              </q-card-section>
              <q-separator />
              <q-card-section class="q-pt-sm">
                <q-list dense>
                  <q-item
                    v-for="row in monthlyTrendsRows"
                    :key="`${row.year}-${row.month}`"
                  >
                    <q-item-section>
                      {{ row.month }}/{{ row.year }}
                    </q-item-section>
                    <q-item-section side class="text-weight-medium">
                      {{ money(row.net_income) }}
                    </q-item-section>
                  </q-item>
                </q-list>
              </q-card-section>
            </q-card>
          </div>
        </div>
      </div>
    </AppContainer>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted } from 'vue';

import AppContainer from 'src/ui/AppContainer.vue';
import AppPageHeader from 'src/ui/AppPageHeader.vue';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

import KpiCard from '../components/KpiCard.vue';
import { useAccountingDashboardStore } from '../stores/accounting-dashboard.store';

const acl = useAclStore();
const ctx = useContextStore();
const dashboard = useAccountingDashboardStore();

const companyLabel = computed(
  () => acl.companyName(ctx.activeCompanyId) ?? ctx.activeCompanyId ?? '—',
);
const branchLabel = computed(
  () => acl.branchName(ctx.activeCompanyId, ctx.activeBranchId) ?? ctx.activeBranchId ?? '—',
);

const canRead = computed(() => {
  const companyId = ctx.activeCompanyId;
  if (!companyId) return false;
  return acl.hasPermission(companyId, 'accounting.dashboard.read');
});

const executiveSummary = computed(() => dashboard.executiveSummary);
const cashPosition = computed(() => dashboard.cashPosition);
const reconciliationHealth = computed(() => dashboard.reconciliationHealth);
const monthlyTrends = computed(() => dashboard.monthlyTrends);
const monthlyTrendsRows = computed(() => monthlyTrends.value?.results ?? []);

function money(value: string | number | null | undefined): string {
  const numeric = Number(value ?? 0);
  if (Number.isNaN(numeric)) return String(value ?? '0.00');
  return new Intl.NumberFormat('es-NI', { style: 'currency', currency: 'NIO' }).format(numeric);
}

async function reload() {
  await dashboard.load({ months: 6, refresh: true });
}

onMounted(async () => {
  if (canRead.value) {
    await dashboard.load({ months: 6 });
  }
});
</script>

