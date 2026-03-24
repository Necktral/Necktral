<template>
  <q-drawer side="right" :model-value="modelValue" overlay bordered :width="360" @update:model-value="$emit('update:modelValue', $event)">
    <div class="q-pa-md">
      <div class="row items-center justify-between q-mb-md">
        <div>
          <div class="text-subtitle1">Tickets recientes</div>
          <div class="text-caption text-grey-7">Reabrir o inspeccionar operación reciente</div>
        </div>
        <q-btn flat round dense icon="close" @click="$emit('update:modelValue', false)" />
      </div>

      <q-list bordered separator class="rounded-borders">
        <q-item v-for="ticket in tickets" :key="ticket.id" clickable @click="$emit('select-ticket', ticket.id)">
          <q-item-section>
            <q-item-label>#{{ ticket.id }} · {{ ticket.status }}</q-item-label>
            <q-item-label caption>{{ ticket.created_at }} · {{ ticket.total }}</q-item-label>
          </q-item-section>
        </q-item>
        <q-item v-if="!tickets.length && !loading">
          <q-item-section class="text-grey-6">
            No hay tickets recientes.
          </q-item-section>
        </q-item>
      </q-list>
    </div>
  </q-drawer>
</template>

<script setup lang="ts">
import type { RetailTicketRow } from '../services/retail-pos.service';

defineProps<{
  modelValue: boolean;
  tickets: RetailTicketRow[];
  loading: boolean;
}>();

defineEmits<{
  (event: 'update:modelValue', value: boolean): void;
  (event: 'select-ticket', ticketId: number): void;
}>();
</script>
