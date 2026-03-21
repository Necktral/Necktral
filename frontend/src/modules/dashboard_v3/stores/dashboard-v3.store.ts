import { defineStore } from 'pinia';

import {
  drilldownDashboard,
  fetchDashboardCatalog,
  fetchDashboardWorkspace,
  queryDashboardWorkspace,
} from '../services/dashboard-v3.service';
import type {
  DashboardCatalogEntry,
  DashboardDrilldownResponse,
  DashboardQueryParams,
  DashboardQueryResponse,
  DashboardWorkspace,
} from '../types';

export const useDashboardV3Store = defineStore('dashboard-v3', {
  state: () => ({
    loading: false as boolean,
    catalogLoading: false as boolean,
    error: null as string | null,
    catalog: [] as DashboardCatalogEntry[],
    workspace: null as DashboardWorkspace | null,
    queryResult: null as DashboardQueryResponse | null,
    drilldownResult: null as DashboardDrilldownResponse | null,
  }),

  actions: {
    async loadCatalog() {
      this.catalogLoading = true;
      this.error = null;
      try {
        const data = await fetchDashboardCatalog();
        this.catalog = data.results;
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : 'No se pudo cargar el catálogo analítico.';
      } finally {
        this.catalogLoading = false;
      }
    },

    async loadWorkspace(workspaceCode: string) {
      this.loading = true;
      this.error = null;
      try {
        const data = await fetchDashboardWorkspace(workspaceCode);
        this.workspace = data.results;
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : 'No se pudo cargar el workspace.';
      } finally {
        this.loading = false;
      }
    },

    async queryWorkspace(workspaceCode: string, payload: DashboardQueryParams) {
      this.loading = true;
      this.error = null;
      try {
        this.queryResult = await queryDashboardWorkspace(workspaceCode, payload);
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : 'No se pudo ejecutar la consulta del dashboard.';
      } finally {
        this.loading = false;
      }
    },

    async runDrilldown(payload: {
      workspace_code: string;
      widget_code: string;
      drill_path?: string[];
      filters?: Record<string, unknown>;
      group_by?: string[];
      metrics?: string[];
      sort?: Array<Record<string, unknown>>;
      cursor?: Record<string, unknown> | string;
      comparison?: Record<string, unknown>;
      company_ids?: number[];
      branch_id?: number | null;
    }) {
      this.loading = true;
      this.error = null;
      try {
        this.drilldownResult = await drilldownDashboard(payload);
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : 'No se pudo ejecutar el drill-down.';
      } finally {
        this.loading = false;
      }
    },
  },
});
