<template>
  <AppContainer>
    <AppPageHeader title="Sync · Offline" subtitle="Enrollment (device) + Batch firmado (/sync/*)">
      <template #badges>
        <q-badge outline color="primary">Company: {{ companyLabel }}</q-badge>
        <q-badge outline>Branch: {{ branchLabel }}</q-badge>
        <q-badge outline :color="deviceEnrolled ? 'positive' : 'negative'">
          Device: {{ deviceEnrolled ? 'ENROLLED' : 'NOT ENROLLED' }}
        </q-badge>
        <q-badge outline v-if="device.deviceId">ID: {{ device.deviceId }}</q-badge>
        <q-badge outline>Outbox pending: {{ outbox.pending }}</q-badge>
        <q-badge outline color="negative">Outbox failed: {{ outbox.failed }}</q-badge>
      </template>

      <template #actions>
        <q-btn flat label="Recargar" :disable="loading" @click="reload" />
        <q-btn
          color="primary"
          label="Flush outbox"
          :disable="loading"
          @click="doFlush"
          title="Envía comandos pendientes via /api/sync/batch/"
        />
      </template>
    </AppPageHeader>

    <div class="q-mt-md row q-col-gutter-md">
      <div class="col-12 col-lg-6">
        <q-card class="app-card">
          <q-card-section>
            <div class="text-h6">Dispositivo local (este navegador)</div>
            <div class="text-caption">
              Se guarda en localStorage. Requisito para firmar comandos (Ed25519) y enviar batches.
            </div>
          </q-card-section>

          <q-separator />

          <q-card-section>
            <q-banner v-if="deviceScopeMismatch" dense rounded class="q-mb-md" inline-actions>
              <div>
                <div class="text-weight-medium">Scope mismatch</div>
                <div class="text-caption">
                  El device fue enrolado en otro contexto. Cambia a ese company/branch o borra el
                  device local.
                </div>
              </div>
              <template #action>
                <q-btn flat color="negative" label="Borrar device" @click="clearDevice" />
              </template>
            </q-banner>

            <div class="row q-col-gutter-md">
              <div class="col-12">
                <q-input
                  v-model="enrollmentCode"
                  outlined
                  label="Enrollment code"
                  placeholder="Pega el enrollment_code"
                />
              </div>
              <div class="col-12">
                <q-input
                  v-model="deviceLabel"
                  outlined
                  label="Label (opcional)"
                  placeholder="Ej: Companion Inventario"
                />
              </div>
              <div class="col-12">
                <q-btn
                  color="primary"
                  label="Enrolar este device"
                  :disable="loading || !enrollmentCode.trim()"
                  @click="enrollLocal"
                />
                <q-btn
                  flat
                  color="negative"
                  class="q-ml-sm"
                  label="Borrar device"
                  :disable="loading"
                  @click="clearDevice"
                />
              </div>
            </div>

            <q-separator spaced />

            <div class="text-caption">
              Secuencia local (lastSequence):
              <span class="text-weight-medium">{{ device.lastSequence }}</span>
            </div>
          </q-card-section>
        </q-card>
      </div>

      <div class="col-12 col-lg-6">
        <q-card class="app-card">
          <q-card-section>
            <div class="text-h6">Generar enrollment code (challenge)</div>
            <div class="text-caption">Requiere permiso: <b>sync.device.enroll</b></div>
          </q-card-section>

          <q-separator />

          <q-card-section>
            <div class="row q-col-gutter-md">
              <div class="col-12">
                <q-input
                  v-model="labelHint"
                  outlined
                  label="Label hint"
                  placeholder="Ej: Companion Inventario"
                />
              </div>
              <div class="col-12 col-md-6">
                <q-input
                  v-model.number="expiresIn"
                  type="number"
                  outlined
                  label="Expira (min)"
                  :min="1"
                  :max="1440"
                />
              </div>
              <div class="col-12 col-md-6">
                <q-input
                  v-model="branchOverride"
                  outlined
                  label="Branch ID (opcional)"
                  placeholder="Vacío = branch activo"
                />
              </div>

              <div class="col-12">
                <q-btn
                  color="primary"
                  label="Crear code"
                  :disable="loading"
                  @click="createChallenge"
                />
              </div>

              <div class="col-12" v-if="challenge">
                <q-input
                  :model-value="challenge.enrollment_code"
                  outlined
                  readonly
                  label="Enrollment code"
                >
                  <template #append>
                    <q-btn flat icon="content_copy" @click="copyChallengeCode" />
                  </template>
                </q-input>
                <div class="text-caption q-mt-sm">
                  Expira: {{ challenge.expires_at }} · Challenge: {{ challenge.challenge_id }}
                </div>
              </div>
            </div>
          </q-card-section>
        </q-card>
      </div>
    </div>

    <div class="q-mt-md">
      <q-card class="app-card">
        <q-card-section class="row items-center justify-between">
          <div>
            <div class="text-h6">Outbox</div>
            <div class="text-caption">Pending/failed se calculan desde IndexedDB.</div>
          </div>
          <div>
            <q-btn flat label="Recargar" :disable="loading" @click="outbox.refreshCounts" />
          </div>
        </q-card-section>

        <q-separator />

        <q-card-section>
          <q-banner v-if="outbox.lastFlush" dense rounded>
            Último flush: sent={{ outbox.lastFlush.sent }} · failed={{ outbox.lastFlush.failed }} ·
            remaining={{ outbox.lastFlush.remaining }} · at={{
              new Date(outbox.lastFlush.at).toISOString()
            }}
          </q-banner>
        </q-card-section>
      </q-card>

      <q-banner v-if="errorMsg" class="q-mt-md" dense rounded>
        {{ errorMsg }}
      </q-banner>
    </div>
  </AppContainer>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';

