<template>
  <AppContainer>
    <AppPageHeader
      title="Auditoría · Bitácora"
      subtitle="GET /audit/bitacora/ · GET /audit/events/{event_id}/"
    />

    <q-banner v-if="!canRead" role="alert" dense rounded class="q-mb-md">
      No tienes permiso <b>audit.read</b> o no hay contexto de company.
    </q-banner>

    <q-card v-else class="app-card q-mb-md">
      <q-card-section>
        <div class="row q-col-gutter-md items-end">
          <div class="col-12 col-md-3">
            <q-input v-model="filters.event_type" label="event_type" outlined dense clearable />
          </div>

          <div class="col-12 col-md-3">
            <q-input v-model="filters.module" label="module" outlined dense clearable />
          </div>

          <div class="col-12 col-md-2">
            <q-select
              v-model="filters.method"
              label="method"
              outlined
              dense
              clearable
              :options="methodOptions"
            />
          </div>

          <div class="col-12 col-md-2">
            <q-input v-model="filters.reason_code" label="reason_code" outlined dense clearable />
          </div>

          <div class="col-12 col-md-2">
            <q-toggle v-model="filters.offline_mode" label="offline_mode" />
          </div>

          <div class="col-12 col-md-3">
            <q-input
              v-model="filters.actor_user_id"
              label="actor_user_id"
              outlined
              dense
              clearable
            />
          </div>

          <div class="col-12 col-md-3">
            <q-input v-model="filters.subject_type" label="subject_type" outlined dense clearable />
          </div>

          <div class="col-12 col-md-3">
            <q-input v-model="filters.subject_id" label="subject_id" outlined dense clearable />
          </div>

          <div class="col-12 col-md-3">
            <q-input
              v-model="filters.path_contains"
              label="path_contains"
              outlined
              dense
              clearable
            />
          </div>

          <div class="col-12 col-md-3">
            <q-input v-model="filters.ip" label="ip" outlined dense clearable />
          </div>

          <div class="col-12 col-md-3">
            <q-input v-model="filters.device_id" label="device_id" outlined dense clearable />
          </div>

          <div class="col-12 col-md-3">
            <q-input
              v-model="filters.after"
              label="after (ISO o YYYY-MM-DD)"
              outlined
              dense
              clearable
            />
          </div>

          <div class="col-12 col-md-3">
            <q-input
              v-model="filters.before"
              label="before (ISO o YYYY-MM-DD)"
              outlined
              dense
              clearable
            />
          </div>

          <div class="col-12 col-md-4">
            <q-toggle v-model="filters.include_integrity" label="include_integrity (más pesado)" />
          </div>

          <div class="col-12 col-md-8 row justify-end q-gutter-sm">
            <q-btn outline label="Limpiar" @click="clearFilters" />
            <q-btn outline label="Recargar" @click="reloadFirstPage" :loading="loading" />
          </div>
        </div>
      </q-card-section>
    </q-card>

    <AppDataTable
      v-if="canRead"
      title="Eventos"
      caption="Listado por cursor. Click en una fila para ver detalle."
      :rows="rows"
      :columns="columns"
      row-key="event_id"
      :loading="loading"
      @row-click="onRowClick"
    />

    <div v-if="canRead" class="row q-mt-md q-gutter-sm">
      <q-btn outline label="Anterior" :disable="!cursorPrev || loading" @click="loadPrev" />
      <q-btn outline label="Siguiente" :disable="!cursorNext || loading" @click="loadNext" />
      <q-space />
      <q-select
        v-model="filters.page_size"
        :options="[25, 50, 100, 200]"
        label="page_size"
        dense
        outlined
        style="width: 140px"
        @update:model-value="reloadFirstPage"
      />
    </div>

    <q-dialog v-model="detailDialog">
      <q-card style="width: 920px; max-width: 96vw" class="app-card">
        <q-card-section class="row items-center justify-between">
          <div class="text-h6">Detalle de evento</div>
          <q-btn flat icon="close" v-close-popup />
        </q-card-section>

        <q-separator />

        <q-card-section v-if="detailLoading">
          <q-linear-progress indeterminate />
        </q-card-section>

        <q-card-section v-else>
          <div class="row q-col-gutter-md">
            <div class="col-12 col-md-6">
              <q-input :model-value="detail?.event_id ?? ''" label="event_id" outlined readonly />
            </div>
            <div class="col-12 col-md-6">
              <q-input
                :model-value="detail?.timestamp_server ?? ''"
                label="timestamp_server"
                outlined
                readonly
              />
            </div>

            <div class="col-12 col-md-4">
              <q-input
                :model-value="detail?.event_type ?? ''"
                label="event_type"
                outlined
                readonly
              />
            </div>
            <div class="col-12 col-md-4">
              <q-input
                :model-value="detail?.reason_code ?? ''"
                label="reason_code"
                outlined
                readonly
              />
            </div>
            <div class="col-12 col-md-4">
              <q-input
                :model-value="String(detail?.actor_user ?? '')"
                label="actor_user"
                outlined
                readonly
              />
            </div>

            <div class="col-12 col-md-4">
              <q-input
                :model-value="detail?.module ?? ''"
                label="module"
                outlined
                readonly
              />
            </div>
            <div class="col-12 col-md-2">
              <q-input
                :model-value="detail?.method ?? ''"
                label="method"
                outlined
                readonly
              />
            </div>
            <div class="col-12 col-md-6">
              <q-input :model-value="detail?.path ?? ''" label="path" outlined readonly />
            </div>

            <div class="col-12 col-md-4">
              <q-input
                :model-value="detail?.subject_type ?? ''"
                label="subject_type"
                outlined
                readonly
              />
            </div>
            <div class="col-12 col-md-8">
              <q-input
                :model-value="detail?.subject_id ?? ''"
                label="subject_id"
                outlined
                readonly
              />
            </div>

            <div class="col-12 col-md-4">
              <q-input
                :model-value="detail?.ip_server_seen ?? ''"
                label="ip_server_seen"
                outlined
                readonly
              />
            </div>
            <div class="col-12 col-md-4">
              <q-input
                :model-value="detail?.device_id ?? ''"
                label="device_id"
                outlined
                readonly
              />
            </div>
            <div class="col-12 col-md-4">
              <q-badge outline>
                offline_mode: {{ detail?.offline_mode ? 'true' : 'false' }}
              </q-badge>
            </div>

            <div class="col-12">
              <div class="text-caption text-grey-7 q-mb-xs">metadata</div>
              <pre class="json-box">{{ pretty(detail?.metadata) }}</pre>
            </div>

            <div v-if="detail?.integrity" class="col-12">
              <div class="text-caption text-grey-7 q-mb-xs">integrity</div>
              <pre class="json-box">{{ pretty(detail?.integrity) }}</pre>
            </div>
          </div>

          <q-banner v-if="detailError" role="alert" class="q-mt-md" dense rounded>
            {{ detailError }}
          </q-banner>
        </q-card-section>
      </q-card>
    </q-dialog>
  </AppContainer>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, reactive, ref, watch } from 'vue';
