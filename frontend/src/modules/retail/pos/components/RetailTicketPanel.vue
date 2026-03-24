<template>
  <q-card class="app-card retail-panel">
    <q-card-section class="row items-center justify-between q-pb-sm">
      <div>
        <div class="text-subtitle1">Ticket</div>
        <div class="text-caption text-grey-7">
          {{ ticket ? `#${ticket.id} · ${ticket.status}` : 'Sin ticket activo' }}
        </div>
      </div>
      <div class="row items-center q-gutter-sm">
        <q-btn outline dense icon="pause_circle" label="Hold" @click="$emit('hold')" />
        <q-btn color="primary" dense icon="payments" label="Cobrar" @click="$emit('checkout')" />
      </div>
    </q-card-section>

    <q-separator />

    <q-card-section class="retail-panel__list">
      <q-list bordered separator class="rounded-borders">
        <q-item v-for="line in ticket?.lines ?? []" :key="line.id" :active="selectedLineId === line.id" active-class="bg-blue-1">
          <q-item-section @click="$emit('select-line', line.id)">
            <q-item-label>{{ line.name_snapshot }}</q-item-label>
            <q-item-label caption>
              {{ line.sku_snapshot }} · {{ line.qty }} x {{ line.unit_price }} · IVA {{ line.tax_rate_snapshot }}
            </q-item-label>
          </q-item-section>
          <q-item-section side class="items-end">
            <div class="text-subtitle2">{{ line.line_total }}</div>
            <q-btn flat dense round icon="delete" color="negative" @click="$emit('remove-line', line.id)" />
          </q-item-section>
        </q-item>
        <q-item v-if="!(ticket?.lines?.length)">
          <q-item-section class="text-grey-6">
            El ticket aún no tiene líneas.
          </q-item-section>
        </q-item>
      </q-list>
    </q-card-section>
  </q-card>
</template>

<script setup lang="ts">
import type { RetailTicketRow } from '../services/retail-pos.service';

defineProps<{
  ticket: RetailTicketRow | null;
  selectedLineId: number | null;
}>();

defineEmits<{
  (event: 'checkout'): void;
  (event: 'hold'): void;
  (event: 'remove-line', lineId: number): void;
  (event: 'select-line', lineId: number): void;
}>();
</script>

<style scoped>
.retail-panel {
  min-height: 100%;
}

.retail-panel__list {
  min-height: 420px;
}
</style>
