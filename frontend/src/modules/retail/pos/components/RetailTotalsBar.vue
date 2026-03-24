<template>
  <div class="retail-totals-bar">
    <div class="retail-totals-bar__metric">
      <span>Subtotal</span>
      <strong>{{ ticket?.subtotal ?? '0.00' }}</strong>
    </div>
    <div class="retail-totals-bar__metric">
      <span>Impuesto</span>
      <strong>{{ ticket?.tax_total ?? '0.00' }}</strong>
    </div>
    <div class="retail-totals-bar__metric retail-totals-bar__metric--grand">
      <span>Total</span>
      <strong>{{ ticket?.total ?? '0.00' }}</strong>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { RetailTicketRow } from '../services/retail-pos.service';

defineProps<{
  ticket: RetailTicketRow | null;
}>();
</script>

<style scoped>
.retail-totals-bar {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.retail-totals-bar__metric {
  background: linear-gradient(145deg, #0f172a, #1f2937);
  border-radius: 14px;
  padding: 12px 14px;
  color: #f8fafc;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.retail-totals-bar__metric span {
  font-size: 12px;
  letter-spacing: 0.04em;
  opacity: 0.75;
}

.retail-totals-bar__metric strong {
  font-size: 22px;
}

.retail-totals-bar__metric--grand {
  background: linear-gradient(145deg, #0f766e, #14532d);
}
</style>
