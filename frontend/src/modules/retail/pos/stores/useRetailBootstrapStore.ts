import { defineStore } from 'pinia';

import { fetchRetailBootstrap, type RetailBootstrapResponse } from '../services/retail-pos.service';

export const useRetailBootstrapStore = defineStore('retail-bootstrap', {
  state: () => ({
    loading: false as boolean,
    error: null as string | null,
    data: null as RetailBootstrapResponse | null,
  }),

  actions: {
    async load() {
      this.loading = true;
      this.error = null;
      try {
        this.data = await fetchRetailBootstrap();
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : 'No se pudo cargar el bootstrap retail.';
      } finally {
        this.loading = false;
      }
    },
  },
});
