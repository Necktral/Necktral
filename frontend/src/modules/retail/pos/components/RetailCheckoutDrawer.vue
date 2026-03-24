<template>
  <q-drawer side="right" :model-value="modelValue" overlay bordered :width="400" @update:model-value="$emit('update:modelValue', $event)">
    <div class="q-pa-md column full-height">
      <div class="row items-center justify-between q-mb-md">
        <div>
          <div class="text-subtitle1">Checkout</div>
          <div class="text-caption text-grey-7">Cobro cash-first y confirmación documental</div>
        </div>
        <q-btn flat round dense icon="close" @click="$emit('update:modelValue', false)" />
      </div>

      <RetailTotalsBar :ticket="ticket" />

      <q-banner v-if="preview && !preview.ok" dense rounded class="bg-warning text-black q-mt-md">
        {{ preview.blocking_errors.map((row) => row.detail).join(' · ') }}
      </q-banner>

      <q-input
        v-model="cashReceived"
        outlined
        dense
        label="Efectivo recibido"
        class="q-mt-md"
        inputmode="decimal"
      />

      <div class="text-caption text-grey-7 q-mt-sm">
        Cambio estimado: <strong>{{ changeDue }}</strong>
      </div>

      <div class="q-mt-md">
        <RetailNumericPad @append="appendKey" @clear="cashReceived = ''" />
      </div>

      <div class="q-mt-md q-gutter-sm">
        <q-btn outline icon="fact_check" label="Preview" :loading="loading" @click="$emit('preview')" />
        <q-btn color="primary" icon="payments" label="Emitir y cobrar" :loading="loading" @click="$emit('commit', cashReceived)" />
        <q-btn flat color="negative" icon="cancel" label="Anular" :loading="loading" @click="$emit('void')" />
      </div>

      <q-space />

      <div class="text-caption text-grey-7">
        Atajos: <strong>F4</strong> checkout, <strong>Enter</strong> confirmar, <strong>Esc</strong> cerrar.
      </div>
    </div>
  </q-drawer>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';

import RetailNumericPad from './RetailNumericPad.vue';
import RetailTotalsBar from './RetailTotalsBar.vue';
import type { RetailCheckoutPreviewResponse, RetailTicketRow } from '../services/retail-pos.service';

const props = defineProps<{
  modelValue: boolean;
  ticket: RetailTicketRow | null;
  preview: RetailCheckoutPreviewResponse | null;
  loading: boolean;
}>();

const emit = defineEmits<{
  (event: 'update:modelValue', value: boolean): void;
  (event: 'preview'): void;
  (event: 'commit', cashReceived: string): void;
  (event: 'void'): void;
}>();

const cashReceived = ref('');

watch(
  () => props.ticket?.total,
  (value) => {
    if (value) cashReceived.value = value;
  },
  { immediate: true },
);

const changeDue = computed(() => {
  const received = Number(cashReceived.value || '0');
  const total = Number(props.ticket?.total || '0');
  return Math.max(received - total, 0).toFixed(2);
});

function appendKey(key: string) {
  cashReceived.value = `${cashReceived.value}${key}`;
}

defineExpose({
  confirm() {
    emit('commit', cashReceived.value || props.ticket?.total || '0.00');
  },
});
</script>