import { api } from 'src/boot/axios';
import { extractErrorMessage } from 'src/core/http/errors';
import { clearSyncDevice, readSyncDevice } from 'src/core/storage/sync_device';
import { enrollSyncDevice } from 'src/core/sync/device';
import { useAclStore } from 'src/stores/acl.store';
import { useContextStore } from 'src/stores/context.store';
import { useOfflineOutboxStore } from 'src/stores/offline_outbox.store';

type ChallengeResponse = {
  challenge_id: string;
  enrollment_code: string;
  expires_at: string;
  company_id: number;
  branch_id: number | null;
};

const acl = useAclStore();
const ctx = useContextStore();
const outbox = useOfflineOutboxStore();

ctx.initFromStorage();

const loading = ref(false);
const errorMsg = ref<string | null>(null);

const device = ref(readSyncDevice());

const enrollmentCode = ref('');
const deviceLabel = ref('Companion Inventario');

const labelHint = ref('Companion Inventario');
const expiresIn = ref(15);
const branchOverride = ref('');
const challenge = ref<ChallengeResponse | null>(null);

const companyLabel = computed(() => {
  const id = ctx.activeCompanyId;
  return acl.companyName(id) ?? id ?? '—';
});

const branchLabel = computed(() => {
  const c = ctx.activeCompanyId;
  const b = ctx.activeBranchId;
  return acl.branchName(c, b) ?? b ?? '—';
});

const deviceEnrolled = computed(() => Boolean(device.value.deviceId && device.value.secretKeyB64));

const deviceScopeMismatch = computed(() => {
  if (!deviceEnrolled.value) return false;
  if (!ctx.activeCompanyId) return false;

  if (device.value.companyId && device.value.companyId !== ctx.activeCompanyId) return true;
  if (device.value.branchId && ctx.activeBranchId && device.value.branchId !== ctx.activeBranchId)
    return true;
  return false;
});

function refreshDevice() {
  device.value = readSyncDevice();
}

async function reload() {
  loading.value = true;
  errorMsg.value = null;
  try {
    refreshDevice();
    await outbox.refreshCounts();
  } catch (e) {
    errorMsg.value = extractErrorMessage(e);
  } finally {
    loading.value = false;
  }
}

async function createChallenge() {
  loading.value = true;
  errorMsg.value = null;
  challenge.value = null;

  try {
    const branchId = (branchOverride.value || ctx.activeBranchId || '').trim();

    const payload: Record<string, unknown> = {
      label_hint: labelHint.value,
      expires_in_minutes: Number(expiresIn.value || 15),
    };

    if (branchId) payload.branch_id = Number(branchId);

    const { data } = await api.post<ChallengeResponse>('/sync/enrollment/challenges/', payload);
    challenge.value = data;
  } catch (e) {
    errorMsg.value = extractErrorMessage(e);
  } finally {
    loading.value = false;
  }
}

async function copyChallengeCode() {
  if (!challenge.value) return;
  try {
    await navigator.clipboard.writeText(challenge.value.enrollment_code);
  } catch (e) {
    errorMsg.value = extractErrorMessage(e);
  }
}

async function enrollLocal() {
  loading.value = true;
  errorMsg.value = null;

  try {
    const code = enrollmentCode.value.trim();
    await enrollSyncDevice(api, { enrollmentCode: code, label: deviceLabel.value });
    refreshDevice();
  } catch (e) {
    errorMsg.value = extractErrorMessage(e);
  } finally {
    loading.value = false;
  }
}

function clearDevice() {
  clearSyncDevice();
  refreshDevice();
}

async function doFlush() {
  loading.value = true;
  errorMsg.value = null;

  try {
    await outbox.flush();
  } catch (e) {
    errorMsg.value = extractErrorMessage(e);
  } finally {
    loading.value = false;
  }
}

onMounted(async () => {
  await reload();
});
</script>
