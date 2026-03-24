<template>
  <q-dialog :model-value="modelValue" @update:model-value="$emit('update:modelValue', $event)">
    <q-card style="min-width: 360px">
      <q-card-section>
        <div class="text-subtitle1">Retener ticket</div>
        <div class="text-caption text-grey-7">Conserva el ticket para retomarlo más tarde.</div>
      </q-card-section>
      <q-card-section>
        <q-input v-model="reason" autofocus outlined dense label="Motivo" />
      </q-card-section>
      <q-card-actions align="right">
        <q-btn flat label="Cancelar" @click="$emit('update:modelValue', false)" />
        <q-btn color="primary" label="Guardar hold" :loading="loading" @click="$emit('confirm', reason)" />
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
  (event: 'confirm', reason: string): void;
}>();

const reason = ref('');
</script>
