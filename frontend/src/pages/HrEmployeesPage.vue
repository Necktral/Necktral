<template>
  <AppContainer>
    <AppPageHeader
      :title="`${labels.humanResources} · Empleados`"
      subtitle="API: GET/POST /hr/employees/ · PATCH /hr/employees/{id}/ · POST /hr/employees/{id}/assignments/ · POST /.../end/ · POST /hr/employees/{id}/provision-user/ · POST /hr/employees/{id}/reset-temp-password/ · POST /hr/employees/{id}/revoke-access/"
    >
      <template #badges>
        <q-badge outline color="primary">Empresa activa: {{ companyLabel }}</q-badge>
        <q-badge outline>Permiso lectura: hr.employee.read</q-badge>
        <q-badge outline v-if="canCreate">Permiso creacion: hr.employee.create</q-badge>
        <q-badge outline v-if="canUpdate">Permiso actualizacion: hr.employee.update</q-badge>
        <q-badge outline v-if="canAssign">Permiso asignacion: hr.assignment.create</q-badge>
        <q-badge outline v-if="canEndAssign">Permiso cierre asignacion: hr.assignment.end</q-badge>
        <q-badge outline v-if="canProvisionUser">
          {{ labels.identityAndAccess }}: iam.users.create
        </q-badge>
        <q-badge outline v-if="canProvisionUser">
          Revocacion {{ labels.identityAndAccess }}: iam.users.create
        </q-badge>
      </template>

      <template #actions>
        <q-btn flat label="Recargar" :disable="loading" @click="reload" />
        <q-btn v-if="canCreate" color="primary" label="Nuevo empleado" @click="openCreate" />
      </template>
    </AppPageHeader>

    <div class="q-mt-md">
      <HrEmployeesTableWidget
        :rows="rows"
        :columns="columns"
        :loading="loading"
        :pagination="pagination"
        :filter="filter"
        :error-msg="errorMsg"
        :can-update="canUpdate"
        :can-assign="canAssign"
        :can-end-assign="canEndAssign"
        :can-provision-user="canProvisionUser"
        @request="onRequest"
        @update:filter="filter = $event"
        @edit="openEdit"
        @assign="openAssign"
        @end="openEnd"
        @provision="openProvision"
        @revoke="openRevokeAccess"
        @reset="openResetTempPassword"
      />
    </div>

    <!-- Create/Edit dialog -->
    <q-dialog v-model="editDialog">
      <q-card style="width: 760px; max-width: 96vw" class="app-card">
        <q-card-section class="row items-center justify-between">
          <div class="text-h6">{{ editingId ? 'Editar empleado' : 'Nuevo empleado' }}</div>
          <q-btn flat icon="close" v-close-popup />
        </q-card-section>

        <q-separator />

        <q-card-section>
          <q-form @submit.prevent="saveEmployee">
            <div class="row q-col-gutter-md">
              <div class="col-12 col-md-4">
                <q-input v-model="form.employee_code" label="Código" outlined />
              </div>
              <div class="col-12 col-md-4">
                <q-input
                  v-model="form.first_name"
                  label="Nombres"
                  outlined
                  :rules="[(v) => !!String(v || '').trim() || 'Requerido']"
                />
              </div>
              <div class="col-12 col-md-4">
                <q-input v-model="form.last_name" label="Apellidos" outlined />
              </div>
            </div>

            <div class="row q-col-gutter-md q-mt-sm">
              <div class="col-12 col-md-6">
                <q-input v-model="form.phone" label="Teléfono" outlined />
              </div>
              <div class="col-12 col-md-6">
                <q-input
                  v-model="form.email"
                  label="Email"
                  type="email"
                  outlined
                  :rules="[
                    (v: string) =>
                      !v || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v) || 'Email inválido',
                  ]"
                />
              </div>
            </div>

            <div class="q-mt-sm" v-if="editingId">
              <q-toggle v-model="form.is_active" label="Activo" />
            </div>

            <div class="q-mt-md">
              <q-btn color="primary" type="submit" :loading="saving" label="Guardar" />
            </div>
          </q-form>
        </q-card-section>
      </q-card>
    </q-dialog>

    <!-- Assign dialog -->
    <q-dialog v-model="assignDialog">
      <q-card style="width: 760px; max-width: 96vw" class="app-card">
        <q-card-section class="row items-center justify-between">
          <div class="text-h6">Asignar puesto</div>
          <q-btn flat icon="close" v-close-popup />
        </q-card-section>

        <q-separator />

        <q-card-section>
          <div class="text-caption text-grey-7">
            Empleado: {{ assignTarget?.first_name }} {{ assignTarget?.last_name }}
          </div>

          <q-form class="q-mt-sm" @submit.prevent="doAssign">
            <div class="row q-col-gutter-md">
              <div class="col-12 col-md-6">
                <q-select
                  v-model="assignForm.position_id"
                  :options="positionOptions"
                  label="Puesto"
                  outlined
                  emit-value
                  map-options
                  :loading="positionsLoading"
                />
              </div>

              <div class="col-12 col-md-6">
                <q-select
                  v-model="assignForm.branch_id"
                  :options="branchOptions"
                  label="Sucursal (opcional)"
                  outlined
                  emit-value
                  map-options
                  clearable
                  :loading="branchesLoading"
                />
              </div>
            </div>

            <q-banner v-if="assignError" class="q-mt-md" dense rounded>
              {{ assignError }}
            </q-banner>

            <div class="q-mt-md">
              <q-btn color="primary" type="submit" :loading="assignSaving" label="Asignar" />
            </div>
          </q-form>
        </q-card-section>
      </q-card>
    </q-dialog>

    <!-- End assignment dialog -->
    <q-dialog v-model="endDialog">
      <q-card style="width: 760px; max-width: 96vw" class="app-card">
        <q-card-section class="row items-center justify-between">
          <div class="text-h6">Terminar asignación</div>
          <q-btn flat icon="close" v-close-popup />
        </q-card-section>

        <q-separator />

        <q-card-section>
          <div class="text-caption text-grey-7">
            Empleado: {{ endTarget?.first_name }} {{ endTarget?.last_name }}
          </div>

          <q-form class="q-mt-sm" @submit.prevent="doEnd">
            <q-select
              v-model="endAssignmentId"
              :options="endAssignmentOptions"
              label="Assignment ID"
              outlined
              emit-value
              map-options
              :disable="!endAssignmentOptions.length"
            />

            <q-banner v-if="!endAssignmentOptions.length" class="q-mt-md" dense rounded>
              No hay asignaciones activas en el resumen (recarga si acabas de asignar).
            </q-banner>

            <q-banner v-if="endError" class="q-mt-md" dense rounded>
              {{ endError }}
            </q-banner>

            <div class="q-mt-md">
              <q-btn color="negative" type="submit" :loading="endSaving" label="Terminar" />
            </div>
          </q-form>
        </q-card-section>
      </q-card>
    </q-dialog>

    <!-- Provision user dialog -->
    <q-dialog v-model="provDialog">
      <q-card style="width: 760px; max-width: 96vw" class="app-card">
        <q-card-section class="row items-center justify-between">
          <div class="text-h6">Provisionar acceso</div>
          <q-btn flat icon="close" v-close-popup />
        </q-card-section>

        <q-separator />

        <q-card-section>
          <div class="text-caption text-grey-7">
            Empleado: {{ provTarget?.first_name }} {{ provTarget?.last_name }}
          </div>

          <q-form class="q-mt-sm" @submit.prevent="doProvision">
            <div class="row q-col-gutter-md">
              <div class="col-12 col-md-6">
                <q-input
                  v-model="provForm.username"
                  label="Username"
                  outlined
                  :rules="[(v) => !!String(v || '').trim() || 'Requerido']"
                />
              </div>
              <div class="col-12 col-md-6">
                <q-input v-model="provForm.email" label="Email (opcional)" outlined />
              </div>
            </div>

            <div class="q-mt-sm">
              <q-toggle v-model="provForm.manualPass" label="Definir contraseña manual" />
            </div>

            <div class="q-mt-sm" v-if="provForm.manualPass">
              <q-input
                v-model="provForm.temp_password"
                label="Contraseña provisional"
                outlined
                type="password"
              />
            </div>

            <q-banner v-if="provError" class="q-mt-md" dense rounded>
              {{ provError }}
            </q-banner>

            <div class="q-mt-md">
              <q-btn color="primary" type="submit" :loading="provSaving" label="Provisionar" />
            </div>
          </q-form>
        </q-card-section>
      </q-card>
    </q-dialog>

    <!-- Provision result dialog -->
    <q-dialog v-model="provResultDialog">
      <q-card style="width: 560px; max-width: 96vw" class="app-card">
        <q-card-section class="row items-center justify-between">
          <div class="text-h6">Credenciales provisionales</div>
          <q-btn flat icon="close" v-close-popup />
        </q-card-section>

        <q-separator />

        <q-card-section>
          <div class="row q-col-gutter-md">
            <div class="col-12">
              <q-input
                :model-value="provResult?.username || ''"
                label="Nombre de usuario"
                outlined
                readonly
              />
            </div>
            <div class="col-12">
              <q-input
                :model-value="provResult?.temp_password || ''"
                label="Contraseña provisional"
                outlined
                readonly
              />
            </div>
          </div>

          <div class="q-mt-md">
            <q-btn flat icon="content_copy" label="Copiar contraseña" @click="copyProvPass" />
          </div>

          <q-banner class="q-mt-md" dense rounded>
            Guarda esta contraseña ahora: no se volverá a mostrar.
          </q-banner>
        </q-card-section>
      </q-card>
    </q-dialog>

    <!-- Reset temp password dialog -->
    <q-dialog v-model="resetDialog">
      <q-card style="width: 760px; max-width: 96vw" class="app-card">
        <q-card-section class="row items-center justify-between">
          <div class="text-h6">Reset contraseña provisional</div>
          <q-btn flat icon="close" v-close-popup />
        </q-card-section>

        <q-separator />

        <q-card-section>
          <div class="text-caption text-grey-7">
            Empleado: {{ resetTarget?.first_name }} {{ resetTarget?.last_name }}
          </div>

          <q-form class="q-mt-sm" @submit.prevent="doResetTempPassword">
            <q-banner class="q-mb-sm" dense rounded>
              Esto invalidará la contraseña actual del usuario y forzará cambio al iniciar sesión.
            </q-banner>

            <div class="q-mt-sm">
              <q-toggle v-model="resetForm.manualPass" label="Definir contraseña manual" />
            </div>

            <div class="q-mt-sm" v-if="resetForm.manualPass">
              <q-input
                v-model="resetForm.temp_password"
                label="Contraseña provisional"
                outlined
                type="password"
              />
            </div>

            <q-banner v-if="resetError" class="q-mt-md" dense rounded>
              {{ resetError }}
            </q-banner>

            <div class="q-mt-md">
              <q-btn color="primary" type="submit" :loading="resetSaving" label="Reset" />
            </div>
          </q-form>
        </q-card-section>
      </q-card>
    </q-dialog>

    <!-- Reset result dialog -->
    <q-dialog v-model="resetResultDialog">
      <q-card style="width: 560px; max-width: 96vw" class="app-card">
        <q-card-section class="row items-center justify-between">
          <div class="text-h6">Credenciales provisionales</div>
          <q-btn flat icon="close" v-close-popup />
        </q-card-section>

        <q-separator />

        <q-card-section>
          <div class="row q-col-gutter-md">
            <div class="col-12">
              <q-input
                :model-value="resetResult?.username || ''"
                label="Nombre de usuario"
                outlined
                readonly
              />
            </div>
            <div class="col-12">
              <q-input
                :model-value="resetResult?.temp_password || ''"
                label="Contraseña provisional"
                outlined
                readonly
              />
            </div>
          </div>

          <div class="q-mt-md">
            <q-btn flat icon="content_copy" label="Copiar contraseña" @click="copyResetPass" />
          </div>

          <q-banner class="q-mt-md" dense rounded>
            Guarda esta contraseña ahora: no se volverá a mostrar.
          </q-banner>
        </q-card-section>
      </q-card>
    </q-dialog>

    <!-- Revoke access dialog -->
    <q-dialog v-model="revokeDialog">
      <q-card style="width: 760px; max-width: 96vw" class="app-card">
        <q-card-section class="row items-center justify-between">
          <div class="text-h6">Revocar acceso</div>
          <q-btn flat icon="close" v-close-popup />
        </q-card-section>

        <q-separator />

        <q-card-section>
          <div class="text-caption text-grey-7">
            Empleado: {{ revokeTarget?.first_name }} {{ revokeTarget?.last_name }}
          </div>

          <q-banner class="q-mt-sm" dense rounded>
            Esto desactiva roles con origen POSITION y memberships del usuario en esta empresa y sus
            sucursales. No borra al empleado ni elimina el usuario.
          </q-banner>

          <div class="q-mt-sm">
            <q-toggle
              v-model="revokeForm.disable_user"
              label="Desactivar usuario globalmente (solo si ya no tiene memberships activas en otras empresas)"
            />
          </div>

          <q-banner v-if="revokeError" class="q-mt-md" dense rounded>
            {{ revokeError }}
          </q-banner>

          <div class="q-mt-md">
            <q-btn
              color="negative"
              :loading="revokeSaving"
              label="Revocar"
              @click="doRevokeAccess"
            />
          </div>
        </q-card-section>
      </q-card>
    </q-dialog>

    <!-- Revoke result dialog -->
    <q-dialog v-model="revokeResultDialog">
      <q-card style="width: 560px; max-width: 96vw" class="app-card">
        <q-card-section class="row items-center justify-between">
          <div class="text-h6">Acceso revocado</div>
          <q-btn flat icon="close" v-close-popup />
        </q-card-section>

        <q-separator />

        <q-card-section>
          <q-input
            :model-value="String(revokeResult?.linked_user_id ?? '')"
            label="linked_user_id"
            outlined
            readonly
          />
          <div class="q-mt-sm">
            <q-input
              :model-value="String(revokeResult?.role_assignments_deactivated ?? 0)"
              label="RoleAssignments POSITION desactivados"
              outlined
              readonly
            />
          </div>
          <div class="q-mt-sm">
            <q-input
              :model-value="String(revokeResult?.memberships_deactivated ?? 0)"
              label="Memberships desactivados"
              outlined
              readonly
            />
          </div>
          <div class="q-mt-sm">
            <q-badge v-if="revokeResult?.user_disabled" outline color="positive">
              Usuario global desactivado
            </q-badge>
            <q-badge v-else outline color="grey-7"> Usuario global no cambiado </q-badge>
          </div>
        </q-card-section>
      </q-card>
    </q-dialog>
  </AppContainer>
