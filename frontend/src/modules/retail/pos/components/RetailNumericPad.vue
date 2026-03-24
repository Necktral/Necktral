<template>
  <div class="retail-numpad">
    <q-btn
      v-for="key in keys"
      :key="key"
      unelevated
      class="retail-numpad__key"
      :label="key"
      @click="$emit('append', key)"
    />
    <q-btn unelevated color="negative" class="retail-numpad__key retail-numpad__key--wide" label="Borrar" @click="$emit('clear')" />
  </div>
</template>

<script setup lang="ts">
const keys = ['7', '8', '9', '4', '5', '6', '1', '2', '3', '0', '00', '.'];

defineEmits<{
  (event: 'append', value: string): void;
  (event: 'clear'): void;
}>();
</script>

<style scoped>
.retail-numpad {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 8px;
}

.retail-numpad__key {
  min-height: 52px;
  font-size: 18px;
  border-radius: 12px;
}

.retail-numpad__key--wide {
  grid-column: span 3;
}
</style>
