# ADR — Semántica Offline de Inventarios (Slice 4.1)

## Estado
Aprobado.

## Contexto
Slice 4.1 habilita operación offline controlada de Inventarios para `receive/issue` sobre arquitectura canónica:

1. Bootstrap único de sesión/capacidades (`/api/auth/bootstrap/session/`).
2. Gating obligatorio por `allowed_modules ∩ ACL`.
3. Shell UX derivado de servidor (`shell_mode`), sin política paralela en frontend.
4. Sincronización diferida por comandos firmados en `/api/sync/batch/`.

El riesgo principal de producto es confundir aceptación local con confirmación canónica.

## Decisión
Se fija semántica oficial para Inventarios offline:

1. `read` se mantiene `online-first`.
2. `capture/commit` offline aplica solo a `receive/issue` y solo como **buffer local diferido**.
3. El servidor sigue siendo la única fuente de verdad final.
4. Estados operativos de cola y significado:
   - `PENDING`: captura local aceptada (sin confirmación canónica).
   - `SYNCING`: comando en reintento contra backend.
   - `APPLIED`: confirmado por servidor (única confirmación final).
   - `FAILED_RETRYABLE`: error recuperable con reintento/backoff.
   - `FAILED_FINAL`: error no recuperable automáticamente; requiere acción manual.
5. Transiciones permitidas:
   - `PENDING -> SYNCING`
   - `SYNCING -> APPLIED | FAILED_RETRYABLE | FAILED_FINAL`
   - `FAILED_RETRYABLE -> SYNCING`
   - `FAILED_FINAL -> PENDING` (solo retry manual)
6. Idempotencia/replay:
   - mantener `command_id`, `idempotency_key`, `occurred_at`, `company_id`, `branch_id`.
   - `device_id` se valida por carril sync (header y firma).
   - no se aceptan “dobles verdades” locales para balance final.

## Alcance y no alcance
Incluye:

1. Inventarios `receive/issue` en modo offline diferido.
2. UX explícita de estados de sincronización.
3. Reintentos automáticos y manuales para finales.

No incluye:

1. Offline global del ERP.
2. `adjust/transfer` en este slice.
3. Facturación/Fuel/Caja avanzada.

## Consecuencias
Positivas:

1. Operación en conectividad intermitente con trazabilidad.
2. Consistencia canónica preservada por confirmación servidor.

Riesgos controlados:

1. Corrupción de cola local mitigada con recuperación segura y snapshot de diagnóstico.
2. Confusión operativa mitigada con semántica explícita `PENDING != APPLIED`.
3. Drift de arquitectura mitigado por invariantes (`bootstrap + ACL + shell_mode`).

Regla de evolución:

1. Ningún módulo adicional habilita offline sin ADR equivalente aprobada.
