<template>
  <q-dialog v-model="open" persistent>
    <q-card class="app-card" style="width: 640px; max-width: 96vw">
      <q-card-section class="q-pb-none">
        <q-input
          ref="searchInput"
          v-model="query"
          outlined
          dense
          autofocus
          placeholder="Buscar acción o ruta de inventario..."
          @keydown.enter.prevent="goFirst"
        >
          <template #prepend>
            <q-icon name="search" />
          </template>
        </q-input>
      </q-card-section>

      <q-list separator style="max-height: 360px" class="scroll">
        <q-item
          v-for="cmd in filteredCommands"
          :key="cmd.id"
          clickable
          @click="run(cmd.to)"
        >
          <q-item-section avatar>
            <q-icon :name="cmd.icon" />
          </q-item-section>
          <q-item-section>
            <q-item-label>{{ cmd.label }}</q-item-label>
            <q-item-label caption>{{ cmd.to }}</q-item-label>
          </q-item-section>
        </q-item>
      </q-list>

      <q-separator />

      <q-card-section class="text-caption text-grey-7">
        Atajos: <b>Alt+1..6</b> para secciones y <b>/</b> para buscar en tabla activa.
      </q-card-section>
    </q-card>
  </q-dialog>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useRouter } from 'vue-router';
import { UI_ROUTE_PATHS } from 'src/shared/ui/business-terms';

type PaletteCommand = {
  id: string;
  label: string;
  icon: string;
  to: string;
};

const props = defineProps<{ modelValue: boolean }>();
const emit = defineEmits<{ (event: 'update:modelValue', value: boolean): void }>();

const router = useRouter();
const query = ref('');
const searchInput = ref<{ focus: () => void } | null>(null);

const open = computed({
  get: () => props.modelValue,
  set: (value: boolean) => emit('update:modelValue', value),
});

const commands: PaletteCommand[] = [
  { id: 'inv-dashboard', label: 'Inventario · Dashboard', icon: 'inventory_2', to: UI_ROUTE_PATHS.inventoryDashboard },
  { id: 'inv-items', label: 'Inventario · Ítems', icon: 'category', to: UI_ROUTE_PATHS.inventoryItems },
  { id: 'inv-warehouses', label: 'Inventario · Almacenes', icon: 'warehouse', to: UI_ROUTE_PATHS.inventoryWarehouses },
  { id: 'inv-movements', label: 'Inventario · Movimientos', icon: 'swap_horiz', to: UI_ROUTE_PATHS.inventoryMovements },
  { id: 'inv-balances', label: 'Inventario · Balances', icon: 'balance', to: UI_ROUTE_PATHS.inventoryBalances },
  { id: 'inv-kardex', label: 'Inventario · Kardex', icon: 'receipt_long', to: UI_ROUTE_PATHS.inventoryKardex },
];

const filteredCommands = computed(() => {
  const q = query.value.trim().toLowerCase();
  if (!q) return commands;
  return commands.filter((cmd) => cmd.label.toLowerCase().includes(q) || cmd.to.toLowerCase().includes(q));
});

watch(
  () => props.modelValue,
  (value) => {
    if (value) {
      query.value = '';
      setTimeout(() => searchInput.value?.focus(), 0);
    }
  },
);

async function run(path: string): Promise<void> {
  open.value = false;
  await router.push(path);
}

function goFirst(): void {
  const first = filteredCommands.value[0];
  if (!first) return;
  void run(first.to);
}
</script>
