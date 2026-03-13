<template>
  <AppContainer>
    <AppPageHeader
      :title="`${labels.humanResources} · Puestos`"
      subtitle="API: GET /hr/positions/ · POST /hr/positions/ · PATCH /hr/positions/{id}/"
    >
      <template #badges>
        <q-badge outline color="primary">Empresa activa: {{ companyLabel }}</q-badge>
        <q-badge outline>Permiso lectura: hr.position.read</q-badge>
        <q-badge outline v-if="canCreate">Permiso creacion: hr.position.create</q-badge>
        <q-badge outline v-if="canUpdate">Permiso actualizacion: hr.position.update</q-badge>
        <q-badge outline v-if="canRoleMap">{{ labels.rolesAndPermissions }}: rbac.roles.read</q-badge>
      </template>

      <template #actions>
        <q-btn flat label="Recargar" :disable="loading" @click="reload" />
        <q-btn v-if="canCreate" color="primary" label="Nuevo puesto" @click="openCreate" />
      </template>
    </AppPageHeader>

    <q-card class="q-mt-md app-card">
      <q-card-section>
        <q-table
          :rows="rows"
          :columns="columns"
          row-key="id"
          :loading="loading"
          :rows-per-page-options="[10, 20, 50, 0]"
          :pagination="pagination"
          @request="onRequest"
        >
          <template #body-cell-actions="props">
            <q-td :props="props">
              <q-btn v-if="canUpdate" dense flat icon="edit" @click="openEdit(props.row)" />
              <q-btn v-if="canRoleMap" dense flat icon="security" @click="openRoleMap(props.row)">
                <q-tooltip>Configurar puesto y roles (reemplaza mapeo)</q-tooltip>
              </q-btn>
            </q-td>
          </template>
        </q-table>

        <q-banner v-if="errorMsg" class="q-mt-md" dense rounded>
          {{ errorMsg }}
        </q-banner>
      </q-card-section>
    </q-card>

    <!-- Create/Edit dialog -->
    <q-dialog v-model="editDialog">
      <q-card style="width: 520px; max-width: 92vw" class="app-card">
        <q-card-section class="row items-center justify-between">
          <div class="text-h6">{{ editingId ? 'Editar puesto' : 'Nuevo puesto' }}</div>
          <q-btn flat icon="close" v-close-popup />
        </q-card-section>

        <q-separator />

        <q-card-section>
          <q-form @submit.prevent="savePosition">
            <q-input
              v-model="form.name"
              label="Nombre"
              outlined
              :rules="[required]"
            />
            <div class="q-mt-sm" />
            <q-input v-model="form.code" label="Código" outlined />
            <div class="q-mt-sm" />
            <q-toggle v-model="form.is_active" label="Activo" />
            <div class="q-mt-md">
              <q-btn color="primary" type="submit" :loading="saving" label="Guardar" />
            </div>
          </q-form>
        </q-card-section>
      </q-card>
    </q-dialog>

    <!-- Role map dialog -->
    <q-dialog v-model="roleDialog">
      <q-card style="width: 720px; max-width: 96vw" class="app-card">
        <q-card-section class="row items-center justify-between">
          <div class="text-h6">Puesto y roles</div>
          <q-btn flat icon="close" v-close-popup />
        </q-card-section>

        <q-separator />

        <q-card-section>
          <q-banner class="q-mb-md" dense rounded>
            Este guardado <b>reemplaza</b> el mapeo actual. El backend desactiva todos y activa o
            crea los nuevos.
          </q-banner>

          <div class="text-caption text-grey-7 q-mb-sm">
            Puesto seleccionado: <b>{{ roleTarget?.name }}</b>
          </div>

          <div class="column q-gutter-sm">
            <div v-for="(m, idx) in roleMaps" :key="idx" class="row q-col-gutter-md items-center">
              <div class="col-7">
                <q-select
                  v-model="m.role_id"
                  :options="roleOptions"
                  label="Rol"
                  outlined
                  emit-value
                  map-options
                  :disable="rolesLoading"
                />
              </div>
              <div class="col-3">
                <q-select
                  v-model="m.scope_mode"
                  :options="scopeOptions"
                  label="Alcance"
                  outlined
                  emit-value
                  map-options
                />
              </div>
              <div class="col-2">
                <q-btn dense flat icon="delete" color="negative" @click="removeMap(idx)" />
              </div>
            </div>
          </div>

          <div class="q-mt-md row items-center q-gutter-sm">
            <q-btn flat label="Agregar" icon="add" @click="addMap" />
            <q-space />
            <q-btn
              color="primary"
              label="Guardar asignacion"
              :loading="rolesSaving"
              @click="saveRoleMap"
            />
          </div>

          <q-banner v-if="roleError" class="q-mt-md" dense rounded>
            {{ roleError }}
          </q-banner>
        </q-card-section>
      </q-card>
    </q-dialog>
  </AppContainer>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue';
import { useQuasar } from 'quasar';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';
import { extractErrorMessage } from 'src/core/http/errors';
import { BUSINESS_LABELS } from 'src/shared/ui/business-terms';
import { computeLimit } from 'src/shared/constants';
import { required } from 'src/shared/validators';
import { listRoles } from 'src/services/rbac.service';
import {
  createPosition,
  listPositions,
  patchPosition,
  setPositionRoleMaps,
  type PositionRow,
  type PositionRoleMapItem,
} from 'src/services/hr.service';
import AppContainer from 'src/ui/AppContainer.vue';
import AppPageHeader from 'src/ui/AppPageHeader.vue';
import type { QTableColumn } from 'quasar';

