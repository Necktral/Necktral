<template>
  <q-page class="q-pa-md analytics-embed-page">
    <div class="row q-col-gutter-md items-start">
      <div class="col-12 col-lg-4">
        <q-card flat bordered>
          <q-card-section>
            <div class="text-h6">Analytics Engine</div>
            <div class="text-caption text-grey-7">
              Integración Quasar control-plane + Dash interaction-plane.
            </div>
          </q-card-section>
          <q-card-section class="q-gutter-md">
            <q-select
              v-model="workspaceCode"
              :options="workspaceOptions"
              emit-value
              map-options
              label="Workspace"
              :loading="loadingCatalog"
            />
            <q-input v-model.number="ttlSeconds" type="number" label="TTL token (segundos)" min="60" max="3600" />
            <q-btn
              color="primary"
              icon="open_in_new"
              label="Generar sesión embebida"
              :loading="loadingToken"
              @click="onGenerate"
            />
          </q-card-section>
          <q-card-section v-if="errorMessage">
            <q-banner dense rounded class="bg-red-1 text-negative">
              {{ errorMessage }}
            </q-banner>
          </q-card-section>
          <q-card-section v-if="embedMeta">
            <div class="text-caption text-grey-8">Expira: {{ embedMeta.expires_at }}</div>
            <div class="text-caption text-grey-8">TTL: {{ embedMeta.ttl_seconds }}s</div>
          </q-card-section>
        </q-card>
      </div>

      <div class="col-12 col-lg-8">
        <q-card flat bordered class="fit">
          <q-card-section class="q-pb-none">
            <div class="text-subtitle1">Vista embebida</div>
          </q-card-section>
          <q-card-section>
            <iframe
              v-if="embedUrl"
              class="analytics-embed-frame"
              :src="embedUrl"
              title="Analytics Engine"
              loading="lazy"
            />
            <div v-else class="text-grey-7">
              Genera un token para abrir el motor analítico embebido.
            </div>
          </q-card-section>
        </q-card>
      </div>
    </div>
  </q-page>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { fetchDashboardCatalog, fetchDashboardEmbedToken } from '../services/dashboard-v3.service';
import type { DashboardCatalogEntry, DashboardEmbedTokenResult } from '../types';

const loadingCatalog = ref(false);
const loadingToken = ref(false);
const errorMessage = ref('');
const workspaces = ref<DashboardCatalogEntry[]>([]);
const workspaceCode = ref('executive_v1');
const ttlSeconds = ref(600);
const embedUrl = ref('');
const embedMeta = ref<DashboardEmbedTokenResult | null>(null);

const workspaceOptions = computed(() =>
  workspaces.value.map((entry) => ({
    label: `${entry.title} (${entry.workspace_code})`,
    value: entry.workspace_code,
  })),
);

async function loadCatalog() {
  loadingCatalog.value = true;
  errorMessage.value = '';
  try {
    const payload = await fetchDashboardCatalog();
    workspaces.value = payload.results;
    if (!workspaceCode.value && payload.results.length > 0) {
      workspaceCode.value = payload.results[0]?.workspace_code ?? 'executive_v1';
    }
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : 'No se pudo cargar catálogo de workspaces.';
  } finally {
    loadingCatalog.value = false;
  }
}

async function onGenerate() {
  if (!workspaceCode.value) {
    errorMessage.value = 'Selecciona un workspace.';
    return;
  }
  loadingToken.value = true;
  errorMessage.value = '';
  try {
    const response = await fetchDashboardEmbedToken({
      workspace_code: workspaceCode.value,
      ttl_seconds: ttlSeconds.value,
    });
    embedMeta.value = response.results;
    embedUrl.value = response.results.embed_url;
    if (!embedUrl.value) {
      errorMessage.value = 'El backend no tiene DASH_EMBED_BASE_URL configurado.';
    }
  } catch (error: unknown) {
    errorMessage.value = error instanceof Error ? error.message : 'No se pudo generar token embebido.';
  } finally {
    loadingToken.value = false;
  }
}

onMounted(async () => {
  await loadCatalog();
});
</script>

<style scoped>
.analytics-embed-page {
  min-height: calc(100vh - 120px);
}

.analytics-embed-frame {
  width: 100%;
  min-height: 70vh;
  border: 0;
  border-radius: 8px;
  background: #fff;
}
</style>
