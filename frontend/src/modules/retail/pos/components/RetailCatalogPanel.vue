<template>
  <q-card class="app-card retail-panel">
    <q-card-section class="row items-center justify-between q-pb-sm">
      <div>
        <div class="text-subtitle1">Catálogo</div>
        <div class="text-caption text-grey-7">SKU, nombre, barcode y quick-add</div>
      </div>
      <q-btn flat dense icon="refresh" @click="$emit('search')" />
    </q-card-section>

    <q-card-section class="q-pt-none">
      <q-input
        ref="searchInputRef"
        :model-value="modelValue"
        dense
        standout
        clearable
        placeholder="Buscar producto o barcode"
        prefix="F2"
        @update:model-value="$emit('update:modelValue', String($event ?? ''))"
        @keyup.enter="$emit('search')"
      >
        <template #append>
          <q-btn flat round dense icon="search" @click="$emit('search')" />
        </template>
      </q-input>
    </q-card-section>

    <q-separator />

    <q-card-section class="retail-panel__list">
      <q-inner-loading :showing="loading">
        <q-spinner color="primary" size="32px" />
      </q-inner-loading>

      <q-banner v-if="error" dense rounded class="bg-negative text-white q-mb-sm">
        {{ error }}
      </q-banner>

      <q-list bordered separator class="rounded-borders">
        <q-item v-for="item in items" :key="item.id" clickable @click="$emit('select-item', item)">
          <q-item-section>
            <q-item-label>{{ item.name }}</q-item-label>
            <q-item-label caption>{{ item.sku }} · {{ item.suggested_price }} · IVA {{ item.tax_rate }}</q-item-label>
          </q-item-section>
          <q-item-section side>
            <q-chip dense square color="secondary" text-color="white">
              {{ item.uom_sale }}
            </q-chip>
          </q-item-section>
        </q-item>
        <q-item v-if="!items.length && !loading">
          <q-item-section class="text-grey-6">
            Sin resultados para la búsqueda actual.
          </q-item-section>
        </q-item>
      </q-list>
    </q-card-section>
  </q-card>
</template>

<script setup lang="ts">
import { ref } from 'vue';

import type { QInput } from 'quasar';

import type { RetailCatalogItem } from '../services/retail-pos.service';

defineProps<{
  modelValue: string;
  items: RetailCatalogItem[];
  loading: boolean;
  error: string | null;
}>();

defineEmits<{
  (event: 'update:modelValue', value: string): void;
  (event: 'search'): void;
  (event: 'select-item', value: RetailCatalogItem): void;
}>();

const searchInputRef = ref<QInput | null>(null);

defineExpose({
  focusInput() {
    searchInputRef.value?.focus();
  },
});
</script>

<style scoped>
.retail-panel {
  min-height: 100%;
}

.retail-panel__list {
  position: relative;
  min-height: 420px;
}
</style>
