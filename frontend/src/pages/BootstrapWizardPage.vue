<template>
  <q-page class="flex flex-center bg-grey-3">
    <q-card style="width: 800px; max-width: 95vw">
      <q-card-section>
        <div class="text-h5 text-primary text-center">System Onboarding</div>
      </q-card-section>

      <q-separator />

      <q-card-section>
        <q-stepper v-model="step" ref="stepper" color="primary" animated header-nav>
          <!-- Step 1: Admin Creation -->
          <q-step :name="1" title="Initial Admin" icon="security" :done="step > 1">
            <div v-if="!isFresh && !isAuthenticated">
              <div class="text-body1 q-mb-md">System is not fresh. Please login normally.</div>
              <q-btn flat label="Go to Login" to="/login" color="primary" />
            </div>
            <div v-else-if="isAuthenticated">
              <p>
                You are logged in as <strong>{{ authStore.user?.username }}</strong
                >.
              </p>
              <p>Continuing to organization setup...</p>
              <q-btn label="Next" color="primary" @click="step = 3" />
            </div>
            <q-form v-else @submit.prevent="createAdmin">
              <div class="row q-col-gutter-md">
                <div class="col-6">
                  <q-input
                    v-model="adminForm.first_name"
                    label="First Name"
                    outlined
                    dense
                    :rules="[(val) => !!val || 'Required']"
                  />
                </div>
                <div class="col-6">
                  <q-input
                    v-model="adminForm.last_name"
                    label="Last Name"
                    outlined
                    dense
                    :rules="[(val) => !!val || 'Required']"
                  />
                </div>
                <div class="col-12">
                  <q-input
                    v-model="adminForm.username"
                    label="Username"
                    outlined
                    dense
                    :rules="[(val) => !!val || 'Required']"
                  />
                </div>
                <div class="col-12">
                  <q-input
                    v-model="adminForm.email"
                    label="Email"
                    type="email"
                    outlined
                    dense
                    :rules="[(val) => !!val || 'Required']"
                  />
                </div>
                <div class="col-12">
                  <q-input
                    v-model="adminForm.password"
                    type="password"
                    label="Password"
                    outlined
                    dense
                    :rules="[(val) => !!val || 'Required']"
                  />
                </div>
                <div class="col-12">
                  <q-input
                    v-model="adminForm.setup_token"
                    type="password"
                    label="Setup Token (optional)"
                    outlined
                    dense
                  />
                </div>
              </div>
              <div class="q-mt-md flex justify-end">
                <q-btn type="submit" label="Create Admin" color="primary" :loading="loading" />
              </div>
            </q-form>
          </q-step>

          <!-- Step 2: Login (Only if not authenticated) -->
          <q-step :name="2" title="Verify Access" icon="login" :done="step > 2">
            <div v-if="isAuthenticated">
              <div class="text-positive q-mb-md">Access verified.</div>
              <q-btn label="Continue" color="primary" @click="step = 3" />
            </div>
            <div v-else>
              <p>Please login with the account you just created.</p>
              <q-form @submit.prevent="doLogin">
                <q-input v-model="loginForm.username" label="Username" outlined dense />
                <q-input
                  v-model="loginForm.password"
                  type="password"
                  label="Password"
                  class="q-mt-sm"
                  outlined
                  dense
                />
                <div class="q-mt-md">
                  <q-btn type="submit" label="Login" color="primary" :loading="loading" />
                </div>
              </q-form>
            </div>
          </q-step>

          <!-- Step 3: Organization -->
          <q-step :name="3" title="Organization" icon="business" :done="step > 3">
            <p class="text-grey-7">
              Setup your initial organization structure (Holding > Company > Branch).
            </p>
            <q-form @submit.prevent="createOrg">
              <div class="row q-col-gutter-sm">
                <div class="col-12 text-subtitle2 text-primary">Holding Company</div>
                <div class="col-12">
                  <q-input
                    v-model="orgForm.holding_name"
                    label="Holding Name"
                    outlined
                    dense
                    :rules="[(val) => !!val || 'Required']"
                  />
                </div>

                <div class="col-12 text-subtitle2 text-primary q-mt-sm">Operating Company</div>
                <div class="col-8">
                  <q-input
                    v-model="orgForm.company_name"
                    label="Company Name"
                    outlined
                    dense
                    :rules="[(val) => !!val || 'Required']"
                  />
                </div>
                <div class="col-4">
                  <q-input
                    v-model="orgForm.company_tax_id"
                    label="Tax ID"
                    outlined
                    dense
                    :rules="[(val) => !!val || 'Required']"
                  />
                </div>

                <div class="col-12 text-subtitle2 text-primary q-mt-sm">Main Branch</div>
                <div class="col-12">
                  <q-input
                    v-model="orgForm.branch_name"
                    label="Branch Name"
                    outlined
                    dense
                    :rules="[(val) => !!val || 'Required']"
                  />
                </div>
                <div class="col-12">
                  <q-input
                    v-model="orgForm.branch_address"
                    label="Branch Address"
                    outlined
                    dense
                    :rules="[(val) => !!val || 'Required']"
                  />
                </div>
              </div>
              <div class="q-mt-md flex justify-end">
                <q-btn type="submit" label="Complete Setup" color="positive" :loading="loading" />
              </div>
            </q-form>
          </q-step>
        </q-stepper>
      </q-card-section>
    </q-card>
  </q-page>
