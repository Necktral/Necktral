# Blast Radius Note — Slice 4.1 Inventarios Offline (2026-04-15)

## Superficie tocada

1. Frontend Inventarios (`/inventarios`): cola offline, sync diferido y semántica UX de estado.
2. Contratos locales de cola (`InventoryOfflineCommand`, estados y transiciones).
3. QA/CI: guard E2E privada para flujo offline->sync->APPLIED.
4. Documentación técnica y ADR de semántica offline.

## Superficie NO tocada

1. Carril público de enroll (`/device/enroll`) en funcionalidad.
2. Contratos públicos backend de inventarios/sync (sin breaking changes).
3. Reglas canónicas de bootstrap, ACL y `shell_mode`.
4. Facturación, Fuel, caja avanzada, reporting funcional.

## Riesgos residuales

1. Operación sin dispositivo enrolado: comandos pueden quedar en error final hasta enrolar.
2. `read` sigue online-first: no hay caché offline de consulta completa.
3. Merge bloqueado hasta PASS de CI + revisión + gate móvil HTTPS 7/7.

## Mitigaciones activas

1. Idempotencia end-to-end y replay firmado en `/api/sync/batch/`.
2. Estado final inequívoco: solo `APPLIED` confirma operación canónica.
3. Guard E2E privada que cubre login/bootstrap/shell/gating/offline-sync/APPLIED.
