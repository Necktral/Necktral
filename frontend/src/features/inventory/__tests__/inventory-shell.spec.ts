import { describe, expect, it } from 'vitest';

import {
  canAccessInventoryModule,
  createIdempotencyKey,
  resolveInventoryShellExperience,
} from 'src/features/inventory/inventory-shell';

describe('inventory shell helpers', () => {
  it('resolves shell experience from bootstrap shell mode', () => {
    expect(resolveInventoryShellExperience('desktop')).toBe('workbench');
    expect(resolveInventoryShellExperience('mobile')).toBe('taskflow');
  });

  it('gates inventory access by allowed_modules + ACL base permission', () => {
    expect(
      canAccessInventoryModule({ allowedModules: ['inventory', 'dashboard'], hasBasePermission: true }),
    ).toBe(true);
    expect(canAccessInventoryModule({ allowedModules: ['dashboard'], hasBasePermission: true })).toBe(false);
    expect(
      canAccessInventoryModule({ allowedModules: ['inventory', 'dashboard'], hasBasePermission: false }),
    ).toBe(false);
  });

  it('creates idempotency key with stable prefix', () => {
    const receiveKey = createIdempotencyKey('receive');
    const issueKey = createIdempotencyKey('issue');

    expect(receiveKey.startsWith('inventory-receive-')).toBe(true);
    expect(issueKey.startsWith('inventory-issue-')).toBe(true);
    expect(receiveKey).not.toBe(issueKey);
  });
});
