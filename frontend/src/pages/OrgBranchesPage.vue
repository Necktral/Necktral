<template>
  <AppContainer>
    <AppPageHeader
      title="ORG · Sucursales"
      subtitle="GET /org/branches/ · POST /org/branches/ · PATCH /org/branches/{id}/"
    >
      <template #badges>
        <q-badge outline color="primary">Company: {{ companyLabel }}</q-badge>
        <q-badge outline>Read: org.branch.read</q-badge>
        <q-badge outline v-if="canCreate">Create: org.branch.create</q-badge>
        <q-badge outline v-if="canUpdate">Update: org.branch.update</q-badge>
      </template>

      <template #actions>
        <q-btn
          flat
          label="Recargar"
          :disable="loading"
          @click="
            () => {
              void load();
            }
          "
        />
        <q-btn v-if="canCreate" color="primary" label="Nueva sucursal" @click="openCreate" />
      </template>
    </AppPageHeader>

    <div class="q-mt-md">
      <AppDataTable
        title="Listado"
        caption="Operación PC-first: tabla con filtro, badges de estado y acciones."
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
          <q-input v-model="filter" dense outlined placeholder="Buscar…" style="width: 280px" />
        </template>

        <template #body-cell-is_active="props">
          <q-td :props="props">
            <q-badge v-if="props.row.is_active" outline>ACTIVA</q-badge>
            <q-badge v-else outline color="negative">INACTIVA</q-badge>
          </q-td>
        </template>

        <template #body-cell-actions="props">
          <q-td :props="props" class="text-right">
            <q-btn v-if="canUpdate" dense flat icon="edit" @click="openEdit(props.row)" />
          </q-td>
        </template>
      </AppDataTable>

      <q-banner v-if="errorMsg" class="q-mt-md" dense rounded>
        {{ errorMsg }}
      </q-banner>
    </div>

    <!-- Create/Edit dialog -->
    <q-dialog v-model="editDialog">
      <q-card style="width: 720px; max-width: 96vw" class="app-card">
        <q-card-section class="row items-center justify-between">
          <div class="text-h6">{{ editingId ? 'Editar sucursal' : 'Nueva sucursal' }}</div>
          <q-btn flat icon="close" v-close-popup />
        </q-card-section>

        <q-separator />

        <q-card-section>
          <q-form @submit.prevent="saveBranch">
            <div class="row q-col-gutter-md">
              <div class="col-12 col-md-8">
                <q-input
                  v-model="form.name"
                  label="Nombre"
                  outlined
                  :rules="[(v) => !!String(v || '').trim() || 'Requerido']"
                />
              </div>
              <div class="col-12 col-md-4">
                <q-input v-model="form.code" label="Código" outlined hint="Ej: SN, CC01" />
              </div>
            </div>

            <div class="row q-col-gutter-md q-mt-sm">
              <div class="col-12 col-md-6">
                <q-input v-model="form.phone" label="Teléfono" outlined />
              </div>
              <div class="col-12 col-md-6">
                <q-input v-model="form.email" label="Email" outlined />
              </div>
            </div>

            <div class="q-mt-sm">
              <q-input v-model="form.address" label="Dirección" outlined type="textarea" autogrow />
            </div>

            <div class="q-mt-sm">
              <q-toggle v-model="form.is_active" label="Activa" />
              <div class="text-caption text-grey-7">
                En creación se ignora “Activa” (para evitar enviar campos no soportados); en edición
                sí se aplica.
              </div>
            </div>

            <q-banner v-if="dialogError" class="q-mt-md" dense rounded>
              {{ dialogError }}
            </q-banner>

            <div class="q-mt-md">
              <q-btn color="primary" type="submit" :loading="saving" label="Guardar" />
            </div>
          </q-form>
        </q-card-section>
      </q-card>
    </q-dialog>
  </AppContainer>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useQuasar } from 'quasar';
import type { QTableColumn } from 'quasar';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';
import { extractErrorMessage } from 'src/core/http/errors';
import { createBranch, listBranches, patchBranch, type BranchRow } from 'src/services/org.service';
import AppContainer from 'src/ui/AppContainer.vue';
import AppPageHeader from 'src/ui/AppPageHeader.vue';
import AppDataTable from 'src/ui/AppDataTable.vue';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();

