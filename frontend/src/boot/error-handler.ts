/**
 * Global error handler — catches unhandled errors and promise rejections
 * and surfaces them via Quasar Notify so they never go silently lost.
 *
 * Registered as a Quasar boot file in `quasar.config.ts`.
 */
import { boot } from 'quasar/wrappers';
import { Notify } from 'quasar';

export default boot(({ app }) => {
  // -----------------------------------------------------------------------
  // Vue component errors (render, lifecycle hooks, watchers, event handlers)
  // -----------------------------------------------------------------------
  app.config.errorHandler = (err, _instance, info) => {
    console.error('[Vue errorHandler]', info, err);

    const message =
      err instanceof Error ? err.message : String(err);

    Notify.create({
      type: 'negative',
      message: `Error inesperado: ${message}`,
      caption: info,
      timeout: 5000,
    });
  };

  // -----------------------------------------------------------------------
  // Unhandled promise rejections (global)
  // -----------------------------------------------------------------------
  window.addEventListener('unhandledrejection', (event) => {
    console.error('[unhandledrejection]', event.reason);

    const message =
      event.reason instanceof Error
        ? event.reason.message
        : String(event.reason);

    // Skip "ContextMissing" — these are handled by the router guard
    if (message.startsWith('ContextMissing')) return;

    Notify.create({
      type: 'negative',
      message: `Error no manejado: ${message}`,
      timeout: 5000,
    });
  });
});