</template>

<script setup lang="ts">
import { computed, reactive, ref } from 'vue';
import { copyToClipboard, useQuasar } from 'quasar';
import { isAxiosError } from 'axios';
import { extractErrorMessage } from 'src/core/http/errors';
import { BUSINESS_LABELS } from 'src/shared/ui/business-terms';
import { useHrEmployeesFeature } from 'src/features/hr/employees/useHrEmployeesFeature';
import { listBranches } from 'src/services/org.service';
import {
  createAssignment,
  createEmployee,
  endAssignment,
  listPositions,
  patchEmployee,
  provisionEmployeeUser,
  resetEmployeeTempPassword,
  revokeEmployeeAccess,
  type EmployeeRow,
} from 'src/services/hr.service';
import AppContainer from 'src/ui/AppContainer.vue';
import AppPageHeader from 'src/ui/AppPageHeader.vue';
import HrEmployeesTableWidget from 'src/widgets/hr/HrEmployeesTableWidget.vue';

const $q = useQuasar();
const labels = BUSINESS_LABELS;
const saving = ref(false);
const {
  companyLabel,
  loading,
  errorMsg,
  rows,
  pagination,
  filter,
  columns,
  canCreate,
  canUpdate,
  canAssign,
  canEndAssign,
  canProvisionUser,
  load,
  onRequest,
  reload,
} = useHrEmployeesFeature();

