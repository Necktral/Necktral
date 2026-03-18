<template>
  <q-page class="flex flex-center bg-grey-3">
    <q-card style="width: 400px; max-width: 90vw">
      <q-card-section>
        <div class="text-h6 text-center text-primary">Change Password</div>
        <div class="text-caption text-center text-grey">
          Your account requires a password change.
        </div>
      </q-card-section>

      <q-card-section>
        <q-form @submit.prevent="submitChange">
          <q-input
            v-model="form.old_password"
            label="Current Password"
            type="password"
            outlined
            dense
            :rules="[(val) => !!val || 'Required']"
          />
          <q-input
            v-model="form.new_password"
            label="New Password"
            type="password"
            class="q-mt-md"
            outlined
            dense
            :rules="[(val) => !!val || 'Required']"
          />
          <q-input
            v-model="form.confirm_password"
            label="Confirm New Password"
            type="password"
            class="q-mt-sm"
            outlined
            dense
            :rules="[
              (val) => !!val || 'Required',
              (val) => val === form.new_password || 'Passwords must match',
            ]"
          />

          <div class="q-mt-lg">
            <q-btn
              label="Update Password"
              type="submit"
              color="primary"
              class="full-width"
              :loading="loading"
            />
          </div>
        </q-form>
      </q-card-section>
    </q-card>
  </q-page>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { api } from 'src/boot/axios';
import { useAuthStore } from 'src/stores/auth.store';
import { useQuasar } from 'quasar';

const router = useRouter();
const authStore = useAuthStore();
const $q = useQuasar();

const loading = ref(false);
const form = reactive({
  old_password: '',
  new_password: '',
  confirm_password: '',
});

async function submitChange() {
  loading.value = true;
  try {
    await api.post('/backend/auth/password/', form);

    $q.notify({ type: 'positive', message: 'Password updated successfully' });

    // Update local state
    if (authStore.user) {
      authStore.user.must_change_password = false;
    }

    await router.push('/dashboard');
  } catch (error) {
    const err = error as { response?: { data?: { detail?: string } } };
    const msg = err.response?.data?.detail || 'Failed to update password';
    $q.notify({ type: 'negative', message: msg });
  } finally {
    loading.value = false;
  }
}
</script>
