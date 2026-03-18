import { defineStore } from 'pinia';
import type { AxiosInstance } from 'axios';
import { api } from 'src/boot/axios';

export type AclBranch = {
  branch_id: string;
  branch_name: string;
};

export type AclCompany = {
  company_id: string;
  company_name: string;
  branches: AclBranch[];
  permissions: string[];
};

export type AclSnapshot = {
  user_id: string;
  username: string;
  server_time: string;
  acl_version: string;
  companies: AclCompany[];
  admin_caps_by_company?: Record<string, string[]>;
  recommended_company_id?: string | null;
  recommended_branch_id?: string | null;
};

function buildPermIndex(companies: AclCompany[]) {
  const m = new Map<string, Set<string>>();
  for (const c of companies) m.set(c.company_id, new Set(c.permissions ?? []));
  return m;
}

export const useAclStore = defineStore('acl', {
  state: () => ({
    loaded: false as boolean,
    snapshot: null as AclSnapshot | null,
    permissionsByCompany: new Map<string, Set<string>>(),
  }),

  getters: {
    companies: (s) => s.snapshot?.companies ?? [],
    recommendedCompanyId: (s) => s.snapshot?.recommended_company_id ?? null,
    recommendedBranchId: (s) => s.snapshot?.recommended_branch_id ?? null,
    aclVersion: (s) => s.snapshot?.acl_version ?? null,
  },

  actions: {
    async loadAcl(client?: AxiosInstance) {
      const http = client ?? api;
      const { data } = await http.get<AclSnapshot>('/backend/auth/me/acl/');
      this.snapshot = data;
      this.permissionsByCompany = buildPermIndex(data.companies ?? []);
      this.loaded = true;
    },

    clearAcl() {
      this.snapshot = null;
      this.permissionsByCompany = new Map();
      this.loaded = false;
    },

    hasPermission(companyId: string, permCode: string) {
      const set = this.permissionsByCompany.get(companyId);
      return Boolean(set && set.has(permCode));
    },

    companyName(companyId: string | null) {
      if (!companyId) return null;
      const c = this.companies.find((x) => x.company_id === companyId);
      return c?.company_name ?? null;
    },

    branchName(companyId: string | null, branchId: string | null) {
      if (!companyId || !branchId) return null;
      const c = this.companies.find((x) => x.company_id === companyId);
      const b = c?.branches?.find((x) => x.branch_id === branchId);
      return b?.branch_name ?? null;
    },
  },
});
