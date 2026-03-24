import { defineStore } from 'pinia';

import { searchRetailCatalog, type RetailCatalogItem } from '../services/retail-pos.service';

export const useRetailCatalogStore = defineStore('retail-catalog', {
  state: () => ({
    loading: false as boolean,
    error: null as string | null,
    query: '' as string,
    results: [] as RetailCatalogItem[],
  }),

  actions: {
    async search(query: string) {
      this.loading = true;
      this.error = null;
      this.query = query;
      try {
        const data = await searchRetailCatalog({ q: query, limit: 24 });
        this.results = data.results;
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : 'No se pudo consultar el catálogo retail.';
      } finally {
        this.loading = false;
      }
    },

    async searchByBarcode(barcode: string) {
      this.loading = true;
      this.error = null;
      this.query = barcode;
      try {
        const data = await searchRetailCatalog({ barcode, limit: 24 });
        this.results = data.results;
      } catch (error: unknown) {
        this.error = error instanceof Error ? error.message : 'No se pudo consultar el catálogo retail.';
      } finally {
        this.loading = false;
      }
    },
  },
});
