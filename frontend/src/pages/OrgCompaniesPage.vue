<template>
  <AppContainer>
    <AppPageHeader
      :title="`${labels.organization} · Empresas`"
      subtitle="API: GET /org/companies/ · POST /org/companies/"
    >
      <template #badges>
        <q-badge outline color="primary">Empresa activa: {{ companyLabel }}</q-badge>
        <q-badge outline>Permiso lectura: org.company.read</q-badge>
        <q-badge outline v-if="canCreate">Permiso creacion: org.company.create</q-badge>
        <q-badge outline>Total: {{ totalRows }}</q-badge>
      </template>

      <template #actions>
        <q-btn flat label="Recargar" :disable="loading" @click="reload" />
        <q-btn v-if="canCreate" color="primary" label="Nueva empresa" @click="openCreate" />
      </template>
    </AppPageHeader>

    <div class="q-mt-md">
      <AppDataTable
        title="Listado"
        caption="Vista operativa simetrica: filtro, estado y accion. Crear empresa registra auditoria y replica accesos del creador."
        :rows="rows"
        :columns="columns"
        row-key="id"
        :loading="loading"
        :rows-per-page-options="[10, 20, 50, 0]"
        :filter="filter"
        :pagination="pagination"
        @request="onRequest"
      >
        <template #toolbar>
          <q-input
            v-model="filter"
            dense
            outlined
            placeholder="Buscar empresa..."
            style="width: 280px"
          />
        </template>

        <template #body-cell-is_active="props">
          <q-td :props="props">
            <q-badge v-if="props.row.is_active" outline>ACTIVA</q-badge>
            <q-badge v-else outline color="negative">INACTIVA</q-badge>
          </q-td>
        </template>

        <template #body-cell-actions="props">
          <q-td :props="props" class="text-right">
            <q-btn
              dense
              flat
              icon="arrow_forward"
              @click="switchToCompany(props.row.id)"
              title="Cambiar contexto operativo"
            />
          </q-td>
        </template>
      </AppDataTable>

      <q-banner v-if="errorMsg" class="q-mt-md" dense rounded>
        {{ errorMsg }}
      </q-banner>
    </div>

    <q-dialog v-model="createDialog">
      <q-card style="width: 820px; max-width: 96vw" class="app-card">
        <q-card-section class="row items-center justify-between">
          <div class="text-h6">Nueva empresa</div>
          <q-btn flat icon="close" v-close-popup />
        </q-card-section>

        <q-separator />

        <q-card-section>
          <q-form @submit.prevent="createOne">
            <div class="text-subtitle2">Identidad</div>
            <q-separator class="q-my-sm" />

            <div class="row q-col-gutter-md">
              <div class="col-12 col-md-6">
                <q-input
                  v-model="form.name"
                  label="Nombre (interno)"
                  outlined
                  :rules="[required]"
                />
              </div>
              <div class="col-12 col-md-6">
                <q-input v-model="form.code" label="Código" outlined hint="Opcional" />
              </div>
            </div>

            <div class="row q-col-gutter-md q-mt-sm">
              <div class="col-12 col-md-8">
                <q-input v-model="form.legal_name" label="Razón social" outlined />
              </div>
              <div class="col-12 col-md-4">
                <q-input v-model="form.tax_id" label="RIF / Tax ID" outlined />
              </div>
            </div>

            <div class="text-subtitle2 q-mt-md">Contacto</div>
            <q-separator class="q-my-sm" />

            <div class="row q-col-gutter-md">
              <div class="col-12 col-md-6">
                <q-input v-model="form.phone" label="Teléfono" outlined />
              </div>
              <div class="col-12 col-md-6">
                <q-input v-model="form.email" label="Email" outlined />
              </div>
              <div class="col-12">
                <q-input
                  v-model="form.address"
                  label="Dirección"
                  outlined
                  type="textarea"
                  autogrow
                />
              </div>
            </div>

            <q-banner v-if="dialogError" class="q-mt-md" dense rounded>
              {{ dialogError }}
            </q-banner>

            <div class="q-mt-md">
              <q-btn color="primary" type="submit" :loading="saving" label="Crear empresa" />
            </div>
          </q-form>
        </q-card-section>
      </q-card>
    </q-dialog>
  </AppContainer>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { useQuasar } from 'quasar';
