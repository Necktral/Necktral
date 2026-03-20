<template>
  <q-card class="app-card kpi-card">
    <q-card-section>
      <div class="text-caption text-grey-7">{{ label }}</div>
      <div class="text-h6">{{ value }}</div>
      <div v-if="hint" class="text-caption text-grey-6">{{ hint }}</div>
    </q-card-section>
  </q-card>
</template>

<script setup lang="ts">
defineProps<{
  label: string;
  value: string;
  hint?: string;
}>();
</script>

<style scoped>
.kpi-card {
  min-height: 112px;
}
</style>