// Create/Edit
const editDialog = ref(false);
const editingId = ref<number | null>(null);

const form = reactive<{
  employee_code: string;
  first_name: string;
  last_name: string;
  phone: string;
  email: string;
  is_active: boolean;
}>({
  employee_code: '',
  first_name: '',
  last_name: '',
  phone: '',
  email: '',
  is_active: true,
});

function openCreate() {
  editingId.value = null;
  Object.assign(form, {
    employee_code: '',
    first_name: '',
    last_name: '',
    phone: '',
    email: '',
    is_active: true,
  });
  editDialog.value = true;
}

function openEdit(e: EmployeeRow) {
  editingId.value = e.id;
  Object.assign(form, {
    employee_code: e.employee_code ?? '',
    first_name: e.first_name ?? '',
    last_name: e.last_name ?? '',
    phone: e.phone ?? '',
    email: e.email ?? '',
    is_active: e.is_active,
  });
  editDialog.value = true;
}

async function saveEmployee() {
  saving.value = true;
  try {
    if (!form.first_name.trim()) return;

    if (!editingId.value) {
      await createEmployee({
        employee_code: form.employee_code ?? '',
        first_name: form.first_name.trim(),
        last_name: form.last_name ?? '',
        phone: form.phone ?? '',
        email: form.email ?? '',
      });
      $q.notify({ type: 'positive', message: 'Empleado creado' });
    } else {
      await patchEmployee(editingId.value, {
        employee_code: form.employee_code ?? '',
        first_name: form.first_name.trim(),
        last_name: form.last_name ?? '',
        phone: form.phone ?? '',
        email: form.email ?? '',
        is_active: form.is_active,
      });
      $q.notify({ type: 'positive', message: 'Empleado actualizado' });
    }

    editDialog.value = false;
    await load();
  } catch (e: unknown) {
    $q.notify({ type: 'negative', message: extractErrorMessage(e) });
  } finally {
    saving.value = false;
  }
}