import { useQuasar } from 'quasar';
import { isAxiosError } from 'axios';
import type { QTableColumn } from 'quasar';

import AppContainer from 'src/ui/AppContainer.vue';
import AppPageHeader from 'src/ui/AppPageHeader.vue';
import AppDataTable from 'src/ui/AppDataTable.vue';

import { extractErrorMessage } from 'src/core/http/errors';
import {
  listAuditEvents,
  getAuditEvent,
  type AuditEventRow,
  type AuditEventDetail,
  type AuditListParams,
} from 'src/services/audit.service';

import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const canRead = computed(() => {
  const companyId = ctx.activeCompanyId;
  if (!companyId) return false;
  return acl.hasPermission(companyId, 'audit.read');
});

const methodOptions = ['GET', 'POST', 'PATCH', 'PUT', 'DELETE'];

type Filters = {
  event_type: string;
  reason_code: string;
  module: string;
  method: string | null;

  actor_user_id: string;
  subject_type: string;
  subject_id: string;

  device_id: string;
  ip: string;
  path_contains: string;

  offline_mode: boolean;
  after: string;
  before: string;

  include_integrity: boolean;
  page_size: number;
};

const filters = reactive<Filters>({
  event_type: '',
  reason_code: '',
  module: '',
  method: null,

  actor_user_id: '',
  subject_type: '',
  subject_id: '',

  device_id: '',
  ip: '',
  path_contains: '',

  offline_mode: false,
  after: '',
  before: '',

  include_integrity: false,
  page_size: 50,
});

const loading = ref(false);
const rows = ref<AuditEventRow[]>([]);
const cursorNext = ref<string | null>(null);
const cursorPrev = ref<string | null>(null);

const columns: QTableColumn<AuditEventRow>[] = [
  {
    name: 'timestamp_server',
    label: 'timestamp',
    field: 'timestamp_server',
    align: 'left',
    sortable: false,
  },
  { name: 'event_type', label: 'event_type', field: 'event_type', align: 'left', sortable: false },
  { name: 'module', label: 'module', field: 'module', align: 'left', sortable: false },
  {
    name: 'actor_user',
    label: 'actor',
    field: (r) => r.actor_user,
    align: 'left',
    sortable: false,
  },
  {
    name: 'subject',
    label: 'subject',
    field: (r) => `${r.subject_type ?? ''}:${r.subject_id ?? ''}`,
    align: 'left',
    sortable: false,
  },
  { name: 'method', label: 'method', field: 'method', align: 'left', sortable: false },
  { name: 'path', label: 'path', field: 'path', align: 'left', sortable: false },
  { name: 'reason_code', label: 'reason', field: 'reason_code', align: 'left', sortable: false },
  {
    name: 'offline_mode',
    label: 'offline',
    field: (r) => (r.offline_mode ? 'Y' : 'N'),
    align: 'left',
    sortable: false,
  },
  {
    name: 'event_id',
    label: 'event_id',
    field: 'event_id',
    align: 'left',
    sortable: false,
  },
];