</template>

<script setup lang="ts">
import { ref, reactive, onMounted, computed } from 'vue';
import { useAuthStore } from 'src/stores/auth.store';
import { useRouter } from 'vue-router';
import { api } from 'src/boot/axios';
import { useQuasar } from 'quasar';

const authStore = useAuthStore();
const router = useRouter();
const $q = useQuasar();

const step = ref(1);
const loading = ref(false);

const isFresh = computed(() => authStore.bootstrapState.is_fresh);
const isAuthenticated = computed(() => authStore.isAuthenticated);

const adminForm = reactive({
  username: '',
  email: '',
  password: '',
  first_name: '',
  last_name: '',
  setup_token: (import.meta.env.VITE_SETUP_TOKEN as string | undefined) ?? '',
});

const loginForm = reactive({
  username: '',
  password: '',
});

const orgForm = reactive({
  holding_name: '',
  company_name: '',
  company_tax_id: '',
  branch_name: 'Main Branch',
  branch_address: '',
});

onMounted(async () => {
  // Check status
  await authStore.checkBootstrap();

  if (authStore.isAuthenticated) {
    // If authenticated but here, maybe setup is incomplete
    if (authStore.user?.is_setup_complete) {
      $q.notify({ type: 'info', message: 'Setup already complete' });
      await router.push('/dashboard');
    } else {
      step.value = 3; // jump to org setup
    }
  } else {
    if (!authStore.bootstrapState.is_fresh) {
      // Not fresh, not auth -> go to login
      $q.notify({ type: 'warning', message: 'System is already initialized.' });
      await router.push('/login');
    }
  }
});

async function createAdmin() {
  loading.value = true;
  try {
    // Initial Admin Check
    // We can use the public endpoint
    const payload = {
      username: adminForm.username,
      email: adminForm.email,
      password: adminForm.password,
      first_name: adminForm.first_name,
      last_name: adminForm.last_name,
    };
    const headers: Record<string, string> = {};
    if (adminForm.setup_token) {
      headers['X-Setup-Token'] = adminForm.setup_token;
    }
    await api.post('/auth/bootstrap/init/', payload, { headers });
    $q.notify({ type: 'positive', message: 'Admin created successfully' });

    // Pre-fill login
    loginForm.username = adminForm.username;

    step.value = 2;
  } catch (error) {
    console.error(error);
    $q.notify({ type: 'negative', message: 'Failed to create admin' });
  } finally {
    loading.value = false;
  }
}

async function doLogin() {
  loading.value = true;
  try {
    await authStore.login(loginForm.username, loginForm.password);
    $q.notify({ type: 'positive', message: 'Login successful' });
    step.value = 3;
  } catch {
    $q.notify({ type: 'negative', message: 'Login failed' });
  } finally {
    loading.value = false;
  }
}

async function createOrg() {
  loading.value = true;
  try {
    await api.post('/auth/bootstrap/org/', orgForm);
    $q.notify({ type: 'positive', message: 'Organization setup complete!' });

    // Refresh me to update is_setup_complete
    await authStore.fetchMe();

    // Redirect to dashboard
    await router.push('/dashboard');
  } catch (error) {
    // Usar tipo desconocido en vez de any
    const err = error as { response?: { data?: { detail?: string } } };
    $q.notify({ type: 'negative', message: err.response?.data?.detail || 'Setup failed' });
  } finally {
    loading.value = false;
  }
}
</script>