// Assign
const assignDialog = ref(false);
const assignTarget = ref<EmployeeRow | null>(null);
const assignSaving = ref(false);
const assignError = ref<string | null>(null);

const positionsLoading = ref(false);
const branchesLoading = ref(false);

const positionOptions = ref<{ label: string; value: number }[]>([]);
const branchOptions = ref<{ label: string; value: number }[]>([]);

const assignForm = reactive<{ position_id: number | null; branch_id: number | null }>({
  position_id: null,
  branch_id: null,
});

async function openAssign(e: EmployeeRow) {
  assignTarget.value = e;
  assignForm.position_id = null;
  assignForm.branch_id = null;
  assignError.value = null;
  assignDialog.value = true;

  positionsLoading.value = true;
  branchesLoading.value = true;

  try {
    const positionsData = await listPositions({ limit: 200, offset: 0 });
    positionOptions.value = positionsData.results.map((p) => ({
      label: `${p.name} (${p.code || '-'})`,
      value: p.id,
    }));
  } catch (err: unknown) {
    assignError.value = `No pude cargar puestos: ${extractErrorMessage(err)}`;
  } finally {
    positionsLoading.value = false;
  }

  try {
    const branchesData = await listBranches({ limit: 200, offset: 0 });
    branchOptions.value = branchesData.results.map((b) => ({
      label: `${b.name} (${b.code})`,
      value: b.id,
    }));
  } catch (err: unknown) {
    // Si no tienes org.branch.read, igual puedes asignar sin branch_id o ingresarlo manual (más adelante si lo quieres)
    // Aquí solo informamos.
    const msg = extractErrorMessage(err);
    assignError.value = assignError.value
      ? `${assignError.value} | Branches: ${msg}`
      : `Branches: ${msg}`;
  } finally {
    branchesLoading.value = false;
  }
}

