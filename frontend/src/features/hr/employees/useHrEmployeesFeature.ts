import { computed, onMounted, ref } from 'vue';
import type { QTableColumn } from 'quasar';

import { extractErrorMessage } from 'src/core/http/errors';
import { computeLimit } from 'src/shared/constants';
import { listEmployees, type EmployeeRow } from 'src/services/hr.service';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';

type HrEmployeesPagination = {
  page: number;
  rowsPerPage: number;
  rowsNumber: number;
};

type HrEmployeesTableRequest = {
  pagination: {
    page: number;
    rowsPerPage: number;
  };
};

const EMPLOYEE_COLUMNS: QTableColumn[] = [
  { name: 'employee_code', label: 'Codigo', field: 'employee_code', align: 'left', sortable: true },
  { name: 'first_name', label: 'Nombres', field: 'first_name', align: 'left', sortable: true },
  { name: 'last_name', label: 'Apellidos', field: 'last_name', align: 'left', sortable: true },
  { name: 'phone', label: 'Telefono', field: 'phone', align: 'left' },
  { name: 'email', label: 'Email', field: 'email', align: 'left' },
  { name: 'assignment', label: 'Asignacion', field: 'has_active_assignment', align: 'left' },
  { name: 'is_active', label: 'Activo', field: 'is_active', align: 'left', sortable: true },
  { name: 'access', label: 'Acceso', field: 'access', align: 'left' },
  { name: 'actions', label: 'Acciones', field: 'actions', align: 'right' },
];

export function useHrEmployeesFeature() {
  const acl = useAclStore();
  const ctx = useContextStore();

  const companyLabel = computed(
    () => acl.companyName(ctx.activeCompanyId) ?? ctx.activeCompanyId ?? '-',
  );

  const loading = ref(false);
  const errorMsg = ref<string | null>(null);
  const rows = ref<EmployeeRow[]>([]);
  const pagination = ref<HrEmployeesPagination>({
    page: 1,
    rowsPerPage: 20,
    rowsNumber: 0,
  });
  const filter = ref('');

  const canCreate = computed(
    () => !!ctx.activeCompanyId && acl.hasPermission(ctx.activeCompanyId, 'hr.employee.create'),
  );
  const canUpdate = computed(
    () => !!ctx.activeCompanyId && acl.hasPermission(ctx.activeCompanyId, 'hr.employee.update'),
  );
  const canAssign = computed(
    () => !!ctx.activeCompanyId && acl.hasPermission(ctx.activeCompanyId, 'hr.assignment.create'),
  );
  const canEndAssign = computed(
    () => !!ctx.activeCompanyId && acl.hasPermission(ctx.activeCompanyId, 'hr.assignment.end'),
  );
  const canProvision = computed(
    () => !!ctx.activeCompanyId && acl.hasPermission(ctx.activeCompanyId, 'iam.users.create'),
  );
  const canProvisionUser = computed(() => canProvision.value && canUpdate.value);

  async function load(
    page = pagination.value.page,
    rowsPerPage = pagination.value.rowsPerPage,
  ): Promise<void> {
    loading.value = true;
    errorMsg.value = null;
    try {
      const limit = computeLimit(rowsPerPage);
      const offset = (page - 1) * limit;
      const data = await listEmployees({ limit, offset });
      rows.value = data.results;
      pagination.value = {
        ...pagination.value,
        page,
        rowsPerPage,
        rowsNumber: data.count,
      };
    } catch (error: unknown) {
      errorMsg.value = extractErrorMessage(error);
    } finally {
      loading.value = false;
    }
  }

  function onRequest(props: HrEmployeesTableRequest): void {
    void load(props.pagination.page, props.pagination.rowsPerPage);
  }

  function reload(): void {
    void load();
  }

  onMounted(() => {
    void load();
  });

  return {
    companyLabel,
    loading,
    errorMsg,
    rows,
    pagination,
    filter,
    columns: EMPLOYEE_COLUMNS,
    canCreate,
    canUpdate,
    canAssign,
    canEndAssign,
    canProvisionUser,
    load,
    onRequest,
    reload,
  };
}
