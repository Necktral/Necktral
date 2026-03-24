<template>
  <q-chip dense square :color="chipColor" text-color="white" icon="receipt_long">
    {{ label }}
  </q-chip>
</template>

<script setup lang="ts">
import { computed } from 'vue';

const props = defineProps<{
  status?: string | null;
}>();

const label = computed(() => props.status || 'SIN FISCALIDAD');
const chipColor = computed(() => {
  if (props.status === 'ISSUED') return 'positive';
  if (props.status === 'VOIDED') return 'negative';
  if (props.status) return 'warning';
  return 'grey-7';
});
</script>