async function doAssign() {
  if (!assignTarget.value) return;
  if (!assignForm.position_id) {
    assignError.value = 'Selecciona un puesto';
    return;
  }
  assignSaving.value = true;
  assignError.value = null;

  try {
    const id = await createAssignment(assignTarget.value.id, {
      position_id: assignForm.position_id,
      branch_id: assignForm.branch_id,
    });
    $q.notify({ type: 'positive', message: `Asignación creada (id=${id})` });
    assignDialog.value = false;
    await load();
  } catch (e: unknown) {
    assignError.value = extractErrorMessage(e);
  } finally {
    assignSaving.value = false;
  }
}

// End assignment
const endDialog = ref(false);
const endTarget = ref<EmployeeRow | null>(null);
const endAssignmentId = ref<number | null>(null);
const endSaving = ref(false);
const endError = ref<string | null>(null);

function openEnd(e: EmployeeRow) {
  endTarget.value = e;
  endAssignmentId.value = e.active_assignments?.[0]?.id ?? null;
  endError.value = null;
  endDialog.value = true;
}

const endAssignmentOptions = computed(() =>
  (endTarget.value?.active_assignments ?? []).map((a) => ({
    label: `${a.id} · ${a.position_name}${a.branch_name ? ` · ${a.branch_name}` : ''}`,
    value: a.id,
  })),
);

