export const STORAGE_KEYS = {
  AUTH_ACCESS: 'necktral.auth.access',
  AUTH_REFRESH: 'necktral.auth.refresh',
  CTX_COMPANY_ID: 'necktral.ctx.company_id',
  CTX_BRANCH_ID: 'necktral.ctx.branch_id',
  UI_THEME: 'necktral.ui.theme',
  UI_DENSITY: 'necktral.ui.density',

  SYNC_DEVICE_ID: 'necktral.sync.device_id',
  SYNC_PUBLIC_KEY_B64: 'necktral.sync.public_key_b64',
  SYNC_SECRET_KEY_B64: 'necktral.sync.secret_key_b64',
  SYNC_COMPANY_ID: 'necktral.sync.company_id',
  SYNC_BRANCH_ID: 'necktral.sync.branch_id',
  SYNC_LAST_SEQUENCE: 'necktral.sync.last_sequence',
} as const;
