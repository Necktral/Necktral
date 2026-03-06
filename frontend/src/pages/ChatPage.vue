<template>
  <q-page>
    <AppContainer>
      <AppPageHeader title="Chat" subtitle="Mensajes del equipo" />

      <q-banner
        v-if="!isAuthenticated"
        class="q-mb-md bg-warning text-white"
        dense
        rounded
        inline-actions
      >
        <q-icon name="lock" left />
        You must be logged in to send messages. Please run
        <router-link to="/login" class="text-white q-ml-xs">/login</router-link>
        para acceder a github cli
        <template #action>
          <q-btn flat color="white" label="Ir a Login" to="/login" />
        </template>
      </q-banner>

      <q-card class="q-mb-md">
        <q-card-section>
          <div
            ref="messagesContainer"
            class="messages-container q-pa-sm"
            style="height: 400px; overflow-y: auto"
          >
            <div v-if="loading" class="flex flex-center" style="height: 100%">
              <q-spinner color="primary" size="2em" />
            </div>
            <div v-else-if="messages.length === 0" class="flex flex-center text-grey-6" style="height: 100%">
              No hay mensajes aún. ¡Sé el primero en escribir!
            </div>
            <div v-else>
              <div
                v-for="msg in messages"
                :key="msg.id"
                class="q-mb-sm"
              >
                <span class="text-weight-bold q-mr-xs">{{ msg.sender_username }}:</span>
                <span>{{ msg.content }}</span>
                <span class="text-caption text-grey-6 q-ml-sm">{{ formatDate(msg.created_at) }}</span>
              </div>
            </div>
          </div>
        </q-card-section>

        <q-separator />

        <q-card-section>
          <q-banner
            v-if="!isAuthenticated"
            class="q-mb-sm bg-grey-2"
            dense
            rounded
          >
            <q-icon name="info" left />
            You must be logged in to send messages. Please run
            <router-link to="/login">/login</router-link>
            para acceder a github cli
          </q-banner>

          <div class="row q-gutter-sm items-center">
            <div class="col">
              <q-input
                v-model="newMessage"
                outlined
                dense
                placeholder="Escribe un mensaje..."
                :disable="!isAuthenticated || sending"
                @keyup.enter="onSend"
              />
            </div>
            <div class="col-auto">
              <q-btn
                color="primary"
                icon="send"
                :loading="sending"
                :disable="!isAuthenticated || !newMessage.trim()"
                @click="onSend"
              />
            </div>
          </div>

          <div v-if="errorMsg" class="text-negative q-mt-sm text-caption">
            {{ errorMsg }}
          </div>
        </q-card-section>
      </q-card>
    </AppContainer>
  </q-page>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, ref } from 'vue';
import { useAuthStore } from 'src/stores/auth.store';
import AppContainer from 'src/ui/AppContainer.vue';
import AppPageHeader from 'src/ui/AppPageHeader.vue';
import { listMessages, sendMessage, type ChatMessage } from 'src/services/chat.service';
import { extractErrorMessage } from 'src/core/http/errors';

const auth = useAuthStore();
const isAuthenticated = computed(() => auth.isAuthenticated);

const messages = ref<ChatMessage[]>([]);
const loading = ref(false);
const newMessage = ref('');
const sending = ref(false);
const errorMsg = ref('');
const messagesContainer = ref<HTMLElement | null>(null);

function formatDate(iso: string): string {
  try {
    return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  } catch {
    return iso;
  }
}

async function scrollToBottom() {
  await nextTick();
  if (messagesContainer.value) {
    messagesContainer.value.scrollTop = messagesContainer.value.scrollHeight;
  }
}

async function loadMessages() {
  if (!isAuthenticated.value) return;
  loading.value = true;
  errorMsg.value = '';
  try {
    messages.value = await listMessages();
    await scrollToBottom();
  } catch (e) {
    errorMsg.value = extractErrorMessage(e);
  } finally {
    loading.value = false;
  }
}

async function onSend() {
  if (!isAuthenticated.value) {
    errorMsg.value =
      'You must be logged in to send messages. Please run /login para acceder a github cli';
    return;
  }
  const content = newMessage.value.trim();
  if (!content) return;

  sending.value = true;
  errorMsg.value = '';
  try {
    const msg = await sendMessage(content);
    messages.value.push(msg);
    newMessage.value = '';
    await scrollToBottom();
  } catch (e) {
    errorMsg.value = extractErrorMessage(e);
  } finally {
    sending.value = false;
  }
}

onMounted(() => {
  void loadMessages();
});
</script>
