import { computed, onMounted, onUnmounted, ref } from 'vue';

export type ScannerInputEvent = {
  raw: string;
  normalized: string;
  startedAt: string;
  completedAt: string;
  source: 'keyboard_wedge';
};

type RetailScannerOptions = {
  enabled?: () => boolean;
  allowInEditable?: boolean;
  minLength?: number;
  idleTimeoutMs?: number;
  onScan: (event: ScannerInputEvent) => void | Promise<void>;
};

function normalizeScan(raw: string): string {
  return raw.replace(/\s+/g, '').trim().toUpperCase();
}

function isPrintableKey(event: KeyboardEvent): boolean {
  return event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey;
}

function isEditableTarget(target: EventTarget | null): boolean {
  if (!target) return false;
  if (typeof Element === 'undefined' || !(target instanceof Element)) return false;
  const node = target;
  if (typeof HTMLInputElement !== 'undefined' && node instanceof HTMLInputElement) return !node.disabled && !node.readOnly;
  if (typeof HTMLTextAreaElement !== 'undefined' && node instanceof HTMLTextAreaElement) return !node.disabled && !node.readOnly;
  if (typeof HTMLSelectElement !== 'undefined' && node instanceof HTMLSelectElement) return !node.disabled;
  return Boolean(node instanceof HTMLElement && (node.isContentEditable || node.closest('[contenteditable="true"]')));
}

export function useRetailScannerInput(options: RetailScannerOptions) {
  const minLength = Math.max(3, Number(options.minLength ?? 6));
  const idleTimeoutMs = Math.max(20, Number(options.idleTimeoutMs ?? 60));
  const enabled = options.enabled ?? (() => true);
  const allowInEditable = options.allowInEditable ?? false;

  const buffer = ref('');
  const startedAt = ref<string>('');
  const isCapturing = ref(false);
  let flushTimer: number | null = null;

  async function flushBuffer() {
    if (!buffer.value) return;
    const raw = buffer.value;
    const normalized = normalizeScan(raw);
    const started = startedAt.value || new Date().toISOString();
    const completed = new Date().toISOString();

    buffer.value = '';
    startedAt.value = '';
    isCapturing.value = false;

    if (normalized.length < minLength) return;

    await options.onScan({
      raw,
      normalized,
      startedAt: started,
      completedAt: completed,
      source: 'keyboard_wedge',
    });
  }

  function clearFlushTimer() {
    if (flushTimer !== null) {
      window.clearTimeout(flushTimer);
      flushTimer = null;
    }
  }

  function scheduleFlush() {
    clearFlushTimer();
    flushTimer = window.setTimeout(() => {
      void flushBuffer();
    }, idleTimeoutMs);
  }

  function onKeydown(event: KeyboardEvent) {
    if (!enabled()) return;
    if (event.key === 'Escape') return;
    if (!allowInEditable && !isCapturing.value && isEditableTarget(event.target)) return;

    if (event.key === 'Enter') {
      if (!buffer.value) return;
      event.preventDefault();
      clearFlushTimer();
      void flushBuffer();
      return;
    }

    if (!isPrintableKey(event)) return;

    if (!startedAt.value) {
      startedAt.value = new Date().toISOString();
    }
    isCapturing.value = true;
    buffer.value = `${buffer.value}${event.key}`;
    event.preventDefault();
    scheduleFlush();
  }

  onMounted(() => {
    window.addEventListener('keydown', onKeydown, true);
  });

  onUnmounted(() => {
    clearFlushTimer();
    window.removeEventListener('keydown', onKeydown, true);
  });

  return {
    isCapturing: computed(() => isCapturing.value),
  };
}
