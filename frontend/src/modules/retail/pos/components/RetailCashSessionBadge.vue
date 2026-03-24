<template>
  <q-chip
    square
    dense
    :color="session ? 'positive' : 'negative'"
    text-color="white"
    icon="point_of_sale"
  >
    {{ label }}
  </q-chip>
</template>

<script setup lang="ts">
import { computed } from 'vue';

import type { RetailCashSession } from '../services/retail-pos.service';

const props = defineProps<{
  session: RetailCashSession | null;
}>();

const label = computed(() =>
  props.session ? `Caja ${props.session.id} · ${props.session.status}` : 'Caja no disponible',
);
</script>
