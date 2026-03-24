<template>
  <q-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)">
    <q-card style="min-width: 420px">
      <q-card-section>
        <div class="text-subtitle1">Devolución rápida</div>
        <div class="text-caption text-grey-7">Genera credit note y refund sobre una línea de la venta cerrada.</div>
      </q-card-section>
      <q-card-section class="q-gutter-md">
        <q-input v-model="qty" outlined dense label="Cantidad" />
        <q-input v-model="reason" outlined dense label="Motivo" />
      </q-card-section>
      <q-card-actions align="right">
        <q-btn flat label="Cancelar" @click="$emit('update:modelValue', false)" />
        <q-btn color="primary" label="Procesar devolución" :loading="loading" @click="$emit('confirm', qty, reason)" />
      </q-card-actions>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { ref } from 'vue';

defineProps<{
  modelValue: boolean;
  loading: boolean;
}>();

defineEmits<{
  (event: 'update:modelValue', value: boolean): void;
  (event: 'confirm', qty: string, reason: string): void;
}>();

const qty = ref('1.0000');
const reason = ref('');
</script>
