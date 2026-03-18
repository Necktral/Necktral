<template>
  <q-page class="q-pa-md" style="max-width: 720px; margin: 0 auto">
    <div class="text-h5 q-mb-sm">Configurar 2FA</div>
    <div class="text-body2 text-grey-7 q-mb-lg">
      Habilita 2FA para cuentas admin. Escanea el secreto con tu app TOTP o usa el `otpauth_uri`
      para generar el QR en otra herramienta.
    </div>

    <q-card class="q-mb-lg">
      <q-card-section>
        <div class="text-subtitle1 q-mb-sm">1) Generar secreto</div>
        <q-btn color="primary" label="Generar secreto" :loading="loading" @click="onGenerate" />
      </q-card-section>

      <q-separator />

      <q-card-section v-if="secret">
        <div class="text-subtitle2 q-mb-xs">Secret</div>
        <q-input v-model="secret" outlined readonly class="q-mb-md" />

        <div class="text-subtitle2 q-mb-xs">OTPAuth URI</div>
        <q-input v-model="otpauthUri" outlined readonly />

        <div v-if="qrDataUrl" class="q-mt-md">
          <div class="text-subtitle2 q-mb-xs">QR</div>
          <img :src="qrDataUrl" alt="QR 2FA" style="max-width: 220px" />
        </div>
      </q-card-section>
    </q-card>

    <q-card>
      <q-card-section>
        <div class="text-subtitle1 q-mb-sm">2) Confirmar codigo</div>
        <q-form @submit.prevent="onConfirm">
          <q-input v-model="code" label="Codigo" outlined />
          <div class="q-mt-md">
            <q-btn
              color="primary"
              label="Confirmar"
              type="submit"
              :disable="!secret"
              :loading="loading"
            />
          </div>
        </q-form>
      </q-card-section>

      <q-separator />

      <q-card-section>
        <div class="text-subtitle1 q-mb-sm">3) Deshabilitar (opcional)</div>
        <q-form @submit.prevent="onDisable">
          <q-input v-model="disableCode" label="Codigo" outlined />
          <div class="q-mt-md">
            <q-btn color="negative" label="Deshabilitar" type="submit" :loading="loading" />
          </div>
        </q-form>
      </q-card-section>
    </q-card>

    <q-banner v-if="message" class="q-mt-lg" dense rounded>
      {{ message }}
    </q-banner>
  </q-page>
</template>

<script setup lang="ts">
import { isAxiosError } from 'axios';
import { ref } from 'vue';
import { authApi } from 'src/boot/axios';
import QRCode from 'qrcode';

const loading = ref(false);
const secret = ref('');
const otpauthUri = ref('');
const qrDataUrl = ref('');
const code = ref('');
const disableCode = ref('');
const message = ref('');

async function onGenerate() {
  loading.value = true;
  message.value = '';

  try {
    const { data } = await authApi.post('/backend/auth/2fa/enable/', {});
    secret.value = String(data?.secret ?? '');
    otpauthUri.value = String(data?.otpauth_uri ?? '');
    qrDataUrl.value = otpauthUri.value
      ? await QRCode.toDataURL(otpauthUri.value, { margin: 1, width: 220 })
      : '';
  } catch (e: unknown) {
    message.value = errorMessage(e) || 'No se pudo generar el secreto.';
  } finally {
    loading.value = false;
  }
}

async function onConfirm() {
  loading.value = true;
  message.value = '';

  try {
    await authApi.post('/backend/auth/2fa/confirm/', { code: code.value.trim() });
    message.value = '2FA habilitado correctamente.';
  } catch (e: unknown) {
    message.value = errorMessage(e) || 'Codigo invalido.';
  } finally {
    loading.value = false;
  }
}

async function onDisable() {
  loading.value = true;
  message.value = '';

  try {
    await authApi.post('/backend/auth/2fa/disable/', { code: disableCode.value.trim() });
    secret.value = '';
    otpauthUri.value = '';
    qrDataUrl.value = '';
    message.value = '2FA deshabilitado.';
  } catch (e: unknown) {
    message.value = errorMessage(e) || 'No se pudo deshabilitar 2FA.';
  } finally {
    loading.value = false;
  }
}

function errorMessage(e: unknown): string {
  if (isAxiosError(e)) {
    const data: unknown = e.response?.data;
    if (typeof data === 'object' && data !== null && 'detail' in data) {
      return String((data as { detail: string }).detail);
    }
    return e.message;
  }
  if (e instanceof Error) return e.message;
  return String(e);
}
</script>