const companyLabel = computed(
  () => acl.companyName(ctx.activeCompanyId) ?? ctx.activeCompanyId ?? '—',
);

const canCreate = computed(
  () => !!ctx.activeCompanyId && acl.hasPermission(ctx.activeCompanyId, 'org.branch.create'),
);
const canUpdate = computed(
  () => !!ctx.activeCompanyId && acl.hasPermission(ctx.activeCompanyId, 'org.branch.update'),
);

const loading = ref(false);
const saving = ref(false);
const errorMsg = ref<string | null>(null);

const filter = ref('');
const rows = ref<BranchRow[]>([]);
const pagination = ref({
  page: 1,
  rowsPerPage: 20,
  rowsNumber: 0,
});

const columns: QTableColumn[] = [
  { name: 'name', label: 'Nombre', field: 'name', align: 'left', sortable: true },
  { name: 'code', label: 'Código', field: 'code', align: 'left', sortable: true },
  { name: 'is_active', label: 'Estado', field: 'is_active', align: 'left', sortable: true },
  { name: 'address', label: 'Dirección', field: 'address', align: 'left' },
  { name: 'phone', label: 'Teléfono', field: 'phone', align: 'left' },
  { name: 'email', label: 'Email', field: 'email', align: 'left' },
  { name: 'actions', label: 'Acciones', field: 'actions', align: 'right' },
];

function computeLimit(rowsPerPage: number) {
  return rowsPerPage === 0 ? 200 : rowsPerPage;
}

async function load(page = pagination.value.page, rowsPerPage = pagination.value.rowsPerPage) {
  loading.value = true;
  errorMsg.value = null;
  try {
    const limit = computeLimit(rowsPerPage);
    const offset = (page - 1) * limit;
    const data = await listBranches({ limit, offset });
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

onMounted(() => {
  void load();
});

// dialog create/edit
const editDialog = ref(false);
const editingId = ref<number | null>(null);
const dialogError = ref<string | null>(null);

const form = reactive<{
  name: string;
  code: string;
  address: string;
  phone: string;
  email: string;
  is_active: boolean;
}>({
  name: '',
  code: '',
  address: '',
  phone: '',
  email: '',
  is_active: true,
});

function openCreate() {
  editingId.value = null;
  dialogError.value = null;
  Object.assign(form, {
    name: '',
    code: '',
    address: '',
    phone: '',
    email: '',
    is_active: true,
  });
  editDialog.value = true;
}

function openEdit(b: BranchRow) {
  editingId.value = b.id;
  dialogError.value = null;
  Object.assign(form, {
    name: b.name ?? '',
    code: b.code ?? '',
    address: b.address ?? '',
    phone: b.phone ?? '',
    email: b.email ?? '',
    is_active: Boolean(b.is_active),
  });
  editDialog.value = true;
}

async function saveBranch() {
  saving.value = true;
  dialogError.value = null;

  try {
    const name = String(form.name || '').trim();
    if (!name) return;

    if (!editingId.value) {
      if (!canCreate.value) {
        dialogError.value = 'No tienes permiso: org.branch.create';
        return;
      }

      const id = await createBranch({
        name,
        code: String(form.code || '').trim(),
        address: String(form.address || '').trim(),
        phone: String(form.phone || '').trim(),
        email: String(form.email || '').trim(),
      });

      $q.notify({ type: 'positive', message: `Sucursal creada (id=${id})` });
    } else {
      if (!canUpdate.value) {
        dialogError.value = 'No tienes permiso: org.branch.update';
        return;
      }

      await patchBranch(editingId.value, {
        name,
        code: String(form.code || '').trim(),
        address: String(form.address || '').trim(),
        phone: String(form.phone || '').trim(),
        email: String(form.email || '').trim(),
        is_active: Boolean(form.is_active),
      });

      $q.notify({ type: 'positive', message: 'Sucursal actualizada' });
    }

    editDialog.value = false;
    await load();
  } catch (e: unknown) {
    const msg = extractErrorMessage(e);
    dialogError.value = msg;
    $q.notify({ type: 'negative', message: msg });
  } finally {
    saving.value = false;
  }
}
</script>