async function doEnd() {
  if (!endTarget.value) return;
  if (!endAssignmentId.value) {
    endError.value = 'Ingresa assignment_id';
    return;
  }
  endSaving.value = true;
  endError.value = null;

  try {
    await endAssignment(endTarget.value.id, endAssignmentId.value);
    $q.notify({ type: 'positive', message: 'Asignación finalizada' });
    endDialog.value = false;
    await load();
  } catch (e: unknown) {
    endError.value = extractErrorMessage(e);
  } finally {
    endSaving.value = false;
  }
}

// Provision user
const provDialog = ref(false);
const provTarget = ref<EmployeeRow | null>(null);
const provSaving = ref(false);
const provError = ref<string | null>(null);

const provResultDialog = ref(false);
const provResult = ref<{ username: string; temp_password: string } | null>(null);

const provForm = reactive<{
  username: string;
  email: string;
  manualPass: boolean;
  temp_password: string;
}>({
  username: '',
  email: '',
  manualPass: false,
  temp_password: '',
});

function openProvision(e: EmployeeRow) {
  if (!e.active_assignments?.length) {
    $q.notify({
      type: 'warning',
      message:
        'El empleado no tiene asignación activa. Asigna un puesto antes de provisionar acceso.',
    });
    return;
  }
  provTarget.value = e;
  provError.value = null;
  provResult.value = null;

  provForm.username = '';
  provForm.email = e.email ?? '';
  provForm.manualPass = false;
  provForm.temp_password = '';

  provDialog.value = true;
}