function pretty(v: unknown) {
  try {
    return JSON.stringify(v ?? null, null, 2);
  } catch {
    return String(v);
  }
}

function cursorFromUrl(url: string | null) {
  if (!url) return null;
  try {
    const u = new URL(url);
    return u.searchParams.get('cursor');
  } catch {
    const idx = url.indexOf('cursor=');
    if (idx === -1) return null;
    return decodeURIComponent(url.substring(idx + 7).split('&')[0] ?? '');
  }
}

async function loadPage(cursor?: string | null) {
  loading.value = true;
  try {
    const params: AuditListParams = {
      page_size: filters.page_size,
    };

    if (cursor) params.cursor = cursor;
    if (filters.event_type) params.event_type = filters.event_type;
    if (filters.reason_code) params.reason_code = filters.reason_code;
    if (filters.module) params.module = filters.module;
    if (filters.method) params.method = filters.method;

    if (filters.actor_user_id) params.actor_user_id = filters.actor_user_id;
    if (filters.subject_type) params.subject_type = filters.subject_type;
    if (filters.subject_id) params.subject_id = filters.subject_id;

    if (filters.device_id) params.device_id = filters.device_id;
    if (filters.ip) params.ip = filters.ip;
    if (filters.path_contains) params.path_contains = filters.path_contains;

    if (filters.offline_mode) params.offline_mode = true;
    if (filters.after) params.after = filters.after;
    if (filters.before) params.before = filters.before;
    if (filters.include_integrity) params.include_integrity = true;

    const data = await listAuditEvents(params);

    rows.value = data.results;
    cursorNext.value = cursorFromUrl(data.next);
    cursorPrev.value = cursorFromUrl(data.previous);
  } catch (e: unknown) {
    if (isAxiosError(e) && e.response?.status === 403) {
      $q.notify({ type: 'negative', message: '403: falta permiso audit.read o contexto.' });
    } else {
      $q.notify({ type: 'negative', message: extractErrorMessage(e) });
    }
  } finally {
    loading.value = false;
  }
}

function reloadFirstPage() {
  void loadPage(null);
}

function loadNext() {
  if (!cursorNext.value) return;
  void loadPage(cursorNext.value);
}

function loadPrev() {
  if (!cursorPrev.value) return;
  void loadPage(cursorPrev.value);
}

function clearFilters() {
  filters.event_type = '';
  filters.reason_code = '';
  filters.module = '';
  filters.method = null;

  filters.actor_user_id = '';
  filters.subject_type = '';
  filters.subject_id = '';

  filters.device_id = '';
  filters.ip = '';
  filters.path_contains = '';

  filters.offline_mode = false;
  filters.after = '';
  filters.before = '';

  filters.include_integrity = false;
  reloadFirstPage();
}

let t: number | null = null;
function debouncedReload() {
  if (t) window.clearTimeout(t);
  t = window.setTimeout(() => reloadFirstPage(), 350);
}

onBeforeUnmount(() => {
  if (t) window.clearTimeout(t);
});

watch(
  () => ({
    ...filters,
    page_size: filters.page_size,
  }),
  () => {
    debouncedReload();
  },
  { deep: true },
);

onMounted(() => {
  if (!canRead.value) return;
  void loadPage(null);
});

const detailDialog = ref(false);
const detailLoading = ref(false);
const detailError = ref<string | null>(null);
const detail = ref<AuditEventDetail | null>(null);

async function onRowClick(_evt: unknown, row: AuditEventRow) {
  detailDialog.value = true;
  detailLoading.value = true;
  detailError.value = null;
  detail.value = null;

  try {
    detail.value = await getAuditEvent(row.event_id);
  } catch (e: unknown) {
    if (isAxiosError(e)) {
      const status = e.response?.status;
      if (status === 403) detailError.value = '403: falta permiso audit.read o contexto.';
      else detailError.value = `Error (${status ?? '??'}): no se pudo cargar el detalle.`;
    } else {
      detailError.value = extractErrorMessage(e);
    }
  } finally {
    detailLoading.value = false;
  }
}
</script>

<style scoped>
.json-box {
  background: rgba(0, 0, 0, 0.06);
  padding: 12px;
  border-radius: 8px;
  overflow: auto;
  max-height: 320px;
  font-family:
    ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, 'Liberation Mono', 'Courier New',
    monospace;
  font-size: 12px;
}
</style>
