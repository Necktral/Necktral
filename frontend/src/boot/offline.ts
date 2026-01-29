import { boot } from 'quasar/wrappers';
import { useOfflineOutboxStore } from 'src/stores/offline_outbox.store';

export default boot(() => {
  const outbox = useOfflineOutboxStore();

  // Intento de flush al arrancar (si hay internet)
  if (typeof navigator !== 'undefined' && navigator.onLine) {
    void outbox.flush();
  } else {
    void outbox.refreshCounts();
  }

  // Al recuperar conectividad, enviamos pendientes.
  if (typeof window !== 'undefined') {
    window.addEventListener('online', () => {
      void outbox.flush();
    });
  }
});