async function doProvision() {
  if (!provTarget.value) return;
  if (!provTarget.value.active_assignments?.length) {
    provError.value =
      'El empleado no tiene asignación activa. Asigna un puesto/sucursal antes de provisionar acceso.';
    return;
  }
  if (!provForm.username.trim()) {
    provError.value = 'Username es requerido';
    return;
  }

  provSaving.value = true;
  provError.value = null;
  try {
    const payload: { username: string; email?: string; temp_password?: string } = {
      username: provForm.username.trim(),
    };
    if (provForm.email.trim()) payload.email = provForm.email.trim();
    if (provForm.manualPass && provForm.temp_password) {
      payload.temp_password = provForm.temp_password;
    }

    const data = await provisionEmployeeUser(provTarget.value.id, payload);

    provDialog.value = false;
    provResult.value = { username: data.username, temp_password: data.temp_password };
    provResultDialog.value = true;
    $q.notify({ type: 'positive', message: 'Acceso provisionado' });
    await load();
  } catch (e: unknown) {
    if (isAxiosError(e)) {
      const status = e.response?.status;
      const detail =
        typeof e.response?.data === 'object' && e.response?.data
          ? (e.response?.data as { detail?: unknown }).detail
          : undefined;
      const detailStr = typeof detail === 'string' ? detail : '';

      if (status === 403) {
        provError.value =
          'No tienes permisos para esta acción (requiere iam.users.create y hr.employee.update).';
      } else if (status === 409) {
        // backend actual devuelve 409 con mensaje en español
        provError.value =
          detailStr ||
          'Conflicto: el empleado ya tiene usuario vinculado o el estado no permite provisionar.';
      } else if (status === 400) {
        // Mensajes “humanos” basados en ValueError del backend (en español)
        if (detailStr.includes('no tiene ninguna asignación activa')) {
          provError.value =
            'El empleado no tiene asignación activa. Asigna un puesto/sucursal antes de provisionar acceso.';
        } else if (detailStr.includes('ya existe') && detailStr.includes('username')) {
          provError.value =
            'El username ya existe. Prueba con otro o usa un estándar (ej: nombre.apellido).';
        } else if (detailStr.includes('ya existe') && detailStr.includes('email')) {
          provError.value = 'El email ya está en uso por otro usuario.';
        } else {
          provError.value = extractErrorMessage(e);
        }
      } else {
        provError.value = extractErrorMessage(e);
      }
    } else {
      provError.value = extractErrorMessage(e);
    }
  } finally {
    provSaving.value = false;
  }
}

async function copyProvPass() {
  const pass = provResult.value?.temp_password;
  if (!pass) return;
  try {
    await copyToClipboard(pass);
    $q.notify({ type: 'positive', message: 'Contraseña copiada' });
  } catch {
    $q.notify({ type: 'negative', message: 'No pude copiar al portapapeles' });
  }
}

// Reset temp password
const resetDialog = ref(false);
const resetTarget = ref<EmployeeRow | null>(null);
const resetSaving = ref(false);
const resetError = ref<string | null>(null);

const resetResultDialog = ref(false);
const resetResult = ref<{ username: string; temp_password: string } | null>(null);

const resetForm = reactive<{ manualPass: boolean; temp_password: string }>({
  manualPass: false,
  temp_password: '',
});

function openResetTempPassword(e: EmployeeRow) {
  resetTarget.value = e;
  resetError.value = null;
  resetResult.value = null;
  resetForm.manualPass = false;
  resetForm.temp_password = '';
  resetDialog.value = true;
}

async function doResetTempPassword() {
  if (!resetTarget.value) return;

  const ok = await new Promise<boolean>((resolve) => {
    $q.dialog({
      title: 'Confirmar reset',
      message:
        'Esto invalidará la contraseña actual y el usuario deberá cambiarla al iniciar sesión. ¿Continuar?',
      cancel: true,
      persistent: true,
    })
      .onOk(() => resolve(true))
      .onCancel(() => resolve(false));
  });
  if (!ok) return;

  resetSaving.value = true;
  resetError.value = null;

  try {
    const payload: { temp_password?: string } = {};
    if (resetForm.manualPass && resetForm.temp_password.trim()) {
      payload.temp_password = resetForm.temp_password;
    }

    const data = await resetEmployeeTempPassword(resetTarget.value.id, payload);

    resetDialog.value = false;
    resetResult.value = { username: data.username, temp_password: data.temp_password };
    resetResultDialog.value = true;
    $q.notify({ type: 'positive', message: 'Contraseña provisional reseteada' });
    await load();
  } catch (e: unknown) {
    if (isAxiosError(e)) {
      const status = e.response?.status;
      const detail =
        typeof e.response?.data === 'object' && e.response?.data
          ? (e.response?.data as { detail?: unknown }).detail
          : undefined;

      if (status === 403) {
        resetError.value =
          'No tienes permisos para esta acción (requiere iam.users.create y hr.employee.update).';
      } else if (status === 404) {
        resetError.value = 'Empleado no encontrado en esta empresa.';
      } else if (status === 409) {
        if (
          detail === 'Employee has no linked user' ||
          detail === 'Employee has no linked user; cannot reset password.' ||
          detail === 'Employee has no linked user'
        ) {
          resetError.value = 'El empleado no tiene usuario vinculado (no se puede resetear).';
        } else if (
          detail === 'Employee has no active assignment' ||
          detail === 'Employee has no active assignment; cannot reset password.'
        ) {
          resetError.value = 'El empleado no tiene asignación activa (no corresponde resetear).';
        } else {
          resetError.value = extractErrorMessage(e);
        }
      } else {
        resetError.value = extractErrorMessage(e);
      }
    } else {
      resetError.value = extractErrorMessage(e);
    }
  } finally {
    resetSaving.value = false;
  }
}

