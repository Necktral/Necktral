# HANDOFF - Slice 4.1 Inventarios Offline + Sync Diferido (2026-04-15)

Version: v1.0  
Fecha: 2026-04-15  
Tipo de cambio: `single_domain_code`  
Modo de ejecucion: auto edit

## A) Diagnóstico del área

Estado previo:

1. Inventarios SPA (`/inventarios`) ya permitia `read/capture/commit` para `receive/issue`.
2. El commit dependia solo de conectividad online (POST directo).
3. Existia infraestructura de sync offline en backend (`/api/sync/batch/`) y precedentes de cola offline en frontend (POS), pero Inventarios no la consumia.

## B) Alcance exacto

Incluido:

1. Cola offline local para inventarios con persistencia y estados operativos.
2. Replay automatico via `/api/sync/batch/` firmado (v2, ed25519) usando identidad de dispositivo enrolado.
3. Integracion de cola en `InventoryPage` para fallback offline, sincronizacion automatica y retry manual de errores finales.
4. Pruebas frontend de cola+sync y actualizacion documental de arquitectura.

Excluido:

1. Cambios backend de contratos/endpoints.
2. `adjust`/`transfer` en UX offline.
3. Nuevas politicas de seguridad/enrollment.

## C) Contratos impactados

Sin cambios breaking:

1. Se mantienen `/api/inventory/*` y `/api/sync/*`.
2. No se agregan endpoints ni migraciones.

Aditivos frontend:

1. Tipo local `InventoryOfflineCommand` + estados `PENDING/SYNCING/APPLIED/FAILED_RETRYABLE/FAILED_FINAL`.
2. Cliente de batch v2 `submitSyncV2Batch` para envio firmado desde SPA.

## D) Implementación realizada

1. **Cola offline Inventarios**
- Nuevo servicio `inventory-offline-queue.ts` con persistencia en `localStorage` y dedupe por `idempotency_key`.
- Soporta enqueue, stats, drain con backoff, mapping a comando sync v2 y retry manual de finales.

2. **Sync diferido**
- Nuevo servicio `sync-batch.service.ts` para construir y firmar batch v2 (`protocol_version=2`, `nonce`, `auth.signature`) y enviarlo a `/api/sync/batch/`.
- Nuevo adaptador `inventory-offline-sync.ts` para ejecutar comandos de inventario contra sync v2 y clasificar errores retryable/final.

3. **Integración UI Inventarios**
- `commit` ahora: intenta online inmediato; en error transiente encola comando offline.
- Se agrega panel de sincronizacion con estados, procesamiento manual y accion de retry para `FAILED_FINAL`.
- Sincronizador automatico: trigger en `online`, apertura de modulo e intervalo corto.
- Logica de fallback encapsulada en `inventory-commit.ts` para mantener el contenedor limpio y testeable.
- Mensajeria UX explicita: `PENDING` no es confirmacion final; `APPLIED` confirma servidor.

4. **Hardening operativo de cola**
- Se congelan transiciones de estado permitidas en la cola offline.
- Se agrega recuperacion segura de cola corrupta con snapshot de diagnostico.
- Se valida compatibilidad de version local del esquema de cola (fail-closed para versiones futuras desconocidas).

5. **Guard E2E privada inventarios offline**
- Nuevo guard deterministico (`pytest`) que valida:
  - login -> bootstrap/session -> shell_mode
  - gating modulo/ACL
  - replay via `/api/sync/batch/` con comando `INVENTORY.MOVEMENT.RECEIVE`
  - convergencia final a `APPLIED`
  - denegacion cuando falta permiso base inventarios

4. **Storage y arquitectura**
- Nueva key de storage `INVENTORY_OFFLINE_QUEUE`.
- Documento de arquitectura actualizado para explicitar Inventarios offline capture + deferred sync.

## E) Pruebas / validación

Frontend ejecutado:

1. `npm --prefix frontend run typecheck` -> PASS.
2. `npm --prefix frontend run lint` -> PASS.
3. `npm --prefix frontend run test -- src/features/inventory/__tests__/inventory-commit.spec.ts src/services/__tests__/inventory-offline-queue.spec.ts src/services/__tests__/inventory-offline-sync.spec.ts src/router/routes.spec.ts src/features/inventory/__tests__/inventory-shell.spec.ts` -> PASS.
4. `make qa-inventory-offline-private-e2e-guard` -> PASS.

Cobertura agregada:

1. Cola offline inventarios: dedupe, drain aplicado, retryable, final + retry manual, mapping sync v2.
2. Ejecutor sync inventarios: mapeo APPLIED/DUPLICATE/REJECTED y clasificación de fallos de transporte.
3. Orquestador de commit: online success, fallback offline, dedupe por idempotency y propagacion correcta de error no retryable.
4. Hardening de estados: transiciones permitidas y recovery ante corrupcion local.
5. E2E privada: flujo canónico offline->sync->APPLIED con verificacion de gating.

## F) Riesgos remanentes y siguiente paso

Riesgos:

1. Si no existe dispositivo enrolado en browser, la cola no puede sincronizar por carril v2 y quedara en error final hasta enrolar.
2. `read` continua online-first; no hay cache offline de catálogos/balance en este slice.
3. El gate operativo movil HTTPS 7/7 PASS se mantiene como condicion de rollout.

Siguiente paso:

1. Slice 4.2: cache local de lectura (`warehouses/items/ultimo balance/historial`) para experiencia offline de consulta.
2. Slice 5: extender offline a `adjust/transfer` con mismas garantias de idempotencia y sync.