import type { QTableColumn } from 'quasar';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';
import { extractErrorMessage } from 'src/core/http/errors';
import { BUSINESS_LABELS, UI_ROUTE_PATHS } from 'src/shared/ui/business-terms';
import { computeLimit } from 'src/shared/constants';
import { required } from 'src/shared/validators';
import { createCompany, listCompanies, type CompanyRow } from 'src/services/org.service';
import AppContainer from 'src/ui/AppContainer.vue';
import AppPageHeader from 'src/ui/AppPageHeader.vue';
import AppDataTable from 'src/ui/AppDataTable.vue';

const $q = useQuasar();
const router = useRouter();
const acl = useAclStore();
const ctx = useContextStore();
const labels = BUSINESS_LABELS;

const companyLabel = computed(
  () => acl.companyName(ctx.activeCompanyId) ?? ctx.activeCompanyId ?? '—',
);

const canCreate = computed(
  () => !!ctx.activeCompanyId && acl.hasPermission(ctx.activeCompanyId, 'org.company.create'),
);

const loading = ref(false);
const saving = ref(false);
const errorMsg = ref<string | null>(null);
const filter = ref('');
const rows = ref<CompanyRow[]>([]);
const pagination = ref({
  page: 1,
  rowsPerPage: 20,
  rowsNumber: 0,
});

const totalRows = computed(() => pagination.value.rowsNumber || rows.value.length);

const columns: QTableColumn[] = [
  { name: 'name', label: 'Nombre', field: 'name', align: 'left', sortable: true },
  { name: 'code', label: 'Código', field: 'code', align: 'left', sortable: true },
  { name: 'legal_name', label: 'Razón social', field: 'legal_name', align: 'left' },
  { name: 'tax_id', label: 'Tax ID', field: 'tax_id', align: 'left' },
  { name: 'is_active', label: 'Estado', field: 'is_active', align: 'left', sortable: true },
  { name: 'actions', label: 'Acciones', field: 'actions', align: 'right' },
];

async function load(page = pagination.value.page, rowsPerPage = pagination.value.rowsPerPage) {
  loading.value = true;
  errorMsg.value = null;
  try {
    const limit = computeLimit(rowsPerPage);
    const offset = (page - 1) * limit;
    const data = await listCompanies({ limit, offset });
    rows.value = data.results;
    pagination.value = {
      ...pagination.value,
      page,
      rowsPerPage,
      rowsNumber: data.count,
    };
  } catch (e: unknown) {
    errorMsg.value = extractErrorMessage(e);
  } finally {
    loading.value = false;
  }
}

function onRequest(props: { pagination: { page: number; rowsPerPage: number } }) {
  const { page, rowsPerPage } = props.pagination;
  void load(page, rowsPerPage);
}

function reload() {
  void load();
}

onMounted(() => {
  void load();
});

// Create dialog
const createDialog = ref(false);
const dialogError = ref<string | null>(null);

const form = reactive({
  name: '',
  code: '',
  legal_name: '',
  tax_id: '',
  address: '',
  phone: '',
  email: '',
});

function openCreate() {
  if (!canCreate.value) {
    $q.notify({ type: 'negative', message: 'No tienes permiso: org.company.create' });
    return;
  }
  dialogError.value = null;
  Object.assign(form, {
    name: '',
    code: '',
    legal_name: '',
    tax_id: '',
    address: '',
    phone: '',
    email: '',
  });
  createDialog.value = true;
}

async function createOne() {
  saving.value = true;
  dialogError.value = null;
  try {
    const name = String(form.name || '').trim();
    if (!name) return;

    const id = await createCompany({
      name,
      code: String(form.code || '').trim(),
      legal_name: String(form.legal_name || '').trim(),
      tax_id: String(form.tax_id || '').trim(),
      address: String(form.address || '').trim(),
      phone: String(form.phone || '').trim(),
      email: String(form.email || '').trim(),
    });

    $q.notify({ type: 'positive', message: `Empresa creada (id=${id})` });
    createDialog.value = false;

    // Recargar control de acceso y listado para evitar refresco manual.
    await acl.loadAcl();
    await load();

    // Cambiar contexto a la empresa nueva y llevar al perfil
    ctx.setContext(String(id), null);
    await router.push(UI_ROUTE_PATHS.organizationCompanyProfile);
  } catch (e: unknown) {
    const msg = extractErrorMessage(e);
    dialogError.value = msg;
    $q.notify({ type: 'negative', message: msg });
  } finally {
    saving.value = false;
  }
}

async function switchToCompany(companyId: number) {
  ctx.setContext(String(companyId), null);
  await router.push('/dashboard');
}
</script>