async function copyResetPass() {
  const pass = resetResult.value?.temp_password;
  if (!pass) return;
  try {
    await copyToClipboard(pass);
    $q.notify({ type: 'positive', message: 'Contraseña copiada' });
  } catch {
    $q.notify({ type: 'negative', message: 'No pude copiar al portapapeles' });
  }
}

// Revoke access (B)
const revokeDialog = ref(false);
const revokeTarget = ref<EmployeeRow | null>(null);
const revokeSaving = ref(false);
const revokeError = ref<string | null>(null);

const revokeResultDialog = ref(false);
const revokeResult = ref<{
  employee_id: number;
  linked_user_id: number;
  role_assignments_deactivated: number;
  memberships_deactivated: number;
  user_disabled: boolean;
} | null>(null);

const revokeForm = reactive<{ disable_user: boolean }>({
  disable_user: false,
});

function openRevokeAccess(e: EmployeeRow) {
  revokeTarget.value = e;
  revokeError.value = null;
  revokeResult.value = null;
  revokeForm.disable_user = false;
  revokeDialog.value = true;
}

async function doRevokeAccess() {
  if (!revokeTarget.value) return;

  // Confirmación (si aún tiene asignación activa, avisar)
  const hasActive = !!revokeTarget.value.active_assignments?.length;

  const ok = await new Promise<boolean>((resolve) => {
    $q.dialog({
      title: 'Confirmar revocación',
      message: hasActive
        ? 'Este empleado aún tiene asignación activa. Lo normal es terminar la asignación y luego revocar el acceso. Si continúas, se revocará el acceso igualmente. ¿Continuar?'
        : 'Esto revocará el acceso del usuario en esta empresa y sus sucursales (desactiva roles POSITION y memberships). ¿Continuar?',
      cancel: true,
      persistent: true,
    })
      .onOk(() => resolve(true))
      .onCancel(() => resolve(false));
  });
  if (!ok) return;

  revokeSaving.value = true;
  revokeError.value = null;
  try {
    const payload: { disable_user?: boolean } = {};
    if (revokeForm.disable_user) payload.disable_user = true;

    const data = await revokeEmployeeAccess(revokeTarget.value.id, payload);

    revokeDialog.value = false;
    revokeResult.value = data;
    revokeResultDialog.value = true;
    $q.notify({ type: 'positive', message: 'Acceso revocado' });
    await load();
  } catch (e: unknown) {
    if (isAxiosError(e)) {
      const status = e.response?.status;
      const detail =
        typeof e.response?.data === 'object' && e.response?.data
          ? (e.response?.data as { detail?: unknown }).detail
          : undefined;
      const detailStr = typeof detail === 'string' ? detail : '';

      if (status === 403) {
        revokeError.value =
          'No tienes permisos para esta acción (requiere iam.users.create y hr.employee.update).';
      } else if (status === 404) {
        revokeError.value = 'Empleado no encontrado.';
      } else if (status === 409) {
        revokeError.value = detailStr || 'Conflicto: el empleado no tiene usuario vinculado.';
      } else {
        revokeError.value = extractErrorMessage(e);
      }
    } else {
      revokeError.value = extractErrorMessage(e);
    }
  } finally {
    revokeSaving.value = false;
  }
}
</script>
