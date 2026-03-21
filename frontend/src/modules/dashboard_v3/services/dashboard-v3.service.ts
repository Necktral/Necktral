import { api } from 'src/boot/axios';

import type {
  DashboardCatalogResponse,
  DashboardDrilldownResponse,
  DashboardQueryParams,
  DashboardQueryResponse,
  DashboardWorkspaceResponse,
} from '../types';

export async function fetchDashboardCatalog(): Promise<DashboardCatalogResponse> {
  const { data } = await api.get<DashboardCatalogResponse>('/backend/dashboard/catalog/');
  return data;
}

export async function fetchDashboardWorkspace(workspaceCode: string): Promise<DashboardWorkspaceResponse> {
  const { data } = await api.get<DashboardWorkspaceResponse>(`/backend/dashboard/workspaces/${workspaceCode}/`);
  return data;
}

export async function queryDashboardWorkspace(
  workspaceCode: string,
  payload: DashboardQueryParams,
): Promise<DashboardQueryResponse> {
  const { data } = await api.post<DashboardQueryResponse>(
    `/backend/dashboard/workspaces/${workspaceCode}/query/`,
    payload,
  );
  return data;
}

export async function drilldownDashboard(payload: {
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
}): Promise<DashboardDrilldownResponse> {
  const { data } = await api.post<DashboardDrilldownResponse>('/backend/dashboard/drilldown/', payload);
  return data;
}
