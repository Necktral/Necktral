export type InventoryShellExperience = 'workbench' | 'taskflow';

export function resolveInventoryShellExperience(shellMode: 'desktop' | 'mobile'): InventoryShellExperience {
  return shellMode === 'mobile' ? 'taskflow' : 'workbench';
}

export function canAccessInventoryModule(options: {
  allowedModules: readonly string[];
  hasBasePermission: boolean;
}): boolean {
  if (!options.hasBasePermission) return false;
  return options.allowedModules.includes('inventory');
}

export function createIdempotencyKey(prefix: 'receive' | 'issue'): string {
  if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
    return `inventory-${prefix}-${crypto.randomUUID()}`;
  }
  return `inventory-${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 10)}`;
}