const $q = useQuasar();
const acl = useAclStore();
const ctx = useContextStore();
const labels = BUSINESS_LABELS;

const loading = ref(false);
const saving = ref(false);
const errorMsg = ref<string | null>(null);
const rows = ref<PositionRow[]>([]);
const pagination = ref({
  page: 1,
  rowsPerPage: 20,
  rowsNumber: 0,
});
const companyLabel = computed(
  () => acl.companyName(ctx.activeCompanyId) ?? ctx.activeCompanyId ?? '-',
);

const columns: QTableColumn[] = [
  { name: 'name', label: 'Nombre', field: 'name', align: 'left', sortable: true },
  { name: 'code', label: 'Código', field: 'code', align: 'left', sortable: true },
  { name: 'is_active', label: 'Activo', field: 'is_active', align: 'left', sortable: true },
  { name: 'actions', label: 'Acciones', field: 'actions', align: 'right' },
];

const canCreate = computed(
  () => !!ctx.activeCompanyId && acl.hasPermission(ctx.activeCompanyId, 'hr.position.create'),
);
const canUpdate = computed(
  () => !!ctx.activeCompanyId && acl.hasPermission(ctx.activeCompanyId, 'hr.position.update'),
);
const canRoleMap = computed(() => {
  if (!ctx.activeCompanyId) return false;
  return (
    acl.hasPermission(ctx.activeCompanyId, 'hr.position.roles.update') &&
    acl.hasPermission(ctx.activeCompanyId, 'rbac.roles.read')
  );
});

async function load(page = pagination.value.page, rowsPerPage = pagination.value.rowsPerPage) {
  loading.value = true;
  errorMsg.value = null;
  try {
    const limit = computeLimit(rowsPerPage);
    const offset = (page - 1) * limit;
    const data = await listPositions({ limit, offset });
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

// Create/Edit
const editDialog = ref(false);
const editingId = ref<number | null>(null);
const form = reactive<{ name: string; code: string; is_active: boolean }>({
  name: '',
  code: '',
  is_active: true,
});

function openCreate() {
  editingId.value = null;
  form.name = '';
  form.code = '';
  form.is_active = true;
  editDialog.value = true;
}

function openEdit(p: PositionRow) {
  editingId.value = p.id;
  form.name = p.name;
  form.code = p.code;
  form.is_active = p.is_active;
  editDialog.value = true;
}

async function savePosition() {
  saving.value = true;
  try {
    if (!form.name.trim()) return;

    if (!editingId.value) {
      await createPosition({ name: form.name.trim(), code: form.code ?? '' });
      $q.notify({ type: 'positive', message: 'Puesto creado' });
    } else {
      await patchPosition(editingId.value, {
        name: form.name.trim(),
        code: form.code ?? '',
        is_active: form.is_active,
      });
      $q.notify({ type: 'positive', message: 'Puesto actualizado' });
    }
    editDialog.value = false;
    await load();
  } catch (e: unknown) {
    $q.notify({ type: 'negative', message: extractErrorMessage(e) });
  } finally {
    saving.value = false;
  }
}

// Role maps
const roleDialog = ref(false);
const roleTarget = ref<PositionRow | null>(null);

const rolesLoading = ref(false);
const rolesSaving = ref(false);
const roleError = ref<string | null>(null);

const roleOptions = ref<{ label: string; value: number }[]>([]);
const scopeOptions = [
  { label: 'Sucursal', value: 'BRANCH' },
  { label: 'Empresa', value: 'COMPANY' },
];

const roleMaps = ref<PositionRoleMapItem[]>([]);

function addMap() {
  roleMaps.value.push({ role_id: 0, scope_mode: 'BRANCH' });
}
function removeMap(idx: number) {
  roleMaps.value.splice(idx, 1);
}

async function openRoleMap(p: PositionRow) {
  roleTarget.value = p;
  roleMaps.value = [{ role_id: 0, scope_mode: 'BRANCH' }];
  roleError.value = null;
  roleDialog.value = true;

  rolesLoading.value = true;
  try {
    const rolesData = await listRoles({ includeInactive: false, limit: 200, offset: 0 });
    roleOptions.value = rolesData.results.map((r) => ({ label: r.name, value: r.id }));
  } catch (e: unknown) {
    roleError.value = extractErrorMessage(e);
  } finally {
    rolesLoading.value = false;
  }
}

async function saveRoleMap() {
  if (!roleTarget.value) return;
  rolesSaving.value = true;
  roleError.value = null;

  try {
    const cleaned = roleMaps.value
      .filter((m) => m.role_id && m.role_id > 0)
      .map((m) => ({ role_id: m.role_id, scope_mode: m.scope_mode }));

    await setPositionRoleMaps(roleTarget.value.id, cleaned);
    $q.notify({ type: 'positive', message: 'Mapeo guardado (reemplazado)' });
    roleDialog.value = false;
  } catch (e: unknown) {
    roleError.value = extractErrorMessage(e);
  } finally {
    rolesSaving.value = false;
  }
}
</script>
