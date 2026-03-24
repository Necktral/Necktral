import { onMounted, onUnmounted } from 'vue';

type RetailShortcutHandlers = {
  focusSearch?: () => void;
  openCheckout?: () => void;
  openHold?: () => void;
  openDiscount?: () => void;
  removeLine?: () => void;
  increaseQty?: () => void;
  decreaseQty?: () => void;
  confirm?: () => void;
  cancel?: () => void;
  isSuspended?: () => boolean;
};

export function useRetailShortcuts(handlers: RetailShortcutHandlers) {
  function onKeydown(event: KeyboardEvent) {
    if (handlers.isSuspended?.()) {
      if (event.key === 'Escape') {
        handlers.cancel?.();
      }
      return;
    }

    if (event.key === 'F2') {
      event.preventDefault();
      handlers.focusSearch?.();
      return;
    }
    if (event.key === 'F4') {
      event.preventDefault();
      handlers.openCheckout?.();
      return;
    }
    if (event.key === 'F6') {
      event.preventDefault();
      handlers.openHold?.();
      return;
    }
    if (event.key === 'F8') {
      event.preventDefault();
      handlers.openDiscount?.();
      return;
    }
    if (event.ctrlKey && event.key === 'Backspace') {
      event.preventDefault();
      handlers.removeLine?.();
      return;
    }
    if (event.key === '+') {
      event.preventDefault();
      handlers.increaseQty?.();
      return;
    }
    if (event.key === '-') {
      event.preventDefault();
      handlers.decreaseQty?.();
      return;
    }
    if (event.key === 'Enter') {
      handlers.confirm?.();
      return;
    }
    if (event.key === 'Escape') {
      handlers.cancel?.();
    }
  }

  onMounted(() => window.addEventListener('keydown', onKeydown));
  onUnmounted(() => window.removeEventListener('keydown', onKeydown));
}
