export function normalizeDashboardGridValue(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value.toLocaleLowerCase();
  if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint') {
    return `${value}`.toLocaleLowerCase();
  }
  if (value instanceof Date) return value.toISOString().toLocaleLowerCase();
  return '';
}

export function dashboardGridValueIncludes(value: unknown, normalizedQuery: string): boolean {
  if (!normalizedQuery) return true;
  return normalizeDashboardGridValue(value).includes(normalizedQuery);
}

export function formatDashboardGridValue(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (typeof value === 'string') return value;
  if (typeof value === 'number' || typeof value === 'boolean' || typeof value === 'bigint') {
    return String(value);
  }
  if (typeof value === 'symbol') {
    return value.description ?? '';
  }
  if (value instanceof Date) return value.toISOString();
  if (typeof value === 'object') {
    try {
      return JSON.stringify(value);
    } catch {
      return '';
    }
  }
  return '';
}

export function dashboardGridHeaderLabel(rawKey: string): string {
  return rawKey.replace(/_/g, ' ').toUpperCase();
}
