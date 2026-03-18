import { api } from 'src/boot/axios';

type PaginatedResponse<T> = {
  count: number;
  limit: number;
  offset: number;
  results: T[];
};

type ListParams = {
  limit?: number;
  offset?: number;
};

function buildListQuery(params?: ListParams): string {
  if (!params) return '';
  const qs = new URLSearchParams();
  if (typeof params.limit === 'number') qs.set('limit', String(params.limit));
  if (typeof params.offset === 'number') qs.set('offset', String(params.offset));
  const out = qs.toString();
  return out ? `?${out}` : '';
}

export type CompanyRow = {
  id: number;
  name: string;
  code: string;
  is_active: boolean;
  legal_name: string;
  tax_id: string;
};

export type CreateCompanyPayload = {
  name: string;
  code?: string;
  legal_name?: string;
  tax_id?: string;
  address?: string;
  phone?: string;
  email?: string;
};

export type CompanyProfile = {
  legal_name: string;
  tax_id: string;
  address: string;
  phone: string;
  email: string;
};

export type BranchRow = {
  id: number;
  name: string;
  code: string;
  is_active: boolean;
  address: string;
  phone: string;
  email: string;
};

export type CreateBranchPayload = {
  name: string;
  code?: string;
  address?: string;
  phone?: string;
  email?: string;
};

export type PatchBranchPayload = Partial<{
  name: string;
  code: string;
  is_active: boolean;
  address: string;
  phone: string;
  email: string;
}>;

export async function getCompanyProfile() {
  const { data } = await api.get<CompanyProfile>('/backend/org/company/profile/');
  return data;
}

export async function listCompanies(params?: ListParams) {
  const qs = buildListQuery(params);
  const { data } = await api.get<PaginatedResponse<CompanyRow>>(`/org/companies/${qs}`);
  return data;
}

export async function createCompany(payload: CreateCompanyPayload) {
  const { data } = await api.post<{ id: number }>('/backend/org/companies/', payload);
  return data.id;
}

export async function updateCompanyProfile(payload: Partial<CompanyProfile>) {
  const { data } = await api.put<{ ok: true }>('/backend/org/company/profile/', payload);
  return data;
}

export async function listBranches(params?: ListParams) {
  const qs = buildListQuery(params);
  const { data } = await api.get<PaginatedResponse<BranchRow>>(`/org/branches/${qs}`);
  return data;
}

export async function createBranch(payload: CreateBranchPayload) {
  const { data } = await api.post<{ id: number }>('/backend/org/branches/', payload);
  return data.id;
}

export async function patchBranch(branchId: number, payload: PatchBranchPayload) {
  const { data } = await api.patch<{ ok: true }>(`/org/branches/${branchId}/`, payload);
  return data;
}
