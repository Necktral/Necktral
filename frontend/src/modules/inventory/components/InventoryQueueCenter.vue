<template>
  <q-card class="app-card">
    <q-card-section class="row items-center justify-between q-col-gutter-sm">
      <div class="col">
        <div class="text-subtitle1">Cola Offline</div>
        <div class="text-caption text-grey-7">Estado de sincronización de comandos de inventario.</div>
      </div>
      <div class="col-auto row items-center q-gutter-xs">
        <q-badge outline color="primary">Pendientes: {{ pendingCount }}</q-badge>
        <q-badge outline color="warning" v-if="conflictCount > 0">Conflictos: {{ conflictCount }}</q-badge>
        <q-badge outline v-if="doneCount > 0">Done: {{ doneCount }}</q-badge>
      </div>
    </q-card-section>

    <q-separator />

    <q-card-section class="row items-center q-gutter-sm">
      <q-btn
        color="primary"
        icon="sync"
        label="Sincronizar ahora"
        :loading="offline.syncing"
        @click="syncNow"
      />
      <q-btn flat icon="cleaning_services" label="Limpiar done" @click="purgeDone" />
      <q-badge v-if="offline.lastSyncError" color="negative" outline>
        {{ offline.lastSyncError }}
      </q-badge>
    </q-card-section>

    <q-separator v-if="conflicts.length > 0" />

    <q-list v-if="conflicts.length > 0" dense>
      <q-item-label header>Conflictos por resolver</q-item-label>
      <q-item v-for="row in conflicts" :key="row.id" clickable>
        <q-item-section>
          <q-item-label>{{ row.type }}</q-item-label>
          <q-item-label caption>
            {{ row.last_error_code || 'INVENTORY_COMMAND_REJECTED' }} · {{ row.last_error_detail || 'Sin detalle' }}
          </q-item-label>
        </q-item-section>
        <q-item-section side>
          <div class="row items-center q-gutter-xs">
            <q-btn dense flat icon="replay" @click.stop="retry(row.id)" />
            <q-btn dense flat icon="task_alt" @click.stop="markDone(row.id)" />
          </div>
        </q-item-section>
      </q-item>
    </q-list>
  </q-card>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useInventoryOfflineStore } from 'src/modules/inventory/stores/inventory-offline.store';

const offline = useInventoryOfflineStore();

const pendingCount = computed(() => offline.pendingCount);
const conflictCount = computed(() => offline.conflictCount);
const doneCount = computed(() => offline.doneCount);
const conflicts = computed(() => offline.queue.filter((row) => row.status === 'CONFLICT'));

function syncNow(): void {
  void offline.flush();
}

function purgeDone(): void {
  void offline.purgeDone();
}

function retry(id: string): void {
  void offline.retryConflict(id);
}

function markDone(id: string): void {
  void offline.markConflictAsDone(id);
}
</script>
