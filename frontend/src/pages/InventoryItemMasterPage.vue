<template>
  <ItemMasterWizard :mode="mode" :item-id="itemId" />
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRoute } from 'vue-router';

import ItemMasterWizard from 'src/modules/inventory/components/ItemMasterWizard.vue';

const route = useRoute();

const hasItemId = computed(() => Number(route.params.id || 0) > 0);
const mode = computed<'create' | 'edit'>(() => (hasItemId.value ? 'edit' : 'create'));
const itemId = computed<number | null>(() => (hasItemId.value ? Number(route.params.id) : null));
</script>
